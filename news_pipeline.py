"""Crypto news pipeline: scrape headlines -> AI picks the most neutral ones ->
download article -> AI rewrite -> AI image prompt.

Run from the command line:  python news_pipeline.py --count 1 --language English
"""

import argparse
import datetime
import os
import re

import requests
from bs4 import BeautifulSoup

try:  # optional: read settings from a local .env file
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

NEWS_URL = os.environ.get("NEWS_URL", "https://incrypted.com/en/news/")
SITE_ROOT = re.match(r"https?://[^/]+", NEWS_URL).group(0)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_ARTICLE_CHARS = 5000
OUTPUT_DIR = "output"

# a browser-like User-Agent so the website doesn't block requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

_client = None


def get_client():
    """Create the OpenAI client once; the key comes from OPENAI_API_KEY."""
    global _client
    if _client is None:
        from openai import OpenAI

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("Set OPENAI_API_KEY in .env (see .env.example)")
        _client = OpenAI()
    return _client


def ask_llm(prompt, temperature=None):
    params = {"model": OPENAI_MODEL, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None:
        params["temperature"] = temperature
    response = get_client().chat.completions.create(**params)
    return response.choices[0].message.content.strip()


# ---------- scraping ----------

def get_latest_news(limit=10):
    """Return up to `limit` latest headlines as [{'title', 'url'}]."""
    try:
        response = requests.get(NEWS_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching news: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    articles, seen = [], set()

    for article in soup.find_all("article"):
        # the first link is often an image, so look for the first link with real text
        for a in article.find_all("a"):
            title = a.get_text(strip=True)
            href = a.get("href")
            # skip empty links and short category labels like "News"
            if not title or not href or len(title) < 10:
                continue
            if href.startswith("/"):
                href = SITE_ROOT + href
            if href not in seen:
                seen.add(href)
                articles.append({"title": title, "url": href})
            break

    return articles[:limit]


def get_article_text(url):
    """Download an article and return its paragraphs as plain text."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching article text: {e}")
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    container = soup.find("article") or soup  # prefer the article body over menus/footer
    paragraphs = (p.get_text(strip=True) for p in container.find_all("p"))
    text = "\n".join(p for p in paragraphs if p)
    return text[:MAX_ARTICLE_CHARS]


# ---------- AI steps ----------

def parse_indices(reply, n_articles, count):
    """Turn an LLM reply like '3, 7' into valid 0-based indices; fall back to the first ones."""
    indices = []
    for num in re.findall(r"\d+", reply):
        idx = int(num) - 1
        if 0 <= idx < n_articles and idx not in indices:
            indices.append(idx)
    for idx in range(n_articles):  # top up if the model returned too few
        if len(indices) >= count:
            break
        if idx not in indices:
            indices.append(idx)
    return indices[:count]


def choose_best_news(articles, count=1):
    """Ask the model to pick the `count` most neutral crypto-industry headlines."""
    if not articles:
        return []
    count = max(1, min(count, len(articles)))
    titles = "\n".join(f"{i + 1}. {a['title']}" for i, a in enumerate(articles))

    prompt = f"""
You are a crypto news editor.

From the list of headlines choose the {count} MOST neutral crypto industry news.

Avoid:
politics, war, Trump, Russia, Ukraine, sanctions, conflicts.

Prefer:
exchanges, crypto platforms, startups, blockchain technology, web3.

Return ONLY the numbers, separated by commas.

HEADLINES:
{titles}
"""
    try:
        reply = ask_llm(prompt, temperature=0)
        print("AI reply:", reply)
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        reply = ""
    return [articles[i] for i in parse_indices(reply, len(articles), count)]


def rewrite_article(text, language="English"):
    if not text:
        return "No original text found to rewrite."

    prompt = f"""
You are a professional crypto journalist and editor.
Rewrite the news article below so that the core meaning, facts and key information stay fully intact,
but the structure, wording, paragraph order and presentation are significantly changed.

Requirements:
- Restructure sentences and paragraphs; you may start from a different key point.
- Preserve all important facts, numbers and events.
- Replace little-known companies with general descriptions ("a crypto company", "an analytics platform", "a major exchange").
- Globally recognized names (Bitcoin, Ethereum, Binance, etc.) may stay.
- Natural, engaging news style; avoid bureaucratic or robotic phrasing.
- Keep approximately the same length as the original.
- Write the result in {language}.

ARTICLE:
{text}
"""
    return ask_llm(prompt)


def generate_image_prompt(title, article):
    prompt = f"""
You are a prompt engineer for AI image generation.
Create a detailed prompt for a news illustration.

Rules:
- no text in the image, no logos, no brand names
- professional tech news illustration, modern fintech style
- realistic lighting, cinematic look
- suitable for crypto / blockchain news

Article title:
{title}

Article content:
{article[:1000]}

Return ONLY the image generation prompt, in English.
"""
    return ask_llm(prompt)


# ---------- pipeline ----------

def run_pipeline(count=1, language="English", candidates=10):
    """Full pipeline. Returns a list of dicts: title, url, text, image_prompt."""
    articles = get_latest_news(limit=candidates)
    if not articles:
        raise RuntimeError("No articles found: check the website layout or network connection")

    results = []
    for chosen in choose_best_news(articles, count):
        print("Selected:", chosen["title"])
        original = get_article_text(chosen["url"])
        rewritten = rewrite_article(original, language)
        results.append({
            "title": chosen["title"],
            "url": chosen["url"],
            "text": rewritten,
            "image_prompt": generate_image_prompt(chosen["title"], rewritten),
        })
    return results


def save_results(results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(OUTPUT_DIR, f"news_{stamp}.md")
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(f"# {r['title']}\n\nSource: {r['url']}\n\n{r['text']}\n\n")
            f.write(f"**Image prompt:** {r['image_prompt']}\n\n---\n\n")
    return path


def main():
    parser = argparse.ArgumentParser(description="Pick and rewrite the latest crypto news with AI")
    parser.add_argument("--count", type=int, default=1, help="how many articles to rewrite")
    parser.add_argument("--language", default="English", help="language of the rewritten text")
    args = parser.parse_args()

    print("Loading latest news...")
    results = run_pipeline(args.count, args.language)
    print("Saved to", save_results(results))


if __name__ == "__main__":
    main()
