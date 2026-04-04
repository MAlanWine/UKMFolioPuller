"""Database module - SQLite operations"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "ukmfolio.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tbl_courses (
            course_id       INTEGER PRIMARY KEY,
            course_name     TEXT NOT NULL,
            course_shortname TEXT NOT NULL,
            course_category TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tbl_items (
            item_id     INTEGER PRIMARY KEY,
            item_type   TEXT NOT NULL,
            item_title  TEXT NOT NULL,
            deadline    INTEGER,
            item_url    TEXT NOT NULL,
            belongs_to  INTEGER NOT NULL,
            FOREIGN KEY (belongs_to) REFERENCES tbl_courses(course_id)
        );
    """)
    conn.commit()
    conn.close()


def upsert_courses(courses: list[dict]):
    """Insert or update course list."""
    conn = get_connection()
    conn.executemany(
        """INSERT INTO tbl_courses (course_id, course_name, course_shortname, course_category)
           VALUES (:course_id, :course_name, :course_shortname, :course_category)
           ON CONFLICT(course_id) DO UPDATE SET
               course_name = excluded.course_name,
               course_shortname = excluded.course_shortname,
               course_category = excluded.course_category""",
        courses,
    )
    conn.commit()
    conn.close()


def get_all_items() -> dict[int, dict]:
    """Return {item_id: {item_id, item_type, item_title, deadline, item_url, belongs_to}}."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM tbl_items").fetchall()
    conn.close()
    return {row["item_id"]: dict(row) for row in rows}


def get_course_info(course_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM tbl_courses WHERE course_id = ?", (course_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_items(items: list[dict]):
    conn = get_connection()
    conn.executemany(
        """INSERT INTO tbl_items (item_id, item_type, item_title, deadline, item_url, belongs_to)
           VALUES (:item_id, :item_type, :item_title, :deadline, :item_url, :belongs_to)""",
        items,
    )
    conn.commit()
    conn.close()


def update_item(item: dict):
    conn = get_connection()
    conn.execute(
        """UPDATE tbl_items SET item_type=:item_type, item_title=:item_title,
           deadline=:deadline, item_url=:item_url, belongs_to=:belongs_to
           WHERE item_id=:item_id""",
        item,
    )
    conn.commit()
    conn.close()


def delete_items(item_ids: list[int]):
    conn = get_connection()
    conn.executemany(
        "DELETE FROM tbl_items WHERE item_id = ?",
        [(i,) for i in item_ids],
    )
    conn.commit()
    conn.close()
