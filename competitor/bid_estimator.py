"""Bid suggestion engine for Amazon PPC keywords."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()


class BidEstimator:
    """Estimate suggested bids for keywords based on performance data."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.bid_multiplier = self.config["bid_multiplier"]
        self.target_acos = self.config["target_acos"]

    def estimate_bid(
        self,
        keyword: str,
        avg_cpc: float = 0,
        competition_level: str = "medium",
        keyword_length: int = 0,
    ) -> dict:
        """Estimate a suggested bid for a keyword.

        Args:
            keyword: The keyword text
            avg_cpc: Average CPC from existing data (0 if new keyword)
            competition_level: 'low', 'medium', 'high' (based on sponsored count)
            keyword_length: Number of words in keyword
        """
        if keyword_length == 0:
            keyword_length = len(keyword.split())

        # Base CPC estimation
        if avg_cpc > 0:
            base_cpc = avg_cpc
        else:
            # Estimate based on competition and keyword length
            base_rates = {"low": 0.50, "medium": 1.00, "high": 1.75}
            base_cpc = base_rates.get(competition_level, 1.00)

        # Long-tail discount: more words = less competitive = lower bid
        length_multiplier = max(0.5, 1.0 - (keyword_length - 2) * 0.1)

        # Competition adjustment
        comp_multiplier = {"low": 0.8, "medium": 1.0, "high": 1.3}.get(competition_level, 1.0)

        estimated_cpc = base_cpc * length_multiplier * comp_multiplier
        suggested_bid = estimated_cpc * self.bid_multiplier

        # Match type recommendation
        if avg_cpc > 0 and keyword_length <= 3:
            match_type = "Exact"
        elif keyword_length <= 2:
            match_type = "Phrase"
        elif keyword_length >= 4:
            match_type = "Broad"
        else:
            match_type = "Phrase"

        return {
            "keyword": keyword,
            "estimated_cpc": round(estimated_cpc, 2),
            "suggested_bid": round(suggested_bid, 2),
            "match_type": match_type,
            "competition": competition_level,
            "keyword_length": keyword_length,
        }

    def estimate_from_search_data(
        self,
        keywords: list[str],
        existing_data: Optional[pd.DataFrame] = None,
        sponsored_count: int = 0,
    ) -> list[dict]:
        """Estimate bids for a list of keywords using existing campaign data as reference."""
        # Determine competition level from sponsored count
        if sponsored_count >= 5:
            competition = "high"
        elif sponsored_count >= 2:
            competition = "medium"
        else:
            competition = "low"

        # Get average CPC from existing data
        avg_cpc = 0
        if existing_data is not None and "CPC" in existing_data.columns:
            cpc_values = pd.to_numeric(existing_data["CPC"], errors="coerce")
            avg_cpc = cpc_values[cpc_values > 0].mean()
            if pd.isna(avg_cpc):
                avg_cpc = 0

        estimates = []
        for kw in keywords:
            estimate = self.estimate_bid(
                keyword=kw,
                avg_cpc=avg_cpc,
                competition_level=competition,
            )
            estimates.append(estimate)

        return estimates

    def calculate_daily_budget(
        self,
        target_acos: float,
        avg_order_value: float,
        target_daily_orders: int,
        conversion_rate: float,
    ) -> dict:
        """Calculate recommended daily budget per campaign.

        Args:
            target_acos: Target ACoS percentage
            avg_order_value: Average revenue per order
            target_daily_orders: How many PPC orders per day
            conversion_rate: Expected conversion rate (%)
        """
        if conversion_rate <= 0 or avg_order_value <= 0:
            return {"daily_budget": 0, "monthly_budget": 0, "error": "Invalid inputs"}

        # Max spend per order at target ACoS
        max_spend_per_order = avg_order_value * (target_acos / 100)

        # Clicks needed per order
        clicks_per_order = 100 / conversion_rate if conversion_rate > 0 else 100

        # Max CPC at target ACoS
        max_cpc = max_spend_per_order / clicks_per_order

        # Daily budget
        daily_clicks_needed = target_daily_orders * clicks_per_order
        daily_budget = daily_clicks_needed * max_cpc

        return {
            "daily_budget": round(daily_budget, 2),
            "monthly_budget": round(daily_budget * 30, 2),
            "max_cpc": round(max_cpc, 2),
            "clicks_per_order": round(clicks_per_order, 1),
            "max_spend_per_order": round(max_spend_per_order, 2),
            "daily_clicks_needed": round(daily_clicks_needed, 0),
        }

    def display_bid_suggestions(self, estimates: list[dict]) -> None:
        """Display bid suggestions in a rich table."""
        c = self.currency
        table = Table(title="Keyword Bid Suggestions", show_lines=True)
        table.add_column("#", width=4)
        table.add_column("Keyword", style="cyan", max_width=35)
        table.add_column("Est. CPC", justify="right")
        table.add_column("Suggested Bid", justify="right", style="bold green")
        table.add_column("Match Type", justify="center")
        table.add_column("Competition", justify="center")
        table.add_column("Words", justify="center")

        comp_colors = {"low": "green", "medium": "yellow", "high": "red"}
        match_colors = {"Exact": "green", "Phrase": "cyan", "Broad": "yellow"}

        for i, est in enumerate(estimates):
            c_color = comp_colors.get(est["competition"], "white")
            m_color = match_colors.get(est["match_type"], "white")

            table.add_row(
                str(i + 1),
                est["keyword"][:35],
                f"{c}{est['estimated_cpc']:.2f}",
                f"[green]{c}{est['suggested_bid']:.2f}[/green]",
                f"[{m_color}]{est['match_type']}[/{m_color}]",
                f"[{c_color}]{est['competition'].upper()}[/{c_color}]",
                str(est["keyword_length"]),
            )

        console.print(table)

    def display_budget_suggestion(self, budget_data: dict) -> None:
        """Display budget calculation results."""
        c = self.currency
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Recommended Daily Budget", f"[bold green]{c}{budget_data['daily_budget']:,.2f}[/bold green]")
        table.add_row("Estimated Monthly Budget", f"[green]{c}{budget_data['monthly_budget']:,.2f}[/green]")
        table.add_row("Max CPC at Target ACoS", f"{c}{budget_data['max_cpc']:.2f}")
        table.add_row("Clicks Needed per Order", f"{budget_data['clicks_per_order']:.0f}")
        table.add_row("Max Spend per Order", f"{c}{budget_data['max_spend_per_order']:.2f}")
        table.add_row("Daily Clicks Needed", f"{budget_data['daily_clicks_needed']:.0f}")

        console.print(Panel(table, title="Budget Recommendation", border_style="green"))
