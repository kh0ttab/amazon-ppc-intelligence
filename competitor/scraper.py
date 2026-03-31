"""Competitor keyword scraper for Amazon search results."""

import logging
import random
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

MARKETPLACE_DOMAINS = {
    "US": "www.amazon.com",
    "UK": "www.amazon.co.uk",
    "DE": "www.amazon.de",
    "FR": "www.amazon.fr",
    "IT": "www.amazon.it",
    "ES": "www.amazon.es",
    "CA": "www.amazon.ca",
    "AU": "www.amazon.com.au",
    "IN": "www.amazon.in",
    "JP": "www.amazon.co.jp",
}


class CompetitorScraper:
    """Scrape Amazon search results for competitor analysis."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.marketplace = self.config.get("marketplace", "US")
        self.domain = MARKETPLACE_DOMAINS.get(self.marketplace, "www.amazon.com")
        self.max_results = self.config.get("max_scrape_results", 10)
        self.session = requests.Session()

    def _get_headers(self) -> dict:
        """Get request headers with a random user agent."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
        }

    def search_keyword(self, keyword: str) -> dict:
        """Search Amazon for a keyword and extract competitor data.

        Returns dict with organic results, sponsored results, and metadata.
        """
        url = f"https://{self.domain}/s"
        params = {"k": keyword, "ref": "nb_sb_noss"}

        console.print(f"[dim]Searching Amazon for: '{keyword}'...[/dim]")

        try:
            response = self.session.get(
                url, params=params, headers=self._get_headers(), timeout=15
            )
            response.raise_for_status()
        except requests.RequestException as e:
            console.print(f"[red]Scraping failed: {e}[/red]")
            console.print("[yellow]Tip: Amazon may be blocking automated requests. "
                          "Try again later or use a VPN.[/yellow]")
            logger.error(f"Scrape failed for '{keyword}': {e}")
            return {"organic": [], "sponsored": [], "keyword": keyword, "error": str(e)}

        soup = BeautifulSoup(response.text, "html.parser")
        organic_results = []
        sponsored_results = []

        # Parse search result items
        items = soup.select('[data-component-type="s-search-result"]')

        for i, item in enumerate(items[:self.max_results * 2]):
            try:
                result = self._parse_result_item(item, i + 1)
                if result:
                    if result.get("sponsored"):
                        sponsored_results.append(result)
                    else:
                        if len(organic_results) < self.max_results:
                            organic_results.append(result)
            except Exception as e:
                logger.debug(f"Failed to parse result item {i}: {e}")
                continue

        logger.info(
            f"Scraped '{keyword}': {len(organic_results)} organic, "
            f"{len(sponsored_results)} sponsored results"
        )

        return {
            "keyword": keyword,
            "organic": organic_results,
            "sponsored": sponsored_results,
            "total_results": len(items),
            "error": None,
        }

    def _parse_result_item(self, item, position: int) -> Optional[dict]:
        """Parse a single search result item."""
        result = {"position": position}

        # Check if sponsored
        sponsored_tag = item.select_one('[data-component-type="sp-sponsored-result"]')
        sponsored_text = item.find(string=re.compile(r"Sponsored|Ad", re.I))
        result["sponsored"] = sponsored_tag is not None or sponsored_text is not None

        # Title
        title_elem = item.select_one("h2 a span") or item.select_one("h2 span")
        result["title"] = title_elem.get_text(strip=True) if title_elem else "N/A"

        # ASIN
        result["asin"] = item.get("data-asin", "N/A")

        # Price
        price_elem = item.select_one(".a-price .a-offscreen")
        result["price"] = price_elem.get_text(strip=True) if price_elem else "N/A"

        # Rating
        rating_elem = item.select_one(".a-icon-alt")
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            match = re.search(r"([\d.]+)", rating_text)
            result["rating"] = float(match.group(1)) if match else 0
        else:
            result["rating"] = 0

        # Review count
        review_elem = item.select_one('[aria-label*="stars"] + span') or item.select_one(".a-size-small .a-link-normal")
        if review_elem:
            review_text = review_elem.get_text(strip=True).replace(",", "")
            match = re.search(r"([\d,]+)", review_text)
            result["reviews"] = int(match.group(1).replace(",", "")) if match else 0
        else:
            result["reviews"] = 0

        # BSR (usually not on search page but try)
        result["bsr"] = "N/A"

        return result if result["title"] != "N/A" else None

    def extract_keywords_from_titles(self, results: list[dict]) -> list[str]:
        """Extract keyword phrases from competitor listing titles using NLP."""
        try:
            import nltk
            try:
                nltk.data.find("tokenizers/punkt_tab")
            except LookupError:
                nltk.download("punkt_tab", quiet=True)
            try:
                nltk.data.find("taggers/averaged_perceptron_tagger_eng")
            except LookupError:
                nltk.download("averaged_perceptron_tagger_eng", quiet=True)

            all_keywords = []
            for result in results:
                title = result.get("title", "")
                tokens = nltk.word_tokenize(title.lower())
                tagged = nltk.pos_tag(tokens)

                # Extract noun phrases (NN, NNS, NNP, JJ+NN)
                keywords = []
                current_phrase = []
                for word, tag in tagged:
                    if tag.startswith(("NN", "JJ", "VBG")):
                        current_phrase.append(word)
                    else:
                        if current_phrase:
                            phrase = " ".join(current_phrase)
                            if len(phrase) > 2:
                                keywords.append(phrase)
                            current_phrase = []
                if current_phrase:
                    phrase = " ".join(current_phrase)
                    if len(phrase) > 2:
                        keywords.append(phrase)

                all_keywords.extend(keywords)

            # Deduplicate and count
            from collections import Counter
            keyword_counts = Counter(all_keywords)
            return [kw for kw, _ in keyword_counts.most_common(50)]

        except ImportError:
            # Fallback: simple word extraction
            words = set()
            stop_words = {"the", "a", "an", "and", "or", "for", "with", "in", "on", "to", "of", "is", "by", "at"}
            for result in results:
                title = result.get("title", "").lower()
                title_words = re.findall(r"\b[a-z]{3,}\b", title)
                words.update(w for w in title_words if w not in stop_words)
            return list(words)[:50]

    def compare_keywords(
        self,
        competitor_keywords: list[str],
        your_keywords: list[str],
    ) -> dict:
        """Compare competitor keywords vs your campaign keywords.

        Returns GAP, SHARED, and UNIQUE keyword lists.
        """
        comp_set = set(k.lower().strip() for k in competitor_keywords)
        your_set = set(k.lower().strip() for k in your_keywords)

        gap = sorted(comp_set - your_set)
        shared = sorted(comp_set & your_set)
        unique = sorted(your_set - comp_set)

        return {
            "gap": gap,
            "shared": shared,
            "unique": unique,
            "gap_count": len(gap),
            "shared_count": len(shared),
            "unique_count": len(unique),
        }

    def display_search_results(self, search_data: dict) -> None:
        """Display search results in a rich table."""
        if search_data.get("error"):
            console.print(f"[red]Search failed: {search_data['error']}[/red]")
            return

        # Organic results
        if search_data["organic"]:
            table = Table(
                title=f"Organic Results for '{search_data['keyword']}'",
                show_lines=True,
            )
            table.add_column("#", width=4)
            table.add_column("Title", style="cyan", max_width=45)
            table.add_column("ASIN", style="dim")
            table.add_column("Price", justify="right")
            table.add_column("Rating", justify="right")
            table.add_column("Reviews", justify="right")

            for r in search_data["organic"]:
                rating_color = "green" if r["rating"] >= 4.0 else "yellow" if r["rating"] >= 3.0 else "red"
                table.add_row(
                    str(r["position"]),
                    r["title"][:45],
                    r["asin"],
                    r["price"],
                    f"[{rating_color}]{r['rating']:.1f}[/{rating_color}]",
                    f"{r['reviews']:,}",
                )
            console.print(table)

        # Sponsored results
        if search_data["sponsored"]:
            sp_table = Table(title="Sponsored Positions", show_lines=True)
            sp_table.add_column("Pos", width=4)
            sp_table.add_column("Title", style="yellow", max_width=45)
            sp_table.add_column("ASIN", style="dim")
            sp_table.add_column("Price", justify="right")

            for r in search_data["sponsored"]:
                sp_table.add_row(
                    str(r["position"]), r["title"][:45], r["asin"], r["price"]
                )
            console.print(sp_table)

    def display_keyword_comparison(self, comparison: dict) -> None:
        """Display keyword gap analysis."""
        # Summary
        console.print(Panel(
            f"[green]GAP (missing):[/green] {comparison['gap_count']}  |  "
            f"[cyan]SHARED:[/cyan] {comparison['shared_count']}  |  "
            f"[yellow]UNIQUE (yours only):[/yellow] {comparison['unique_count']}",
            title="Keyword Comparison Summary",
            border_style="blue",
        ))

        # GAP keywords
        if comparison["gap"]:
            table = Table(title="GAP Keywords (Competitors Have, You Don't)", show_lines=True)
            table.add_column("#", width=4)
            table.add_column("Keyword", style="green")
            table.add_column("Priority", justify="center")

            for i, kw in enumerate(comparison["gap"][:25]):
                priority = "HIGH" if len(kw.split()) <= 3 else "MEDIUM"
                p_color = "red" if priority == "HIGH" else "yellow"
                table.add_row(str(i + 1), kw, f"[{p_color}]{priority}[/{p_color}]")
            console.print(table)

        # Shared keywords
        if comparison["shared"]:
            shared_list = ", ".join(comparison["shared"][:20])
            console.print(Panel(
                shared_list,
                title=f"Shared Keywords ({comparison['shared_count']})",
                border_style="cyan",
            ))
