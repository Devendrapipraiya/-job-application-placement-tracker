import sqlite3

DATABASE = "jobs.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    # Create table if it does not exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            applied_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Applied',
            interview_date TEXT,
            salary_package REAL,
            company_website TEXT
        )
    """)

    # Add new columns to an existing database safely
    existing_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(applications)"
        ).fetchall()
    }

    new_columns = {
        "interview_date": "TEXT",
        "salary_package": "REAL",
        "company_website": "TEXT",
    }

    for column, data_type in new_columns.items():
        if column not in existing_columns:
            conn.execute(
                f"ALTER TABLE applications ADD COLUMN {column} {data_type}"
            )

    conn.commit()
    conn.close()