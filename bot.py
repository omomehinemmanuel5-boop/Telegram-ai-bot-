# Bot.py
# Telegram bot (OpenAI only) — python-telegram-bot v21 (async)

import os
import logging
from typing import List, Dict

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ---- OpenAI (Responses API) ----
from openai import OpenAI
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---- Config / State ----
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN or not os.getenv("OPENAI_API_KEY"):
    raise ValueError("Missing TELEGRAM_TOKEN or OPENAI_API_KEY")

DEFAULT_SYSTEM = "You are a helpful AI assistant in Telegram. Be concise and friendly."
DEFAULT_MODEL  = "gpt-4.1-mini"  # change to gpt-4.1 or o4-mini if you have access

# in-memory state (good enough for personal bot)
HISTORY: Dict[int, List[Dict[str, str]]] = {}
SETTINGS: Dict[int, Dict[str, str]] = {}
STATS:    Dict[int, Dict[str, int]] = {}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lex-telegram")

def init_user(user_id: int):
    HISTORY.setdefault(user_id, [])
    SETTINGS.setdefault(user_id, {"system": DEFAULT_SYSTEM, "model": DEFAULT_MODEL})
    STATS.setdefault(user_id, {"messages": 0, "in": 0, "out": 0})

# ---- LLM helper (OpenAI Responses API) ----
async def llm_reply(messages: List[Dict[str, str]], system: str, max_tokens: int = 800):
    # Pack conversation into a single user message (simple + works with Responses API)
    transcript = [f"[{m['role'].capitalize()}]\n{m['content']}" for m in messages]
    prompt = f"[System]\n{system}\n\n" + "\n\n".join(transcript)

    resp = openai_client.responses.create(
        model=SETTINGS[messages and 0 or 0 if False else list(SETTINGS.values())[0]]["model"]
        if SETTINGS else DEFAULT_MODEL,
        input=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        max_output_tokens=max_tokens,
    )

    text = ""
    if resp.output and hasattr(resp.output[0], "content"):
        for chunk in resp.output[0].content:
            if chunk["type"] == "output_text":
                text += chunk["text"]

    usage = getattr(resp, "usage", {}) or {}
    return text or "I couldn't generate a reply.", usage.get("input_tokens", 0), usage.get("output_tokens", 0)

# ---- Commands ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    msg = (
        "🚀 *Lex OpenAI Telegram Bot*\n\n"
        "Commands:\n"
        "/start – help message\n"
        "/reset – clear history\n"
        "/system <text> – set personality\n"
        "/stats – usage\n"
        "/help – tips"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    HISTORY[user_id] = []
    await update.message.reply_text("🔄 History cleared.")

async def set_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    if context.args:
        SETTINGS[user_id]["system"] = " ".join(context.args)
        await update.message.reply_text("✅ System prompt updated.")
    else:
        await update.message.reply_text(f"*Current:*\n{SETTINGS[user_id]['system']}", parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    s = STATS[user_id]
    await update.message.reply_text(
        f"📊 Stats\nMessages: {s['messages']}\nTokens in: {s['in']}\nTokens out: {s['out']}"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Tips:\n• Be specific\n• I remember context\n• Use /reset to change topics"
    )

# ---- Text handler ----
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    user_text = update.message.text

    HISTORY[user_id].append({"role": "user", "content": user_text})

    try:
        answer, used_in, used_out = await llm_reply(
            HISTORY[user_id], SETTINGS[user_id]["system"], max_tokens=800
        )
        HISTORY[user_id].append({"role": "assistant", "content": answer})

        # keep last 40 turns to control cost
        if len(HISTORY[user_id]) > 80:
            HISTORY[user_id] = HISTORY[user_id][-80:]

        # stats
        STATS[user_id]["messages"] += 1
        STATS[user_id]["in"] += used_in
        STATS[user_id]["out"] += used_out

        await update.message.reply_text(answer)
    except Exception as e:
        log.exception("Reply error")
        await update.message.reply_text(f"⚠️ Error: {e}")

# ---- Main ----
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("system", set_system))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🚀 Bot is running (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
