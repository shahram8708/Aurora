import uuid
from datetime import datetime
from typing import Iterable
from flask import current_app
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from botocore.exceptions import ClientError
from app.extensions import db
from app.models import Product, ProductImage, ProductTag, Wishlist
from app.core.storage import get_s3_client, s3_public_url


class ProductError(Exception):
    pass


def _as_uuid(value, label: str = "id") -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise ProductError(f"Invalid {label}") from exc


def _upload_product_images(product_id: str, files: Iterable) -> list[str]:
    if not files:
        return []
    s3 = get_s3_client()
    bucket = current_app.config["AWS_S3_BUCKET"]
    urls: list[str] = []
    for idx, file_storage in enumerate(files):
        key = f"products/{product_id}/{uuid.uuid4().hex}_{idx}"
        try:
            s3.upload_fileobj(
                file_storage,
                bucket,
                key,
                ExtraArgs={"ContentType": file_storage.mimetype, "ACL": "public-read"},
            )
        except ClientError as exc:  # pragma: no cover - network path
            current_app.logger.exception("Failed to upload product image")
            raise ProductError("Upload failed") from exc
        urls.append(s3_public_url(key))
    return urls


def create_product(seller_id: str, payload: dict, files: Iterable) -> Product:
    seller_uuid = _as_uuid(seller_id, "seller_id")
    product = Product(
        seller_id=seller_uuid,
        title=payload.get("title"),
        description=payload.get("description"),
        price=int(payload.get("price")),
        currency=payload.get("currency", "INR"),
        stock_quantity=int(payload.get("stock_quantity", 0)),
        category=payload.get("category"),
        is_active=True,
    )
    db.session.add(product)
    db.session.flush()

    urls = _upload_product_images(str(product.id), files)
    for order_index, url in enumerate(urls):
        db.session.add(ProductImage(product_id=product.id, image_url=url, order_index=order_index))
    db.session.commit()
    return product


def update_product(product_id: str, seller_id: str, payload: dict, files: Iterable | None = None) -> Product:
    product_uuid = _as_uuid(product_id, "product_id")
    seller_uuid = _as_uuid(seller_id, "seller_id")
    product = Product.query.options(joinedload(Product.images)).filter_by(id=product_uuid, is_deleted=False).first_or_404()
    if product.seller_id != seller_uuid:
        raise ProductError("Not allowed")
    for field in ["title", "description", "category", "currency"]:
        if payload.get(field) is not None:
            setattr(product, field, payload[field])
    if payload.get("price") is not None:
        product.price = int(payload["price"])
    if payload.get("stock_quantity") is not None:
        qty = int(payload["stock_quantity"])
        if qty < 0:
            raise ProductError("Stock cannot be negative")
        product.stock_quantity = qty
    valid_files = [f for f in files or [] if getattr(f, "filename", "")]  # ignore empty file inputs
    new_urls: list[str] = []
    if valid_files:
        # upload first so we don't lose existing images if upload fails mid-way
        new_urls = _upload_product_images(str(product.id), valid_files)
    if new_urls:
        ProductImage.query.filter_by(product_id=product.id).delete()
        for order_index, url in enumerate(new_urls):
            db.session.add(ProductImage(product_id=product.id, image_url=url, order_index=order_index))
    db.session.commit()
    return product


def soft_delete_product(product_id: str, seller_id: str):
    product_uuid = _as_uuid(product_id, "product_id")
    seller_uuid = _as_uuid(seller_id, "seller_id")
    product = Product.query.filter_by(id=product_uuid, is_deleted=False).first_or_404()
    if product.seller_id != seller_uuid:
        raise ProductError("Not allowed")
    product.is_deleted = True
    product.is_active = False
    db.session.commit()


def list_products(category: str | None, page: int, per_page: int):
    query = Product.query.filter_by(is_deleted=False, is_active=True)
    if category:
        query = query.filter(Product.category == category)
    return query.order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)


def get_product(product_id: str) -> Product:
    product_uuid = _as_uuid(product_id, "product_id")
    return Product.query.options(joinedload(Product.images)).filter_by(id=product_uuid, is_deleted=False).first_or_404()


def toggle_wishlist(user_id: str, product_id: str) -> bool:
    user_uuid = _as_uuid(user_id, "user_id")
    product_uuid = _as_uuid(product_id, "product_id")
    existing = Wishlist.query.filter_by(user_id=user_uuid, product_id=product_uuid).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return False
    db.session.add(Wishlist(user_id=user_uuid, product_id=product_uuid))
    db.session.commit()
    return True


def wishlist_for_user(user_id: str):
    user_uuid = _as_uuid(user_id, "user_id")
    return (
        db.session.execute(
            select(Product, Wishlist.created_at)
            .join(Wishlist, Wishlist.product_id == Product.id)
            .where(Wishlist.user_id == user_uuid, Product.is_deleted.is_(False))
            .order_by(Wishlist.created_at.desc())
        )
        .all()
    )


def tag_product_to_post(product_id: str, post_id: str, seller_id: str):
    product_uuid = _as_uuid(product_id, "product_id")
    seller_uuid = _as_uuid(seller_id, "seller_id")
    product = Product.query.get_or_404(product_uuid)
    if product.seller_id != seller_uuid:
        raise ProductError("Not allowed")
    exists = ProductTag.query.filter_by(product_id=product_uuid, post_id=post_id).first()
    if exists:
        return exists
    tag = ProductTag(product_id=product_uuid, post_id=post_id)
    db.session.add(tag)
    db.session.commit()
    return tag


def popular_products(limit: int = 8):
    cache_key = "shop:popular"
    cached = current_app.redis_client.get(cache_key)
    if cached:
        ids = []
        for raw in cached.split(","):
            try:
                ids.append(uuid.UUID(raw))
            except Exception:
                continue
        products = Product.query.filter(Product.id.in_(ids)).all() if ids else []
        return products
    ids = [str(pid) for pid, _ in db.session.execute(select(Product.id, func.random()).order_by(func.random()).limit(limit))]
    if ids:
        current_app.redis_client.setex(cache_key, current_app.config.get("TRENDING_CACHE_TTL", 300), ",".join(ids))
    uuid_ids = [uuid.UUID(pid) for pid in ids]
    return Product.query.filter(Product.id.in_(uuid_ids)).all() if uuid_ids else []
