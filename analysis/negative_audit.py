"""Negative keyword audit - find and group wasteful search terms."""

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config, REPORT_DIR

logger = logging.getLogger(__name__)
console = Console()

# Common negative keyword root categories
NEGATIVE_CATEGORIES = {
    "cheap": ["cheap", "cheapest", "inexpensive", "budget", "affordable", "low cost", "discount"],
    "used": ["used", "refurbished", "second hand", "pre-owned", "secondhand"],
    "free": ["free", "freebie", "giveaway", "sample"],
    "diy": ["diy", "homemade", "how to make", "recipe", "tutorial"],
    "review": ["review", "reviews", "comparison", "vs", "versus", "reddit"],
    "competitor": [],  # Populated dynamically
    "irrelevant_intent": ["what is", "how does", "meaning", "definition", "wiki"],
    "return": ["return", "refund", "warranty", "complaint"],
}


class NegativeKeywordAuditor:
    """Audit search terms for negative keyword candidates."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.clicks_threshold = self.config["negative_clicks_threshold"]
        self.spend_threshold = self.config["negative_spend_threshold"]

    def audit(self, df: pd.DataFrame) -> dict:
        """Find all search terms that should be negated.

        Returns dict with negative candidates grouped by root word category.
        """
        for col in ["Clicks", "Orders", "Spend", "Sales", "Impressions"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else "Targeting"

        # Find terms meeting negative threshold: clicks >= N, orders = 0, spend > $M
        negative_mask = (
            (df["Clicks"] >= self.clicks_threshold) &
            (df["Orders"] == 0) &
            (df["Spend"] > self.spend_threshold)
        )
        negatives = df[negative_mask].copy()
        negatives = negatives.sort_values("Spend", ascending=False)

        # Extract root words and group
        root_groups = defaultdict(list)
        ungrouped = []

        for _, row in negatives.iterrows():
            term = str(row.get(keyword_col, "")).lower().strip()
            categorized = False

            for category, patterns in NEGATIVE_CATEGORIES.items():
                for pattern in patterns:
                    if pattern in term:
                        root_groups[category].append({
                            "term": row[keyword_col],
                            "spend": row["Spend"],
                            "clicks": row["Clicks"],
                            "impressions": row.get("Impressions", 0),
                            "campaign": row.get("Campaign Name", ""),
                        })
                        categorized = True
                        break
                if categorized:
                    break

            if not categorized:
                # Try to extract a root word (most common 2-word combination)
                words = re.findall(r"\b[a-z]{3,}\b", term)
                if words:
                    root = words[0]  # Use first significant word as root
                    root_groups[f"root:{root}"].append({
                        "term": row[keyword_col],
                        "spend": row["Spend"],
                        "clicks": row["Clicks"],
                        "impressions": row.get("Impressions", 0),
                        "campaign": row.get("Campaign Name", ""),
                    })
                else:
                    ungrouped.append({
                        "term": row[keyword_col],
                        "spend": row["Spend"],
                        "clicks": row["Clicks"],
                        "impressions": row.get("Impressions", 0),
                        "campaign": row.get("Campaign Name", ""),
                    })

        # Calculate group totals
        group_summaries = {}
        for group, terms in root_groups.items():
            total_spend = sum(t["spend"] for t in terms)
            group_summaries[group] = {
                "terms": terms,
                "count": len(terms),
                "total_spend": total_spend,
            }

        # Sort groups by total spend
        group_summaries = dict(
            sorted(group_summaries.items(), key=lambda x: x[1]["total_spend"], reverse=True)
        )

        total_waste = negatives["Spend"].sum()
        monthly_savings = total_waste  # Assuming 30-day data

        result = {
            "all_negatives": negatives,
            "groups": group_summaries,
            "ungrouped": ungrouped,
            "total_count": len(negatives),
            "total_waste": total_waste,
            "estimated_monthly_savings": monthly_savings,
        }

        logger.info(
            f"Negative audit: {result['total_count']} candidates, "
            f"{len(group_summaries)} groups, "
            f"total waste: {self.currency}{total_waste:.2f}"
        )
        return result

    def export_negative_list(self, audit_result: dict, campaign_name: str = "") -> Path:
        """Export negative keyword list as Amazon bulk upload CSV."""
        rows = []

        for group_name, group_data in audit_result["groups"].items():
            for term_data in group_data["terms"]:
                rows.append({
                    "Record Type": "Keyword",
                    "Campaign Name": campaign_name or term_data.get("campaign", ""),
                    "Ad Group Name": "",
                    "Keyword": term_data["term"],
                    "Match Type": "Negative Exact",
                    "State": "enabled",
                })

        for term_data in audit_result.get("ungrouped", []):
            rows.append({
                "Record Type": "Keyword",
                "Campaign Name": campaign_name or term_data.get("campaign", ""),
                "Ad Group Name": "",
                "Keyword": term_data["term"],
                "Match Type": "Negative Exact",
                "State": "enabled",
            })

        if not rows:
            console.print("[yellow]No negative keywords to export.[/yellow]")
            return Path()

        df = pd.DataFrame(rows)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = REPORT_DIR / f"negative_keywords_{timestamp}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8-sig")

        console.print(f"[green]Negative keyword list exported:[/green] {filepath}")
        console.print(f"[dim]{len(rows)} negative keywords ready for Amazon Bulk Upload[/dim]")
        return filepath

    def display_report(self, audit_result: dict) -> None:
        """Display negative keyword audit report."""
        c = self.currency

        # Summary
        console.print(Panel(
            f"[bold]{audit_result['total_count']}[/bold] negative keyword candidates found\n"
            f"Total wasted spend: [bold red]{c}{audit_result['total_waste']:,.2f}[/bold red]\n"
            f"Estimated monthly savings if applied: [bold green]{c}{audit_result['estimated_monthly_savings']:,.2f}[/bold green]",
            title="Negative Keyword Audit",
            border_style="red",
        ))

        # Group summary table
        groups = audit_result["groups"]
        if groups:
            group_table = Table(title="Waste by Root Word Group", show_lines=True)
            group_table.add_column("#", width=4)
            group_table.add_column("Root Category", style="bold", max_width=20)
            group_table.add_column("Terms", justify="right")
            group_table.add_column("Total Spend", justify="right")
            group_table.add_column("Sample Terms", max_width=40)

            for i, (group_name, data) in enumerate(list(groups.items())[:20]):
                display_name = group_name.replace("root:", "").title()
                samples = ", ".join(t["term"][:20] for t in data["terms"][:3])

                group_table.add_row(
                    str(i + 1),
                    display_name,
                    str(data["count"]),
                    f"[red]{c}{data['total_spend']:,.2f}[/red]",
                    f"[dim]{samples}[/dim]",
                )

            console.print(group_table)

        # Top individual negatives
        negatives = audit_result["all_negatives"]
        if len(negatives) > 0:
            keyword_col = "Customer Search Term" if "Customer Search Term" in negatives.columns else "Targeting"

            neg_table = Table(title="Top Wasteful Search Terms (Add as Negative)", show_lines=True)
            neg_table.add_column("#", width=4)
            neg_table.add_column("Search Term", style="red", max_width=35)
            neg_table.add_column("Clicks", justify="right")
            neg_table.add_column("Spend", justify="right")
            neg_table.add_column("Orders", justify="right")
            neg_table.add_column("Campaign", max_width=20)

            for i, (_, row) in enumerate(negatives.head(25).iterrows()):
                neg_table.add_row(
                    str(i + 1),
                    str(row.get(keyword_col, "N/A"))[:35],
                    str(int(row["Clicks"])),
                    f"[red]{c}{row['Spend']:,.2f}[/red]",
                    "[red]0[/red]",
                    str(row.get("Campaign Name", ""))[:20],
                )

            console.print(neg_table)
