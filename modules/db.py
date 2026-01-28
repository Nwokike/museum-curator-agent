import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Neon Connection String
DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Establishes a connection to the Neon Postgres DB."""
    if not DB_URL:
        raise ValueError("❌ DATABASE_URL missing in .env")
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def init_db():
    """
    verifies connection to the cloud database.
    (Tables are created via the SQL script you ran in root, so we just check access here).
    """
    try:
        conn = get_connection()
        conn.close()
        print("[DB] ✅ Connected to Neon Postgres.")
    except Exception as e:
        print(f"[DB] ⚠️ Connection Failed: {e}")

def log_thought(agent_name: str, message: str, visual_context: str = None):
    """
    Writes to the Neural Feed (agent_logs).
    Used by the Dashboard/Telegram to show what the bot is thinking.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_logs (agent_name, message, visual_context_url) 
                VALUES (%s, %s, %s)
                """,
                (agent_name, message, visual_context)
            )
        conn.commit()
    except Exception as e:
        print(f"[DB Log Error] {e}")
    finally:
        conn.close()

def get_config(key: str):
    """
    Reads from 'system_config' table. 
    Used for the Master Switch (RUNNING/STOPPED).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM system_config WHERE key = %s", (key,))
            row = cur.fetchone()
            return row['value'] if row else None
    except Exception as e:
        print(f"[DB Config Error] {e}")
        return None
    finally:
        conn.close()

def save_config(key: str, value: str):
    """
    Updates 'system_config'.
    Used by Telegram/Dashboard to Start or Stop the bot.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO system_config (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, value)
            )
        conn.commit()
    except Exception as e:
        print(f"[DB Config Save Error] {e}")
    finally:
        conn.close()