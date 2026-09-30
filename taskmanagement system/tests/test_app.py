import os
import re
import tempfile
import unittest

_test_database = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = (
    f"sqlite:///{os.path.join(_test_database.name, 'test.db')}"
)

from app import app as flask_app
from app import db


class TaskFlowTests(unittest.TestCase):
    def setUp(self):
        flask_app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
        )
        self.client = flask_app.test_client()
        with flask_app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with flask_app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def register(self, username="alex", email="alex@example.com", password="securepass123"):
        return self.client.post(
            "/register",
            data={"username": username, "email": email, "password": password},
            follow_redirects=True,
        )

    def login(self, email="alex@example.com", password="securepass123"):
        return self.client.post(
            "/login", data={"email": email, "password": password}, follow_redirects=True
        )

    def test_authentication_and_task_crud(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your account is ready", response.data)
        self.assertIn(b"Log out", response.data)

        create_response = self.client.post(
            "/tasks/new",
            data={
                "title": "Prepare demo",
                "description": "Walk through the project",
                "priority": "High",
                "status": "In Progress",
                "due_date": "2030-01-15",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Prepare demo", create_response.data)
        self.assertIn(b"High priority", create_response.data)

        with flask_app.app_context():
            from app import Task

            task = Task.query.one()
            task_id = task.id

        update_response = self.client.post(
            f"/tasks/{task_id}/edit",
            data={
                "title": "Demo complete",
                "description": "Ready to present",
                "priority": "Low",
                "status": "Completed",
                "due_date": "",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Demo complete", update_response.data)
        self.assertIn(b"Completed", update_response.data)

        filtered = self.client.get("/dashboard?q=Demo&status=Completed&priority=Low")
        self.assertIn(b"Demo complete", filtered.data)
        self.assertNotIn(b"Prepare demo", filtered.data)

        delete_response = self.client.post(f"/tasks/{task_id}/delete", follow_redirects=True)
        self.assertIn(b"Task deleted", delete_response.data)
        self.assertIn(b"A fresh start.", delete_response.data)

        logout_response = self.client.post("/logout", follow_redirects=True)
        self.assertIn(b"You have been logged out", logout_response.data)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_users_cannot_read_or_change_each_others_tasks(self):
        self.register()
        created = self.client.post(
            "/api/tasks",
            json={"title": "Private task", "priority": "Medium", "status": "Pending"},
        )
        self.assertEqual(created.status_code, 201)
        task_id = created.get_json()["id"]
        self.client.post("/logout")
        self.register("sam", "sam@example.com")

        missing_task = self.client.get(f"/api/tasks/{task_id}")
        self.assertEqual(missing_task.status_code, 404)
        self.assertEqual(missing_task.get_json()["error"], "Task not found.")
        self.assertEqual(
            self.client.put(
                f"/api/tasks/{task_id}",
                json={"title": "Stolen", "priority": "High", "status": "Completed"},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.delete(f"/api/tasks/{task_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/tasks").get_json(), [])

    def test_api_validation_and_login_logout(self):
        self.register()
        self.client.post("/logout")
        self.assertIn(b"Log in to pick up", self.client.get("/login").data)
        bad_login = self.login(password="wrong-password")
        self.assertIn(b"Email or password is incorrect", bad_login.data)
        self.login()

        invalid_task = self.client.post(
            "/api/tasks",
            json={"title": "", "priority": "Urgent", "status": "Blocked"},
        )
        self.assertEqual(invalid_task.status_code, 400)
        self.assertIn("title", invalid_task.get_json()["errors"])
        self.assertEqual(
            self.client.post("/api/tasks", json=["not", "an", "object"]).status_code,
            400,
        )

        created = self.client.post(
            "/api/tasks",
            json={
                "title": "API task",
                "description": "created through the API",
                "priority": "High",
                "status": "Pending",
                "due_date": "2030-05-01",
            },
        )
        self.assertEqual(created.status_code, 201)
        task_id = created.get_json()["id"]
        updated = self.client.put(
            f"/api/tasks/{task_id}",
            json={
                "title": "API task updated",
                "description": "",
                "priority": "Low",
                "status": "Completed",
            },
        )
        self.assertEqual(updated.get_json()["status"], "Completed")
        self.assertEqual(self.client.get("/api/tasks?status=Completed").get_json()[0]["id"], task_id)
        self.assertEqual(self.client.delete(f"/api/tasks/{task_id}").status_code, 204)

    def test_api_writes_require_csrf_token(self):
        self.register()
        flask_app.config["WTF_CSRF_ENABLED"] = True
        page = self.client.get("/dashboard")
        token = re.search(
            rb'<meta name="csrf-token" content="([^"]+)"', page.data
        ).group(1).decode()

        rejected = self.client.post("/api/tasks", json={"title": "No token"})
        self.assertEqual(rejected.status_code, 400)
        accepted = self.client.post(
            "/api/tasks",
            json={"title": "Protected task"},
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(accepted.status_code, 201)


if __name__ == "__main__":
    unittest.main()
