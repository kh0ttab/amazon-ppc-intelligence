"""Competitor keyword scraper."""

import random
import re
from typing import Optional
import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def search_amazon(keyword: str, marketplace: str = "US") -> dict:
    domains = {"US": "www.amazon.com", "UK": "www.amazon.co.uk", "DE": "www.amazon.de", "CA": "www.amazon.ca"}
    domain = domains.get(marketplace, "www.amazon.com")

    try:
        resp = requests.get(
            f"https://{domain}/s",
            params={"k": keyword},
            headers={"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"organic": [], "sponsored": [], "keyword": keyword, "error": str(e)}

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select('[data-component-type="s-search-result"]')
    organic, sponsored = [], []

    for i, item in enumerate(items[:20]):
        try:
            title_el = item.select_one("h2 a span") or item.select_one("h2 span")
            title = title_el.get_text(strip=True) if title_el else "N/A"
            asin = item.get("data-asin", "")
            price_el = item.select_one(".a-price .a-offscreen")
            price = price_el.get_text(strip=True) if price_el else ""

            is_sponsored = item.select_one('[data-component-type="sp-sponsored-result"]') is not None

            entry = {"position": i + 1, "title": title, "asin": asin, "price": price, "sponsored": is_sponsored}

            if is_sponsored:
                sponsored.append(entry)
            elif len(organic) < 10:
                organic.append(entry)
        except Exception:
            continue

    return {"organic": organic, "sponsored": sponsored, "keyword": keyword, "error": None}


def extract_keywords(results: list[dict]) -> list[str]:
    stop = {"the", "a", "an", "and", "or", "for", "with", "in", "on", "to", "of", "is", "by", "at"}
    words: dict[str, int] = {}
    for r in results:
        title = r.get("title", "").lower()
        for w in re.findall(r"\b[a-z]{3,}\b", title):
            if w not in stop:
                words[w] = words.get(w, 0) + 1
    return [w for w, _ in sorted(words.items(), key=lambda x: x[1], reverse=True)][:50]


def compare_keywords(competitor_kws: list[str], your_kws: list[str]) -> dict:
    comp = set(k.lower() for k in competitor_kws)
    yours = set(k.lower() for k in your_kws)
    return {
        "gap": sorted(comp - yours),
        "shared": sorted(comp & yours),
        "unique": sorted(yours - comp),
    }
