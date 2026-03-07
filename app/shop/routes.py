import uuid
from flask import request, render_template, jsonify, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm import joinedload, selectinload
from app.extensions import limiter, db
from app.models import Post, Cart, CartItem, Wishlist
from app.models.commerce import ProductTag
from . import shop_bp
from app.commerce.product_service import (
    create_product,
    update_product,
    soft_delete_product,
    list_products,
    get_product,
    toggle_wishlist,
    wishlist_for_user,
    tag_product_to_post,
    popular_products,
)


@shop_bp.get("")
@shop_bp.get("/")
@jwt_required(optional=True)
def catalog():
    category = request.args.get("category")
    page = int(request.args.get("page", 1))
    products_page = list_products(category, page, per_page=12)
    popular = popular_products()
    user_id = get_jwt_identity()
    cart_product_ids: set[str] = set()
    wishlist_ids: set[str] = set()
    try:
        user_uuid = uuid.UUID(str(user_id)) if user_id else None
    except Exception:
        user_uuid = None
    if user_uuid:
        cart = Cart.query.filter_by(user_id=user_uuid).options(joinedload(Cart.items)).first()
        if cart:
            cart_product_ids = {str(item.product_id) for item in cart.items}
        wishlist_ids = {str(w.product_id) for w in Wishlist.query.filter_by(user_id=user_uuid).all()}
    return render_template(
        "shop/catalog.html",
        products=products_page.items,
        pagination=products_page,
        popular=popular,
        cart_product_ids=cart_product_ids,
        wishlist_ids=wishlist_ids,
    )


@shop_bp.get("/products/<uuid:product_id>")
@jwt_required(optional=True)
def product_detail(product_id):
    product = get_product(product_id)
    user_id = get_jwt_identity()
    in_cart = False
    in_wishlist = False
    is_owner = False
    tagged_posts = (
        Post.query.join(ProductTag, ProductTag.post_id == Post.id)
        .filter(ProductTag.product_id == product.id, Post.is_archived.is_(False))
        .options(selectinload(Post.media))
        .order_by(Post.created_at.desc())
        .all()
    )
    try:
        user_uuid = uuid.UUID(str(user_id)) if user_id else None
    except Exception:
        user_uuid = None
    if user_uuid:
        cart = Cart.query.filter_by(user_id=user_uuid).options(joinedload(Cart.items)).first()
        if cart:
            in_cart = any(str(item.product_id) == str(product.id) for item in cart.items)
        in_wishlist = Wishlist.query.filter_by(user_id=user_uuid, product_id=product.id).first() is not None
        is_owner = str(product.seller_id) == str(user_uuid)
    return render_template(
        "shop/product_detail.html",
        product=product,
        in_cart=in_cart,
        in_wishlist=in_wishlist,
        is_owner=is_owner,
        tagged_posts=tagged_posts,
    )


@shop_bp.post("/products")
@jwt_required()
@limiter.limit("10 per hour")
def product_create():
    seller_id = get_jwt_identity()
    payload = request.form.to_dict()
    files = request.files.getlist("images")
    product = create_product(seller_id, payload, files)
    return jsonify({"id": str(product.id)})


@shop_bp.post("/products/<uuid:product_id>/edit")
@jwt_required()
@limiter.limit("10 per hour")
def product_edit(product_id):
    seller_id = get_jwt_identity()
    payload = request.form.to_dict()
    files = request.files.getlist("images")
    product = update_product(product_id, seller_id, payload, files)
    return jsonify({"id": str(product.id)})


@shop_bp.get("/products/new")
@jwt_required()
def product_new():
    return render_template("shop/create_product.html")


@shop_bp.post("/products/<uuid:product_id>/delete")
@jwt_required()
def product_delete(product_id):
    soft_delete_product(product_id, get_jwt_identity())
    return jsonify({"status": "deleted"})


@shop_bp.post("/products/<uuid:product_id>/wishlist")
@jwt_required()
def wishlist_toggle(product_id):
    added = toggle_wishlist(get_jwt_identity(), product_id)
    return jsonify({"added": added})


@shop_bp.get("/wishlist")
@jwt_required()
def wishlist_page():
    items = wishlist_for_user(get_jwt_identity())
    return render_template("shop/wishlist.html", items=items)


@shop_bp.post("/products/<uuid:product_id>/tag")
@jwt_required()
def tag_product(product_id):
    data = request.get_json(force=True)
    post_raw = data.get("post_id")
    try:
        post_uuid = uuid.UUID(str(post_raw))
    except Exception:
        abort(400)
    if not Post.query.get(post_uuid):
        abort(404)
    tag_product_to_post(product_id, post_uuid, get_jwt_identity())
    return jsonify({"status": "tagged"})
