"""Telegram bot interface for the news pipeline.

Commands:
  /start     - help and current settings
  /settings  - choose language and number of articles (inline buttons)
  /headlines - show the latest headlines
  /news      - pick, rewrite and send articles with the current settings
"""

import asyncio
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import news_pipeline

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

LANGUAGES = {"en": "English", "uk": "Ukrainian", "ru": "Russian"}
COUNTS = [1, 2, 3]
DEFAULTS = {"language": "en", "count": 1}
TELEGRAM_LIMIT = 4096

# only these Telegram user ids may run the bot (protects your OpenAI budget)
ALLOWED_USER_IDS = {
    int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x
}


def is_allowed(update: Update) -> bool:
    return not ALLOWED_USER_IDS or update.effective_user.id in ALLOWED_USER_IDS


def get_settings(context: ContextTypes.DEFAULT_TYPE) -> dict:
    for key, value in DEFAULTS.items():
        context.user_data.setdefault(key, value)
    return context.user_data


def settings_text(s: dict) -> str:
    return f"Language: {LANGUAGES[s['language']]} · Articles: {s['count']}"


def settings_keyboard(s: dict) -> InlineKeyboardMarkup:
    mark = lambda on, label: f"✅ {label}" if on else label  # noqa: E731
    lang_row = [
        InlineKeyboardButton(mark(code == s["language"], name), callback_data=f"lang:{code}")
        for code, name in LANGUAGES.items()
    ]
    count_row = [
        InlineKeyboardButton(mark(n == s["count"], str(n)), callback_data=f"count:{n}")
        for n in COUNTS
    ]
    return InlineKeyboardMarkup([lang_row, count_row])


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list:
    """Split long text into Telegram-sized chunks, preferring paragraph breaks."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    s = get_settings(context)
    await update.message.reply_text(
        "Crypto news rewriter.\n\n"
        "/settings - language and number of articles\n"
        "/headlines - latest headlines\n"
        "/news - get rewritten articles\n\n" + settings_text(s)
    )


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    s = get_settings(context)
    await update.message.reply_text(settings_text(s), reply_markup=settings_keyboard(s))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_allowed(update):
        return
    s = get_settings(context)
    kind, value = query.data.split(":", 1)
    if kind == "lang" and value in LANGUAGES:
        s["language"] = value
    elif kind == "count" and int(value) in COUNTS:
        s["count"] = int(value)
    await query.edit_message_text(settings_text(s), reply_markup=settings_keyboard(s))


async def headlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    articles = await asyncio.to_thread(news_pipeline.get_latest_news)
    if not articles:
        await update.message.reply_text("Could not load headlines.")
        return
    lines = [f"{i + 1}. {a['title']}" for i, a in enumerate(articles)]
    await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    s = get_settings(context)
    await update.message.reply_text(f"Working on it... ({settings_text(s)})")
    try:
        # the pipeline is blocking (HTTP + OpenAI), so run it in a worker thread
        results = await asyncio.to_thread(
            news_pipeline.run_pipeline, s["count"], LANGUAGES[s["language"]]
        )
    except Exception as exc:
        logging.exception("pipeline failed")
        await update.message.reply_text(f"Error: {exc}")
        return

    for r in results:
        text = f"{r['title']}\n\n{r['text']}\n\nSource: {r['url']}\n\nImage prompt:\n{r['image_prompt']}"
        for chunk in split_message(text):
            await update.message.reply_text(chunk, disable_web_page_preview=True)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env (see .env.example)")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("headlines", headlines))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CallbackQueryHandler(on_button))
    app.run_polling()


if __name__ == "__main__":
    main()
