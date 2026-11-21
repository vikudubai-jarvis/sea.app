import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timedelta

DB_PATH = "sea_users.db"

def init_db():
    """Initialize the database with users table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            email TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            question TEXT NOT NULL,
            response TEXT,
            asked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_email) REFERENCES users(email)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS remember_tokens (
            token_hash TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            last_seen TIMESTAMP NOT NULL
        )
    """)

    user_columns = [row[1] for row in cursor.execute("PRAGMA table_info(users)")]
    if "pin_hash" not in user_columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN pin_hash TEXT")
        except sqlite3.OperationalError as e:
            # Another browser session added it at the same moment
            if "duplicate column" not in str(e):
                raise

    # Unique per account: rows of the same account may share a PIN, different accounts may not.
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS users_pin_unique
        BEFORE INSERT ON users
        WHEN NEW.pin_hash IS NOT NULL
             AND EXISTS (SELECT 1 FROM users WHERE pin_hash = NEW.pin_hash AND email != NEW.email)
        BEGIN
            SELECT RAISE(ABORT, 'UNIQUE constraint failed: users.pin_hash');
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS users_pin_unique_update
        BEFORE UPDATE OF pin_hash ON users
        WHEN NEW.pin_hash IS NOT NULL
             AND EXISTS (SELECT 1 FROM users WHERE pin_hash = NEW.pin_hash AND email != NEW.email)
        BEGIN
            SELECT RAISE(ABORT, 'UNIQUE constraint failed: users.pin_hash');
        END
    """)

    conn.commit()
    conn.close()

def add_user(name, age, email, pin_hash=None):
    """Add a new user to the database. `email` is the account ID (an internal one for PIN accounts)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Allow same email to register again (removed UNIQUE constraint)
        cursor.execute("""
            INSERT INTO users (name, age, email, created_at, pin_hash)
            VALUES (?, ?, ?, ?, ?)
        """, (name, age, email, datetime.now(), pin_hash))

        conn.commit()
        conn.close()
        return True, "Account created successfully!"

    except sqlite3.IntegrityError:
        return False, "That PIN is already taken. Please pick a different one."
    except Exception as e:
        return False, f"Error: {str(e)}"

def get_user(email):
    """Get user data by email (most recent if registered multiple times)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get the most recent user registration with this email
        cursor.execute("""
            SELECT name, age, email, created_at
            FROM users
            WHERE email = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (email,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "name": result[0],
                "age": result[1],
                "email": result[2],
                "created_at": result[3]
            }
        return None

    except Exception as e:
        print(f"Error getting user: {e}")
        return None

def pin_in_use(pin_hash):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT 1 FROM users WHERE pin_hash = ? LIMIT 1", (pin_hash,)).fetchone()
    conn.close()
    return row is not None


def pin_in_use_by_other(pin_hash, email):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT 1 FROM users WHERE pin_hash = ? AND email != ? LIMIT 1", (pin_hash, email)
    ).fetchone()
    conn.close()
    return row is not None


def update_user_fields(email, **fields):
    """Update name / age / pin_hash on every row for this account."""
    allowed = {"name", "age", "pin_hash"}
    assignments = [f"{col} = ?" for col in fields if col in allowed]
    values = [fields[col] for col in fields if col in allowed]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE users SET {', '.join(assignments)} WHERE email = ?", (*values, email))
    conn.commit()
    conn.close()


def get_account_id_by_pin(pin_hash):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT email FROM users WHERE pin_hash = ? ORDER BY created_at DESC LIMIT 1",
        (pin_hash,),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_account_ids_by_name_age(name, age):
    """All distinct accounts whose name (any capitalisation) and age match."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT DISTINCT email FROM users WHERE lower(trim(name)) = lower(trim(?)) AND age = ?",
        (name, age),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def update_last_login(email):
    """Update last login timestamp for the most recent registration."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Update the most recent user with this email
        cursor.execute("""
            UPDATE users
            SET last_login = ?
            WHERE email = ? AND created_at = (
                SELECT MAX(created_at) FROM users WHERE email = ?
            )
        """, (datetime.now(), email, email))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating login: {e}")

def save_question(email, question, response):
    """Save a question and response to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO questions (user_email, question, response, asked_at)
            VALUES (?, ?, ?, ?)
        """, (email, question, response, datetime.now()))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving question: {e}")

def get_user_questions(email, limit=10):
    """Get user's question history."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT question, response, asked_at FROM questions
            WHERE user_email = ?
            ORDER BY asked_at DESC
            LIMIT ?
        """, (email, limit))

        results = cursor.fetchall()
        conn.close()
        return results

    except Exception as e:
        print(f"Error getting questions: {e}")
        return []

REMEMBER_DAYS = 30


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_remember_token(email):
    """Create a 'stay logged in' token for this email; only its hash is stored."""
    token = secrets.token_urlsafe(32)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO remember_tokens (token_hash, email, last_seen) VALUES (?, ?, ?)",
        (_hash_token(token), email, datetime.now()),
    )
    conn.commit()
    conn.close()
    return token


def get_email_for_token(token):
    """Return the email for a valid token and refresh its 30-day window, or None."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT email, last_seen FROM remember_tokens WHERE token_hash = ?",
        (_hash_token(token),),
    ).fetchone()

    if not row:
        conn.close()
        return None

    email, last_seen = row
    if datetime.now() - datetime.fromisoformat(str(last_seen)) > timedelta(days=REMEMBER_DAYS):
        conn.execute("DELETE FROM remember_tokens WHERE token_hash = ?", (_hash_token(token),))
        conn.commit()
        conn.close()
        return None

    conn.execute(
        "UPDATE remember_tokens SET last_seen = ? WHERE token_hash = ?",
        (datetime.now(), _hash_token(token)),
    )
    conn.commit()
    conn.close()
    return email


def delete_remember_tokens_for_email(email):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM remember_tokens WHERE email = ?", (email,))
    conn.commit()
    conn.close()


def delete_account(email):
    """Delete an account and everything saved for it."""
    conn = sqlite3.connect(DB_PATH)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.execute("DELETE FROM remember_tokens WHERE email = ?", (email,))
    for table in ("questions", "sessions", "session_messages"):
        if table in tables:
            conn.execute(f"DELETE FROM {table} WHERE user_email = ?", (email,))
    conn.commit()
    conn.close()


def get_all_users():
    """Get all registered users (for admin/backup purposes)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT email, name, age, created_at FROM users")
        results = cursor.fetchall()
        conn.close()
        return results

    except Exception as e:
        print(f"Error getting users: {e}")
        return []
