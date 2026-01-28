-- 1. System Control (The Kill Switch)
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT INTO system_config (key, value) VALUES ('status', 'STOPPED') 
ON CONFLICT (key) DO NOTHING;

-- 2. The Artifact Queue (Workload Management)
CREATE TABLE IF NOT EXISTS artifact_queue (
    id TEXT PRIMARY KEY,              
    url TEXT UNIQUE NOT NULL,         
    status TEXT DEFAULT 'PENDING',    
    museum_name TEXT,
    retry_count INT DEFAULT 0,
    last_error TEXT,                  -- NEW: Tracks the reason for failure
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. The Master Archive Record (Dublin Core Standard)
CREATE TABLE IF NOT EXISTS archives (
    id TEXT PRIMARY KEY REFERENCES artifact_queue(id),
    
    -- Identity & Rights (DC: Identifier, Rights)
    accession_number TEXT,            
    original_url TEXT NOT NULL,       
    rights_holder TEXT,               
    
    -- Description (DC: Title, Type, Subject)
    title TEXT,
    type TEXT DEFAULT 'Physical Object', 
    subject TEXT,                     
    
    -- Provenance (DC: Creator, Spatial, Temporal)
    creator TEXT,                     
    spatial_coverage TEXT,            
    temporal_coverage TEXT,           
    
    -- Content (DC: Description)
    description_museum TEXT,          
    description_ai TEXT,              
    
    -- Management
    posted_to_socials BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 4. Media Assets (Multi-View Support)
CREATE TABLE IF NOT EXISTS media_assets (
    id SERIAL PRIMARY KEY,
    artifact_id TEXT REFERENCES archives(id) ON DELETE CASCADE,
    original_image_url TEXT,          
    file_type TEXT,                   
    role TEXT DEFAULT 'Primary',      
    hf_path TEXT,                     
    visual_analysis_raw TEXT,         
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. Agent Logs
CREATE TABLE IF NOT EXISTS agent_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    agent_name TEXT,
    message TEXT,
    visual_context_url TEXT
);

-- 6. Telegram State
CREATE TABLE IF NOT EXISTS telegram_state (
    chat_id BIGINT PRIMARY KEY,
    status_message_id INT,
    last_update TIMESTAMP DEFAULT NOW()
);

-- 7. Discovery State (Browser Context)
CREATE TABLE IF NOT EXISTS discovery_state (
    source_name TEXT PRIMARY KEY,     
    last_page_scraped INT DEFAULT 0,
    current_search_url TEXT,          
    is_finished BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT NOW()
);