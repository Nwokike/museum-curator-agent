import asyncio
import json
from modules.db import get_connection, log_thought
from modules.browser import browser_instance

# --- Scout Tools ---

async def add_url_to_queue(url: str, museum_name: str) -> str:
    """
    Adds a found object URL to the database.
    Returns: "ADDED" or "DUPLICATE".
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Check for existing
            cur.execute("SELECT id FROM artifact_queue WHERE url = %s", (url,))
            if cur.fetchone():
                return "DUPLICATE"
            
            # Create a simple deterministic ID
            import hashlib
            obj_id = f"{museum_name}_{hashlib.md5(url.encode()).hexdigest()[:8]}"
            
            cur.execute(
                """
                INSERT INTO artifact_queue (id, url, status, museum_name)
                VALUES (%s, %s, 'PENDING', %s)
                """,
                (obj_id, url, museum_name)
            )
        conn.commit()
        log_thought("Tool", f"Queued {url}", visual_context=None)
        return f"ADDED ID: {obj_id}"
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        conn.close()

# --- Vision Tools ---

async def capture_page_content(url: str) -> str:
    """
    Navigates to the URL and returns a simplified HTML snapshot for the Scout.
    """
    if not browser_instance.page:
        await browser_instance.launch()
    
    try:
        page = browser_instance.page
        await page.goto(url, timeout=60000)
        await asyncio.sleep(5) # Wait for dynamic load
        
        # Return specific container text to save tokens
        content = await page.evaluate("""() => {
            return document.body.innerText.substring(0, 20000); 
        }""")
        return content
    except Exception as e:
        return f"BROWSER_ERROR: {e}"

async def save_artifact_data(id: str, title: str, metadata: dict) -> str:
    """
    Saves extracted JSON data to the 'archives' table.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO archives (id, title, metadata)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE 
                SET title = EXCLUDED.title, metadata = EXCLUDED.metadata
                """,
                (id, title, json.dumps(metadata))
            )
            # Update Queue Status
            cur.execute("UPDATE artifact_queue SET status='SCANNED' WHERE id = %s", (id,))
        conn.commit()
        return "SUCCESS"
    except Exception as e:
        return f"DB_ERROR: {e}"
    finally:
        conn.close()

# --- Historian Tools ---

async def google_search_tool(query: str) -> str:
    """
    Performs a search for cultural context.
    (For now, returns a mock to save API calls in development).
    """
    log_thought("Tool", f"Searching Google: {query}")
    return f"SIMULATED_RESULT: '{query}' is a significant Igbo artifact used in..."

async def finalize_archive_entry(id: str, description_ai: str) -> str:
    """
    Writes the final AI description and marks as RESEARCHED.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE archives SET description_ai = %s WHERE id = %s",
                (description_ai, id)
            )
            cur.execute("UPDATE artifact_queue SET status='RESEARCHED' WHERE id = %s", (id,))
        conn.commit()
        return "ARCHIVED"
    except Exception as e:
        return f"DB_ERROR: {e}"
    finally:
        conn.close()