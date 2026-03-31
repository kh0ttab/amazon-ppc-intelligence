"""ASIN profitability calculator - true profit after all costs."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()


class ProfitabilityCalculator:
    """Calculate true profitability per ASIN including all costs."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.cogs = self.config["cogs_per_unit"]
        self.fba_fee = self.config["fba_fee"]
        self.referral_pct = self.config["referral_fee_pct"]

    def calculate(
        self,
        business_data: pd.DataFrame,
        ppc_data: Optional[pd.DataFrame] = None,
        asin_costs: Optional[dict] = None,
    ) -> pd.DataFrame:
        """Calculate profitability per ASIN.

        Args:
            business_data: Business Report DataFrame with ASIN, Sales, Units
            ppc_data: PPC data for ad spend per ASIN (optional)
            asin_costs: Dict of ASIN -> {cogs, fba_fee} for per-ASIN costs (optional)
        """
        if "ASIN" not in business_data.columns:
            console.print("[yellow]Business data must have ASIN column.[/yellow]")
            return pd.DataFrame()

        sales_col = "Ordered Product Sales" if "Ordered Product Sales" in business_data.columns else "Sales"
        units_col = "Units Ordered" if "Units Ordered" in business_data.columns else "Orders"

        biz = business_data.copy()
        for col in [sales_col, units_col]:
            if col in biz.columns:
                biz[col] = pd.to_numeric(biz[col], errors="coerce").fillna(0)

        asin_data = biz.groupby("ASIN").agg({
            sales_col: "sum",
            units_col: "sum",
        }).reset_index()
        asin_data.columns = ["ASIN", "Revenue", "Units"]

        # Add title if available
        if "Title" in biz.columns:
            titles = biz.groupby("ASIN")["Title"].first().reset_index()
            asin_data = asin_data.merge(titles, on="ASIN", how="left")

        # Average selling price
        asin_data["ASP"] = asin_data.apply(
            lambda r: r["Revenue"] / r["Units"] if r["Units"] > 0 else 0, axis=1
        )

        # Costs per unit
        asin_data["COGS"] = asin_data["ASIN"].apply(
            lambda a: asin_costs.get(a, {}).get("cogs", self.cogs) if asin_costs else self.cogs
        )
        asin_data["FBA_Fee"] = asin_data["ASIN"].apply(
            lambda a: asin_costs.get(a, {}).get("fba_fee", self.fba_fee) if asin_costs else self.fba_fee
        )
        asin_data["Referral_Fee"] = asin_data["ASP"] * (self.referral_pct / 100)

        # Total cost per unit (before ad spend)
        asin_data["Cost_Per_Unit"] = asin_data["COGS"] + asin_data["FBA_Fee"] + asin_data["Referral_Fee"]

        # Ad spend per ASIN
        if ppc_data is not None and "ASIN" in ppc_data.columns:
            ppc_spend = ppc_data.copy()
            ppc_spend["Spend"] = pd.to_numeric(ppc_spend["Spend"], errors="coerce").fillna(0)
            ppc_asin = ppc_spend.groupby("ASIN")["Spend"].sum().reset_index()
            ppc_asin.columns = ["ASIN", "Ad_Spend"]
            asin_data = asin_data.merge(ppc_asin, on="ASIN", how="left")
        elif ppc_data is not None:
            total_ad_spend = pd.to_numeric(ppc_data["Spend"], errors="coerce").fillna(0).sum()
            total_rev = asin_data["Revenue"].sum()
            if total_rev > 0:
                asin_data["Ad_Spend"] = asin_data["Revenue"] / total_rev * total_ad_spend
            else:
                asin_data["Ad_Spend"] = 0
        else:
            asin_data["Ad_Spend"] = 0

        asin_data["Ad_Spend"] = asin_data["Ad_Spend"].fillna(0)
        asin_data["Ad_Spend_Per_Unit"] = asin_data.apply(
            lambda r: r["Ad_Spend"] / r["Units"] if r["Units"] > 0 else 0, axis=1
        )

        # Profitability
        asin_data["Total_Costs"] = (asin_data["Cost_Per_Unit"] * asin_data["Units"]) + asin_data["Ad_Spend"]
        asin_data["Net_Profit"] = asin_data["Revenue"] - asin_data["Total_Costs"]
        asin_data["Profit_Margin"] = asin_data.apply(
            lambda r: (r["Net_Profit"] / r["Revenue"] * 100) if r["Revenue"] > 0 else 0, axis=1
        )
        asin_data["Profit_Per_Unit"] = asin_data.apply(
            lambda r: r["Net_Profit"] / r["Units"] if r["Units"] > 0 else 0, axis=1
        )

        # Break-even ACoS = (ASP - COGS - FBA - Referral) / ASP * 100
        asin_data["Break_Even_ACoS"] = asin_data.apply(
            lambda r: ((r["ASP"] - r["Cost_Per_Unit"]) / r["ASP"] * 100) if r["ASP"] > 0 else 0, axis=1
        )

        # Max viable ACoS (break-even point)
        asin_data["Max_ACoS"] = asin_data["Break_Even_ACoS"]

        # Current ACoS
        asin_data["Current_ACoS"] = asin_data.apply(
            lambda r: (r["Ad_Spend"] / r["Revenue"] * 100) if r["Revenue"] > 0 else 0, axis=1
        )

        # Profitability status
        asin_data["Status"] = asin_data.apply(self._classify_profitability, axis=1)

        return asin_data.sort_values("Revenue", ascending=False)

    def _classify_profitability(self, row) -> str:
        """Classify ASIN profitability status."""
        if row["Revenue"] == 0:
            return "NO SALES"
        if row["Net_Profit"] > 0 and row["Current_ACoS"] < row["Break_Even_ACoS"] * 0.7:
            return "PROFITABLE"
        if row["Net_Profit"] > 0:
            return "MARGINAL"
        if row["Current_ACoS"] > row["Break_Even_ACoS"]:
            return "LOSING MONEY"
        return "BREAK EVEN"

    def display_report(self, profit_data: pd.DataFrame) -> None:
        """Display profitability report."""
        c = self.currency

        if len(profit_data) == 0:
            console.print("[yellow]No profitability data to display.[/yellow]")
            return

        # Portfolio summary
        total_rev = profit_data["Revenue"].sum()
        total_costs = profit_data["Total_Costs"].sum()
        total_profit = profit_data["Net_Profit"].sum()
        total_ad = profit_data["Ad_Spend"].sum()
        overall_margin = (total_profit / total_rev * 100) if total_rev > 0 else 0

        profit_color = "green" if total_profit > 0 else "red"
        margin_color = "green" if overall_margin > 15 else "yellow" if overall_margin > 0 else "red"

        summary = Table(show_header=False, box=None, padding=(0, 2))
        summary.add_column("Metric", style="bold")
        summary.add_column("Value", justify="right")

        summary.add_row("Total Revenue", f"[green]{c}{total_rev:,.2f}[/green]")
        summary.add_row("Total Costs (incl. ads)", f"[red]{c}{total_costs:,.2f}[/red]")
        summary.add_row("Total Ad Spend", f"{c}{total_ad:,.2f}")
        summary.add_row("Net Profit", f"[{profit_color}]{c}{total_profit:,.2f}[/{profit_color}]")
        summary.add_row("Overall Margin", f"[{margin_color}]{overall_margin:.1f}%[/{margin_color}]")

        losing = len(profit_data[profit_data["Status"] == "LOSING MONEY"])
        if losing > 0:
            summary.add_row("ASINs Losing Money", f"[bold red]{losing}[/bold red]")

        console.print(Panel(summary, title="Portfolio Profitability", border_style="blue"))

        # Per-ASIN table
        table = Table(title="ASIN Profitability Breakdown", show_lines=True)
        table.add_column("ASIN", style="cyan")
        table.add_column("Revenue", justify="right")
        table.add_column("Units", justify="right")
        table.add_column("ASP", justify="right")
        table.add_column("Ad Spend", justify="right")
        table.add_column("Net Profit", justify="right")
        table.add_column("Margin", justify="right")
        table.add_column("Curr ACoS", justify="right")
        table.add_column("BE ACoS", justify="right")
        table.add_column("Status", justify="center")

        status_colors = {
            "PROFITABLE": "green",
            "MARGINAL": "yellow",
            "BREAK EVEN": "dim",
            "LOSING MONEY": "bold red",
            "NO SALES": "dim",
        }

        for _, row in profit_data.head(20).iterrows():
            status = row["Status"]
            s_color = status_colors.get(status, "white")
            profit_c = "green" if row["Net_Profit"] > 0 else "red"
            acos_c = "green" if row["Current_ACoS"] < row["Break_Even_ACoS"] else "red"

            table.add_row(
                str(row["ASIN"]),
                f"{c}{row['Revenue']:,.2f}",
                str(int(row["Units"])),
                f"{c}{row['ASP']:.2f}",
                f"[red]{c}{row['Ad_Spend']:,.2f}[/red]",
                f"[{profit_c}]{c}{row['Net_Profit']:,.2f}[/{profit_c}]",
                f"[{profit_c}]{row['Profit_Margin']:.1f}%[/{profit_c}]",
                f"[{acos_c}]{row['Current_ACoS']:.1f}%[/{acos_c}]",
                f"{row['Break_Even_ACoS']:.1f}%",
                f"[{s_color}]{status}[/{s_color}]",
            )

        console.print(table)

        # Alert for losing ASINs
        losers = profit_data[profit_data["Status"] == "LOSING MONEY"]
        if len(losers) > 0:
            loss_total = abs(losers["Net_Profit"].sum())
            console.print(Panel(
                f"[bold red]WARNING:[/bold red] {len(losers)} ASINs are selling at a loss!\n"
                f"Total loss: [red]{c}{loss_total:,.2f}[/red]\n\n"
                f"[yellow]These ASINs have Current ACoS > Break-Even ACoS.\n"
                f"Either reduce ad spend, increase price, or reduce COGS.[/yellow]",
                title="Profitability Alert",
                border_style="red",
            ))
