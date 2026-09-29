# Personal Portfolio

A small, beginner-friendly portfolio built with Flask, SQLAlchemy, and SQLite. The project section is loaded from the database, and contact form messages are saved there too.

## Requirements

- Python 3.9 or newer
- pip

## Run locally

Open a terminal in the project folder, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell prevents virtual-environment activation, run the install and app commands using `.\.venv\Scripts\python.exe` instead.

Visit [http://127.0.0.1:5000](http://127.0.0.1:5000). On the first run, the app creates `instance/portfolio.db` and inserts three example projects. The database and sample data are kept between runs.

The app generates a fresh secret key for local development when `SECRET_KEY` is not set. Set a private `SECRET_KEY` environment variable for a stable key before deploying. Debug mode is off by default; set `FLASK_DEBUG=1` only during local development.

## Pages

- `/` — introduction and selected projects
- `/about` — education, career interests, and skills
- `/projects` — projects read from SQLite
- `/projects/<id>` — an individual project page, with links to related technology filters
- `/contact` — validated contact form; successful submissions are stored in SQLite

The projects page supports searching by title, description, and technology, and filtering by a technology tag. The skill tags on the Home and About pages link to matching projects. Each project card opens a detail page. Sample entries currently link to the GitHub profile; replace each `github_url` with its real repository URL when available.

## Personalize it

The profile is currently set up for **Chiranth V Raj**. The email `chiranthvraj@example.com` is a demo address, not a real inbox. Before publishing, replace it with your actual email and verify the GitHub and LinkedIn links in `add_profile_details()` in `app.py`. Add your course, college, and graduation year there too. Replace `static/images/profile.svg` with your own image if you prefer. TaskFlow, Weatherly, and StudySpace are example entries; replace them with your real work and repository URLs.

Example projects missing from the database are added at startup without overwriting custom project entries. To add a project, use the Flask shell:

```powershell
python -m flask --app app shell
```

Then in the shell:

```python
from app import Project, db
project = Project(
    title="My project",
    description="A short description of what it does.",
    technologies="Python, Flask",
    github_url="https://github.com/your-name/your-project",
    image="project-taskflow.svg",
)
db.session.add(project)
db.session.commit()
```

Use an image filename that exists in `static/images/`.

## Project structure

```text
app.py                  Flask routes, models, and sample data
requirements.txt        Python dependencies
instance/portfolio.db   SQLite database (created on first run)
templates/              Jinja HTML templates
static/css/style.css    Responsive styles
static/js/script.js     Mobile navigation
static/images/          Local profile and project illustrations
```
