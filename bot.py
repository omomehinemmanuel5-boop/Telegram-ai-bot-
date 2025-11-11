import os
import base64
from typing import List, Dict, Optional

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    ContextTypes,
    filters,
)

from openai import OpenAI

# ==============================
# ENV + CLIENT
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Missing API keys! Set TELEGRAM_TOKEN and OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# ==============================
# STATE
# ==============================
conversation_history: Dict[int, List[Dict]] = {}
user_settings: Dict[int, Dict] = {}
usage_stats: Dict[int, Dict] = {}

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant in Telegram. Be concise and friendly."
DEFAULT_MODEL = "gpt-4o-mini"  # works for text + vision. You can switch to gpt-4o if you have access.


def init_user(user_id: int):
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    if user_id not in user_settings:
        user_settings[user_id] = {"system_prompt": DEFAULT_SYSTEM_PROMPT, "model": DEFAULT_MODEL}
    if user_id not in usage_stats:
        usage_stats[user_id] = {"messages": 0, "tokens": 0}

# ==============================
# LLM HELPER (OpenAI only)
# ==============================
async def llm_reply_openai(
    messages: List[Dict],
    system_prompt: Optional[str] = None,
    image_base64: Optional[str] = None,
    image_mime: str = "image/jpeg",
    max_tokens: int = 700,
):
    """
    messages: list of {"role": "user"/"assistant", "content": "text"}
    image_base64: if provided, attaches a single image to the last user message
    """
    system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    oai_messages: List[Dict] = [{"role": "system", "content": system_prompt}]

    # copy text messages first
    for m in messages:
        oai_messages.append({"role": m["role"], "content": m["content"]})

    # If an image is provided, attach as content parts to the last user message
    if image_base64:
        # ensure last message is a user message; if not, create one
        if not oai_messages or oai_messages[-1]["role"] != "user":
            oai_messages.append({"role": "user", "content": ""})

        last = oai_messages[-1]
        text_part = {"type": "text", "text": last["content"] or "Describe this image."}
        data_url = f"data:{image_mime};base64,{image_base64}"
        image_part = {"type": "image_url", "image_url": {"url": data_url}}

        last["content"] = [text_part, image_part]

    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=oai_messages,
        max_tokens=max_tokens,
        temperature=0.4,
    )

    text = resp.choices[0].message.content or ""
    used_in = getattr(resp.usage, "prompt_tokens", 0)
    used_out = getattr(resp.usage, "completion_tokens", 0)
    return text, used_in, used_out


# ==============================
# COMMANDS
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    welcome = (
        "🚀 *Your AI Assistant is Ready!*\n\n"
        "I can help with:\n"
        "• Conversations\n"
        "• Image analysis\n"
        "• Inline mode\n\n"
        "*Commands:*\n"
        "/start – This message\n"
        "/reset – Clear history\n"
        "/system <text> – Custom personality\n"
        "/stats – Usage stats\n"
        "/help – Detailed help"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🔄 History cleared!")


async def set_system_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    if context.args:
        custom = " ".join(context.args)
        user_settings[user_id]["system_prompt"] = custom
        await update.message.reply_text(f"✅ Personality set!\n\n_{custom}_", parse_mode="Markdown")
    else:
        current = user_settings[user_id]["system_prompt"]
        await update.message.reply_text(
            f"*Current:*\n_{current}_\n\nChange: `/system your text`",
            parse_mode="Markdown"
        )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    s = usage_stats[user_id]
    msg = (
        "📊 *Stats*\n\n"
        f"Messages: {s.get('messages', 0)}\n"
        f"Tokens: ~{s.get('tokens', 0)}\n"
        f"History turns: {len(conversation_history[user_id])}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Help Guide*\n\n"
        "*Text:* Just chat naturally.\n"
        "*Images:* Send a photo for analysis.\n"
        "*Inline mode:* In any chat, type `@YourBotName question`.\n\n"
        "*Tips:*\n"
        "• Be specific\n"
        "• I remember short context\n"
        "• Use /reset to change topics"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ==============================
# HANDLERS
# ==============================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    await update.message.chat.send_action("typing")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        photo_base64 = base64.b64encode(photo_bytes).decode("utf-8")
        caption = update.message.caption or "What’s in this image?"

        # We keep the convo short for vision
        vision_messages = [{"role": "user", "content": caption}]

        answer, used_in, used_out = await llm_reply_openai(
            messages=vision_messages,
            system_prompt=user_settings[user_id]["system_prompt"],
            image_base64=photo_base64,
            max_tokens=600
        )

        conversation_history[user_id].append({"role": "user", "content": f"[Image] {caption}"})
        conversation_history[user_id].append({"role": "assistant", "content": answer})
        usage_stats[user_id]["messages"] += 1
        usage_stats[user_id]["tokens"] += (used_in + used_out)

        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")


async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return
    try:
        answer, _, _ = await llm_reply_openai(
            messages=[{"role": "user", "content": query}],
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            max_tokens=220
        )

        results = [
            InlineQueryResultArticle(
                id="1",
                title="Answer",
                input_message_content=InputTextMessageContent(
                    message_text=f"❓ *{query}*\n\n{answer}",
                    parse_mode="Markdown"
                ),
                description=(answer[:100] + "…") if len(answer) > 100 else answer,
            )
        ]
        await update.inline_query.answer(results, cache_time=300)
    except Exception as _:
        # swallow inline errors quietly (Telegram UX)
        return


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text or ""
    init_user(user_id)

    conversation_history[user_id].append({"role": "user", "content": user_message})
    await update.message.chat.send_action("typing")

    try:
        answer, used_in, used_out = await llm_reply_openai(
            messages=conversation_history[user_id],
            system_prompt=user_settings[user_id]["system_prompt"],
            max_tokens=700
        )

        conversation_history[user_id].append({"role": "assistant", "content": answer})
        usage_stats[user_id]["messages"] += 1
        usage_stats[user_id]["tokens"] += (used_in + used_out)

        # Trim history to last 50 turns to keep tokens low
        if len(conversation_history[user_id]) > 50:
            conversation_history[user_id] = conversation_history[user_id][-50:]

        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")


# ==============================
# MAIN
# ==============================
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("system", set_system_prompt))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(InlineQueryHandler(handle_inline_query))

    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, lambda u, c: u.message.reply_text("📎 PDF upload not supported in OpenAI-only mode yet. Send text or images.")))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot is running!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
