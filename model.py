from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import Text, String
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import enum
import uuid


# Initialize SQLAlchemy
db = SQLAlchemy()

# Enum definitions
class UserRole(enum.Enum):
    ADMIN = "ADMIN"
    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"

    def __str__(self):
        return self.value

class OrderStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"

class PaymentStatus(enum.Enum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    PAID = 'paid'
    FAILED = 'failed'
    REFUNDED = 'refunded'
    CANCELED = 'canceled'
    CHARGEBACK = 'chargeback'
    ON_HOLD = 'on_hold'

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.CUSTOMER)
    permissions = db.Column(db.Text, nullable=True)
    address = db.Column(db.Text, nullable=True)
    county = db.Column(db.String(255), nullable=True)  # Changed from city to county
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    phone = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    orders = db.relationship(
        'Order',
        back_populates='user',
        foreign_keys='Order.user_id',
        lazy=True
    )

    approved_orders = db.relationship(
        'Order',
        back_populates='approved_by_user',
        foreign_keys='Order.approved_by',
        lazy=True
    )
    generated_reports = db.relationship('Report', back_populates='generated_by_user', foreign_keys='Report.generated_by_user_id', lazy=True)
    created_products = db.relationship('Product', foreign_keys='Product.created_by', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def is_admin(self):
        return self.role == UserRole.ADMIN

    def is_staff(self):
        return self.role in [UserRole.ADMIN, UserRole.STAFF]

    def is_customer(self):
        return self.role == UserRole.CUSTOMER

    def has_permission(self, permission):
        """Check if user has a specific permission"""
        if self.is_admin():
            return True
        if not self.permissions:
            return False
        user_permissions = [p.strip() for p in self.permissions.split(',')]
        return permission in user_permissions

    def as_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role.value,
            "permissions": self.permissions,
            "address": self.address,
            "county": self.county,  # Changed from city to county
            "phone": self.phone,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

# Category model
class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Relationships
    products = db.relationship('Product', back_populates='category', lazy=True)
    top_selling_reports = db.relationship('Report', back_populates='top_selling_category', foreign_keys='Report.top_selling_category_id', lazy=True)

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active
        }

# Product model
class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    image_url = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    category_id = db.Column(String(36), db.ForeignKey('categories.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = db.Column(String(36), db.ForeignKey('users.id'), nullable=True)

    # Relationships
    category = db.relationship('Category', back_populates='products')
    order_items = db.relationship('OrderItem', back_populates='product', lazy=True)
    custom_images = db.relationship('CustomImage', back_populates='product', lazy=True)
    top_selling_reports = db.relationship('Report', back_populates='top_selling_product', foreign_keys='Report.top_selling_product_id', lazy=True)

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": float(self.price),
            "quantity": self.quantity,
            "image_url": self.image_url,
            "is_active": self.is_active,
            "category_id": self.category_id,
            "category": self.category.name if self.category else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by
        }

# Pickup Point model
class PickupPoint(db.Model):
    __tablename__ = 'pickup_points'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    location_details = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    orders = db.relationship('Order', back_populates='pickup_point', lazy=True)

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "location_details": self.location_details,
            "city": self.city,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated": self.updated.isoformat()
        }

# Order model
class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(String(36), db.ForeignKey('users.id'), nullable=False)
    order_number = db.Column(db.String(255), nullable=False, unique=True)
    status = db.Column(db.Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(db.String(255), nullable=False)
    delivery_address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(255), nullable=True)
    pickup_point_id = db.Column(String(36), db.ForeignKey('pickup_points.id'), nullable=True)
    order_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    approved_by = db.Column(String(36), db.ForeignKey('users.id'), nullable=True)

    # Relationships
    user = db.relationship('User', back_populates='orders')
    pickup_point = db.relationship('PickupPoint', back_populates='orders')
    approved_by_user = db.relationship('User', back_populates='approved_orders', foreign_keys=[approved_by])
    order_items = db.relationship('OrderItem', back_populates='order', lazy=True, cascade="all, delete-orphan")
    payments = db.relationship('Payment', back_populates='order', lazy=True)

    def __init__(self, user_id, order_number, total_amount, customer_name, customer_phone, 
                 delivery_address=None, city=None, pickup_point_id=None, order_notes=None):
        self.user_id = user_id
        self.order_number = order_number
        self.total_amount = total_amount
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self.delivery_address = delivery_address
        self.city = city
        self.pickup_point_id = pickup_point_id
        self.order_notes = order_notes

    def as_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "order_number": self.order_number,
            "status": self.status.value,
            "total_amount": float(self.total_amount),
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "delivery_address": self.delivery_address,
            "city": self.city,
            "pickup_point_id": self.pickup_point_id,
            "pickup_point": self.pickup_point.name if self.pickup_point else None,
            "order_notes": self.order_notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "approved_by": self.approved_by,
            "order_items": [item.as_dict() for item in self.order_items] if self.order_items else []
        }

# Order Item model
class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = db.Column(String(36), db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(String(36), db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    custom_images = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    order = db.relationship('Order', back_populates='order_items')
    product = db.relationship('Product', back_populates='order_items')
    custom_images_list = db.relationship('CustomImage', back_populates='order_item', lazy=True)

    @property
    def total_price(self):
        return float(self.quantity * self.unit_price)

    def as_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else None,
            "quantity": self.quantity,
            "unit_price": float(self.unit_price),
            "total_price": self.total_price,
            "custom_images": self.custom_images,
            "created_at": self.created_at.isoformat()
        }

# Payment model
class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = db.Column(String(36), db.ForeignKey('orders.id'), nullable=False)
    mpesa_code = db.Column(db.String(255), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    phone_number = db.Column(db.String(255), nullable=False)

    # Relationships
    order = db.relationship('Order', back_populates='payments')

    def as_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "mpesa_code": self.mpesa_code,
            "amount": float(self.amount),
            "status": self.status.value,
            "payment_date": self.payment_date.isoformat(),
            "phone_number": self.phone_number
        }

# Custom Image model
class CustomImage(db.Model):
    __tablename__ = 'custom_images'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_item_id = db.Column(String(36), db.ForeignKey('order_items.id'), nullable=False)
    product_id = db.Column(String(36), db.ForeignKey('products.id'), nullable=True)
    image_url = db.Column(db.Text, nullable=False)
    image_name = db.Column(db.String(255), nullable=True)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    order_item = db.relationship('OrderItem', back_populates='custom_images_list')
    product = db.relationship('Product', back_populates='custom_images')

    def as_dict(self):
        return {
            "id": self.id,
            "order_item_id": self.order_item_id,
            "product_id": self.product_id,
            "image_url": self.image_url,
            "image_name": self.image_name,
            "upload_date": self.upload_date.isoformat()
        }


class Report(db.Model):
    __tablename__ = 'report'
    
    id = db.Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_name = db.Column(db.String(255), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    total_orders = db.Column(db.Integer, nullable=False, default=0)
    total_revenue = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    total_products_sold = db.Column(db.Integer, nullable=False, default=0)
    
    # Foreign keys for relationships
    top_selling_category_id = db.Column(String(36), db.ForeignKey('categories.id'), nullable=True)
    top_selling_product_id = db.Column(String(36), db.ForeignKey('products.id'), nullable=True)
    generated_by_user_id = db.Column(String(36), db.ForeignKey('users.id'), nullable=True)
    
    pending_orders = db.Column(db.Integer, nullable=False, default=0)
    complete_orders = db.Column(db.Integer, nullable=False, default=0)
    failed_payments = db.Column(db.Integer, nullable=False, default=0)
    summary = db.Column(db.Text, nullable=True)

    # Use JSON for better compatibility across databases
    # For SQLite compatibility, use db.JSON instead of JSONB
    report_data = db.Column(db.JSON, nullable=False, default=dict)

    # Relationships
    top_selling_category = db.relationship('Category', foreign_keys=[top_selling_category_id])
    top_selling_product = db.relationship('Product', foreign_keys=[top_selling_product_id])
    generated_by_user = db.relationship('User', foreign_keys=[generated_by_user_id])

    def as_dict(self):
        return {
            "id": self.id,
            "report_name": self.report_name,
            "generated_at": self.generated_at.isoformat(),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "total_orders": self.total_orders,
            "total_revenue": float(self.total_revenue),
            "total_products_sold": self.total_products_sold,
            "top_selling_category_id": self.top_selling_category_id,
            "top_selling_category_name": self.top_selling_category.name if self.top_selling_category else None,
            "top_selling_product_id": self.top_selling_product_id,
            "top_selling_product_name": self.top_selling_product.name if self.top_selling_product else None,
            "pending_orders": self.pending_orders,
            "complete_orders": self.complete_orders,
            "failed_payments": self.failed_payments,
            "generated_by_user_id": self.generated_by_user_id,
            "generated_by_user_name": self.generated_by_user.name if self.generated_by_user else None,
            "summary": self.summary,
            "report_data": self.report_data
        }