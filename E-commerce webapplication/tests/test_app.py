import re
import unittest
from decimal import Decimal
import os

from werkzeug.security import generate_password_hash

os.environ["DATABASE_URL"] = "sqlite://"

from app import Order, OrderItem, Product, User, app, db


class ShopAppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite://",
        )
        with app.app_context():
            db.drop_all()
            db.create_all()
            self.product = Product(
                name="Canvas Tote",
                description="A useful everyday tote.",
                price=Decimal("22.00"),
                image_url="https://example.com/tote.jpg",
                stock=4,
                featured=True,
            )
            self.admin = User(
                name="Shop Admin",
                email="admin@example.test",
                password_hash=generate_password_hash("admin-password"),
                role="admin",
            )
            db.session.add_all([self.product, self.admin])
            db.session.commit()
            self.product_id = self.product.id
        self.client = app.test_client()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def token(self, response):
        match = re.search(rb'name="_csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_guest_can_add_items_and_complete_checkout(self):
        products_page = self.client.get("/products")
        response = self.client.post(
            f"/cart/add/{self.product_id}",
            data={"_csrf_token": self.token(products_page)},
        )
        self.assertEqual(response.status_code, 302)
        cart_page = self.client.get("/cart")
        self.assertIn("₹22.00".encode(), cart_page.data)

        checkout_page = self.client.get("/checkout")
        response = self.client.post(
            "/checkout",
            data={
                "_csrf_token": self.token(checkout_page),
                "name": "Taylor Shopper",
                "email": "taylor@example.test",
                "phone": "555 123 4567",
                "address": "10 Market Street",
            },
        )
        self.assertEqual(response.status_code, 302)
        confirmation = self.client.get(response.location)
        self.assertEqual(confirmation.status_code, 200)
        self.assertIn(b"Thank you, Taylor!", confirmation.data)
        self.assertIn(b"DELIVERY STATUS", confirmation.data)
        self.assertIn(b"Pending", confirmation.data)
        with app.app_context():
            order = Order.query.one()
            self.assertEqual(order.total, Decimal("22.00"))
            self.assertEqual(order.items[0].product_name, "Canvas Tote")
            self.assertEqual(db.session.get(Product, self.product_id).stock, 3)

    def test_customer_can_view_order_status_and_history(self):
        register_page = self.client.get("/register")
        self.client.post(
            "/register",
            data={
                "_csrf_token": self.token(register_page),
                "name": "Taylor Shopper",
                "email": "taylor@example.test",
                "password": "secure-password",
            },
        )
        products_page = self.client.get("/products")
        self.client.post(
            f"/cart/add/{self.product_id}",
            data={"_csrf_token": self.token(products_page)},
        )
        checkout_page = self.client.get("/checkout")
        response = self.client.post(
            "/checkout",
            data={
                "_csrf_token": self.token(checkout_page),
                "name": "Taylor Shopper",
                "email": "taylor@example.test",
                "phone": "555 123 4567",
                "address": "10 Market Street",
            },
        )
        confirmation = self.client.get(response.location)
        self.assertIn(b"View my orders", confirmation.data)
        self.assertIn(b"Pending", self.client.get("/my-orders").data)

        with app.app_context():
            order = Order.query.one()
            order.status = "Shipped"
            db.session.commit()
            order_id = order.id
        history = self.client.get("/my-orders")
        self.assertIn(b"Shipped", history.data)
        self.assertEqual(
            self.client.get(f"/orders/{order_id}/confirmation").status_code, 200
        )

    def test_guest_can_track_order_with_order_number_and_checkout_email(self):
        products_page = self.client.get("/products")
        self.client.post(
            f"/cart/add/{self.product_id}",
            data={"_csrf_token": self.token(products_page)},
        )
        checkout_page = self.client.get("/checkout")
        checkout_response = self.client.post(
            "/checkout",
            data={
                "_csrf_token": self.token(checkout_page),
                "name": "Taylor Shopper",
                "email": "taylor@example.test",
                "phone": "555 123 4567",
                "address": "10 Market Street",
            },
        )
        order_id = checkout_response.location.rsplit("/", 2)[1]

        tracker = app.test_client()
        track_page = tracker.get("/track-order")
        failed_lookup = tracker.post(
            "/track-order",
            data={
                "_csrf_token": self.token(track_page),
                "order_number": order_id,
                "email": "wrong@example.test",
            },
        )
        self.assertEqual(failed_lookup.status_code, 200)
        self.assertIn(b"couldn&#39;t find an order", failed_lookup.data)
        self.assertEqual(
            tracker.get(f"/orders/{order_id}/confirmation").status_code, 403
        )

        track_page = tracker.get("/track-order")
        successful_lookup = tracker.post(
            "/track-order",
            data={
                "_csrf_token": self.token(track_page),
                "order_number": order_id,
                "email": "TAYLOR@example.test",
            },
        )
        self.assertEqual(successful_lookup.status_code, 302)
        tracked_order = tracker.get(successful_lookup.location)
        self.assertEqual(tracked_order.status_code, 200)
        self.assertIn(b"DELIVERY STATUS", tracked_order.data)
        self.assertIn(b"Pending", tracked_order.data)

    def test_homepage_and_search_display_available_products(self):
        homepage = self.client.get("/")
        self.assertEqual(homepage.status_code, 200)
        self.assertIn(b"Canvas Tote", homepage.data)
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})
        results = self.client.get("/products?q=canvas")
        self.assertEqual(results.status_code, 200)
        self.assertIn(b"Canvas Tote", results.data)
        self.assertNotIn(b"desk lamp", results.data.lower())

    def test_catalog_filter_and_rupee_format(self):
        with app.app_context():
            db.session.get(Product, self.product_id).category = "Books"
            db.session.add(
                Product(
                    name="Trail Helmet",
                    category="Helmets",
                    description="A sturdy riding helmet.",
                    price=Decimal("2499.00"),
                    image_url="https://example.com/helmet.jpg",
                    stock=4,
                )
            )
            db.session.commit()
        books = self.client.get("/products?category=Books")
        self.assertIn(b"Canvas Tote", books.data)
        self.assertNotIn(b"Trail Helmet", books.data)
        self.assertIn("₹22.00".encode(), books.data)
        self.assertIn("₹2,499.00".encode(), self.client.get("/products").data)

    def test_init_db_migrates_old_seed_catalog_and_is_idempotent(self):
        legacy_order = Order(
            customer_name="Taylor Shopper",
            email="taylor@example.test",
            phone="555 123 4567",
            address="10 Market Street",
            total=Decimal("22.00"),
        )
        legacy_order.items.append(
            OrderItem(
                product_id=self.product_id,
                product_name="Canvas Tote",
                unit_price=Decimal("22.00"),
                quantity=1,
            )
        )
        with app.app_context():
            db.session.add(legacy_order)
            db.session.commit()
            order_id = legacy_order.id

        runner = app.test_cli_runner()
        first_run = runner.invoke(args=["init-db"])
        self.assertEqual(first_run.exit_code, 0, first_run.output)
        with app.app_context():
            bicycle = Product.query.filter_by(name="City Commuter Bicycle").one()
            bicycle.price = Decimal("123.00")
            db.session.commit()
        second_run = runner.invoke(args=["init-db"])
        self.assertEqual(second_run.exit_code, 0, second_run.output)
        with app.app_context():
            products = Product.query.all()
            self.assertEqual(len(products), 8)
            self.assertEqual({product.category for product in products}, {
                "Bicycles", "Helmets", "Books", "Gadgets", "Phones", "Laptops"
            })
            self.assertEqual(
                Product.query.filter_by(name="City Commuter Bicycle").one().price,
                Decimal("123.00"),
            )
            historical_item = OrderItem.query.filter_by(order_id=order_id).one()
            self.assertIsNone(historical_item.product_id)
            self.assertEqual(historical_item.product_name, "Canvas Tote")
            self.assertEqual(Order.query.count(), 1)
            self.assertEqual(
                User.query.filter_by(email="admin@shop.local", role="admin").count(),
                1,
            )

    def test_admin_can_create_products_and_update_order_status(self):
        response = self.client.get("/login")
        response = self.client.post(
            "/login",
            data={
                "_csrf_token": self.token(response),
                "email": "admin@example.test",
                "password": "admin-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/admin"))

        dashboard = self.client.get("/admin")
        self.assertEqual(self.client.get("/admin/products/new").status_code, 200)
        response = self.client.post(
            "/admin/products/new",
            data={
                "_csrf_token": self.token(dashboard),
                "name": "Desk Lamp",
                "description": "Warm light for the evening.",
                "category": "Gadgets",
                "price": "45.50",
                "stock": "3",
                "image_url": "https://example.com/lamp.jpg",
                "featured": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(Product.query.filter_by(name="Desk Lamp").one().price, Decimal("45.50"))
            order = Order(
                customer_name="Taylor Shopper",
                email="taylor@example.test",
                phone="555 123 4567",
                address="10 Market Street",
                total=Decimal("22.00"),
            )
            order.items.append(
                OrderItem(
                    product_id=self.product_id,
                    product_name="Canvas Tote",
                    unit_price=Decimal("22.00"),
                    quantity=1,
                )
            )
            db.session.get(Product, self.product_id).stock = 3
            db.session.add(order)
            db.session.commit()
            order_id = order.id
        dashboard = self.client.get("/admin")
        response = self.client.post(
            f"/admin/orders/{order_id}/status",
            data={
                "_csrf_token": self.token(dashboard),
                "status": "Shipped",
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.get(Order, order_id).status, "Shipped")
            self.assertEqual(db.session.get(Product, self.product_id).stock, 3)
        dashboard = self.client.get("/admin")
        self.client.post(
            f"/admin/orders/{order_id}/status",
            data={"_csrf_token": self.token(dashboard), "status": "Cancelled"},
        )
        with app.app_context():
            self.assertEqual(db.session.get(Product, self.product_id).stock, 4)
        dashboard = self.client.get("/admin")
        self.client.post(
            f"/admin/orders/{order_id}/status",
            data={"_csrf_token": self.token(dashboard), "status": "Processing"},
        )
        with app.app_context():
            self.assertEqual(db.session.get(Product, self.product_id).stock, 3)

    def test_admin_rejects_non_finite_product_prices(self):
        login_page = self.client.get("/login")
        self.client.post(
            "/login",
            data={
                "_csrf_token": self.token(login_page),
                "email": "admin@example.test",
                "password": "admin-password",
            },
        )
        product_form = self.client.get("/admin/products/new")
        response = self.client.post(
            "/admin/products/new",
            data={
                "_csrf_token": self.token(product_form),
                "name": "Broken Price",
                "description": "An invalid price should not be accepted.",
                "category": "Gadgets",
                "price": "NaN",
                "stock": "1",
                "image_url": "https://example.com/item.jpg",
            },
        )
        self.assertEqual(response.status_code, 200)
        with app.app_context():
            self.assertIsNone(Product.query.filter_by(name="Broken Price").first())

    def test_deleting_product_preserves_historical_order_item(self):
        login_page = self.client.get("/login")
        self.client.post(
            "/login",
            data={
                "_csrf_token": self.token(login_page),
                "email": "admin@example.test",
                "password": "admin-password",
            },
        )
        with app.app_context():
            order = Order(
                customer_name="Taylor Shopper",
                email="taylor@example.test",
                phone="555 123 4567",
                address="10 Market Street",
                total=Decimal("22.00"),
            )
            order.items.append(
                OrderItem(
                    product_id=self.product_id,
                    product_name="Canvas Tote",
                    unit_price=Decimal("22.00"),
                    quantity=1,
                )
            )
            db.session.add(order)
            db.session.commit()
            order_id = order.id
        dashboard = self.client.get("/admin")
        response = self.client.post(
            f"/admin/products/{self.product_id}/delete",
            data={"_csrf_token": self.token(dashboard)},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            item = OrderItem.query.filter_by(order_id=order_id).one()
            self.assertIsNone(item.product_id)
            self.assertEqual(item.product_name, "Canvas Tote")

    def test_registration_and_cart_survive_login(self):
        products_page = self.client.get("/products")
        self.client.post(
            f"/cart/add/{self.product_id}",
            data={"_csrf_token": self.token(products_page)},
        )
        register_page = self.client.get("/register")
        response = self.client.post(
            "/register",
            data={
                "_csrf_token": self.token(register_page),
                "name": "Taylor Shopper",
                "email": "taylor@example.test",
                "password": "secure-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        cart_page = self.client.get("/cart")
        self.assertIn(b"Canvas Tote", cart_page.data)

    def test_regular_user_cannot_open_admin_and_csrf_is_required(self):
        self.assertEqual(self.client.post(f"/cart/add/{self.product_id}").status_code, 400)
        register_page = self.client.get("/register")
        self.client.post(
            "/register",
            data={
                "_csrf_token": self.token(register_page),
                "name": "Taylor Shopper",
                "email": "taylor@example.test",
                "password": "secure-password",
            },
        )
        self.assertEqual(self.client.get("/admin").status_code, 403)


if __name__ == "__main__":
    unittest.main()
