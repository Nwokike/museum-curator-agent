import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    if not DB_URL:
        raise ValueError("❌ DATABASE_URL missing in .env")
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def init_db():
    try:
        conn = get_connection()
        conn.close()
        print("[DB] ✅ Connected to Neon Postgres.")
    except Exception as e:
        print(f"[DB] ⚠️ Connection Failed: {e}")

# --- Core Write Functions ---

def register_artifact(id, url, museum_name):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO artifact_queue (id, url, museum_name, status) 
                VALUES (%s, %s, %s, 'PENDING')
                ON CONFLICT (url) DO NOTHING
                """,
                (id, url, museum_name)
            )
        conn.commit()
    finally:
        conn.close()

def save_metadata_draft(id, metadata: dict):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO archives (
                    id, original_url, accession_number, title, 
                    archive_type, category, original_author, 
                    location, date_created, circa_date, copyright_holder,
                    description_museum
                ) VALUES (
                    %(id)s, %(url)s, %(acc_num)s, %(title)s, 
                    %(type)s, %(cat)s, %(author)s, 
                    %(loc)s, %(date)s, %(circa)s, %(copy)s, 
                    %(desc)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description_museum = EXCLUDED.description_museum,
                    date_created = EXCLUDED.date_created
                """,
                metadata
            )
            cur.execute("UPDATE artifact_queue SET status='ANALYZED' WHERE id=%s", (id,))
        conn.commit()
    finally:
        conn.close()

def log_media_asset(artifact_id, image_url, role="Primary"):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO media_assets (artifact_id, original_image_url, role)
                VALUES (%s, %s, %s)
                """,
                (artifact_id, image_url, role)
            )
        conn.commit()
    finally:
        conn.close()

# --- Discovery State Management (NEW) ---

def get_discovery_state(source_name):
    """Gets the next page to scrape."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT last_page_scraped FROM discovery_state WHERE source_name = %s", (source_name,))
            row = cur.fetchone()
            return row['last_page_scraped'] if row else 0
    finally:
        conn.close()

def update_discovery_state(source_name, page_number):
    """Updates the bookmark."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO discovery_state (source_name, last_page_scraped) 
                VALUES (%s, %s)
                ON CONFLICT (source_name) DO UPDATE SET 
                last_page_scraped = EXCLUDED.last_page_scraped,
                updated_at = NOW()
                """,
                (source_name, page_number)
            )
        conn.commit()
    finally:
        conn.close()

# --- System Utils ---

def log_thought(agent_name: str, message: str, visual_context: str = None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_logs (agent_name, message, visual_context_url) VALUES (%s, %s, %s)",
                (agent_name, message, visual_context)
            )
        conn.commit()
    finally:
        conn.close()

def get_system_status():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM system_config WHERE key = 'status'")
            row = cur.fetchone()
            return row['value'] if row else 'STOPPED'
    finally:
        conn.close()

def set_system_status(status):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO system_config (key, value) VALUES ('status', %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (status,)
            )
        conn.commit()
    finally:
        conn.close()