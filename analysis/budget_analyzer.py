"""Budget waste detection and optimization."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()


class BudgetAnalyzer:
    """Detect budget waste and suggest optimizations."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.waste_threshold = self.config["waste_acos_threshold"]
        self.target_acos = self.config["target_acos"]

    def find_waste(self, df: pd.DataFrame) -> dict:
        """Find all budget waste across keywords.

        Returns dict with waste categories and total waste amount.
        """
        for col in ["Spend", "Sales", "Orders", "Impressions", "Clicks"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Keywords spending with zero orders
        zero_orders = df[(df["Spend"] > 0) & (df["Orders"] == 0)].copy()
        zero_orders = zero_orders.sort_values("Spend", ascending=False)

        # Keywords with ACoS > waste threshold
        if "ACoS" not in df.columns:
            df["ACoS"] = df.apply(
                lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 0, axis=1
            )

        high_acos = df[
            (df["ACoS"] > self.waste_threshold) & (df["Orders"] > 0)
        ].copy()
        high_acos = high_acos.sort_values("Spend", ascending=False)

        # Total waste calculation
        zero_order_waste = zero_orders["Spend"].sum()
        # Waste from high ACoS = spend above what target ACoS would allow
        high_acos_waste = 0
        if len(high_acos) > 0:
            high_acos["Target_Spend"] = high_acos["Sales"] * (self.target_acos / 100)
            high_acos["Excess_Spend"] = high_acos["Spend"] - high_acos["Target_Spend"]
            high_acos_waste = high_acos["Excess_Spend"].sum()

        total_waste = zero_order_waste + max(0, high_acos_waste)

        result = {
            "zero_orders": zero_orders,
            "high_acos": high_acos,
            "zero_order_waste": zero_order_waste,
            "high_acos_waste": max(0, high_acos_waste),
            "total_waste": total_waste,
            "total_spend": df["Spend"].sum(),
            "waste_pct": (total_waste / df["Spend"].sum() * 100) if df["Spend"].sum() > 0 else 0,
        }

        logger.info(
            f"Budget waste detected: {self.currency}{total_waste:.2f} "
            f"({result['waste_pct']:.1f}% of total spend)"
        )
        return result

    def get_recommendations(self, waste_data: dict) -> list[dict]:
        """Generate specific recommendations for each wasted keyword."""
        recommendations = []

        # Zero order keywords
        for _, row in waste_data["zero_orders"].iterrows():
            keyword = row.get("Customer Search Term", row.get("Targeting", "N/A"))
            spend = row.get("Spend", 0)
            clicks = row.get("Clicks", 0)
            impressions = row.get("Impressions", 0)

            if clicks >= 20 and spend > 10:
                action = "PAUSE"
                reason = f"Spent {self.currency}{spend:.2f} with {clicks} clicks but 0 orders"
            elif clicks >= 10:
                action = "LOWER BID"
                reason = f"{clicks} clicks, 0 conversions - reduce bid by 50%"
            elif impressions > 1000 and clicks < 5:
                action = "ADD NEGATIVE"
                reason = f"Low relevance: {impressions} impressions but only {clicks} clicks"
            else:
                action = "MONITOR"
                reason = f"Low data ({clicks} clicks) - needs more time"

            recommendations.append({
                "keyword": keyword,
                "spend": spend,
                "action": action,
                "reason": reason,
            })

        # High ACoS keywords
        for _, row in waste_data["high_acos"].iterrows():
            keyword = row.get("Customer Search Term", row.get("Targeting", "N/A"))
            spend = row.get("Spend", 0)
            acos = row.get("ACoS", 0)
            orders = row.get("Orders", 0)

            if acos > 300:
                action = "PAUSE"
                reason = f"ACoS {acos:.0f}% is extreme - {orders} orders not worth {self.currency}{spend:.2f}"
            else:
                target_bid = row.get("CPC", 0) * (self.target_acos / acos) if acos > 0 else 0
                action = "LOWER BID"
                reason = f"ACoS {acos:.0f}% > target {self.target_acos}% - reduce bid to ~{self.currency}{target_bid:.2f}"

            recommendations.append({
                "keyword": keyword,
                "spend": spend,
                "action": action,
                "reason": reason,
            })

        return sorted(recommendations, key=lambda x: x["spend"], reverse=True)

    def display_waste_report(self, waste_data: dict) -> None:
        """Display a rich waste report."""
        c = self.currency

        # Summary panel
        summary_table = Table(show_header=False, box=None, padding=(0, 2))
        summary_table.add_column("Metric", style="bold")
        summary_table.add_column("Value", justify="right")

        summary_table.add_row("Total Ad Spend", f"{c}{waste_data['total_spend']:,.2f}")
        summary_table.add_row(
            "Total Waste",
            f"[bold red]{c}{waste_data['total_waste']:,.2f}[/bold red]",
        )
        summary_table.add_row(
            "Waste %",
            f"[red]{waste_data['waste_pct']:.1f}%[/red]",
        )
        summary_table.add_row(
            "Zero-Order Waste",
            f"[red]{c}{waste_data['zero_order_waste']:,.2f}[/red]",
        )
        summary_table.add_row(
            f"High ACoS (>{self.waste_threshold}%) Excess",
            f"[yellow]{c}{waste_data['high_acos_waste']:,.2f}[/yellow]",
        )

        console.print(Panel(summary_table, title="Budget Waste Summary", border_style="red"))

        # Top wasters - zero orders
        if len(waste_data["zero_orders"]) > 0:
            keyword_col = "Customer Search Term" if "Customer Search Term" in waste_data["zero_orders"].columns else waste_data["zero_orders"].columns[0]
            table = Table(title="Top Keywords Spending with ZERO Orders", show_lines=True)
            table.add_column("#", width=4)
            table.add_column("Keyword", style="red", max_width=35)
            table.add_column("Spend", justify="right")
            table.add_column("Clicks", justify="right")
            table.add_column("Impressions", justify="right")
            table.add_column("CTR", justify="right")

            for i, (_, row) in enumerate(waste_data["zero_orders"].head(15).iterrows()):
                ctr = (row["Clicks"] / row["Impressions"] * 100) if row["Impressions"] > 0 else 0
                table.add_row(
                    str(i + 1),
                    str(row.get(keyword_col, "N/A"))[:35],
                    f"[red]{c}{row['Spend']:,.2f}[/red]",
                    str(int(row["Clicks"])),
                    f"{int(row['Impressions']):,}",
                    f"{ctr:.2f}%",
                )
            console.print(table)

        # Recommendations
        recs = self.get_recommendations(waste_data)
        if recs:
            rec_table = Table(title="Action Items", show_lines=True)
            rec_table.add_column("#", width=4)
            rec_table.add_column("Keyword", max_width=30)
            rec_table.add_column("Waste", justify="right")
            rec_table.add_column("Action", style="bold")
            rec_table.add_column("Reason", max_width=45)

            action_colors = {"PAUSE": "red", "LOWER BID": "yellow", "ADD NEGATIVE": "magenta", "MONITOR": "dim"}

            for i, rec in enumerate(recs[:20]):
                color = action_colors.get(rec["action"], "white")
                rec_table.add_row(
                    str(i + 1),
                    str(rec["keyword"])[:30],
                    f"{c}{rec['spend']:,.2f}",
                    f"[{color}]{rec['action']}[/{color}]",
                    rec["reason"],
                )
            console.print(rec_table)

    def get_campaign_budget_allocation(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Analyze budget allocation across campaigns."""
        if "Campaign Name" not in df.columns:
            return None

        campaign_df = df.groupby("Campaign Name").agg({
            "Spend": "sum",
            "Sales": "sum",
            "Orders": "sum",
            "Clicks": "sum",
            "Impressions": "sum",
        }).reset_index()

        campaign_df["ACoS"] = campaign_df.apply(
            lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 0, axis=1
        )
        campaign_df["ROAS"] = campaign_df.apply(
            lambda r: (r["Sales"] / r["Spend"]) if r["Spend"] > 0 else 0, axis=1
        )

        total_spend = campaign_df["Spend"].sum()
        campaign_df["Budget_Pct"] = campaign_df["Spend"] / total_spend * 100 if total_spend > 0 else 0

        return campaign_df.sort_values("Spend", ascending=False)

    def suggest_reallocation(self, campaign_df: pd.DataFrame) -> list[dict]:
        """Suggest budget reallocation between campaigns."""
        if campaign_df is None or len(campaign_df) < 2:
            return []

        suggestions = []
        total_spend = campaign_df["Spend"].sum()

        winners = campaign_df[campaign_df["ACoS"] <= self.target_acos].sort_values("ROAS", ascending=False)
        losers = campaign_df[campaign_df["ACoS"] > self.waste_threshold].sort_values("ACoS", ascending=False)

        for _, loser in losers.iterrows():
            excess = loser["Spend"] * 0.5  # Suggest moving 50% of overspending campaigns
            for _, winner in winners.iterrows():
                if excess <= 0:
                    break
                move_amount = min(excess, total_spend * 0.1)  # Cap at 10% of total
                suggestions.append({
                    "from_campaign": loser["Campaign Name"],
                    "to_campaign": winner["Campaign Name"],
                    "amount": move_amount,
                    "from_acos": loser["ACoS"],
                    "to_acos": winner["ACoS"],
                    "reason": f"Move from {loser['ACoS']:.0f}% ACoS to {winner['ACoS']:.0f}% ACoS campaign",
                })
                excess -= move_amount

        return suggestions
