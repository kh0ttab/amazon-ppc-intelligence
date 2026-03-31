"""Sales data analysis: PPC vs Organic breakdown."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()


class SalesAnalyzer:
    """Analyze PPC vs Organic sales breakdown."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]

    def calculate_breakdown(
        self,
        ppc_data: Optional[pd.DataFrame],
        business_data: Optional[pd.DataFrame],
    ) -> dict:
        """Calculate PPC vs Organic sales split.

        Args:
            ppc_data: Search term or campaign report DataFrame
            business_data: Business report DataFrame
        """
        result = {
            "ppc_sales": 0,
            "ppc_orders": 0,
            "total_sales": 0,
            "total_orders": 0,
            "organic_sales": 0,
            "organic_orders": 0,
            "organic_pct": 0,
            "ppc_pct": 0,
            "total_spend": 0,
            "tacos": 0,
        }

        if ppc_data is not None and "Sales" in ppc_data.columns:
            result["ppc_sales"] = ppc_data["Sales"].sum()
            result["ppc_orders"] = ppc_data["Orders"].sum() if "Orders" in ppc_data.columns else 0
            result["total_spend"] = ppc_data["Spend"].sum() if "Spend" in ppc_data.columns else 0

        if business_data is not None:
            sales_col = "Ordered Product Sales" if "Ordered Product Sales" in business_data.columns else "Sales"
            orders_col = "Units Ordered" if "Units Ordered" in business_data.columns else "Orders"

            if sales_col in business_data.columns:
                result["total_sales"] = pd.to_numeric(
                    business_data[sales_col], errors="coerce"
                ).fillna(0).sum()
            if orders_col in business_data.columns:
                result["total_orders"] = pd.to_numeric(
                    business_data[orders_col], errors="coerce"
                ).fillna(0).sum()
        else:
            # If no business report, PPC sales = total (can't determine organic)
            result["total_sales"] = result["ppc_sales"]
            result["total_orders"] = result["ppc_orders"]

        # Calculate organic
        result["organic_sales"] = max(0, result["total_sales"] - result["ppc_sales"])
        result["organic_orders"] = max(0, result["total_orders"] - result["ppc_orders"])

        # Percentages
        if result["total_sales"] > 0:
            result["organic_pct"] = result["organic_sales"] / result["total_sales"] * 100
            result["ppc_pct"] = result["ppc_sales"] / result["total_sales"] * 100
            result["tacos"] = result["total_spend"] / result["total_sales"] * 100

        logger.info(
            f"Sales breakdown: PPC={self.currency}{result['ppc_sales']:.2f}, "
            f"Organic={self.currency}{result['organic_sales']:.2f}, "
            f"TACoS={result['tacos']:.1f}%"
        )
        return result

    def display_breakdown(self, breakdown: dict) -> None:
        """Display sales breakdown as a rich panel."""
        c = self.currency

        table = Table(show_header=True, box=None, padding=(0, 3))
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Total Revenue", f"[bold green]{c}{breakdown['total_sales']:,.2f}[/bold green]")
        table.add_row("Total Orders", f"[bold]{breakdown['total_orders']:,.0f}[/bold]")
        table.add_row("", "")
        table.add_row(
            "PPC Sales",
            f"[cyan]{c}{breakdown['ppc_sales']:,.2f}[/cyan] ({breakdown['ppc_pct']:.1f}%)",
        )
        table.add_row(
            "Organic Sales",
            f"[green]{c}{breakdown['organic_sales']:,.2f}[/green] ({breakdown['organic_pct']:.1f}%)",
        )
        table.add_row("", "")
        table.add_row("Ad Spend", f"[red]{c}{breakdown['total_spend']:,.2f}[/red]")

        tacos_color = "green" if breakdown["tacos"] < 15 else "yellow" if breakdown["tacos"] < 25 else "red"
        table.add_row("TACoS", f"[{tacos_color}]{breakdown['tacos']:.1f}%[/{tacos_color}]")

        console.print(Panel(table, title="PPC vs Organic Sales Breakdown", border_style="blue"))

        # Visual bar
        if breakdown["total_sales"] > 0:
            ppc_bars = int(breakdown["ppc_pct"] / 2)
            org_bars = int(breakdown["organic_pct"] / 2)
            bar = f"[cyan]{'█' * ppc_bars}[/cyan][green]{'█' * org_bars}[/green]"
            console.print(f"\n  {bar}")
            console.print(f"  [cyan]█ PPC ({breakdown['ppc_pct']:.1f}%)[/cyan]  "
                          f"[green]█ Organic ({breakdown['organic_pct']:.1f}%)[/green]\n")

    def get_asin_breakdown(
        self,
        ppc_data: Optional[pd.DataFrame],
        business_data: Optional[pd.DataFrame],
    ) -> Optional[pd.DataFrame]:
        """Get per-ASIN PPC vs Organic breakdown if ASIN data available."""
        if business_data is None or "ASIN" not in business_data.columns:
            return None

        sales_col = "Ordered Product Sales" if "Ordered Product Sales" in business_data.columns else "Sales"
        orders_col = "Units Ordered" if "Units Ordered" in business_data.columns else "Orders"

        asin_df = business_data.groupby("ASIN").agg({
            sales_col: "sum",
            orders_col: "sum",
        }).reset_index()
        asin_df.columns = ["ASIN", "Total_Sales", "Total_Orders"]

        if ppc_data is not None and "ASIN" in ppc_data.columns:
            ppc_asin = ppc_data.groupby("ASIN").agg({
                "Sales": "sum",
                "Spend": "sum",
            }).reset_index()
            ppc_asin.columns = ["ASIN", "PPC_Sales", "PPC_Spend"]
            asin_df = asin_df.merge(ppc_asin, on="ASIN", how="left")
        else:
            asin_df["PPC_Sales"] = 0
            asin_df["PPC_Spend"] = 0

        asin_df = asin_df.fillna(0)
        asin_df["Organic_Sales"] = asin_df["Total_Sales"] - asin_df["PPC_Sales"]
        asin_df["Organic_Pct"] = asin_df.apply(
            lambda r: (r["Organic_Sales"] / r["Total_Sales"] * 100) if r["Total_Sales"] > 0 else 0,
            axis=1,
        )

        return asin_df.sort_values("Total_Sales", ascending=False)
