"""
database.py
-----------
Everything related to storing file metadata in SQLite.

WHY A DATABASE INSTEAD OF JUST os.listdir()?
The original project just listed whatever was in the uploads/ folder.
That works, but it can't tell you WHO uploaded a file, WHEN, or HOW
MANY TIMES it's been downloaded. A database lets us store that extra
information permanently (it survives server restarts, unlike variables
in memory).

We use SQLite because it's a single file (no separate database server
to install/run) - perfect for a small project like this.
"""

import sqlite3
from datetime import datetime

import config

DB_PATH = config.DB_PATH


def get_connection():
    """Open a connection to the database file (creates it if it doesn't exist)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row["filename"]
    return conn


def init_db():
    """Create the files table if it doesn't already exist. Call this once at startup."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            uploader TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            download_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def add_file_record(filename: str, uploader: str, size_bytes: int):
    """Insert a new row when a file is uploaded."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO files (filename, uploader, upload_time, size_bytes) VALUES (?, ?, ?, ?)",
        (filename, uploader, datetime.now().strftime("%Y-%m-%d %H:%M"), size_bytes)
    )
    conn.commit()
    conn.close()


def get_all_files(search: str = ""):
    """Return all file records, optionally filtered by a search string (matches filename)."""
    conn = get_connection()
    if search:
        rows = conn.execute(
            "SELECT * FROM files WHERE filename LIKE ? ORDER BY id DESC",
            (f"%{search}%",)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM files ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_file_record(filename: str):
    """Remove a file's row from the database (called when the file itself is deleted)."""
    conn = get_connection()
    conn.execute("DELETE FROM files WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()


def increment_download_count(filename: str):
    """Bump the download counter each time a file is downloaded."""
    conn = get_connection()
    conn.execute("UPDATE files SET download_count = download_count + 1 WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()


def rename_file_record(old_filename: str, new_filename: str):
    """Update the stored filename after a rename (the row's id/history stays put)."""
    conn = get_connection()
    conn.execute("UPDATE files SET filename = ? WHERE filename = ?", (new_filename, old_filename))
    conn.commit()
    conn.close()


def filename_exists(filename: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM files WHERE filename = ?", (filename,)).fetchone()
    conn.close()
    return row is not None
