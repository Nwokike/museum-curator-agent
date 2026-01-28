-- 1. System Control (The Kill Switch)
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT INTO system_config (key, value) VALUES ('status', 'STOPPED') 
ON CONFLICT (key) DO NOTHING;

-- 2. The Artifact Queue (Workload Management)
-- Tracks the URL discovery status.
CREATE TABLE IF NOT EXISTS artifact_queue (
    id TEXT PRIMARY KEY,              -- e.g. 'PRM_1904.23.1'
    url TEXT UNIQUE NOT NULL,         -- The original museum URL
    status TEXT DEFAULT 'PENDING',    -- PENDING -> ANALYZED -> RESEARCHED -> APPROVED -> ARCHIVED -> REJECTED
    museum_name TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. The Master Archive Record (The Metadata)
-- Stores the strict fields required by the Igbo Archives platform.
CREATE TABLE IF NOT EXISTS archives (
    id TEXT PRIMARY KEY REFERENCES artifact_queue(id),
    
    -- Identity
    accession_number TEXT,            -- Museum's internal ID
    original_url TEXT NOT NULL,       -- Link to source
    copyright_holder TEXT,            -- e.g. "British Museum"
    
    -- Classification
    title TEXT,
    archive_type TEXT DEFAULT 'Image', -- Image, Audio, Document
    category TEXT,                    -- Mask, Statue, Currency
    
    -- Provenance & History
    original_author TEXT,             -- Creator/Photographer
    location TEXT,                    -- e.g. "Bende, Abia State"
    date_created TEXT,                -- Exact date if known
    circa_date TEXT,                  -- e.g. "c. 1901"
    
    -- Descriptions
    description_museum TEXT,          -- Raw text scraped from page
    description_ai TEXT,              -- The synthesized "Deep Description"
    
    -- External Links
    hf_dataset_url TEXT,              -- Link to your Hugging Face Dataset
    posted_to_socials BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 4. Media Assets (Multi-Image Support)
-- Allows one artifact to have Front, Side, Back, Detail images.
CREATE TABLE IF NOT EXISTS media_assets (
    id SERIAL PRIMARY KEY,
    artifact_id TEXT REFERENCES archives(id) ON DELETE CASCADE,
    
    original_image_url TEXT,          -- The raw .jpg link on the museum site
    file_type TEXT,                   -- jpg, png, etc.
    role TEXT DEFAULT 'Primary',      -- Primary, Side, Back, Detail
    
    hf_path TEXT,                     -- Path in HF Repo: data/images/PRM_123_a.jpg
    
    visual_analysis_raw TEXT,         -- The raw Gemini Vision output for THIS specific image
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. The Neural Feed (Telegram Logs)
CREATE TABLE IF NOT EXISTS agent_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    agent_name TEXT,
    message TEXT,
    visual_context_url TEXT
);

-- 6. Telegram State (Live Message Editing)
CREATE TABLE IF NOT EXISTS telegram_state (
    chat_id BIGINT PRIMARY KEY,
    status_message_id INT,
    last_update TIMESTAMP DEFAULT NOW()
);