import os
import re
import secrets
from datetime import datetime

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///portfolio.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

os.makedirs(app.instance_path, exist_ok=True)
db = SQLAlchemy(app)


class Project(db.Model):
    """A portfolio project shown on the home and projects pages."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    technologies = db.Column(db.String(255), nullable=False)
    github_url = db.Column(db.String(255), nullable=False)
    image = db.Column(db.String(120), nullable=False)


class Contact(db.Model):
    """A message submitted through the contact form."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())


SAMPLE_PROJECTS = [
    {
        "title": "TaskFlow",
        "description": "A simple task planner that helps people organize daily work and keep track of progress.",
        "technologies": "Python, Flask, SQLite",
        "github_url": "https://github.com/chiranthvraj",
        "image": "project-taskflow.svg",
    },
    {
        "title": "Weatherly",
        "description": "A responsive weather dashboard with clear forecasts and a friendly, easy-to-read interface.",
        "technologies": "HTML, CSS, JavaScript",
        "github_url": "https://github.com/chiranthvraj",
        "image": "project-weatherly.svg",
    },
    {
        "title": "StudySpace",
        "description": "A focused study companion for keeping notes, planning sessions, and building consistent habits.",
        "technologies": "Python, Flask, JavaScript",
        "github_url": "https://github.com/chiranthvraj",
        "image": "project-studyspace.svg",
    },
    {
        "title": "Personal Portfolio",
        "description": "A responsive portfolio that presents projects and skills, with project search and a contact form backed by SQLite.",
        "technologies": "HTML, CSS, JavaScript, Flask, SQLite, SQLAlchemy",
        "github_url": "https://github.com/chiranthvraj",
        "image": "project-portfolio.svg",
    },
]


def initialize_database():
    """Create the tables and add example projects the first time the app runs."""
    with app.app_context():
        db.create_all()
        existing_titles = {project.title for project in Project.query.all()}
        missing_examples = [
            Project(**project)
            for project in SAMPLE_PROJECTS
            if project["title"] not in existing_titles
        ]
        if missing_examples:
            db.session.add_all(missing_examples)
        # Replace old sample placeholders without changing custom project URLs.
        updated_placeholders = Project.query.filter_by(
            github_url="https://github.com/"
        ).update({Project.github_url: "https://github.com/chiranthvraj"})
        if missing_examples or updated_placeholders:
            db.session.commit()


initialize_database()


@app.context_processor
def add_profile_details():
    """Make the editable profile details available to every template."""
    return {
        "profile": {
            "name": "Chiranth V Raj",
            "role": "Aspiring Full-Stack Developer",
            "intro": (
                "I'm Chiranth V Raj, an aspiring full-stack developer who enjoys "
                "turning thoughtful ideas into useful web experiences."
            ),
            "about": (
                "I'm Chiranth V Raj, a curious student who enjoys solving problems "
                "and building for the web. I'm learning how each part of an "
                "application fits together, from the interface to the database."
            ),
            "education": "Add your course, college, and expected graduation year here.",
            "interests": "Web development, accessible design, and building practical software.",
            "github": "https://github.com/chiranthvraj",
            "linkedin": "https://www.linkedin.com/",
            "email": "chiranthvraj@example.com",
            "current_year": datetime.now().year,
        }
    }


@app.route("/")
def home():
    projects = Project.query.order_by(Project.id.desc()).limit(3).all()
    return render_template("index.html", projects=projects)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/projects")
def projects():
    search_text = request.args.get("q", "").strip()[:100]
    selected_technology = request.args.get("technology", "").strip()[:60]
    project_query = Project.query

    if search_text:
        search_pattern = f"%{search_text}%"
        project_query = project_query.filter(
            db.or_(
                Project.title.ilike(search_pattern),
                Project.description.ilike(search_pattern),
                Project.technologies.ilike(search_pattern),
            )
        )

    if selected_technology:
        project_query = project_query.filter(
            Project.technologies.ilike(f"%{selected_technology}%")
        )

    all_projects = project_query.order_by(Project.id.desc()).all()
    technologies = sorted(
        {
            technology.strip()
            for project in Project.query.all()
            for technology in project.technologies.split(",")
            if technology.strip()
        },
        key=str.casefold,
    )
    return render_template(
        "projects.html",
        projects=all_projects,
        technologies=technologies,
        search_text=search_text,
        selected_technology=selected_technology,
    )


@app.route("/projects/<int:project_id>")
def project_detail(project_id):
    project = db.session.get(Project, project_id)
    if project is None:
        abort(404)
    return render_template("project_detail.html", project=project)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash("Please fill in every field.", "error")
        elif len(name) > 100 or len(email) > 120 or len(message) > 5000:
            flash("Please keep your details within the allowed length.", "error")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Please enter a valid email address.", "error")
        else:
            db.session.add(Contact(name=name, email=email, message=message))
            db.session.commit()
            flash("Thanks for reaching out! Your message has been saved.", "success")
            return redirect(url_for("contact"))

    return render_template("contact.html")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
