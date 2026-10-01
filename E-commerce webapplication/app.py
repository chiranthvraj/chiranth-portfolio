import os
import re
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import quote_plus

import click
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL") or (
    "mysql+pymysql://"
    f"{quote_plus(os.environ.get('MYSQL_USER', 'root'))}:"
    f"{quote_plus(os.environ.get('MYSQL_PASSWORD', ''))}@"
    f"{os.environ.get('MYSQL_HOST', '127.0.0.1')}:"
    f"{os.environ.get('MYSQL_PORT', '3306')}/"
    f"{os.environ.get('MYSQL_DATABASE', 'ecommerce_db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

ORDER_STATUSES = ("Pending", "Processing", "Shipped", "Delivered", "Cancelled")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    orders = db.relationship("Order", back_populates="user")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), nullable=False, default="Everyday")
    description = db.Column(db.String(500), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=10)
    featured = db.Column(db.Boolean, nullable=False, default=False)
    order_items = db.relationship("OrderItem", back_populates="product")


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    customer_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.String(500), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    user = db.relationship("User", back_populates="orders")
    items = db.relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    product_name = db.Column(db.String(120), nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="order_items")


def valid_email(email):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


def csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.before_request
def protect_forms():
    if request.method == "POST":
        submitted = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not secrets.compare_digest(submitted, expected):
            abort(400, description="The form expired. Please reload the page and try again.")


@app.context_processor
def template_context():
    return {
        "csrf_token": csrf_token,
        "cart_count": sum(session.get("cart", {}).values()),
        "now_year": datetime.now().year,
        "current_user": db.session.get(User, session.get("user_id"))
        if session.get("user_id")
        else None,
    }


@app.template_filter("money")
def money(value):
    return f"₹{Decimal(value):,.2f}"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if user is None or user.role != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def get_cart_lines():
    cart = session.get("cart", {})
    lines = []
    total = Decimal("0.00")
    for product_id, quantity in cart.items():
        product = db.session.get(Product, int(product_id))
        if product is None or not isinstance(quantity, int) or quantity < 1:
            continue
        quantity = min(quantity, product.stock)
        if quantity:
            line_total = product.price * quantity
            total += line_total
            lines.append(
                {"product": product, "quantity": quantity, "line_total": line_total}
            )
    return lines, total


@app.route("/")
def home():
    featured = (
        Product.query.filter_by(featured=True).filter(Product.stock > 0)
        .order_by(Product.id)
        .limit(4)
        .all()
    )
    return render_template("index.html", featured=featured)


@app.route("/products")
def products():
    query = request.args.get("q", "").strip()[:100]
    selected_category = request.args.get("category", "").strip()[:60]
    product_query = Product.query.filter(Product.stock > 0)
    if query:
        pattern = f"%{query}%"
        product_query = product_query.filter(
            db.or_(
                Product.name.ilike(pattern),
                Product.category.ilike(pattern),
                Product.description.ilike(pattern),
            )
        )
    if selected_category:
        product_query = product_query.filter_by(category=selected_category)
    items = product_query.order_by(Product.id).all()
    categories = [
        row[0]
        for row in db.session.query(Product.category)
        .filter(Product.stock > 0)
        .distinct()
        .order_by(Product.category)
        .all()
    ]
    return render_template(
        "products.html",
        products=items,
        query=query,
        categories=categories,
        selected_category=selected_category,
    )


@app.post("/cart/add/<int:product_id>")
def add_to_cart(product_id):
    product = db.get_or_404(Product, product_id)
    cart = session.get("cart", {})
    key = str(product.id)
    quantity = cart.get(key, 0)
    if product.stock < 1:
        flash("This item is currently out of stock.", "error")
    elif quantity >= product.stock:
        flash("Your cart already contains all available stock.", "error")
    else:
        cart[key] = quantity + 1
        session["cart"] = cart
        flash(f"{product.name} added to your cart.", "success")
    return redirect(url_for("products"))


@app.route("/cart", methods=["GET", "POST"])
def cart():
    if request.method == "POST":
        action = request.form.get("action")
        product_id = request.form.get("product_id", "")
        cart_items = session.get("cart", {})
        product = db.session.get(Product, int(product_id)) if product_id.isdigit() else None
        if action == "remove" and product_id in cart_items:
            cart_items.pop(product_id)
            flash("Item removed from your cart.", "info")
        elif action == "update" and product:
            try:
                quantity = int(request.form.get("quantity", ""))
            except ValueError:
                quantity = 0
            if quantity < 1:
                cart_items.pop(product_id, None)
            elif quantity > product.stock:
                flash(f"Only {product.stock} of {product.name} are available.", "error")
                cart_items[product_id] = product.stock
            else:
                cart_items[product_id] = quantity
        session["cart"] = cart_items
        return redirect(url_for("cart"))

    lines, subtotal = get_cart_lines()
    return render_template("cart.html", lines=lines, subtotal=subtotal)


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines, total = get_cart_lines()
    if not lines:
        flash("Add an item to your cart before checking out.", "info")
        return redirect(url_for("products"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        if (
            not name
            or not valid_email(email)
            or not re.fullmatch(r"[+\d\s().-]{7,30}", phone)
            or not address
            or len(name) > 100
            or len(email) > 120
            or len(address) > 500
        ):
            flash("Please provide valid details in every checkout field.", "error")
            return render_template(
                "checkout.html", lines=lines, total=total, form=request.form
            )

        for line in lines:
            if line["quantity"] > line["product"].stock:
                flash(f"{line['product'].name} no longer has enough stock.", "error")
                return redirect(url_for("cart"))

        order = Order(
            user_id=session.get("user_id"),
            customer_name=name,
            email=email,
            phone=phone,
            address=address,
            total=total,
        )
        for line in lines:
            product = line["product"]
            product.stock -= line["quantity"]
            order.items.append(
                OrderItem(
                    product_id=product.id,
                    product_name=product.name,
                    unit_price=product.price,
                    quantity=line["quantity"],
                )
            )
        db.session.add(order)
        db.session.commit()
        session["cart"] = {}
        session["last_order_id"] = order.id
        return redirect(url_for("order_confirmation", order_id=order.id))

    current = db.session.get(User, session.get("user_id")) if session.get("user_id") else None
    form = {"name": current.name, "email": current.email} if current else {}
    return render_template("checkout.html", lines=lines, total=total, form=form)


@app.route("/orders/<int:order_id>/confirmation")
def order_confirmation(order_id):
    order = db.get_or_404(Order, order_id)
    user = db.session.get(User, session.get("user_id")) if session.get("user_id") else None
    is_owner = user is not None and user.id == order.user_id
    is_admin = user is not None and user.role == "admin"
    is_guest_order = (
        order.user_id is None
        and order.id
        in (session.get("last_order_id"), session.get("tracked_order_id"))
    )
    if not (is_owner or is_admin or is_guest_order):
        abort(403)
    return render_template("confirmation.html", order=order)


@app.route("/track-order", methods=["GET", "POST"])
def track_order():
    if request.method == "POST":
        order_number = request.form.get("order_number", "").strip()
        email = request.form.get("email", "").strip().lower()
        if order_number.isdigit():
            order = Order.query.filter_by(
                id=int(order_number), email=email
            ).first()
        else:
            order = None
        if order is None:
            flash("We couldn't find an order with those details.", "error")
        else:
            session["tracked_order_id"] = order.id
            return redirect(url_for("order_confirmation", order_id=order.id))
    return render_template("track_order.html")


@app.route("/my-orders")
@login_required
def my_orders():
    user = db.session.get(User, session["user_id"])
    if user is None or user.role != "user":
        abort(403)
    orders = (
        Order.query.filter_by(user_id=user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template("my_orders.html", orders=orders)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or len(name) > 100 or not valid_email(email) or len(email) > 120:
            flash("Please enter a name and a valid email address.", "error")
        elif len(password) < 8:
            flash("Your password must be at least 8 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
                role="user",
            )
            db.session.add(user)
            db.session.commit()
            cart_items = session.get("cart", {})
            session.clear()
            session["cart"] = cart_items
            session["user_id"] = user.id
            flash("Your account is ready. Welcome!", "success")
            return redirect(url_for("home"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user is None or not check_password_hash(user.password_hash, password):
            flash("Email or password is incorrect.", "error")
        else:
            cart_items = session.get("cart", {})
            session.clear()
            session["cart"] = cart_items
            session["user_id"] = user.id
            flash(f"Welcome back, {user.name}.", "success")
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("admin_dashboard" if user.role == "admin" else "home"))
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    product_count = Product.query.count()
    orders = Order.query.order_by(Order.created_at.desc()).all()
    products = Product.query.order_by(Product.id.desc()).all()
    return render_template(
        "admin.html", products=products, orders=orders, product_count=product_count
    )


@app.route("/admin/products/new", methods=["GET", "POST"])
@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_product(product_id=None):
    product = db.session.get(Product, product_id) if product_id else None
    if product_id and product is None:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        category = request.form.get("category", "").strip()
        try:
            price = Decimal(request.form.get("price", ""))
            stock = int(request.form.get("stock", ""))
        except (InvalidOperation, ValueError):
            price, stock = Decimal("0"), -1
        if (
            not name
            or len(name) > 120
            or not category
            or len(category) > 60
            or not description
            or len(description) > 500
            or not image_url.startswith(("https://", "/", "http://"))
            or len(image_url) > 500
            or not price.is_finite()
            or price <= 0
            or price > Decimal("99999999.99")
            or stock < 0
        ):
            flash("Check the product details, price, and stock quantity.", "error")
        else:
            product = product or Product()
            product.name = name
            product.category = category
            product.description = description
            product.image_url = image_url
            product.price = price
            product.stock = stock
            product.featured = request.form.get("featured") == "on"
            db.session.add(product)
            db.session.commit()
            flash("Product saved.", "success")
            return redirect(url_for("admin_dashboard"))
    return render_template("product_form.html", product=product)


@app.post("/admin/products/<int:product_id>/delete")
@admin_required
def delete_product(product_id):
    product = db.get_or_404(Product, product_id)
    OrderItem.query.filter_by(product_id=product.id).update(
        {OrderItem.product_id: None}, synchronize_session="fetch"
    )
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/orders/<int:order_id>/status")
@admin_required
def update_order_status(order_id):
    order = db.get_or_404(Order, order_id)
    status = request.form.get("status", "")
    if status not in ORDER_STATUSES:
        abort(400, description="Unknown order status.")
    if order.status != "Cancelled" and status == "Cancelled":
        for item in order.items:
            product = db.session.get(Product, item.product_id) if item.product_id else None
            if product:
                product.stock += item.quantity
    elif order.status == "Cancelled" and status != "Cancelled":
        products_to_restock = []
        for item in order.items:
            product = db.session.get(Product, item.product_id) if item.product_id else None
            if product is None or product.stock < item.quantity:
                flash("There is not enough stock to reopen this cancelled order.", "error")
                return redirect(url_for("admin_dashboard") + "#orders")
            products_to_restock.append((product, item.quantity))
        for product, quantity in products_to_restock:
            product.stock -= quantity
    order.status = status
    db.session.commit()
    flash(f"Order #{order.id} updated to {status.lower()}.", "success")
    return redirect(url_for("admin_dashboard") + "#orders")


@app.cli.command("init-db")
def init_db():
    """Create database tables and add starter products and a demo admin."""
    db.create_all()
    product_columns = {column["name"] for column in inspect(db.engine).get_columns("product")}
    if "category" not in product_columns:
        db.session.execute(
            text(
                "ALTER TABLE product ADD COLUMN category "
                "VARCHAR(60) NOT NULL DEFAULT 'Everyday'"
            )
        )
        db.session.commit()

    old_sample_names = (
        "Everyday Backpack",
        "Ceramic Coffee Set",
        "Desk Lamp",
        "Canvas Tote",
    )
    old_samples = Product.query.filter(Product.name.in_(old_sample_names)).all()
    if old_samples:
        old_sample_ids = [product.id for product in old_samples]
        OrderItem.query.filter(OrderItem.product_id.in_(old_sample_ids)).update(
            {OrderItem.product_id: None}, synchronize_session="fetch"
        )
        for product in old_samples:
            db.session.delete(product)
        db.session.flush()

    sample_products = [
        {
            "name": "City Commuter Bicycle",
            "category": "Bicycles",
            "description": "A lightweight 7-speed bicycle built for comfortable everyday city rides.",
            "price": Decimal("15999.00"),
            "image_url": "https://images.unsplash.com/photo-1485965120184-e220f721d03e?auto=format&fit=crop&w=900&q=85",
            "stock": 8,
            "featured": True,
        },
        {
            "name": "Trail Rider Helmet",
            "category": "Helmets",
            "description": "A ventilated, adjustable helmet for safer rides around town and on trails.",
            "price": Decimal("2499.00"),
            "image_url": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&w=900&q=85",
            "stock": 14,
            "featured": True,
        },
        {
            "name": "The Art of Everyday",
            "category": "Books",
            "description": "A beautifully illustrated hardcover about creativity and finding inspiration in daily life.",
            "price": Decimal("599.00"),
            "image_url": "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&w=900&q=85",
            "stock": 20,
            "featured": True,
        },
        {
            "name": "Wireless Studio Headphones",
            "category": "Gadgets",
            "description": "Comfortable over-ear headphones with rich sound for music, calls, and focus time.",
            "price": Decimal("3999.00"),
            "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=900&q=85",
            "stock": 10,
            "featured": True,
        },
        {
            "name": "Nova 5G Smartphone",
            "category": "Phones",
            "description": "A bright, sharp display and all-day battery in a pocket-friendly 5G phone.",
            "price": Decimal("24999.00"),
            "image_url": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=900&q=85",
            "stock": 7,
            "featured": True,
        },
        {
            "name": "Everyday 14-inch Laptop",
            "category": "Laptops",
            "description": "A slim everyday laptop for study, work, browsing, and getting things done.",
            "price": Decimal("54999.00"),
            "image_url": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=900&q=85",
            "stock": 5,
            "featured": True,
        },
        {
            "name": "Smart Fitness Watch",
            "category": "Gadgets",
            "description": "A simple smartwatch for activity tracking, notifications, and daily routines.",
            "price": Decimal("6999.00"),
            "image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=900&q=85",
            "stock": 9,
            "featured": False,
        },
        {
            "name": "Trail Companion Paperback",
            "category": "Books",
            "description": "A practical pocket-sized guide to planning your next outdoor adventure.",
            "price": Decimal("449.00"),
            "image_url": "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&w=900&q=85",
            "stock": 18,
            "featured": False,
        },
    ]
    for sample in sample_products:
        product = Product.query.filter_by(name=sample["name"]).first()
        if product is None:
            db.session.add(Product(**sample))
        else:
            for field, value in sample.items():
                setattr(product, field, value)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@shop.local").strip().lower()
    if User.query.filter_by(email=admin_email).first() is None:
        db.session.add(
            User(
                name="Shop Admin",
                email=admin_email,
                password_hash=generate_password_hash(
                    os.environ.get("ADMIN_PASSWORD", "Admin123!")
                ),
                role="admin",
            )
        )
    db.session.commit()
    click.echo("Database initialized with sample products and the demo admin account.")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
