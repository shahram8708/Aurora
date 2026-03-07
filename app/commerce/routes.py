from flask import request, jsonify, render_template, abort, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import limiter, csrf
from . import commerce_bp
from .cart_service import get_cart, add_item, update_item, remove_item, recalc_cart, cart_totals
from .order_service import (
    create_checkout_order,
    finalize_order_payment,
    finalize_order_payment_by_gateway_order,
    handle_payment_failure,
    OrderError,
)
from .razorpay_checkout_service import RazorpayError
from app.models import Product, Order


@commerce_bp.get("/cart")
@jwt_required(optional=True)
def cart_page():
    user_id = get_jwt_identity()
    if not user_id:
        abort(401)
    cart = get_cart(user_id)
    recalc_cart(cart)
    affiliate_code = request.cookies.get("affiliate_code")
    return render_template(
        "commerce/cart.html",
        cart=cart,
        total=cart_totals(cart),
        razorpay_key=current_app.config.get("RAZORPAY_KEY_ID"),
        affiliate_code=affiliate_code,
    )


@commerce_bp.post("/cart/add")
@jwt_required()
@limiter.limit("30 per hour")
def cart_add():
    data = request.get_json(force=True)
    cart = add_item(get_jwt_identity(), data.get("product_id"), int(data.get("quantity", 1)))
    return jsonify({"total": cart_totals(cart)})


@commerce_bp.post("/cart/update")
@jwt_required()
@limiter.limit("60 per hour")
def cart_update():
    data = request.get_json(force=True)
    cart = update_item(get_jwt_identity(), data.get("product_id"), int(data.get("quantity", 1)))
    return jsonify({"total": cart_totals(cart)})


@commerce_bp.post("/cart/remove")
@jwt_required()
@limiter.limit("60 per hour")
def cart_remove():
    data = request.get_json(force=True)
    cart = remove_item(get_jwt_identity(), data.get("product_id"))
    return jsonify({"total": cart_totals(cart)})


@commerce_bp.post("/checkout")
@jwt_required()
@limiter.limit("10 per hour")
def checkout_start():
    data = request.get_json(force=True)
    try:
        order, rp_order = create_checkout_order(get_jwt_identity(), data.get("shipping_address"))
        return jsonify({"order_id": str(order.id), "razorpay_order": rp_order})
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": str(exc)}), 400


@commerce_bp.post("/checkout/verify")
@jwt_required()
def checkout_verify():
    data = request.get_json(force=True)
    affiliate_code = (data.get("affiliate_code") or request.cookies.get("affiliate_code") or "").strip() or None
    try:
        order = finalize_order_payment(
            data.get("order_id"),
            data.get("payment_id"),
            data.get("signature"),
            affiliate_code,
        )
        return jsonify({"status": order.status})
    except RazorpayError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": str(exc)}), 400


@commerce_bp.route("/checkout/callback", methods=["GET", "POST"])
@csrf.exempt
@jwt_required(optional=True)
def checkout_callback():
    payload = request.values
    rp_order_id = payload.get("razorpay_order_id")
    rp_payment_id = payload.get("razorpay_payment_id")
    rp_signature = payload.get("razorpay_signature")
    rp_subscription_id = payload.get("razorpay_subscription_id")
    affiliate_code = (
        payload.get("affiliate_code")
        or payload.get("notes[affiliate_code]")
        or request.cookies.get("affiliate_code")
        or ""
    ).strip() or None
    err_desc = (
        payload.get("error[description]")
        or payload.get("error_description")
        or payload.get("error")
        or payload.get("error[code]")
    )

    # Support subscription checkout redirects that return a subscription id but no order id.
    if rp_subscription_id and not rp_order_id:
        if err_desc:
            return render_template("commerce/checkout_result.html", status="error", message=err_desc), 400
        return render_template("commerce/checkout_result.html", status="success", message="Subscription payment received.")

    if not rp_order_id:
        return render_template("commerce/checkout_result.html", status="error", message="Missing Razorpay order id."), 400

    try:
        if rp_payment_id and rp_signature:
            order = finalize_order_payment_by_gateway_order(rp_order_id, rp_payment_id, rp_signature, affiliate_code)
            return render_template("commerce/checkout_result.html", status="success", order=order)

        failure_reason = err_desc or "Payment cancelled or failed."
        order = Order.query.filter_by(razorpay_order_id=rp_order_id).first()
        if order:
            handle_payment_failure(order.id, failure_reason)
        return (
            render_template("commerce/checkout_result.html", status="error", message=failure_reason),
            400,
        )
    except RazorpayError as exc:
        order = Order.query.filter_by(razorpay_order_id=rp_order_id).first()
        if order:
            handle_payment_failure(order.id, str(exc))
        return render_template("commerce/checkout_result.html", status="error", message=str(exc)), 400
    except OrderError as exc:
        return render_template("commerce/checkout_result.html", status="error", message=str(exc)), 400
    except Exception as exc:  # pylint: disable=broad-except
        current_app.logger.exception("Checkout callback failed", extra={"razorpay_order_id": rp_order_id})
        return (
            render_template(
                "commerce/checkout_result.html",
                status="error",
                message="Something went wrong while finalizing your payment.",
            ),
            500,
        )


@commerce_bp.get("/products/<uuid:product_id>/quick")
@jwt_required(optional=True)
def quick_product(product_id):
    product = Product.query.get_or_404(product_id)
    return jsonify({"id": str(product.id), "title": product.title, "price": product.price, "currency": product.currency})
