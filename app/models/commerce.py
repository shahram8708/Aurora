import uuid
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from app.extensions import db
from .user import TimestampMixin


class Product(db.Model, TimestampMixin):
    __tablename__ = "products"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False)  # stored in smallest currency unit (e.g., paise)
    currency = db.Column(db.String(8), default="INR", nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(db.String(80), index=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)

    images = db.relationship("ProductImage", backref="product", cascade="all, delete-orphan", order_by="ProductImage.order_index")
    tags = db.relationship("ProductTag", backref="product", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_product_active_category", "is_active", "category"),
        Index("ix_product_title", "title"),
        CheckConstraint("price >= 0", name="ck_product_price_non_negative"),
        CheckConstraint("stock_quantity >= 0", name="ck_product_stock_non_negative"),
    )


class ProductImage(db.Model, TimestampMixin):
    __tablename__ = "product_images"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    image_url = db.Column(db.String(512), nullable=False)
    order_index = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_product_image_order", "product_id", "order_index"),
    )


class ProductTag(db.Model, TimestampMixin):
    __tablename__ = "product_tags"

    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    post_id = db.Column(UUID(as_uuid=True), db.ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (Index("ix_product_tag_post", "post_id"),)


class Wishlist(db.Model, TimestampMixin):
    __tablename__ = "wishlists"

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (
        Index("ix_wishlist_user", "user_id"),
        Index("ix_wishlist_product", "product_id"),
    )


class Cart(db.Model, TimestampMixin):
    __tablename__ = "carts"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    items = db.relationship("CartItem", backref="cart", cascade="all, delete-orphan")


class CartItem(db.Model, TimestampMixin):
    __tablename__ = "cart_items"

    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(UUID(as_uuid=True), db.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price_snapshot = db.Column(db.Integer, nullable=False)

    product = db.relationship("Product")

    __table_args__ = (
        UniqueConstraint("cart_id", "product_id", name="uq_cart_product"),
        CheckConstraint("quantity > 0", name="ck_cartitem_quantity_positive"),
    )


class Order(db.Model, TimestampMixin):
    __tablename__ = "orders"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    total_amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), default="INR", nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False, index=True)
    razorpay_order_id = db.Column(db.String(80), nullable=True, unique=True)
    razorpay_payment_id = db.Column(db.String(80), nullable=True, unique=True)
    razorpay_signature = db.Column(db.String(255), nullable=True)
    shipping_address_json = db.Column(db.JSON, nullable=True)

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    shipment = db.relationship("ShipmentTracking", backref="order", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_order_buyer_status", "buyer_id", "status"),
    )


class OrderItem(db.Model, TimestampMixin):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    seller_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_orderitem_quantity_positive"),
    )


class ShipmentTracking(db.Model, TimestampMixin):
    __tablename__ = "shipment_tracking"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)
    tracking_number = db.Column(db.String(120), nullable=True)
    carrier = db.Column(db.String(80), nullable=True)
    status = db.Column(db.String(50), default="pending", nullable=False)

    __table_args__ = (
        Index("ix_shipment_order_status", "order_id", "status"),
    )


class InventoryReservation(db.Model, TimestampMixin):
    __tablename__ = "inventory_reservations"

    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(UUID(as_uuid=True), db.ForeignKey("carts.id", ondelete="CASCADE"), nullable=True, index=True)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(minutes=15))
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True)
    status = db.Column(db.String(32), default="locked", nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_reservation_quantity_positive"),
        Index("ix_inventory_reservation_expiry", "expires_at"),
    )


class AffiliateProgram(db.Model, TimestampMixin):
    __tablename__ = "affiliate_programs"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, unique=True)
    commission_percentage = db.Column(db.Float, nullable=False, default=10.0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class AffiliateLink(db.Model, TimestampMixin):
    __tablename__ = "commerce_affiliate_links"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    unique_code = db.Column(db.String(80), unique=True, nullable=False)
    clicks = db.Column(db.Integer, default=0, nullable=False)
    conversions = db.Column(db.Integer, default=0, nullable=False)
    earnings = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_affiliate_user_product"),
    )


class AffiliateCommission(db.Model, TimestampMixin):
    __tablename__ = "affiliate_commissions"

    id = db.Column(db.Integer, primary_key=True)
    affiliate_id = db.Column(UUID(as_uuid=True), db.ForeignKey("commerce_affiliate_links.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False)

    __table_args__ = (
        UniqueConstraint("affiliate_id", "order_id", name="uq_affiliate_order"),
    )


class NFTAsset(db.Model, TimestampMixin):
    __tablename__ = "nft_assets"

    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.String(180), unique=True, nullable=False)
    blockchain_network = db.Column(db.String(80), nullable=False)
    owner_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    metadata_url = db.Column(db.String(512), nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_nft_owner", "owner_id"),
    )
