"""Placement performance analysis - Top of Search vs Product Pages vs Rest."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()

PLACEMENT_NAMES = {
    "top": ["Top of Search", "Top of Search (first page)", "top of search"],
    "product": ["Product Pages", "Detail Page", "product pages"],
    "rest": ["Rest of Search", "Other", "rest of search"],
}


def _normalize_placement(name: str) -> str:
    """Map placement name to canonical form."""
    lower = name.strip().lower()
    for canonical, aliases in PLACEMENT_NAMES.items():
        if any(a.lower() in lower for a in aliases):
            return canonical
    return "rest"


class PlacementAnalyzer:
    """Analyze performance by ad placement."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.target_acos = self.config["target_acos"]

    def analyze(self, df: pd.DataFrame) -> dict:
        """Analyze placement performance.

        Expects either a Placement Report with 'Placement' column,
        or campaign data that can be grouped by placement.
        """
        for col in ["Impressions", "Clicks", "Spend", "Sales", "Orders"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        placement_col = "Placement" if "Placement" in df.columns else None

        if placement_col is None:
            console.print("[yellow]No 'Placement' column found. Load a Placement Report CSV.[/yellow]")
            return {"placements": pd.DataFrame(), "multipliers": {}}

        df["Placement_Normalized"] = df[placement_col].apply(_normalize_placement)

        placement_data = df.groupby("Placement_Normalized").agg({
            "Impressions": "sum",
            "Clicks": "sum",
            "Spend": "sum",
            "Sales": "sum",
            "Orders": "sum",
        }).reset_index()

        # Calculate metrics per placement
        placement_data["ACoS"] = placement_data.apply(
            lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 0, axis=1
        )
        placement_data["ROAS"] = placement_data.apply(
            lambda r: (r["Sales"] / r["Spend"]) if r["Spend"] > 0 else 0, axis=1
        )
        placement_data["CTR"] = placement_data.apply(
            lambda r: (r["Clicks"] / r["Impressions"] * 100) if r["Impressions"] > 0 else 0, axis=1
        )
        placement_data["CPC"] = placement_data.apply(
            lambda r: (r["Spend"] / r["Clicks"]) if r["Clicks"] > 0 else 0, axis=1
        )
        placement_data["CVR"] = placement_data.apply(
            lambda r: (r["Orders"] / r["Clicks"] * 100) if r["Clicks"] > 0 else 0, axis=1
        )

        # Calculate bid multiplier suggestions
        multipliers = {}
        for _, row in placement_data.iterrows():
            placement = row["Placement_Normalized"]
            acos = row["ACoS"]

            if acos == 0:
                multipliers[placement] = {"pct": 0, "reason": "No sales data"}
            elif acos < self.target_acos * 0.8:
                # Performing well - increase multiplier
                headroom = ((self.target_acos - acos) / self.target_acos) * 100
                suggested = min(int(headroom), 100)
                multipliers[placement] = {
                    "pct": suggested,
                    "reason": f"ACoS {acos:.0f}% < target {self.target_acos}% - room to increase",
                }
            elif acos <= self.target_acos * 1.2:
                # Near target - small or no adjustment
                multipliers[placement] = {
                    "pct": 0,
                    "reason": f"ACoS {acos:.0f}% near target - no change needed",
                }
            elif acos <= self.target_acos * 2:
                # Above target - suggest reduction
                multipliers[placement] = {
                    "pct": -25,
                    "reason": f"ACoS {acos:.0f}% above target - reduce bids",
                }
            else:
                # Way above target
                multipliers[placement] = {
                    "pct": -50,
                    "reason": f"ACoS {acos:.0f}% >> target - strongly reduce or set to 0%",
                }

        logger.info(f"Placement analysis: {len(placement_data)} placements analyzed")
        return {"placements": placement_data, "multipliers": multipliers}

    def display_report(self, result: dict) -> None:
        """Display placement performance report with visual bars."""
        c = self.currency
        placements = result["placements"]
        multipliers = result["multipliers"]

        if len(placements) == 0:
            return

        # Performance table
        table = Table(title="Performance by Placement", show_lines=True)
        table.add_column("Placement", style="bold")
        table.add_column("Impressions", justify="right")
        table.add_column("Clicks", justify="right")
        table.add_column("Spend", justify="right")
        table.add_column("Revenue", justify="right")
        table.add_column("ACoS", justify="right")
        table.add_column("ROAS", justify="right")
        table.add_column("CTR", justify="right")
        table.add_column("CPC", justify="right")
        table.add_column("CVR", justify="right")

        placement_labels = {"top": "Top of Search", "product": "Product Pages", "rest": "Rest of Search"}
        placement_colors = {"top": "green", "product": "yellow", "rest": "dim"}

        for _, row in placements.iterrows():
            p = row["Placement_Normalized"]
            label = placement_labels.get(p, p)
            color = placement_colors.get(p, "white")
            acos_color = "green" if row["ACoS"] <= self.target_acos else "red"

            table.add_row(
                f"[{color}]{label}[/{color}]",
                f"{int(row['Impressions']):,}",
                f"{int(row['Clicks']):,}",
                f"{c}{row['Spend']:,.2f}",
                f"[green]{c}{row['Sales']:,.2f}[/green]",
                f"[{acos_color}]{row['ACoS']:.1f}%[/{acos_color}]",
                f"{row['ROAS']:.2f}x",
                f"{row['CTR']:.2f}%",
                f"{c}{row['CPC']:.2f}",
                f"{row['CVR']:.1f}%",
            )

        console.print(table)

        # Visual bar comparison
        console.print("\n[bold]Spend Distribution:[/bold]")
        total_spend = placements["Spend"].sum()
        if total_spend > 0:
            for _, row in placements.iterrows():
                p = row["Placement_Normalized"]
                label = placement_labels.get(p, p)
                color = placement_colors.get(p, "white")
                pct = row["Spend"] / total_spend * 100
                bars = int(pct / 2)
                console.print(
                    f"  {label:20s} [{color}]{'█' * bars}[/{color}] "
                    f"{pct:.1f}% ({c}{row['Spend']:,.2f})"
                )

        console.print(f"\n[bold]Revenue Distribution:[/bold]")
        total_sales = placements["Sales"].sum()
        if total_sales > 0:
            for _, row in placements.iterrows():
                p = row["Placement_Normalized"]
                label = placement_labels.get(p, p)
                pct = row["Sales"] / total_sales * 100
                bars = int(pct / 2)
                console.print(
                    f"  {label:20s} [green]{'█' * bars}[/green] "
                    f"{pct:.1f}% ({c}{row['Sales']:,.2f})"
                )

        # Multiplier suggestions
        console.print()
        mult_table = Table(title="Bid Multiplier Recommendations", show_lines=True)
        mult_table.add_column("Placement", style="bold")
        mult_table.add_column("Suggested Multiplier", justify="center")
        mult_table.add_column("Reason")

        for placement, mult in multipliers.items():
            label = placement_labels.get(placement, placement)
            pct = mult["pct"]
            if pct > 0:
                mult_str = f"[green]+{pct}%[/green]"
            elif pct < 0:
                mult_str = f"[red]{pct}%[/red]"
            else:
                mult_str = "[dim]0% (no change)[/dim]"

            mult_table.add_row(label, mult_str, mult["reason"])

        console.print(mult_table)
