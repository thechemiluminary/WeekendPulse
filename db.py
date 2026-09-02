"""
WeekendPulse - SQLite database helpers.
Tracks scraped articles + whether they've been posted (prevents reposting).
"""
import sqlite3
from datetime import datetime
from config import DB_PATH


def get_conn():
    """Return a connection with row access as dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist + migrate older DBs."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            source TEXT,
            summary TEXT,
            published DATETIME,
            image_url TEXT,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            post_type TEXT,
            posted BOOLEAN DEFAULT 0,
            post_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Migration: older DBs lack image_url column.
    cols = [row[1] for row in cur.execute("PRAGMA table_info(articles)").fetchall()]
    if "image_url" not in cols:
        cur.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_posted ON articles(posted)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url)")
    conn.commit()
    conn.close()


def article_exists(conn, url):
    """Return True if an article with this URL is already known."""
    row = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone()
    return row is not None


def insert_article(conn, url, title, source, summary, published, post_type, image_url=None):
    """Insert a new article. Returns True if newly inserted, False if duplicate."""
    try:
        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO articles
                (url, title, source, summary, published, post_type, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (url, title, source, summary, published, post_type, image_url),
        )
        conn.commit()
        # If INSERT OR IGNORE was ignored (duplicate), total_changes didn't move.
        return conn.total_changes > before
    except sqlite3.IntegrityError:
        return False


def get_unposted_articles(conn, limit=5):
    """Return the newest articles that haven't been posted yet."""
    rows = conn.execute(
        """
        SELECT * FROM articles
        WHERE posted = 0
        ORDER BY scraped_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return rows


def mark_posted(conn, article_id, post_id=None):
    """Mark an article as posted with optional FB post id."""
    conn.execute(
        "UPDATE articles SET posted = 1, post_id = ? WHERE id = ?",
        (post_id, article_id),
    )
    conn.commit()


def count_posted_today(conn):
    """Count how many posts were made today (to enforce daily pacing)."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM articles
        WHERE posted = 1 AND date(created_at) = ?
        """,
        (today,),
    ).fetchone()
    return row["c"] if row else 0
