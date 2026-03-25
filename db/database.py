"""
Vercel Postgres database — stores run metadata.

Replaces log.json as the source of truth. Each pipeline run
inserts a row with the date, seed word, generated sentence,
video URL, and style mode. The frontend reads from this via
the /api/runs endpoint.

If POSTGRES_URL isn't configured, all functions return None
and print a message — the pipeline falls back to log.json.
"""

import config


def _get_connection():
    """
    Open a connection to Vercel Postgres.

    Returns a psycopg2 connection, or None if not configured.
    psycopg2 is imported here (not at module level) so the
    codebase doesn't crash if it isn't installed yet.
    """
    if not config.POSTGRES_URL:
        print("  Postgres not configured — falling back to log.json")
        return None

    import psycopg2

    # psycopg2.connect() parses the full connection string:
    #   postgres://user:password@host:port/database
    # Vercel provides this as the POSTGRES_URL env var.
    return psycopg2.connect(config.POSTGRES_URL)


def init_db():
    """
    Create the runs table if it doesn't exist.

    Call this at pipeline startup. CREATE TABLE IF NOT EXISTS
    is idempotent — safe to call every time.

    Returns True if table exists/was created, None if not configured.
    """
    conn = _get_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL,
                    seed VARCHAR(100) NOT NULL,
                    sentence TEXT NOT NULL,
                    video_url TEXT,
                    datamosh_url TEXT,
                    style_mode VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
        conn.commit()
        print("  Database initialized")
        return True
    finally:
        conn.close()


def insert_run(date, seed, sentence, video_url, style_mode):
    """
    Insert a new pipeline run into the database.

    Args:
        date: Date string like "2026-03-20"
        seed: Seed word like "elevator"
        sentence: The generated composite sentence
        video_url: R2 public URL for the video (or None)
        style_mode: Style mode name like "ABSTRACT" (or None)

    Returns:
        The new row's id, or None if not configured.
    """
    conn = _get_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            # RETURNING id gives us the auto-generated primary key
            # so we can reference this run later (e.g. to update datamosh_url).
            cur.execute(
                """INSERT INTO runs (date, seed, sentence, video_url, style_mode)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (date, seed, sentence, video_url, style_mode),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        print(f"  Inserted run #{run_id}")
        return run_id
    finally:
        conn.close()


def update_datamosh_url(run_id, datamosh_url):
    """
    Update the datamosh URL for a specific run.

    Called after datamosh.py finishes and uploads to R2.

    Returns True if updated, None if not configured.
    """
    conn = _get_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE runs SET datamosh_url = %s WHERE id = %s",
                (datamosh_url, run_id),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_runs():
    """
    Fetch all runs, newest first.

    Returns a list of dicts, or None if not configured.
    Each dict has: id, date, seed, sentence, video_url,
    datamosh_url, style_mode, created_at.
    """
    conn = _get_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, date, seed, sentence, video_url,
                          datamosh_url, style_mode, created_at
                   FROM runs ORDER BY created_at DESC"""
            )
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        # Convert each row tuple into a dict keyed by column name.
        # zip(columns, row) pairs up column names with values.
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()


def get_latest_run():
    """
    Fetch the most recent run.

    Returns a dict, or None if not configured / no runs exist.
    """
    conn = _get_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, date, seed, sentence, video_url,
                          datamosh_url, style_mode, created_at
                   FROM runs ORDER BY created_at DESC LIMIT 1"""
            )
            row = cur.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))
    finally:
        conn.close()


def delete_run(run_id):
    """
    Delete a run by id. Used by tests for cleanup.

    Returns True if deleted, None if not configured.
    """
    conn = _get_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM runs WHERE id = %s", (run_id,))
        conn.commit()
        return True
    finally:
        conn.close()
