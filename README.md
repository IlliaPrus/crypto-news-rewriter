# Crypto News Rewriter

AI-assisted tool for a content team: it collects the latest crypto news, lets an
LLM pick the most neutral industry stories, rewrites them in the chosen language
and prepares a prompt for an illustration. Works from the command line or
through a Telegram bot.

Built to speed up a copywriter's daily routine at an educational academy.

## How it works

```
news site ──► scrape headlines ──► LLM picks N neutral stories ──► download article
          ──► LLM rewrite (chosen language) ──► LLM image prompt ──► Telegram / .md file
```

1. **Scraping** — `requests` + `BeautifulSoup` collect the latest headlines and
   article text.
2. **Selection** — the LLM chooses the most neutral industry news (exchanges,
   platforms, web3) and avoids politics; the answer is parsed and validated.
3. **Rewrite** — the article is restructured while keeping all facts and numbers.
4. **Image prompt** — a prompt for an AI image generator (no text, no logos).
5. **Delivery** — results are sent to Telegram or saved to `output/` with a link
   to the original source.

## Tech stack

Python · requests · BeautifulSoup · OpenAI API (gpt-4o-mini) · prompt engineering ·
python-telegram-bot · asyncio

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/<your-username>/crypto-news-rewriter.git
cd crypto-news-rewriter
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then put your keys into .env
```

| Variable | Description |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI API key |
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user ids allowed to use the bot |
| `NEWS_URL` | News list page (default: incrypted.com/en/news) |
| `OPENAI_MODEL` | Model name (default: gpt-4o-mini) |

## Usage

Command line:

```bash
python news_pipeline.py --count 2 --language Ukrainian
```

Telegram bot:

```bash
python bot.py
```

| Command | Action |
| --- | --- |
| `/settings` | Choose language (English / Ukrainian / Russian) and number of articles (1–3) |
| `/headlines` | Show the latest headlines |
| `/news` | Get rewritten articles with image prompts |

## Notes

- Scraping depends on the site's HTML layout; if it changes, update
  `get_latest_news()`.
- Each result keeps a link to the original article. Respect the source site's
  terms of use when publishing.

## License

MIT
