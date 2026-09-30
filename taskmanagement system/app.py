import os
import re
import secrets
from datetime import date, datetime, timezone
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///tasks.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

os.makedirs(app.instance_path, exist_ok=True)
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

TASK_STATUSES = ("Pending", "In Progress", "Completed")
TASK_PRIORITIES = ("Low", "Medium", "High")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    tasks = db.relationship(
        "Task", back_populates="user", cascade="all, delete-orphan"
    )


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    priority = db.Column(db.String(10), nullable=False, default="Medium")
    status = db.Column(db.String(20), nullable=False, default="Pending")
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    user = db.relationship("User", back_populates="tasks")


with app.app_context():
    db.create_all()


@app.context_processor
def inject_template_values():
    return {
        "current_user": g.get("current_user"),
        "csrf_token": generate_csrf,
        "task_statuses": TASK_STATUSES,
        "task_priorities": TASK_PRIORITIES,
    }


@app.before_request
def load_current_user():
    user_id = session.get("user_id")
    g.current_user = db.session.get(User, user_id) if user_id else None


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    if request.path.startswith("/api/"):
        return jsonify(error="Your session expired. Please refresh and try again."), 400
    flash("Your session expired. Please try again.", "error")
    return redirect(url_for("login"))


@app.errorhandler(404)
def handle_not_found(error):
    if request.path.startswith("/api/"):
        return jsonify(error="Task not found."), 404
    return error


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.current_user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in to continue."), 401
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def get_owned_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=g.current_user.id).first()
    if task is None:
        abort(404)
    return task


def task_values(source):
    title_value = source.get("title", "")
    description_value = source.get("description", "")
    priority = source.get("priority", "Medium")
    status = source.get("status", "Pending")
    due_date_value = source.get("due_date", "")

    errors = {}
    title = title_value.strip() if isinstance(title_value, str) else ""
    description = (
        description_value.strip() if isinstance(description_value, str) else ""
    )
    if not isinstance(title_value, str):
        errors["title"] = "A task title is required."
    elif not isinstance(description_value, str):
        errors["description"] = "Description must be text."
    if not title:
        errors["title"] = "A task title is required."
    elif len(title) > 120:
        errors["title"] = "The title must be 120 characters or fewer."
    if len(description) > 2000:
        errors["description"] = "The description must be 2,000 characters or fewer."
    if not isinstance(priority, str) or priority not in TASK_PRIORITIES:
        errors["priority"] = "Choose a valid priority."
    if not isinstance(status, str) or status not in TASK_STATUSES:
        errors["status"] = "Choose a valid status."

    parsed_due_date = None
    if due_date_value:
        if not isinstance(due_date_value, str):
            errors["due_date"] = "Enter a valid due date."
        else:
            try:
                parsed_due_date = date.fromisoformat(due_date_value)
            except ValueError:
                errors["due_date"] = "Enter a valid due date."

    return {
        "title": title,
        "description": description,
        "priority": priority if isinstance(priority, str) else "Medium",
        "status": status if isinstance(status, str) else "Pending",
        "due_date": parsed_due_date,
    }, errors


def task_to_dict(task):
    return {
        "id": task.id,
        "user_id": task.user_id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": task.status,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat(),
    }


def filtered_tasks(user_id):
    tasks_query = Task.query.filter_by(user_id=user_id)
    search_text = request.args.get("q", "").strip()[:120]
    selected_status = request.args.get("status", "").strip()
    selected_priority = request.args.get("priority", "").strip()

    if search_text:
        tasks_query = tasks_query.filter(Task.title.ilike(f"%{search_text}%"))
    if selected_status in TASK_STATUSES:
        tasks_query = tasks_query.filter_by(status=selected_status)
    if selected_priority in TASK_PRIORITIES:
        tasks_query = tasks_query.filter_by(priority=selected_priority)

    return (
        tasks_query.order_by(
            Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.desc()
        ).all(),
        search_text,
        selected_status,
        selected_priority,
    )


@app.route("/")
def index():
    return redirect(url_for("dashboard") if g.current_user else url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.current_user:
        return redirect(url_for("dashboard"))

    values = {"username": "", "email": ""}
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        values = {"username": username, "email": email}
        errors = []

        if not username or len(username) > 40:
            errors.append("Username is required and must be 40 characters or fewer.")
        if not EMAIL_PATTERN.fullmatch(email) or len(email) > 120:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if User.query.filter_by(username=username).first():
            errors.append("That username is already registered.")
        if User.query.filter_by(email=email).first():
            errors.append("That email address is already registered.")

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            user = User(
                username=username,
                email=email,
                password=generate_password_hash(password),
            )
            db.session.add(user)
            db.session.commit()
            session.clear()
            session["user_id"] = user.id
            flash("Your account is ready. Welcome!", "success")
            return redirect(url_for("dashboard"))

    return render_template("register.html", values=values)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.current_user:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user is None or not check_password_hash(user.password, password):
            flash("Email or password is incorrect.", "error")
        else:
            session.clear()
            session["user_id"] = user.id
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    tasks, search_text, selected_status, selected_priority = filtered_tasks(
        g.current_user.id
    )
    user_tasks = Task.query.filter_by(user_id=g.current_user.id)
    counts = {
        "total": user_tasks.count(),
        "pending": user_tasks.filter_by(status="Pending").count(),
        "in_progress": user_tasks.filter_by(status="In Progress").count(),
        "completed": user_tasks.filter_by(status="Completed").count(),
    }
    return render_template(
        "dashboard.html",
        tasks=tasks,
        counts=counts,
        search_text=search_text,
        selected_status=selected_status,
        selected_priority=selected_priority,
    )


@app.route("/tasks/new", methods=["GET", "POST"])
@login_required
def create_task():
    values = {"priority": "Medium", "status": "Pending"}
    if request.method == "POST":
        values, errors = task_values(request.form)
        if errors:
            for error in errors.values():
                flash(error, "error")
        else:
            task = Task(user_id=g.current_user.id, **values)
            db.session.add(task)
            db.session.commit()
            flash("Task created.", "success")
            return redirect(url_for("task_details", task_id=task.id))
    return render_template("task_form.html", task=None, values=values)


@app.route("/tasks/<int:task_id>")
@login_required
def task_details(task_id):
    return render_template("task_details.html", task=get_owned_task(task_id))


@app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    task = get_owned_task(task_id)
    values = {
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": task.status,
        "due_date": task.due_date.isoformat() if task.due_date else "",
    }
    if request.method == "POST":
        values, errors = task_values(request.form)
        if errors:
            for error in errors.values():
                flash(error, "error")
        else:
            for field, value in values.items():
                setattr(task, field, value)
            db.session.commit()
            flash("Task updated.", "success")
            return redirect(url_for("task_details", task_id=task.id))
    return render_template("task_form.html", task=task, values=values)


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    task = get_owned_task(task_id)
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/tasks", methods=["GET", "POST"])
@login_required
def tasks_api():
    if request.method == "GET":
        tasks, _, _, _ = filtered_tasks(g.current_user.id)
        return jsonify([task_to_dict(task) for task in tasks])

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(errors={"request": "Expected a JSON object."}), 400
    values, errors = task_values(payload)
    if errors:
        return jsonify(errors=errors), 400
    task = Task(user_id=g.current_user.id, **values)
    db.session.add(task)
    db.session.commit()
    return jsonify(task_to_dict(task)), 201


@app.route("/api/tasks/<int:task_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def task_api(task_id):
    task = get_owned_task(task_id)
    if request.method == "GET":
        return jsonify(task_to_dict(task))
    if request.method == "DELETE":
        db.session.delete(task)
        db.session.commit()
        return "", 204

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(errors={"request": "Expected a JSON object."}), 400
    values, errors = task_values(payload)
    if errors:
        return jsonify(errors=errors), 400
    for field, value in values.items():
        setattr(task, field, value)
    db.session.commit()
    return jsonify(task_to_dict(task))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
