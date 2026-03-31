"""Sponsored Products vs Brands vs Display split analysis."""

import logging
import re
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

from config import load_config

logger = logging.getLogger(__name__)
console = Console()

# Campaign name patterns to detect ad type
AD_TYPE_PATTERNS = {
    "SP": [
        r"\bSP\b", r"Sponsored Product", r"\bsp\b", r"sponsored.?product",
        r"Auto", r"Manual", r"Exact", r"Broad", r"Phrase",
    ],
    "SB": [
        r"\bSB\b", r"Sponsored Brand", r"\bsb\b", r"sponsored.?brand",
        r"Brand", r"Video", r"headline",
    ],
    "SD": [
        r"\bSD\b", r"Sponsored Display", r"\bsd\b", r"sponsored.?display",
        r"Display", r"Retarget", r"Remarket", r"DPVR", r"audience",
    ],
}


def detect_ad_type(campaign_name: str) -> str:
    """Detect ad type from campaign name patterns."""
    name = str(campaign_name)
    # Check SD first (more specific), then SB, then default to SP
    for ad_type in ["SD", "SB", "SP"]:
        for pattern in AD_TYPE_PATTERNS[ad_type]:
            if re.search(pattern, name, re.IGNORECASE):
                return ad_type
    return "SP"  # Default to SP


class AdTypeSplitAnalyzer:
    """Analyze performance separately by ad type (SP/SB/SD)."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.target_acos = self.config["target_acos"]

    def split_by_ad_type(self, df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Split data by detected ad type.

        Returns dict with keys 'SP', 'SB', 'SD', each containing filtered DataFrame.
        """
        if "Campaign Name" not in df.columns:
            console.print("[yellow]No 'Campaign Name' column. Cannot split by ad type.[/yellow]")
            return {"SP": df.copy()}

        data = df.copy()
        data["Ad_Type"] = data["Campaign Name"].apply(detect_ad_type)

        result = {}
        for ad_type in ["SP", "SB", "SD"]:
            subset = data[data["Ad_Type"] == ad_type]
            if len(subset) > 0:
                result[ad_type] = subset

        return result

    def analyze_all(self, df: pd.DataFrame) -> dict:
        """Analyze performance for each ad type separately."""
        splits = self.split_by_ad_type(df)

        for col in ["Spend", "Sales", "Orders", "Clicks", "Impressions"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        summaries = {}
        for ad_type, type_df in splits.items():
            for col in ["Spend", "Sales", "Orders", "Clicks", "Impressions"]:
                if col in type_df.columns:
                    type_df[col] = pd.to_numeric(type_df[col], errors="coerce").fillna(0)

            spend = type_df["Spend"].sum()
            sales = type_df["Sales"].sum()
            orders = type_df["Orders"].sum()
            clicks = type_df["Clicks"].sum()
            impressions = type_df["Impressions"].sum()

            summaries[ad_type] = {
                "data": type_df,
                "spend": spend,
                "sales": sales,
                "orders": orders,
                "clicks": clicks,
                "impressions": impressions,
                "acos": (spend / sales * 100) if sales > 0 else 0,
                "roas": (sales / spend) if spend > 0 else 0,
                "ctr": (clicks / impressions * 100) if impressions > 0 else 0,
                "cpc": (spend / clicks) if clicks > 0 else 0,
                "cvr": (orders / clicks * 100) if clicks > 0 else 0,
                "campaigns": type_df["Campaign Name"].nunique() if "Campaign Name" in type_df.columns else 0,
            }

        return summaries

    def get_type_recommendations(self, summaries: dict) -> dict[str, list[str]]:
        """Generate ad-type-specific recommendations."""
        recs = {}

        if "SP" in summaries:
            sp = summaries["SP"]
            sp_recs = []
            if sp["acos"] > self.target_acos * 1.5:
                sp_recs.append(f"SP ACoS ({sp['acos']:.0f}%) is high. Focus on exact match harvesting and negative keywords.")
            elif sp["acos"] < self.target_acos * 0.6:
                sp_recs.append(f"SP ACoS ({sp['acos']:.0f}%) has headroom. Consider increasing bids to capture more volume.")
            if sp["cvr"] < 5:
                sp_recs.append(f"SP conversion rate ({sp['cvr']:.1f}%) is low. Review listing quality and keyword relevance.")
            if sp["cvr"] > 15:
                sp_recs.append(f"SP conversion rate ({sp['cvr']:.1f}%) is strong. Scale winning campaigns.")
            recs["SP"] = sp_recs or ["SP performance is balanced. Continue monitoring."]

        if "SB" in summaries:
            sb = summaries["SB"]
            sb_recs = []
            if sb["ctr"] < 0.3:
                sb_recs.append("SB CTR is low. Test new ad creative, headlines, and brand logos.")
            if sb["acos"] > self.target_acos * 2:
                sb_recs.append(f"SB ACoS ({sb['acos']:.0f}%) is high. SB targets top-of-funnel - consider it a branding investment, but cap spend.")
            sb_recs.append("Track new-to-brand percentage if available - SB's main value is customer acquisition.")
            recs["SB"] = sb_recs

        if "SD" in summaries:
            sd = summaries["SD"]
            sd_recs = []
            if sd["ctr"] < 0.2:
                sd_recs.append("SD CTR is typical for display. Focus on DPVR (detail page view rate) instead.")
            if sd["acos"] > self.target_acos * 3:
                sd_recs.append(f"SD ACoS ({sd['acos']:.0f}%) is very high. SD is remarketing - ensure audience targeting is tight.")
            sd_recs.append("SD works best for remarketing and competitor conquesting. Don't compare its ACoS to SP directly.")
            recs["SD"] = sd_recs

        return recs

    def display_report(self, summaries: dict) -> None:
        """Display split analysis report."""
        c = self.currency

        type_labels = {
            "SP": ("Sponsored Products", "green"),
            "SB": ("Sponsored Brands", "cyan"),
            "SD": ("Sponsored Display", "yellow"),
        }

        # Overview table
        overview = Table(title="Performance by Ad Type", show_lines=True)
        overview.add_column("Metric", style="bold")

        for ad_type in ["SP", "SB", "SD"]:
            if ad_type in summaries:
                label, color = type_labels[ad_type]
                overview.add_column(f"[{color}]{label}[/{color}]", justify="right")

        metrics = [
            ("Campaigns", lambda s: str(s["campaigns"])),
            ("Spend", lambda s: f"{c}{s['spend']:,.2f}"),
            ("Revenue", lambda s: f"{c}{s['sales']:,.2f}"),
            ("Orders", lambda s: f"{int(s['orders']):,}"),
            ("ACoS", lambda s: f"{s['acos']:.1f}%"),
            ("ROAS", lambda s: f"{s['roas']:.2f}x"),
            ("CTR", lambda s: f"{s['ctr']:.2f}%"),
            ("CPC", lambda s: f"{c}{s['cpc']:.2f}"),
            ("CVR", lambda s: f"{s['cvr']:.1f}%"),
        ]

        for label, formatter in metrics:
            row = [label]
            for ad_type in ["SP", "SB", "SD"]:
                if ad_type in summaries:
                    row.append(formatter(summaries[ad_type]))
            overview.add_row(*row)

        console.print(overview)

        # Spend distribution bars
        total_spend = sum(s["spend"] for s in summaries.values())
        if total_spend > 0:
            console.print("\n[bold]Spend Distribution:[/bold]")
            for ad_type in ["SP", "SB", "SD"]:
                if ad_type in summaries:
                    label, color = type_labels[ad_type]
                    pct = summaries[ad_type]["spend"] / total_spend * 100
                    bars = int(pct / 2)
                    console.print(
                        f"  {label:25s} [{color}]{'█' * bars}[/{color}] "
                        f"{pct:.1f}% ({c}{summaries[ad_type]['spend']:,.2f})"
                    )

        # Type-specific recommendations
        recs = self.get_type_recommendations(summaries)
        for ad_type, rec_list in recs.items():
            label, color = type_labels[ad_type]
            console.print(f"\n[bold {color}]{label} Recommendations:[/bold {color}]")
            for rec in rec_list:
                console.print(f"  [{color}]>[/{color}] {rec}")

        # Warning about mixing
        if len(summaries) > 1:
            console.print(Panel(
                "[yellow]Important:[/yellow] Never average ACoS across ad types. "
                "SP targets direct conversions, SB targets brand awareness, "
                "SD targets remarketing. Each has different KPIs and benchmarks.",
                title="Ad Type Warning",
                border_style="yellow",
            ))
