import os
import asyncio
import logging
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Import the Database Logic
from modules.db import set_system_status, get_system_status, get_connection

# Load Environment
load_dotenv()

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handshake command."""
    await update.message.reply_text(
        "🏛️ **Igbo Archives Curator** is Online.\n"
        "Commands:\n"
        "🚀 /run - Start the Agents\n"
        "🛑 /stop - Pause everything\n"
        "📡 /status - Check system state"
    )

async def run_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The Start Button."""
    set_system_status("RUNNING")
    await update.message.reply_text("🚀 **System STARTED**.\nThe Orchestrator is now polling the queue.")

async def stop_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The Stop Button."""
    set_system_status("STOPPED")
    await update.message.reply_text("🛑 **System STOPPED**.\nAgents will finish their current task and halt.")

async def status_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status Report."""
    state = get_system_status()
    
    # Get Queue Stats
    conn = get_connection()
    stats_msg = ""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status, COUNT(*) FROM artifact_queue GROUP BY status")
            rows = cur.fetchall()
            stats_msg = "\n".join([f"- {row['status']}: {row['count']}" for row in rows])
    finally:
        conn.close()

    await update.message.reply_text(
        f"📡 **Status:** {state}\n\n"
        f"📊 **Queue Metrics:**\n{stats_msg if stats_msg else '- Queue Empty'}"
    )

# --- Background Worker Launcher ---

def start_worker():
    """Run main.py loop in a separate thread."""
    import main
    asyncio.run(main.main())

# --- Main Execution ---

if __name__ == '__main__':
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        print("❌ Error: TELEGRAM_TOKEN not found.")
        exit(1)

    # 1. Start the Worker Thread (The Agent Loop)
    # This runs main.py alongside the bot
    worker_thread = threading.Thread(target=start_worker, daemon=True)
    worker_thread.start()

    # 2. Start the Telegram Bot (Webhook Mode for Render)
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("run", run_agent))
    app.add_handler(CommandHandler("stop", stop_agent))
    app.add_handler(CommandHandler("status", status_check))

    PORT = int(os.environ.get('PORT', '8443'))
    HOOK_URL = os.getenv("WEBHOOK_URL")
    
    if HOOK_URL:
        print(f"🌍 Starting Webhook on Port {PORT}...")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{HOOK_URL}/{TOKEN}"
        )
    else:
        print("⚠️ WEBHOOK_URL not set. Running in Polling mode (Local Dev).")
        app.run_polling()