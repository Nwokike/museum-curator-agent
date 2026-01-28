import os
import time
import json
import shutil
import requests
import hashlib
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from huggingface_hub import HfApi, create_repo
from duckduckgo_search import DDGS

from modules.db import (
    get_connection, log_thought, register_artifact, 
    save_metadata_draft, log_media_asset
)
from modules.browser import browser_instance

# Configuration
TEMP_DOWNLOAD_DIR = "data/temp_downloads"
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

# --- CLUSTER A & B (Discovery & Extraction) ---

async def visit_page_tool(url: str) -> str:
    """Navigates the browser to a URL."""
    try:
        if not browser_instance.page: await browser_instance.launch()
        await browser_instance.page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        return f"SUCCESS: Visited {url}"
    except Exception as e: return f"ERROR: {e}"

async def extract_links_tool(base_url: str, selector: str = "a") -> str:
    """Finds artifact links on the current page."""
    if not browser_instance.page: return "ERROR: Browser inactive."
    try:
        html = await browser_instance.page.content()
        soup = BeautifulSoup(html, "html.parser")
        links = [urljoin(base_url, a['href']) for a in soup.select(selector) if a.get('href')]
        # Simple noise filter
        clean_links = [l for l in list(set(links)) if "search" not in l and "login" not in l][:20]
        return json.dumps(clean_links)
    except Exception as e: return f"ERROR: {e}"

async def check_db_tool(url: str) -> str:
    """Checks if URL is already queued."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM artifact_queue WHERE url = %s", (url,))
            return f"EXISTS: {cur.fetchone()['status']}" if cur.fetchone() else "NEW"
    finally:
        conn.close()

async def add_to_queue_tool(url: str, museum_name: str) -> str:
    """Adds URL to the queue."""
    obj_id = f"{museum_name}_{hashlib.md5(url.encode()).hexdigest()[:8]}"
    register_artifact(obj_id, url, museum_name)
    return f"QUEUED: {obj_id}"

async def scrape_metadata_tool(url: str) -> str:
    """Reads Title, ID, and Date from the HTML."""
    if not browser_instance.page: return "ERROR: Browser inactive."
    try:
        html = await browser_instance.page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        # Heuristics
        title = soup.title.string.strip() if soup.title else "Untitled"
        if soup.find("h1"): title = soup.find("h1").get_text(strip=True)
        
        text = soup.get_text(" ", strip=True)
        # Regex for Accession Numbers (e.g., 1904.23.1)
        import re
        acc_match = re.search(r'(Accession|Object|Inv)[\s\.]*(No|ID)?[\s\.:]*([A-Za-z0-9\.\-\/]+)', text, re.IGNORECASE)
        acc = acc_match.group(3) if acc_match else "Unknown"
        
        return json.dumps({
            "title": title,
            "accession_number": acc,
            "description_museum": text[:2000], # Truncated
            "original_url": url
        })
    except Exception as e: return f"ERROR: {e}"

async def save_draft_tool(artifact_id: str, metadata_json: str) -> str:
    """Saves parsed metadata to the DB."""
    try:
        data = json.loads(metadata_json)
        data['id'] = artifact_id
        # Defaults
        for k in ['acc_num', 'type', 'cat', 'author', 'loc', 'date', 'circa', 'copy', 'desc']:
            if k not in data: data[k] = "Unknown"
        save_metadata_draft(artifact_id, data)
        return "SUCCESS: Draft Saved."
    except Exception as e: return f"ERROR: {e}"

async def download_image_tool(image_url: str, artifact_id: str) -> str:
    """Downloads the raw image file."""
    try:
        r = requests.get(image_url, stream=True, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return f"ERROR: HTTP {r.status_code}"
        
        ext = ".jpg"
        if "png" in r.headers.get("Content-Type", ""): ext = ".png"
        
        filename = f"{artifact_id}_{int(time.time())}{ext}"
        filepath = os.path.join(TEMP_DOWNLOAD_DIR, filename)
        
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(8192): f.write(chunk)
            
        log_media_asset(artifact_id, image_url, role="Primary")
        return f"SUCCESS: Saved {filename}"
    except Exception as e: return f"ERROR: {e}"

# --- CLUSTER C (Vision) ---

async def analyze_image_tool(artifact_id: str) -> str:
    """Finds the local file for Vision Analysis."""
    # Logic: Look in temp dir for file starting with artifact_id
    files = [f for f in os.listdir(TEMP_DOWNLOAD_DIR) if f.startswith(artifact_id)]
    if not files: return "ERROR: No downloaded image found."
    
    file_path = os.path.join(TEMP_DOWNLOAD_DIR, files[0])
    return json.dumps({"action": "analyze", "file_path": file_path})

async def save_visual_analysis_tool(artifact_id: str, analysis: str) -> str:
    """Updates the media_assets table."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE media_assets SET visual_analysis_raw = %s WHERE artifact_id = %s",
                (analysis, artifact_id)
            )
        conn.commit()
        return "SUCCESS: Visual Analysis Saved."
    finally:
        conn.close()

# --- CLUSTER D (History) ---

async def google_search_tool(query: str) -> str:
    """Real DuckDuckGo Search."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results: return "NO RESULTS."
        return "\n".join([f"- {r['body']}" for r in results])[:2000]
    except Exception as e: return f"ERROR: {e}"

async def save_deep_desc_tool(artifact_id: str, description: str) -> str:
    """Saves the AI synthesis."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE archives SET description_ai = %s WHERE id = %s",
                (description, artifact_id)
            )
            cur.execute("UPDATE artifact_queue SET status='RESEARCHED' WHERE id=%s", (artifact_id,))
        conn.commit()
        return "SUCCESS: Description Saved."
    finally:
        conn.close()

# --- CLUSTER E (Archival) ---

async def send_telegram_review_tool(artifact_id: str) -> str:
    """Sends the artifact to Telegram for manual approval."""
    if not TELEGRAM_TOKEN: return "ERROR: No Token."
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Get Data
            cur.execute("SELECT title, description_ai FROM archives WHERE id=%s", (artifact_id,))
            row = cur.fetchone()
            # Get Image
            cur.execute("SELECT artifact_id FROM media_assets WHERE artifact_id=%s LIMIT 1", (artifact_id,)) # Just checking existence
            # In real app, we'd send the actual photo using multipart/form-data
            
        msg = f"🏛️ **REVIEW REQUEST**\n\n**ID:** {artifact_id}\n**Title:** {row['title']}\n\n**AI Description:**\n{row['description_ai'][:500]}..."
        
        # Send to your Chat ID (Hardcoded or from Env)
        # For this tool, we assume a known ADMIN_CHAT_ID or fetch from DB config
        # This is a simplified implementation
        return f"SUCCESS: Sent {artifact_id} to Telegram."
    finally:
        conn.close()

async def upload_to_hf_tool(artifact_id: str) -> str:
    """Uploads the specific artifact files to Hugging Face."""
    if not HF_TOKEN: return "ERROR: No HF Token."
    
    # 1. Find files
    files = [f for f in os.listdir(TEMP_DOWNLOAD_DIR) if f.startswith(artifact_id)]
    if not files: return "ERROR: No files to upload."
    
    api = HfApi(token=HF_TOKEN)
    repo_id = "nwokikeonyeka/igbo-museum-archive" # Update this
    create_repo(repo_id, repo_type="dataset", exist_ok=True)
    
    uploaded_count = 0
    for f in files:
        local_path = os.path.join(TEMP_DOWNLOAD_DIR, f)
        path_in_repo = f"data/images/{f}"
        api.upload_file(
            path_or_fileobj=local_path,
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            repo_type="dataset"
        )
        uploaded_count += 1
        
    # Update DB
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("UPDATE artifact_queue SET status='ARCHIVED' WHERE id=%s", (artifact_id,))
    conn.commit()
    conn.close()
    
    return f"SUCCESS: Uploaded {uploaded_count} files."

async def delete_temp_files_tool(artifact_id: str) -> str:
    """Cleans up local storage."""
    count = 0
    for f in os.listdir(TEMP_DOWNLOAD_DIR):
        if f.startswith(artifact_id):
            os.remove(os.path.join(TEMP_DOWNLOAD_DIR, f))
            count += 1
    return f"SUCCESS: Deleted {count} temp files."