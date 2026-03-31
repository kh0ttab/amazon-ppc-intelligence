"""Competitor price monitor with SQLite tracking."""

import json
import logging
import random
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config, DB_DIR

logger = logging.getLogger(__name__)
console = Console()

DB_PATH = DB_DIR / "prices.db"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

MARKETPLACE_DOMAINS = {
    "US": "www.amazon.com",
    "UK": "www.amazon.co.uk",
    "DE": "www.amazon.de",
    "CA": "www.amazon.ca",
}


class PriceMonitor:
    """Track competitor prices over time using SQLite."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.marketplace = self.config.get("marketplace", "US")
        self.domain = MARKETPLACE_DOMAINS.get(self.marketplace, "www.amazon.com")
        self.alert_pct = self.config.get("competitor_price_alert_pct", 5.0)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for price tracking."""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT NOT NULL,
                title TEXT,
                price REAL,
                currency TEXT,
                timestamp TEXT NOT NULL,
                marketplace TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_asin_time ON price_history (asin, timestamp)
        """)
        conn.commit()
        conn.close()

    def fetch_price(self, asin: str) -> Optional[dict]:
        """Fetch current price for an ASIN from Amazon product page."""
        url = f"https://{self.domain}/dp/{asin}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Price fetch failed for {asin}: {e}")
            return None

        html = response.text

        # Extract price
        price = None
        price_patterns = [
            r'"priceAmount":\s*([\d.]+)',
            r'class="a-price-whole">([\d,]+)</span>.*?class="a-price-fraction">(\d+)',
            r'id="priceblock_ourprice"[^>]*>\s*\$?([\d,.]+)',
            r'class="a-offscreen">\s*\$?([\d,.]+)',
        ]

        for pattern in price_patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    if match.lastindex == 2:
                        price = float(match.group(1).replace(",", "") + "." + match.group(2))
                    else:
                        price = float(match.group(1).replace(",", ""))
                    break
                except ValueError:
                    continue

        # Extract title
        title = "N/A"
        title_match = re.search(r'id="productTitle"[^>]*>\s*(.+?)\s*</span>', html)
        if title_match:
            title = title_match.group(1).strip()[:100]

        if price is None:
            logger.warning(f"Could not extract price for {asin}")
            return None

        result = {
            "asin": asin,
            "title": title,
            "price": price,
            "currency": self.currency,
            "timestamp": datetime.now().isoformat(),
        }

        # Save to database
        self._save_price(result)
        return result

    def _save_price(self, price_data: dict):
        """Save a price data point to SQLite."""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO price_history (asin, title, price, currency, timestamp, marketplace) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                price_data["asin"],
                price_data["title"],
                price_data["price"],
                price_data["currency"],
                price_data["timestamp"],
                self.marketplace,
            ),
        )
        conn.commit()
        conn.close()

    def get_price_history(self, asin: str, days: int = 30) -> list[dict]:
        """Get price history for an ASIN from SQLite."""
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute(
            "SELECT asin, title, price, currency, timestamp FROM price_history "
            "WHERE asin = ? AND timestamp >= ? ORDER BY timestamp",
            (asin, cutoff),
        )
        rows = cursor.fetchall()
        conn.close()

        return [
            {"asin": r[0], "title": r[1], "price": r[2], "currency": r[3], "timestamp": r[4]}
            for r in rows
        ]

    def check_all_competitors(self, asins: Optional[list[str]] = None) -> list[dict]:
        """Check prices for all tracked competitor ASINs."""
        if asins is None:
            asins = self.config.get("competitor_asins", [])

        if not asins:
            console.print("[yellow]No competitor ASINs configured. Add them in Settings.[/yellow]")
            return []

        results = []
        for asin in asins:
            console.print(f"[dim]Checking {asin}...[/dim]")
            price_data = self.fetch_price(asin)
            if price_data:
                # Check for alerts
                history = self.get_price_history(asin, days=7)
                alert = self._check_price_alert(asin, price_data["price"], history)
                price_data["alert"] = alert
                results.append(price_data)

        return results

    def _check_price_alert(self, asin: str, current_price: float, history: list[dict]) -> Optional[dict]:
        """Check if price dropped significantly."""
        if len(history) < 2:
            return None

        # Get previous price (excluding the current one just saved)
        prev_prices = [h["price"] for h in history[:-1] if h["price"] > 0]
        if not prev_prices:
            return None

        avg_prev = sum(prev_prices) / len(prev_prices)
        change_pct = ((current_price - avg_prev) / avg_prev) * 100

        if change_pct < -self.alert_pct:
            return {
                "type": "PRICE_DROP",
                "previous_avg": avg_prev,
                "current": current_price,
                "change_pct": change_pct,
                "message": f"Price dropped {abs(change_pct):.1f}% "
                           f"({self.currency}{avg_prev:.2f} -> {self.currency}{current_price:.2f})",
            }
        elif change_pct > self.alert_pct:
            return {
                "type": "PRICE_INCREASE",
                "previous_avg": avg_prev,
                "current": current_price,
                "change_pct": change_pct,
                "message": f"Price increased {change_pct:.1f}% "
                           f"({self.currency}{avg_prev:.2f} -> {self.currency}{current_price:.2f})",
            }

        return None

    def display_report(self, results: list[dict]) -> None:
        """Display competitor price monitoring report."""
        c = self.currency

        if not results:
            return

        table = Table(title="Competitor Price Monitor", show_lines=True)
        table.add_column("ASIN", style="cyan")
        table.add_column("Title", max_width=35)
        table.add_column("Current Price", justify="right", style="bold")
        table.add_column("Alert", max_width=40)

        for r in results:
            alert_str = ""
            if r.get("alert"):
                alert = r["alert"]
                if alert["type"] == "PRICE_DROP":
                    alert_str = f"[red]{alert['message']}[/red]"
                elif alert["type"] == "PRICE_INCREASE":
                    alert_str = f"[green]{alert['message']}[/green]"
            else:
                alert_str = "[dim]No significant change[/dim]"

            table.add_row(
                r["asin"],
                r.get("title", "N/A")[:35],
                f"{c}{r['price']:.2f}",
                alert_str,
            )

        console.print(table)

        # Actionable alerts
        drops = [r for r in results if r.get("alert") and r["alert"]["type"] == "PRICE_DROP"]
        if drops:
            console.print(Panel(
                "\n".join(
                    f"[red]>{r['asin']}[/red]: {r['alert']['message']}\n"
                    f"  [yellow]Action: Consider temporary bid reduction until you reprice.[/yellow]"
                    for r in drops
                ),
                title="Price Drop Alerts",
                border_style="red",
            ))

    def display_price_history(self, asin: str, days: int = 30) -> None:
        """Display price history chart for a single ASIN."""
        c = self.currency
        history = self.get_price_history(asin, days)

        if not history:
            console.print(f"[yellow]No price history found for {asin}.[/yellow]")
            return

        console.print(f"\n[bold]Price History for {asin} (last {days} days):[/bold]")

        prices = [h["price"] for h in history]
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price if max_price != min_price else 1

        chart_height = 8
        chart_width = min(len(prices), 50)

        if len(prices) > chart_width:
            step = len(prices) // chart_width
            chart_prices = prices[::step][:chart_width]
        else:
            chart_prices = prices

        for row in range(chart_height, -1, -1):
            threshold = min_price + (price_range * row / chart_height)
            label = f"{c}{threshold:6.2f} │"
            line = ""
            for val in chart_prices:
                normalized = (val - min_price) / price_range * chart_height
                if abs(normalized - row) < 0.5:
                    line += "●"
                elif normalized > row:
                    line += "│"
                else:
                    line += " "
            console.print(f"  {label}{line}")

        console.print(f"          └{'─' * len(chart_prices)}")

        # Summary
        console.print(f"\n  Min: {c}{min_price:.2f}  Max: {c}{max_price:.2f}  "
                       f"Current: {c}{prices[-1]:.2f}  Data points: {len(history)}")
