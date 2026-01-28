import os
import asyncio
import threading
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from modules.db import set_system_status, get_connection

logging.basicConfig(level=logging.INFO)

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏛️ **Curator Online.** Use /run to start.")

async def run_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_system_status("RUNNING")
    await update.message.reply_text("🚀 **System STARTED.**")

async def stop_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_system_status("STOPPED")
    await update.message.reply_text("🛑 **System STOPPED.**")

# --- Interactive Review Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the Approve/Reject buttons."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":") # e.g., "APPROVE:PRM_123"
    action, artifact_id = data[0], data[1]
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if action == "APPROVE":
                cur.execute("UPDATE artifact_queue SET status='APPROVED' WHERE id=%s", (artifact_id,))
                new_text = f"✅ **APPROVED:** {artifact_id}\nQueued for Upload."
            elif action == "REJECT":
                cur.execute("UPDATE artifact_queue SET status='REJECTED' WHERE id=%s", (artifact_id,))
                new_text = f"❌ **REJECTED:** {artifact_id}\nDiscarded."
        conn.commit()
        
        # Edit the message to remove buttons and show result
        await query.edit_message_caption(caption=new_text)
        
    finally:
        conn.close()

# --- Launcher ---
def start_worker():
    import main
    asyncio.run(main.main())

if __name__ == '__main__':
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    # Threading the Agent Loop
    t = threading.Thread(target=start_worker, daemon=True)
    t.start()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("run", run_agent))
    app.add_handler(CommandHandler("stop", stop_agent))
    # Register the Button Handler
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Bot Polling...")
    app.run_polling()