# TaskFlow — Task Management

TaskFlow is a small, beginner-friendly full-stack task manager built with Flask, SQLite, and SQLAlchemy. Register for a private workspace, organize tasks, and track progress from a responsive dashboard.

## Features

- Account registration, login, logout, and securely hashed passwords
- Private, per-user task lists with ownership checks
- Create, view, edit, and delete tasks
- Task priority, status, optional due date, and creation date
- Dashboard totals for all statuses
- Search task titles and filter by status and priority
- JSON REST API for authenticated task CRUD
- Server-side validation, clear flash messages, and CSRF protection
- Responsive layout for desktop, tablet, and mobile

## Technologies

- Python 3.9+
- Flask and Flask-SQLAlchemy
- SQLite
- HTML, CSS, JavaScript, and Bootstrap 5
- Flask-WTF CSRF protection

## Project structure

```text
taskmanagement system/
├── app.py
├── requirements.txt
├── README.md
├── instance/              # SQLite database, created automatically
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── task_form.html
│   └── task_details.html
├── static/
│   ├── css/styles.css
│   └── js/script.js
└── tests/
    └── test_app.py
```

## Installation and run

From this project directory, create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Set a stable secret key before running the app. Use a unique, private value in your own environment:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-secret"
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The SQLite database is created at `instance/tasks.db` on first start. Set `FLASK_DEBUG=1` only for local development. Optionally set `DATABASE_URL` to use another SQLAlchemy-supported database URL.

## Using the app

Create an account with a username, valid email, and password of at least eight characters. The dashboard shows your task counts. Use **Add a task** to set a title, optional description and due date, priority, and status. Select a task to view details; edit and delete actions are available from the list and detail page. Search matches task titles, and the status and priority selectors can be combined.

## REST API

All task endpoints require the same logged-in Flask session as the web pages. Responses are JSON, except successful deletion, which returns `204 No Content`. The application enforces ownership on every task lookup.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/tasks` | List the signed-in user's tasks. Optional query filters: `q`, `status`, `priority`. |
| `POST` | `/api/tasks` | Create a task. |
| `GET` | `/api/tasks/<id>` | Get one of the signed-in user's tasks. |
| `PUT` | `/api/tasks/<id>` | Replace a task's editable fields. |
| `DELETE` | `/api/tasks/<id>` | Delete one of the signed-in user's tasks. |

Task JSON fields are `title`, `description`, `priority` (`Low`, `Medium`, `High`), `status` (`Pending`, `In Progress`, `Completed`), and optional ISO `due_date` (`YYYY-MM-DD`). Responses also include `id`, `user_id`, and ISO `created_at`. API write requests use the authenticated session and Flask-WTF CSRF protection; send the `csrf_token` from an authenticated page as the `X-CSRFToken` request header.

For example, in a browser session with a CSRF token:

```javascript
fetch("/api/tasks", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content
  },
  body: JSON.stringify({
    title: "Prepare project demo",
    description: "Review the task flows",
    priority: "High",
    status: "In Progress",
    due_date: "2030-05-01"
  })
});
```

## Test

Run the focused authentication, CRUD, filtering, validation, API, and ownership tests with:

```powershell
python -m unittest discover -s tests -v
```

## Future enhancements

- Pagination for larger task lists
- Optional task categories
- Automated browser and accessibility tests
- Deployment configuration for a production WSGI server and managed database
