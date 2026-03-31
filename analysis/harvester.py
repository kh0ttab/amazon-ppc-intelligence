"""Search term harvesting pipeline - auto to manual keyword migration."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

from config import load_config, REPORT_DIR

logger = logging.getLogger(__name__)
console = Console()


class SearchTermHarvester:
    """Automated search term harvesting with configurable thresholds."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.clicks_threshold = self.config["harvest_clicks_threshold"]
        self.orders_threshold = self.config["harvest_orders_threshold"]
        self.neg_clicks_threshold = self.config["negative_clicks_threshold"]
        self.neg_spend_threshold = self.config["negative_spend_threshold"]
        self.target_acos = self.config["target_acos"]

    def harvest(self, df: pd.DataFrame) -> dict:
        """Run the full harvesting pipeline.

        Returns dict with:
        - promote_exact: terms to add to manual exact campaigns
        - add_negative: terms to add as negative exact
        - promote_standalone: terms performing better than parent keyword
        """
        for col in ["Clicks", "Orders", "Spend", "Sales", "Impressions"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else "Targeting"
        campaign_col = "Campaign Name" if "Campaign Name" in df.columns else None

        # Aggregate by search term (across all campaigns)
        agg_cols = {"Clicks": "sum", "Orders": "sum", "Spend": "sum", "Sales": "sum", "Impressions": "sum"}
        group_cols = [keyword_col]
        if campaign_col and campaign_col in df.columns:
            group_cols.append(campaign_col)
        if "Ad Group Name" in df.columns:
            group_cols.append("Ad Group Name")
        if "Match Type" in df.columns:
            group_cols.append("Match Type")

        term_data = df.groupby(group_cols).agg(agg_cols).reset_index()

        # Calculate metrics
        term_data["ACoS"] = term_data.apply(
            lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 0, axis=1
        )

        # RULE 1: Promote to manual exact
        # Clicks >= threshold AND Orders >= threshold
        promote_mask = (
            (term_data["Clicks"] >= self.clicks_threshold) &
            (term_data["Orders"] >= self.orders_threshold)
        )
        promote_exact = term_data[promote_mask].copy()
        promote_exact = promote_exact.sort_values("Orders", ascending=False)

        # Detect AUTO campaign terms (campaign name contains 'auto' case-insensitive)
        if campaign_col and campaign_col in promote_exact.columns:
            auto_mask = promote_exact[campaign_col].str.lower().str.contains("auto", na=False)
            promote_from_auto = promote_exact[auto_mask].copy()
        else:
            promote_from_auto = promote_exact.copy()

        # RULE 2: Add as negative exact
        # Clicks >= threshold AND Orders = 0 AND Spend > threshold
        negative_mask = (
            (term_data["Clicks"] >= self.neg_clicks_threshold) &
            (term_data["Orders"] == 0) &
            (term_data["Spend"] > self.neg_spend_threshold)
        )
        add_negative = term_data[negative_mask].copy()
        add_negative = add_negative.sort_values("Spend", ascending=False)

        # RULE 3: Promote as standalone
        # Term has lower ACoS than the campaign average
        promote_standalone = pd.DataFrame()
        if campaign_col and campaign_col in term_data.columns:
            campaign_avg_acos = term_data.groupby(campaign_col)["ACoS"].mean()

            standalone_rows = []
            for _, row in term_data.iterrows():
                if row["Orders"] > 0 and row["ACoS"] > 0:
                    camp = row.get(campaign_col, "")
                    camp_avg = campaign_avg_acos.get(camp, self.target_acos)
                    if row["ACoS"] < camp_avg * 0.7 and row["Orders"] >= 2:
                        row_dict = row.to_dict()
                        row_dict["Campaign_Avg_ACoS"] = camp_avg
                        row_dict["ACoS_Improvement"] = camp_avg - row["ACoS"]
                        standalone_rows.append(row_dict)

            if standalone_rows:
                promote_standalone = pd.DataFrame(standalone_rows)
                promote_standalone = promote_standalone.sort_values("ACoS_Improvement", ascending=False)

        result = {
            "promote_exact": promote_from_auto,
            "add_negative": add_negative,
            "promote_standalone": promote_standalone,
            "promote_count": len(promote_from_auto),
            "negative_count": len(add_negative),
            "standalone_count": len(promote_standalone),
            "potential_savings": add_negative["Spend"].sum() if len(add_negative) > 0 else 0,
        }

        logger.info(
            f"Harvest: {result['promote_count']} to promote, "
            f"{result['negative_count']} negatives, "
            f"{result['standalone_count']} standalone candidates"
        )
        return result

    def generate_bulk_csv(self, harvest_result: dict, manual_campaign: str = "",
                          manual_ad_group: str = "") -> Path:
        """Generate Amazon-ready bulk upload CSV from harvest results."""
        rows = []
        keyword_col = None

        # Promote to exact
        for _, row in harvest_result["promote_exact"].iterrows():
            keyword_col = keyword_col or ("Customer Search Term" if "Customer Search Term" in row.index else "Targeting")
            cpc = (row["Spend"] / row["Clicks"]) if row["Clicks"] > 0 else 0.75
            bid = round(cpc * self.config["bid_multiplier"], 2)

            rows.append({
                "Record Type": "Keyword",
                "Campaign Name": manual_campaign or row.get("Campaign Name", "SP - Manual Exact - Harvested"),
                "Ad Group Name": manual_ad_group or row.get("Ad Group Name", "Harvested Keywords"),
                "Keyword": row[keyword_col],
                "Match Type": "Exact",
                "Bid": bid,
                "State": "enabled",
            })

        # Negative exact
        for _, row in harvest_result["add_negative"].iterrows():
            keyword_col = keyword_col or ("Customer Search Term" if "Customer Search Term" in row.index else "Targeting")
            campaign = row.get("Campaign Name", "")

            rows.append({
                "Record Type": "Keyword",
                "Campaign Name": campaign,
                "Ad Group Name": row.get("Ad Group Name", ""),
                "Keyword": row[keyword_col],
                "Match Type": "Negative Exact",
                "Bid": "",
                "State": "enabled",
            })

        if not rows:
            console.print("[yellow]No harvest actions to export.[/yellow]")
            return Path()

        df = pd.DataFrame(rows)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = REPORT_DIR / f"bulk_harvest_{timestamp}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8-sig")

        console.print(f"[green]Bulk upload file saved:[/green] {filepath}")
        console.print(f"[dim]Contains {len(rows)} operations ready for Amazon Bulk Upload[/dim]")
        logger.info(f"Bulk harvest CSV exported: {filepath} ({len(rows)} rows)")
        return filepath

    def display_report(self, result: dict) -> None:
        """Display harvest results."""
        c = self.currency

        # Summary
        summary = (
            f"[green]Promote to Exact:[/green] {result['promote_count']} terms\n"
            f"[red]Add as Negative:[/red] {result['negative_count']} terms\n"
            f"[cyan]Standalone Candidates:[/cyan] {result['standalone_count']} terms\n"
            f"Potential Monthly Savings: [bold green]{c}{result['potential_savings']:,.2f}[/bold green]"
        )
        console.print(Panel(summary, title="Search Term Harvest Summary", border_style="green"))

        keyword_col = None

        # Promote to exact table
        if result["promote_count"] > 0:
            df = result["promote_exact"]
            keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else "Targeting"

            table = Table(title="Promote to Manual Exact Campaign", show_lines=True)
            table.add_column("#", width=4)
            table.add_column("Search Term", style="green", max_width=30)
            table.add_column("Campaign", max_width=20)
            table.add_column("Clicks", justify="right")
            table.add_column("Orders", justify="right")
            table.add_column("Revenue", justify="right")
            table.add_column("ACoS", justify="right")
            table.add_column("Sugg. Bid", justify="right")

            for i, (_, row) in enumerate(df.head(20).iterrows()):
                cpc = (row["Spend"] / row["Clicks"]) if row["Clicks"] > 0 else 0.75
                bid = cpc * self.config["bid_multiplier"]
                acos_color = "green" if row["ACoS"] <= self.target_acos else "yellow"
                table.add_row(
                    str(i + 1),
                    str(row[keyword_col])[:30],
                    str(row.get("Campaign Name", ""))[:20],
                    str(int(row["Clicks"])),
                    f"[bold]{int(row['Orders'])}[/bold]",
                    f"[green]{c}{row['Sales']:,.2f}[/green]",
                    f"[{acos_color}]{row['ACoS']:.1f}%[/{acos_color}]",
                    f"[bold]{c}{bid:.2f}[/bold]",
                )
            console.print(table)

        # Negative keywords table
        if result["negative_count"] > 0:
            df = result["add_negative"]
            keyword_col = keyword_col or ("Customer Search Term" if "Customer Search Term" in df.columns else "Targeting")

            table = Table(title="Add as Negative Exact (Wasting Budget)", show_lines=True)
            table.add_column("#", width=4)
            table.add_column("Search Term", style="red", max_width=30)
            table.add_column("Campaign", max_width=20)
            table.add_column("Clicks", justify="right")
            table.add_column("Spend", justify="right")
            table.add_column("Orders", justify="right")

            for i, (_, row) in enumerate(df.head(20).iterrows()):
                table.add_row(
                    str(i + 1),
                    str(row[keyword_col])[:30],
                    str(row.get("Campaign Name", ""))[:20],
                    str(int(row["Clicks"])),
                    f"[red]{c}{row['Spend']:,.2f}[/red]",
                    "[red]0[/red]",
                )
            console.print(table)

        # Standalone candidates
        if result["standalone_count"] > 0:
            df = result["promote_standalone"]
            keyword_col = keyword_col or ("Customer Search Term" if "Customer Search Term" in df.columns else "Targeting")

            table = Table(title="Standalone Exact Campaign Candidates", show_lines=True)
            table.add_column("#", width=4)
            table.add_column("Search Term", style="cyan", max_width=30)
            table.add_column("Term ACoS", justify="right")
            table.add_column("Campaign Avg", justify="right")
            table.add_column("Improvement", justify="right")
            table.add_column("Orders", justify="right")
            table.add_column("Revenue", justify="right")

            for i, (_, row) in enumerate(df.head(15).iterrows()):
                table.add_row(
                    str(i + 1),
                    str(row[keyword_col])[:30],
                    f"[green]{row['ACoS']:.1f}%[/green]",
                    f"[yellow]{row['Campaign_Avg_ACoS']:.1f}%[/yellow]",
                    f"[bold green]-{row['ACoS_Improvement']:.1f}%[/bold green]",
                    str(int(row["Orders"])),
                    f"{c}{row['Sales']:,.2f}",
                )
            console.print(table)
