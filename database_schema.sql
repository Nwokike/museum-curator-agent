-- 1. System Control 
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT INTO system_config (key, value) VALUES ('status', 'STOPPED') 
ON CONFLICT (key) DO NOTHING;

-- 2. The Artifact Queue
CREATE TABLE IF NOT EXISTS artifact_queue (
    id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'PENDING',  
    museum_name TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. The Live Feed 
CREATE TABLE IF NOT EXISTS telegram_state (
    chat_id BIGINT PRIMARY KEY,
    status_message_id INT,          
    last_update TIMESTAMP DEFAULT NOW()
);