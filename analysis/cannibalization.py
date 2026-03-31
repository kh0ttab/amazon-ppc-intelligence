"""Campaign cannibalization detector - finds internal auction competition."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

from config import load_config

logger = logging.getLogger(__name__)
console = Console()


class CannibalizationDetector:
    """Detect search terms competing across multiple campaigns."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]

    def detect(self, df: pd.DataFrame) -> dict:
        """Find search terms appearing in multiple campaigns.

        Expects DataFrame with 'Customer Search Term' and 'Campaign Name' columns.
        Returns dict with cannibalized terms, waste estimate, and recommendations.
        """
        keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else "Targeting"
        campaign_col = "Campaign Name"

        if keyword_col not in df.columns or campaign_col not in df.columns:
            console.print("[yellow]Need both search term and campaign data for cannibalization analysis.[/yellow]")
            return {"cannibalized": pd.DataFrame(), "total_waste": 0, "recommendations": []}

        for col in ["Spend", "Sales", "Orders", "Clicks", "Impressions"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Group by search term and campaign
        grouped = df.groupby([keyword_col, campaign_col]).agg({
            "Spend": "sum",
            "Sales": "sum",
            "Orders": "sum",
            "Clicks": "sum",
            "Impressions": "sum",
        }).reset_index()

        # Find terms in 2+ campaigns
        term_campaign_counts = grouped.groupby(keyword_col)[campaign_col].nunique()
        cannibalized_terms = term_campaign_counts[term_campaign_counts >= 2].index.tolist()

        if not cannibalized_terms:
            return {"cannibalized": pd.DataFrame(), "total_waste": 0, "recommendations": []}

        cannibal_data = grouped[grouped[keyword_col].isin(cannibalized_terms)].copy()

        # For each term, find the best campaign and estimate waste from others
        recommendations = []
        total_waste = 0

        for term in cannibalized_terms:
            term_rows = cannibal_data[cannibal_data[keyword_col] == term].copy()

            # Best campaign = lowest ACoS with orders, or highest ROAS
            term_rows["ACoS"] = term_rows.apply(
                lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 999, axis=1
            )
            term_rows = term_rows.sort_values("ACoS")

            best_campaign = term_rows.iloc[0][campaign_col]
            best_acos = term_rows.iloc[0]["ACoS"]

            # Other campaigns are wasting via self-competition
            other_campaigns = term_rows.iloc[1:]
            waste_from_term = 0

            for _, other in other_campaigns.iterrows():
                # Estimate waste: CPC inflation from self-bidding (~20% of spend on duplicate)
                estimated_waste = other["Spend"] * 0.20
                waste_from_term += estimated_waste

                recommendations.append({
                    "search_term": term,
                    "owner_campaign": best_campaign,
                    "owner_acos": best_acos,
                    "duplicate_campaign": other[campaign_col],
                    "duplicate_spend": other["Spend"],
                    "duplicate_acos": other["ACoS"],
                    "estimated_waste": estimated_waste,
                    "action": f"Add as NEGATIVE EXACT in '{other[campaign_col]}'",
                })

            total_waste += waste_from_term

        # Build cannibalization matrix
        matrix = cannibal_data.pivot_table(
            index=keyword_col,
            columns=campaign_col,
            values="Spend",
            aggfunc="sum",
            fill_value=0,
        )

        logger.info(
            f"Cannibalization: {len(cannibalized_terms)} terms in multiple campaigns, "
            f"estimated waste: {self.currency}{total_waste:.2f}"
        )

        return {
            "cannibalized": cannibal_data,
            "matrix": matrix,
            "total_waste": total_waste,
            "recommendations": sorted(recommendations, key=lambda x: x["estimated_waste"], reverse=True),
            "term_count": len(cannibalized_terms),
        }

    def display_report(self, result: dict) -> None:
        """Display cannibalization analysis results."""
        c = self.currency

        if result["term_count"] == 0:
            console.print(Panel(
                "[green]No cannibalization detected. Each search term appears in only one campaign.[/green]",
                title="Cannibalization Check",
                border_style="green",
            ))
            return

        # Summary
        console.print(Panel(
            f"[red]{result['term_count']}[/red] search terms found in multiple campaigns\n"
            f"Estimated waste from self-competition: [bold red]{c}{result['total_waste']:,.2f}[/bold red]",
            title="Cannibalization Detected",
            border_style="red",
        ))

        # Matrix view (top 15 terms)
        if "matrix" in result and len(result["matrix"]) > 0:
            matrix = result["matrix"]
            campaigns = list(matrix.columns)

            table = Table(title="Cannibalization Matrix (Spend by Campaign)", show_lines=True)
            table.add_column("Search Term", style="cyan", max_width=30)
            for camp in campaigns[:6]:  # Limit columns for readability
                table.add_column(str(camp)[:20], justify="right", max_width=12)
            table.add_column("Total", justify="right", style="bold")

            for term in list(matrix.index)[:15]:
                row_vals = []
                for camp in campaigns[:6]:
                    val = matrix.loc[term, camp]
                    if val > 0:
                        row_vals.append(f"[red]{c}{val:,.2f}[/red]")
                    else:
                        row_vals.append("[dim]-[/dim]")
                total = matrix.loc[term].sum()
                table.add_row(str(term)[:30], *row_vals, f"{c}{total:,.2f}")

            console.print(table)

        # Recommendations
        recs = result["recommendations"][:20]
        if recs:
            rec_table = Table(title="Cannibalization Fix Actions", show_lines=True)
            rec_table.add_column("#", width=4)
            rec_table.add_column("Search Term", style="cyan", max_width=25)
            rec_table.add_column("Owner Campaign", style="green", max_width=20)
            rec_table.add_column("Owner ACoS", justify="right")
            rec_table.add_column("Duplicate Campaign", style="red", max_width=20)
            rec_table.add_column("Dup Spend", justify="right")
            rec_table.add_column("Est. Waste", justify="right")
            rec_table.add_column("Action", max_width=30)

            for i, rec in enumerate(recs):
                rec_table.add_row(
                    str(i + 1),
                    str(rec["search_term"])[:25],
                    str(rec["owner_campaign"])[:20],
                    f"{rec['owner_acos']:.1f}%",
                    str(rec["duplicate_campaign"])[:20],
                    f"[red]{c}{rec['duplicate_spend']:,.2f}[/red]",
                    f"[red]{c}{rec['estimated_waste']:,.2f}[/red]",
                    rec["action"][:30],
                )

            console.print(rec_table)
