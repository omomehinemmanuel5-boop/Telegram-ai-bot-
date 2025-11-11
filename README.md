# Lex OpenAI Telegram Bot

A minimal Telegram bot that uses OpenAI (Responses API) with polling.

## Quick Start

1. **Create bot token**
   - In Telegram, talk to **@BotFather** → `/newbot` → copy the token.

2. **Clone or make a GitHub repo**
   - Add these files: `Bot.py`, `requirements.txt`, `Procfile`, `README.md`.

3. **Deploy on Railway**
   - Go to railway.app → New Project → Deploy from GitHub → select this repo.
   - After first build, open the service → **Variables** and add:
     - `TELEGRAM_TOKEN` = your BotFather token
     - `OPENAI_API_KEY` = your OpenAI key
   - Redeploy. You should see `🚀 Bot is running (polling)…` in **Logs**.

4. **Test**
   - Open your bot in Telegram (t.me/YourBotName) → send `/start`.

## Commands
- `/start` — help
- `/reset` — clear chat memory
- `/system <text>` — change the assistant personality
- `/stats` — show usage
- `/help` — tips

## Notes
- This build uses **polling**, which is simplest on Railway/Render.  
- If you want **Cloudflare Workers**, you’ll need a webhook + an HTTP handler (serverless). Start here only after the polling version works.
