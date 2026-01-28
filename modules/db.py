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

# --- Core Write Functions for the New Schema ---

def register_artifact(id, url, museum_name):
    """Adds a new URL to the queue (Scout)."""
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
    """Saves the text metadata scraped from the page (Parser)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Upsert into archives
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
            # Update Status
            cur.execute("UPDATE artifact_queue SET status='ANALYZED' WHERE id=%s", (id,))
        conn.commit()
    finally:
        conn.close()

def log_media_asset(artifact_id, image_url, role="Primary"):
    """Registers an image file found for an artifact."""
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

# ... (Keep existing log_thought, get_config, save_config functions) ...
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