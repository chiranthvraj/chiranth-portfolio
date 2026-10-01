# Little Shop

A beginner-friendly Flask and MySQL storefront with INR prices, bicycles, helmets, books, gadgets, phones, laptops, product search, registration and login, a session-based cart, checkout, order history for the shop admin, and product management.

## Requirements

- Python 3.9+
- MySQL 8+ (or MariaDB with InnoDB)
- pip

## Run locally

1. Create the database:

   ```sql
   CREATE DATABASE ecommerce_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

   Or run `database/schema.sql` with your MySQL client.

2. From this project folder, configure the database connection and install packages:

   ```powershell
   $env:MYSQL_HOST = "127.0.0.1"
   $env:MYSQL_PORT = "3306"
   $env:MYSQL_DATABASE = "ecommerce_db"
   $env:MYSQL_USER = "root"
   $env:MYSQL_PASSWORD = "your-mysql-password"

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   flask --app app init-db
   python app.py
   ```

   `DATABASE_URL` can be set instead of the individual `MYSQL_*` variables, for example:
   `mysql+pymysql://shop_user:password@127.0.0.1:3306/ecommerce_db`.
   To run automated tests or try the app without MySQL, set
   `DATABASE_URL=sqlite:///ecommerce.db`.

3. Visit [http://127.0.0.1:5000](http://127.0.0.1:5000).

The first `init-db` run creates eight sample products across the shop categories and a local demo admin:
`admin@shop.local` / `Admin123!`. Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` before running
`init-db` to use your own values. Change the demo password before sharing or deploying.
Set a stable, private `SECRET_KEY` before deployment.

## Deploy the full app with GitHub and Render

The app needs a Python web server and a reachable MySQL database; GitHub Pages
cannot run Flask. This repository includes `render.yaml` for a Render web service.

1. Make sure your hosted MySQL database is reachable from Render and create an
   empty database for the shop. Copy its **public/external** connection details.
2. In Render, choose **New → Blueprint**, connect
   `chiranthvraj/chiranth-portfolio`, and select
   `E-commerce webapplication/render.yaml` as the Blueprint file.
3. Review and create the `little-shop` web service. In its environment settings,
   set `DATABASE_URL` to your hosted MySQL URL using the PyMySQL driver, for example:
   `mysql+pymysql://USER:PASSWORD@HOST:3306/ecommerce_db?charset=utf8mb4`.
   Keep this URL private; do not add it to GitHub. If the database password has
   URL-special characters, percent-encode them first.
4. Deploy. The start command installs the schema and missing sample products, then
   starts Gunicorn. Existing products and admin accounts are left unchanged on later
   restarts. Render generates a private `SECRET_KEY` and initial `ADMIN_PASSWORD`;
   find the generated admin password in the service's environment settings. The
   default admin email is `admin@shop.local`.
5. Open the service's `onrender.com` URL. The `/health` endpoint is configured for
   Render health checks.

The repository's `main` branch is connected to the service, so subsequent pushes
can trigger automatic deployments. The free web-service plan may sleep when idle;
the database remains hosted separately.

## Run the tests

The focused route and workflow tests use an in-memory SQLite database, so MySQL does
not need to be running:

```powershell
python -m unittest discover -s tests -v
```

## What is included

- Product catalogue with keyword search and featured products
- Registration, login, hashed passwords, and user/admin roles
- Cart quantities, stock checks, remove controls, subtotal, and checkout
- Saved orders and order items; checkout decrements available stock
- Delivery-status updates on order confirmations, customer order history, and guest order tracking by order number and checkout email
- Admin product create/edit/delete and order-status management
- CSRF checks on submitted forms and server-side input validation
- Responsive Bootstrap layout with a small custom stylesheet

No payment provider is connected; checkout records a cash-on-delivery/demo order.
Product images are loaded from the example image URLs and can be replaced in the
admin product form.

## Project structure

```text
app.py                  Flask routes, database models, and CLI setup
render.yaml             Render web-service deployment configuration
requirements.txt        Python dependencies
database/schema.sql    MySQL database creation
templates/              Jinja pages and shared layout
static/css/style.css    Responsive storefront styling
static/js/app.js        Small client-side helpers
tests/test_app.py       Cart, checkout, user, and admin workflow tests
```
