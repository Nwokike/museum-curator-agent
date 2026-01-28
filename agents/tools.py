import os
import time
import json
import shutil
import requests
import hashlib
import asyncio
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from huggingface_hub import HfApi, create_repo
from duckduckgo_search import DDGS
from google.genai import types

from modules.db import (
    get_connection, log_thought, register_artifact, 
    save_metadata_draft, log_media_asset
)
from modules.browser import browser_instance
from modules.llm_bridge import GeminiFallbackClient

# Configuration
TEMP_DOWNLOAD_DIR = "data/temp_downloads"
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID") 

# Rate Limiting State
LAST_ACCESS = {}
DOMAIN_DELAY = 5.0 # Seconds between requests to the same domain

# Initialize Intelligence for Scraping
extraction_model = GeminiFallbackClient()

# --- CLUSTER A: DISCOVERY & NAVIGATION ---

async def visit_page_tool(url: str) -> str:
    """Navigates the browser to a URL with strict Politeness Rate Limiting."""
    try:
        # Politeness Check
        domain = urlparse(url).netloc
        if domain in LAST_ACCESS:
            elapsed = time.time() - LAST_ACCESS[domain]
            if elapsed < DOMAIN_DELAY:
                wait_time = DOMAIN_DELAY - elapsed
                print(f"[Politeness] ⏳ Waiting {wait_time:.2f}s for {domain}...")
                await asyncio.sleep(wait_time)
        
        # Update Lock
        LAST_ACCESS[domain] = time.time()

        if not browser_instance.page: await browser_instance.launch()
        # Increased timeout for museum archives which are often slow
        await browser_instance.page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        return f"SUCCESS: Visited {url}"
    except Exception as e: return f"ERROR: {e}"

async def click_next_page_tool() -> str:
    """
    Robustly finds and clicks the 'Next' pagination button.
    Supports standard patterns: 'Next', '>', '›', or 'rel=next'.
    """
    if not browser_instance.page: return "ERROR: Browser inactive."
    page = browser_instance.page
    try:
        # Common Pagination Selectors
        selectors = [
            "a[rel='next']",
            "text='Next'",
            "text='next'",
            "text='›'",
            "text='»'",
            ".pager-next a",
            ".next a"
        ]
        
        for sel in selectors:
            if await page.locator(sel).first.is_visible():
                await page.locator(sel).first.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(3) # Politeness wait
                return f"SUCCESS: Navigated to {page.url}"
                
        return "END_OF_ARCHIVE: No next button found."
    except Exception as e:
        return f"ERROR: Navigation failed - {e}"

async def extract_links_tool(base_url: str, selector: str = "a") -> str:
    """Finds artifact links, strictly filtering out nav/noise."""
    if not browser_instance.page: return "ERROR: Browser inactive."
    try:
        html = await browser_instance.page.content()
        soup = BeautifulSoup(html, "html.parser")
        links = [urljoin(base_url, a['href']) for a in soup.select(selector) if a.get('href')]
        
        # Strict Noise Filter
        valid_links = []
        for l in list(set(links)):
            if any(x in l for x in ["search", "login", "user", "contact", "about", "policy"]): continue
            # Heuristic: Object pages often have numbers or specific keywords
            if any(x in l for x in ["collection-object", "objects", "item", "record"]):
                valid_links.append(l)
        
        return json.dumps(valid_links[:20]) # Limit batch size
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
    # Create deterministic ID
    obj_id = f"{museum_name}_{hashlib.md5(url.encode()).hexdigest()[:8]}"
    register_artifact(obj_id, url, museum_name)
    return f"QUEUED: {obj_id}"

# --- CLUSTER B: COGNITIVE EXTRACTION (LLM + VISION) ---

async def _call_llm_extractor(contents):
    """Helper to send content (Text or Image) to Gemini."""
    response_text = ""
    try:
        async for chunk in extraction_model.generate_content_async(contents=contents):
            if hasattr(chunk, 'text'):
                response_text += chunk.text
            elif hasattr(chunk, 'candidates'):
                response_text += chunk.candidates[0].content.parts[0].text
    except Exception as e:
        print(f"[Tools] LLM Extraction Partial Error: {e}")
        
    return response_text

async def scrape_metadata_tool(url: str) -> str:
    """
    Cognitive Scraper: Uses LLM to parse HTML, with Visual Fallback.
    """
    if not browser_instance.page: return "ERROR: Browser inactive."
    
    try:
        # 1. Get Cleaned HTML
        raw_html = await browser_instance.page.content()
        soup = BeautifulSoup(raw_html, "html.parser")
        
        # Remove noise to save tokens
        for tag in soup(['script', 'style', 'nav', 'footer', 'iframe', 'svg']):
            tag.decompose()
        
        # Extract potential images for the LLM to choose from
        img_tags = soup.find_all('img')
        img_candidates = [urljoin(url, img['src']) for img in img_tags if img.get('src') and len(img.get('src')) > 10]
        
        clean_text = soup.get_text(separator='\n', strip=True)[:25000] # Limit context
        
        # 2. Construct Prompt for Text Extraction
        prompt_text = f"""
        You are a Museum Archivist. Extract the Dublin Core metadata from this webpage text.
        
        URL: {url}
        IMAGE CANDIDATES: {json.dumps(img_candidates[:10])}
        
        PAGE TEXT:
        {clean_text}
        
        INSTRUCTIONS:
        1. Extract the following fields: 'title', 'accession_number', 'creator', 'subject' (category), 'spatial' (location), 'temporal' (date), 'desc' (description).
        2. Identify the 'media_urls' list. Select the high-resolution object images from the candidates. Ignore icons/logos.
        3. Return ONLY valid JSON. No markdown formatting.
        """
        
        print(f"[Scraper] Attempting Text Extraction for {url}...")
        json_response = await _call_llm_extractor([types.Part(text=prompt_text)])
        
        # 3. Validation & Visual Fallback
        is_valid = False
        data = {}
        
        try:
            # Clean generic markdown block wrappers if present
            clean_json = json_response.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            
            # Simple validation: If title is missing or "Unknown", try vision
            if data.get("title") and data.get("title") != "Unknown" and len(data.get("title")) > 3:
                is_valid = True
        except:
            pass
            
        if not is_valid:
            print(f"[Scraper] Text Extraction Weak. Engaging Gemini Vision...")
            
            # Take Screenshot
            screenshot_bytes = await browser_instance.page.screenshot(type='jpeg', quality=80)
            
            vision_prompt = """
            Read this museum object page. Extract the metadata as JSON.
            Keys: title, accession_number, creator, subject, spatial, temporal, desc.
            Also, strictly output 'media_urls': [] as an empty list (I will handle images separately).
            Return ONLY JSON.
            """
            
            vision_response = await _call_llm_extractor([
                types.Part(text=vision_prompt),
                types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=screenshot_bytes))
            ])
            
            try:
                clean_json_vis = vision_response.replace("```json", "").replace("```", "").strip()
                vision_data = json.loads(clean_json_vis)
                # Merge: Prefer Vision for text, but keep Text-extracted images if any
                vision_data["media_urls"] = data.get("media_urls", [])
                data = vision_data
                data["original_url"] = url # Ensure URL is present
            except Exception as e:
                return f"ERROR: Vision Parsing Failed - {e}"

        # Ensure required keys exist
        data["original_url"] = url
        if "media_urls" not in data: data["media_urls"] = []
        
        return json.dumps(data)

    except Exception as e:
        return f"ERROR: Critical Scraper Fail - {e}"

async def save_draft_tool(artifact_id: str, metadata_json: str) -> str:
    """Saves parsed metadata to the DB (Dublin Core Mapping)."""
    conn = get_connection()
    try:
        data = json.loads(metadata_json)
        
        # MAPPING: Scraper Keys -> DB Columns (Dublin Core)
        # Defaults
        db_record = {
            "id": artifact_id,
            "url": data.get("original_url", ""),
            "acc_num": data.get("acc_num", data.get("accession_number", "Unknown")),
            "title": data.get("title", "Untitled"),
            "subject": data.get("subject", data.get("cat", "Uncategorized")),
            "creator": data.get("creator", data.get("author", "Unknown")),
            "spatial": data.get("spatial", data.get("loc", "Unknown")),
            "temporal": data.get("temporal", data.get("date", "Unknown")),
            "rights": "Unknown",
            "desc": data.get("desc", data.get("description", ""))
        }

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO archives (
                    id, original_url, accession_number, title, 
                    subject, creator, spatial_coverage, temporal_coverage, 
                    rights_holder, description_museum
                ) VALUES (
                    %(id)s, %(url)s, %(acc_num)s, %(title)s, 
                    %(subject)s, %(creator)s, %(spatial)s, %(temporal)s, 
                    %(rights)s, %(desc)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description_museum = EXCLUDED.description_museum
                """,
                db_record
            )
            # We don't change status to ANALYZED yet, wait for images
        conn.commit()
        return "SUCCESS: Draft Saved."
    except Exception as e: 
        return f"ERROR: {e}"
    finally:
        conn.close()

async def download_image_tool(image_url: str, artifact_id: str) -> str:
    """Downloads the raw image file."""
    try:
        if not image_url: return "ERROR: Empty Image URL"
        
        r = requests.get(image_url, stream=True, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return f"ERROR: HTTP {r.status_code}"
        
        ext = ".jpg"
        if "png" in r.headers.get("Content-Type", ""): ext = ".png"
        
        # Unique filename for multi-image support
        file_hash = hashlib.md5(image_url.encode()).hexdigest()[:6]
        filename = f"{artifact_id}_{file_hash}{ext}"
        filepath = os.path.join(TEMP_DOWNLOAD_DIR, filename)
        
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(8192): f.write(chunk)
            
        log_media_asset(artifact_id, image_url, role="Primary")
        return f"SUCCESS: Saved {filename}"
    except Exception as e: return f"ERROR: {e}"

# --- CLUSTER C (Vision) ---

async def analyze_image_tool(artifact_id: str) -> str:
    """Finds ALL local files for Vision Analysis (Multi-View)."""
    files = [f for f in os.listdir(TEMP_DOWNLOAD_DIR) if f.startswith(artifact_id)]
    if not files: return "ERROR: No downloaded images found."
    
    file_paths = [os.path.join(TEMP_DOWNLOAD_DIR, f) for f in files]
    return json.dumps({"action": "analyze", "file_paths": file_paths})

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
            cur.execute("SELECT title, description_ai FROM archives WHERE id=%s", (artifact_id,))
            row = cur.fetchone()
            
        text = f"🏛️ *REVIEW REQUEST*\n\n*ID:* `{artifact_id}`\n*Title:* {row['title']}\n\n*AI Analysis:*\n{row['description_ai'][:800]}..."
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"APPROVE:{artifact_id}"},
                {"text": "❌ Reject", "callback_data": f"REJECT:{artifact_id}"}
            ]]
        }
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": ADMIN_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": json.dumps(keyboard)
        }
        
        requests.post(url, json=payload)
        return f"SUCCESS: Sent {artifact_id} to Telegram."
            
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        conn.close()

async def upload_to_hf_tool(artifact_id: str) -> str:
    """Uploads the specific artifact files to Hugging Face."""
    if not HF_TOKEN: return "ERROR: No HF Token."
    
    files = [f for f in os.listdir(TEMP_DOWNLOAD_DIR) if f.startswith(artifact_id)]
    if not files: return "ERROR: No files to upload."
    
    api = HfApi(token=HF_TOKEN)
    repo_id = "nwokikeonyeka/igbo-museum-archive" 
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