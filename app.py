import csv
from io import StringIO
from datetime import date
from urllib.parse import urlparse

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    Response
)

from database import get_db_connection, init_db


app = Flask(__name__)
app.secret_key = "development-key-change-later"

STATUSES = ["Applied", "Interview", "Selected", "Rejected"]


# =========================
# VALIDATION FUNCTIONS
# =========================

def valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def valid_website(value):
    if not value:
        return True

    try:
        parsed = urlparse(value)
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
            and " " not in value
        )
    except ValueError:
        return False


def valid_salary(value):
    if not value:
        return True

    try:
        return float(value) >= 0
    except (ValueError, TypeError):
        return False


# =========================
# HOME: DASHBOARD
# =========================

@app.route("/")
def home():
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    today = date.today().isoformat()

    conn = get_db_connection()

    try:
        # Search and filter applications
        query = "SELECT * FROM applications WHERE 1=1"
        params = []

        if search:
            query += " AND (company LIKE ? OR role LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])

        if status_filter in STATUSES:
            query += " AND status = ?"
            params.append(status_filter)

        query += " ORDER BY id DESC"

        applications = conn.execute(
            query, params
        ).fetchall()

        # Overall dashboard statistics
        stats = conn.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(
                    CASE WHEN status = 'Interview'
                    THEN 1 ELSE 0 END
                ), 0) AS interviews,
                COALESCE(SUM(
                    CASE WHEN status = 'Selected'
                    THEN 1 ELSE 0 END
                ), 0) AS selected,
                COALESCE(SUM(
                    CASE WHEN status = 'Rejected'
                    THEN 1 ELSE 0 END
                ), 0) AS rejected
            FROM applications
        """).fetchone()

        # Upcoming interviews
        upcoming_interviews = conn.execute("""
            SELECT *
            FROM applications
            WHERE interview_date >= ?
              AND status = 'Interview'
            ORDER BY interview_date ASC
            LIMIT 5
        """, (today,)).fetchall()

        # Placement analytics
        placement_stats = conn.execute("""
            SELECT
                COALESCE(SUM(
                    CASE WHEN status = 'Selected'
                    THEN salary_package ELSE 0 END
                ), 0) AS total_package,
                COUNT(
                    CASE WHEN status = 'Selected'
                    THEN 1 END
                ) AS offers
            FROM applications
        """).fetchone()

    finally:
        # Database closes only after all queries finish
        conn.close()

    # Calculate selection rate
    total = stats["total"]
    selected = stats["selected"]

    selection_rate = (
        round((selected / total) * 100, 2)
        if total > 0 else 0
    )

    # Chart data
    chart_data = {
        "applied": (
            total
            - stats["interviews"]
            - stats["selected"]
            - stats["rejected"]
        ),
        "interview": stats["interviews"],
        "selected": stats["selected"],
        "rejected": stats["rejected"]
    }

    return render_template(
        "index.html",
        applications=applications,
        today=today,
        stats=stats,
        chart_data=chart_data,
        search=search,
        status_filter=status_filter,
        statuses=STATUSES,
        selection_rate=selection_rate,
        upcoming_interviews=upcoming_interviews,
        placement_stats=placement_stats
    )


# =========================
# ADD APPLICATION
# =========================

@app.route("/add", methods=["POST"])
def add_application():
    company = request.form.get("company", "").strip()
    role = request.form.get("role", "").strip()
    applied_date = request.form.get("applied_date", "").strip()
    status = request.form.get("status", "Applied").strip()
    interview_date = request.form.get("interview_date", "").strip()
    salary_text = request.form.get("salary_package", "").strip()
    company_website = request.form.get("company_website", "").strip()

    if (
        not company
        or not role
        or status not in STATUSES
        or not valid_date(applied_date)
    ):
        flash("Please enter valid company, role, date and status.")
        return redirect(url_for("home"))

    if interview_date and not valid_date(interview_date):
        flash("Please enter a valid interview date.")
        return redirect(url_for("home"))

    if not valid_salary(salary_text):
        flash("Salary package must be a non-negative number.")
        return redirect(url_for("home"))

    if not valid_website(company_website):
        flash("Website must start with http:// or https://.")
        return redirect(url_for("home"))

    salary = float(salary_text) if salary_text else None

    conn = get_db_connection()

    try:
        conn.execute("""
            INSERT INTO applications (
                company, role, applied_date, status,
                interview_date, salary_package, company_website
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            company,
            role,
            applied_date,
            status,
            interview_date or None,
            salary,
            company_website or None
        ))

        conn.commit()

    finally:
        conn.close()

    flash("Application added successfully!")
    return redirect(url_for("home"))


# =========================
# EDIT APPLICATION
# =========================

@app.route("/edit/<int:app_id>", methods=["GET", "POST"])
def edit_application(app_id):
    conn = get_db_connection()

    if request.method == "POST":
        company = request.form.get("company", "").strip()
        role = request.form.get("role", "").strip()
        applied_date = request.form.get("applied_date", "").strip()
        status = request.form.get("status", "").strip()
        interview_date = request.form.get("interview_date", "").strip()
        salary_text = request.form.get("salary_package", "").strip()
        company_website = request.form.get("company_website", "").strip()

        if (
            not company
            or not role
            or not valid_date(applied_date)
            or status not in STATUSES
        ):
            conn.close()
            flash("Please enter valid application details.")
            return redirect(
                url_for("edit_application", app_id=app_id)
            )

        if interview_date and not valid_date(interview_date):
            conn.close()
            flash("Please enter a valid interview date.")
            return redirect(
                url_for("edit_application", app_id=app_id)
            )

        if not valid_salary(salary_text):
            conn.close()
            flash("Salary package must be a non-negative number.")
            return redirect(
                url_for("edit_application", app_id=app_id)
            )

        if not valid_website(company_website):
            conn.close()
            flash("Website must start with http:// or https://.")
            return redirect(
                url_for("edit_application", app_id=app_id)
            )

        salary = float(salary_text) if salary_text else None

        try:
            result = conn.execute("""
                UPDATE applications
                SET company = ?,
                    role = ?,
                    applied_date = ?,
                    status = ?,
                    interview_date = ?,
                    salary_package = ?,
                    company_website = ?
                WHERE id = ?
            """, (
                company,
                role,
                applied_date,
                status,
                interview_date or None,
                salary,
                company_website or None,
                app_id
            ))

            conn.commit()
            updated = result.rowcount

        finally:
            conn.close()

        if updated:
            flash("Application updated successfully!")
        else:
            flash("Application not found.")

        return redirect(url_for("home"))

    try:
        application = conn.execute(
            "SELECT * FROM applications WHERE id = ?",
            (app_id,)
        ).fetchone()

    finally:
        conn.close()

    if application is None:
        flash("Application not found.")
        return redirect(url_for("home"))

    return render_template(
        "edit.html",
        application=application,
        statuses=STATUSES
    )


# =========================
# DELETE APPLICATION
# =========================

@app.route("/delete/<int:app_id>", methods=["POST"])
def delete_application(app_id):
    conn = get_db_connection()

    try:
        result = conn.execute(
            "DELETE FROM applications WHERE id = ?",
            (app_id,)
        )

        conn.commit()
        deleted = result.rowcount

    finally:
        conn.close()

    if deleted:
        flash("Application deleted successfully!")
    else:
        flash("Application not found.")

    return redirect(url_for("home"))


# =========================
# EXPORT CSV REPORT
# =========================

@app.route("/export")
def export_csv():
    conn = get_db_connection()

    try:
        applications = conn.execute("""
            SELECT
                company,
                role,
                applied_date,
                status,
                interview_date,
                salary_package,
                company_website
            FROM applications
            ORDER BY id DESC
        """).fetchall()

    finally:
        conn.close()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Company",
        "Job Role",
        "Application Date",
        "Status",
        "Interview Date",
        "Salary Package (LPA)",
        "Company Website"
    ])

    for item in applications:
        writer.writerow([
            item["company"],
            item["role"],
            item["applied_date"],
            item["status"],
            item["interview_date"],
            item["salary_package"],
            item["company_website"]
        ])

    response = Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=job_applications.csv"
    )

    return response


# =========================
# START APPLICATION
# =========================

if __name__ == "__main__":
    init_db()
    app.run(debug=True)