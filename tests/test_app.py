import csv
import io
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import app as project


class JobTrackerTests(unittest.TestCase):

    def setUp(self):
        # Create a separate temporary database for every test
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(
            self.temp_dir.name, "test_jobs.db"
        )

        self.create_test_database()

        # Redirect app database connections to the test database
        self.db_patch = patch.object(
            project,
            "get_db_connection",
            side_effect=self.get_test_connection
        )
        self.db_patch.start()

        project.app.config["TESTING"] = True
        project.app.config["SECRET_KEY"] = "test-secret-key"
        self.client = project.app.test_client()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def get_test_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_test_database(self):
        conn = self.get_test_connection()

        conn.execute("""
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                applied_date TEXT NOT NULL,
                status TEXT NOT NULL,
                interview_date TEXT,
                salary_package REAL,
                company_website TEXT
            )
        """)

        conn.commit()
        conn.close()

    def add_test_application(self, **overrides):
        data = {
            "company": "Test Company",
            "role": "Python Developer",
            "applied_date": "2026-10-20",
            "status": "Applied",
            "interview_date": "",
            "salary_package": "5.5",
            "company_website": "https://example.com"
        }
        data.update(overrides)

        conn = self.get_test_connection()
        cursor = conn.execute("""
            INSERT INTO applications (
                company, role, applied_date, status,
                interview_date, salary_package, company_website
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["company"],
            data["role"],
            data["applied_date"],
            data["status"],
            data["interview_date"] or None,
            float(data["salary_package"])
                if data["salary_package"] else None,
            data["company_website"] or None
        ))

        conn.commit()
        app_id = cursor.lastrowid
        conn.close()
        return app_id

    def get_application(self, app_id):
        conn = self.get_test_connection()
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?",
            (app_id,)
        ).fetchone()
        conn.close()
        return row

    # 1. Application imports successfully
    def test_app_exists(self):
        self.assertIsNotNone(project.app)

    # 2. Validation functions
    def test_valid_date(self):
        self.assertTrue(project.valid_date("2026-10-25"))

    def test_invalid_date(self):
        self.assertFalse(project.valid_date("25-10-2026"))

    def test_valid_website(self):
        self.assertTrue(
            project.valid_website("https://example.com")
        )

    def test_invalid_website(self):
        self.assertFalse(
            project.valid_website("example.com")
        )

    def test_valid_salary(self):
        self.assertTrue(project.valid_salary("5.5"))
        self.assertTrue(project.valid_salary("0"))

    def test_invalid_salary(self):
        self.assertFalse(project.valid_salary("-5"))
        self.assertFalse(project.valid_salary("abc"))

    # 3. Dashboard
    def test_homepage_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_search_company(self):
        self.add_test_application(company="Google")

        response = self.client.get("/?search=Google")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Google", response.data)

    def test_status_filter(self):
        self.add_test_application(status="Interview")

        response = self.client.get("/?status=Interview")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Interview", response.data)

    # 4. Add application
    def test_add_application_success(self):
        response = self.client.post("/add", data={
            "company": "OpenAI",
            "role": "Python Developer",
            "applied_date": "2026-10-20",
            "status": "Applied",
            "interview_date": "",
            "salary_package": "8",
            "company_website": "https://example.com"
        })

        self.assertEqual(response.status_code, 302)

        conn = self.get_test_connection()
        row = conn.execute(
            "SELECT * FROM applications WHERE company = ?",
            ("OpenAI",)
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["role"], "Python Developer")

    def test_add_application_invalid_date(self):
        response = self.client.post("/add", data={
            "company": "Test Company",
            "role": "Developer",
            "applied_date": "wrong-date",
            "status": "Applied"
        })

        self.assertEqual(response.status_code, 302)

        conn = self.get_test_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM applications"
        ).fetchone()[0]
        conn.close()

        self.assertEqual(count, 0)

    def test_add_application_invalid_status(self):
        response = self.client.post("/add", data={
            "company": "Test Company",
            "role": "Developer",
            "applied_date": "2026-10-20",
            "status": "Unknown"
        })

        self.assertEqual(response.status_code, 302)

        conn = self.get_test_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM applications"
        ).fetchone()[0]
        conn.close()

        self.assertEqual(count, 0)

    def test_add_application_negative_salary(self):
        response = self.client.post("/add", data={
            "company": "Test Company",
            "role": "Developer",
            "applied_date": "2026-10-20",
            "status": "Applied",
            "salary_package": "-10"
        })

        self.assertEqual(response.status_code, 302)

        conn = self.get_test_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM applications"
        ).fetchone()[0]
        conn.close()

        self.assertEqual(count, 0)

    def test_add_application_invalid_website(self):
        response = self.client.post("/add", data={
            "company": "Test Company",
            "role": "Developer",
            "applied_date": "2026-10-20",
            "status": "Applied",
            "company_website": "not-a-url"
        })

        self.assertEqual(response.status_code, 302)

        conn = self.get_test_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM applications"
        ).fetchone()[0]
        conn.close()

        self.assertEqual(count, 0)

    # 5. Edit application
    def test_edit_page_loads(self):
        app_id = self.add_test_application()

        response = self.client.get(f"/edit/{app_id}")

        self.assertEqual(response.status_code, 200)

    def test_edit_application_success(self):
        app_id = self.add_test_application()

        response = self.client.post(f"/edit/{app_id}", data={
            "company": "Updated Company",
            "role": "Senior Developer",
            "applied_date": "2026-10-21",
            "status": "Interview",
            "interview_date": "2026-10-30",
            "salary_package": "10",
            "company_website": "https://example.com"
        })

        self.assertEqual(response.status_code, 302)

        row = self.get_application(app_id)
        self.assertEqual(row["company"], "Updated Company")
        self.assertEqual(row["status"], "Interview")
        self.assertEqual(row["salary_package"], 10)

    def test_edit_invalid_application(self):
        app_id = self.add_test_application()

        response = self.client.post(f"/edit/{app_id}", data={
            "company": "",
            "role": "Developer",
            "applied_date": "2026-10-20",
            "status": "Applied"
        })

        self.assertEqual(response.status_code, 302)

        row = self.get_application(app_id)
        self.assertEqual(row["company"], "Test Company")

    def test_edit_nonexistent_application(self):
        response = self.client.get("/edit/99999")

        self.assertEqual(response.status_code, 302)

    # 6. Delete application
    def test_delete_application_success(self):
        app_id = self.add_test_application()

        response = self.client.post(f"/delete/{app_id}")

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.get_application(app_id))

    def test_delete_nonexistent_application(self):
        response = self.client.post("/delete/99999")

        self.assertEqual(response.status_code, 302)

    # 7. CSV export
    def test_export_csv(self):
        self.add_test_application(company="CSV Company")

        response = self.client.get("/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        self.assertIn(
            "attachment; filename=job_applications.csv",
            response.headers.get("Content-Disposition", "")
        )
        self.assertIn(b"Company", response.data)
        self.assertIn(b"CSV Company", response.data)

    def test_export_csv_headers(self):
        response = self.client.get("/export")

        content = response.data.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        headers = next(reader)

        self.assertEqual(headers[0], "Company")
        self.assertEqual(headers[1], "Job Role")
        self.assertEqual(headers[3], "Status")

    # 8. Unknown route
    def test_unknown_route(self):
        response = self.client.get("/route-does-not-exist")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)