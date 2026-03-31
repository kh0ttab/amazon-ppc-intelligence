"""TACoS trend tracker - per ASIN total advertising cost of sales over time."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()


class TACOSTracker:
    """Track TACoS trends over time per ASIN."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]

    def calculate_daily_tacos(
        self,
        ppc_data: pd.DataFrame,
        business_data: pd.DataFrame,
    ) -> Optional[pd.DataFrame]:
        """Calculate daily TACoS from combined PPC and business reports.

        Returns DataFrame with Date, Total_Spend, Total_Sales, TACoS columns.
        """
        # Find date columns
        ppc_date = self._find_date_col(ppc_data)
        biz_date = self._find_date_col(business_data)

        if ppc_date is None:
            console.print("[yellow]No date column in PPC data. TACoS trend requires dated reports.[/yellow]")
            return None

        ppc = ppc_data.copy()
        ppc["_Date"] = pd.to_datetime(ppc[ppc_date], errors="coerce")
        ppc = ppc.dropna(subset=["_Date"])
        ppc["_Date"] = ppc["_Date"].dt.date

        for col in ["Spend", "Sales"]:
            if col in ppc.columns:
                ppc[col] = pd.to_numeric(ppc[col], errors="coerce").fillna(0)

        daily_ppc = ppc.groupby("_Date").agg({"Spend": "sum", "Sales": "sum"}).reset_index()
        daily_ppc.columns = ["Date", "Ad_Spend", "PPC_Sales"]

        if biz_date is not None:
            biz = business_data.copy()
            biz["_Date"] = pd.to_datetime(biz[biz_date], errors="coerce")
            biz = biz.dropna(subset=["_Date"])
            biz["_Date"] = biz["_Date"].dt.date

            sales_col = "Ordered Product Sales" if "Ordered Product Sales" in biz.columns else "Sales"
            if sales_col in biz.columns:
                biz[sales_col] = pd.to_numeric(biz[sales_col], errors="coerce").fillna(0)

            daily_biz = biz.groupby("_Date").agg({sales_col: "sum"}).reset_index()
            daily_biz.columns = ["Date", "Total_Sales"]

            daily = daily_ppc.merge(daily_biz, on="Date", how="outer").fillna(0)
        else:
            daily = daily_ppc.copy()
            daily["Total_Sales"] = daily["PPC_Sales"]

        daily["TACoS"] = daily.apply(
            lambda r: (r["Ad_Spend"] / r["Total_Sales"] * 100) if r["Total_Sales"] > 0 else 0, axis=1
        )
        daily["ACoS"] = daily.apply(
            lambda r: (r["Ad_Spend"] / r["PPC_Sales"] * 100) if r["PPC_Sales"] > 0 else 0, axis=1
        )

        daily = daily.sort_values("Date")
        logger.info(f"TACoS trend: {len(daily)} data points calculated")
        return daily

    def calculate_asin_tacos(
        self,
        ppc_data: pd.DataFrame,
        business_data: pd.DataFrame,
    ) -> Optional[pd.DataFrame]:
        """Calculate TACoS per ASIN."""
        if "ASIN" not in business_data.columns:
            return None

        sales_col = "Ordered Product Sales" if "Ordered Product Sales" in business_data.columns else "Sales"
        orders_col = "Units Ordered" if "Units Ordered" in business_data.columns else "Orders"

        biz_asin = business_data.copy()
        for col in [sales_col, orders_col]:
            if col in biz_asin.columns:
                biz_asin[col] = pd.to_numeric(biz_asin[col], errors="coerce").fillna(0)

        biz_grouped = biz_asin.groupby("ASIN").agg({
            sales_col: "sum",
            orders_col: "sum",
        }).reset_index()
        biz_grouped.columns = ["ASIN", "Total_Sales", "Total_Orders"]

        if "ASIN" in ppc_data.columns:
            ppc_grouped = ppc_data.copy()
            for col in ["Spend", "Sales"]:
                ppc_grouped[col] = pd.to_numeric(ppc_grouped[col], errors="coerce").fillna(0)

            ppc_asin = ppc_grouped.groupby("ASIN").agg({"Spend": "sum", "Sales": "sum"}).reset_index()
            ppc_asin.columns = ["ASIN", "Ad_Spend", "PPC_Sales"]

            result = biz_grouped.merge(ppc_asin, on="ASIN", how="left").fillna(0)
        else:
            result = biz_grouped.copy()
            total_spend = pd.to_numeric(ppc_data["Spend"], errors="coerce").fillna(0).sum()
            total_ppc_sales = pd.to_numeric(ppc_data["Sales"], errors="coerce").fillna(0).sum()
            # Distribute proportionally
            if result["Total_Sales"].sum() > 0:
                result["Ad_Spend"] = result["Total_Sales"] / result["Total_Sales"].sum() * total_spend
                result["PPC_Sales"] = result["Total_Sales"] / result["Total_Sales"].sum() * total_ppc_sales
            else:
                result["Ad_Spend"] = 0
                result["PPC_Sales"] = 0

        result["TACoS"] = result.apply(
            lambda r: (r["Ad_Spend"] / r["Total_Sales"] * 100) if r["Total_Sales"] > 0 else 0, axis=1
        )
        result["Organic_Sales"] = result["Total_Sales"] - result["PPC_Sales"]
        result["Organic_Pct"] = result.apply(
            lambda r: (r["Organic_Sales"] / r["Total_Sales"] * 100) if r["Total_Sales"] > 0 else 0, axis=1
        )

        return result.sort_values("Total_Sales", ascending=False)

    def get_trend_alerts(self, daily_tacos: pd.DataFrame) -> list[dict]:
        """Generate alerts based on TACoS trends."""
        alerts = []

        if daily_tacos is None or len(daily_tacos) < 7:
            return alerts

        # Calculate weekly averages
        daily_tacos["Date"] = pd.to_datetime(daily_tacos["Date"])
        daily_tacos["Week"] = daily_tacos["Date"].dt.isocalendar().week

        weekly = daily_tacos.groupby("Week").agg({"TACoS": "mean", "Ad_Spend": "sum", "Total_Sales": "sum"}).reset_index()
        weekly = weekly.sort_values("Week")

        if len(weekly) >= 2:
            current_tacos = weekly.iloc[-1]["TACoS"]
            prev_tacos = weekly.iloc[-2]["TACoS"]
            change = current_tacos - prev_tacos

            if change > 3:
                alerts.append({
                    "type": "WARNING",
                    "message": f"TACoS increased by {change:.1f}pp week-over-week "
                               f"({prev_tacos:.1f}% -> {current_tacos:.1f}%). "
                               "Organic rank may be declining. Review keyword rankings.",
                    "severity": "high",
                })
            elif change < -3:
                alerts.append({
                    "type": "OPPORTUNITY",
                    "message": f"TACoS decreased by {abs(change):.1f}pp week-over-week "
                               f"({prev_tacos:.1f}% -> {current_tacos:.1f}%). "
                               "Organic growing! Consider reducing bids on top-ranking terms.",
                    "severity": "low",
                })

        # Check 30-day trend
        if len(daily_tacos) >= 30:
            first_half = daily_tacos.head(len(daily_tacos) // 2)["TACoS"].mean()
            second_half = daily_tacos.tail(len(daily_tacos) // 2)["TACoS"].mean()

            if second_half > first_half * 1.2:
                alerts.append({
                    "type": "WARNING",
                    "message": f"TACoS trending up over 30 days ({first_half:.1f}% -> {second_half:.1f}%). "
                               "Long-term organic decline. Investigate listing changes and ranking drops.",
                    "severity": "high",
                })

        return alerts

    def display_trend(self, daily_tacos: Optional[pd.DataFrame]) -> None:
        """Display TACoS trend as ASCII line chart."""
        if daily_tacos is None or len(daily_tacos) == 0:
            console.print("[yellow]No TACoS data available.[/yellow]")
            return

        c = self.currency

        # Summary stats
        avg_tacos = daily_tacos["TACoS"].mean()
        min_tacos = daily_tacos["TACoS"].min()
        max_tacos = daily_tacos["TACoS"].max()
        total_spend = daily_tacos["Ad_Spend"].sum()
        total_sales = daily_tacos["Total_Sales"].sum()

        summary = Table(show_header=False, box=None, padding=(0, 2))
        summary.add_column("Metric", style="bold")
        summary.add_column("Value", justify="right")

        tacos_color = "green" if avg_tacos < 15 else "yellow" if avg_tacos < 25 else "red"
        summary.add_row("Average TACoS", f"[{tacos_color}]{avg_tacos:.1f}%[/{tacos_color}]")
        summary.add_row("TACoS Range", f"{min_tacos:.1f}% - {max_tacos:.1f}%")
        summary.add_row("Total Ad Spend", f"[red]{c}{total_spend:,.2f}[/red]")
        summary.add_row("Total Revenue", f"[green]{c}{total_sales:,.2f}[/green]")
        summary.add_row("Data Points", str(len(daily_tacos)))

        console.print(Panel(summary, title="TACoS Trend Summary", border_style="blue"))

        # ASCII chart
        console.print("\n[bold]TACoS Trend Chart:[/bold]")

        chart_height = 12
        chart_width = min(len(daily_tacos), 60)

        # Resample if too many data points
        if len(daily_tacos) > chart_width:
            step = len(daily_tacos) // chart_width
            chart_data = daily_tacos.iloc[::step]["TACoS"].tolist()[:chart_width]
        else:
            chart_data = daily_tacos["TACoS"].tolist()

        if not chart_data:
            return

        max_val = max(chart_data) if max(chart_data) > 0 else 1
        min_val = min(chart_data)
        val_range = max_val - min_val if max_val != min_val else 1

        # Draw chart
        for row in range(chart_height, -1, -1):
            threshold = min_val + (val_range * row / chart_height)
            label = f"{threshold:5.1f}% │"
            line_chars = []
            for val in chart_data:
                normalized = (val - min_val) / val_range * chart_height
                if abs(normalized - row) < 0.5:
                    if val > avg_tacos * 1.2:
                        line_chars.append("[red]●[/red]")
                    elif val < avg_tacos * 0.8:
                        line_chars.append("[green]●[/green]")
                    else:
                        line_chars.append("[yellow]●[/yellow]")
                elif normalized > row:
                    line_chars.append("[dim]│[/dim]")
                else:
                    line_chars.append(" ")

            console.print(f"  {label}{''.join(line_chars)}")

        console.print(f"        └{'─' * len(chart_data)}")
        console.print(f"  [dim]     Oldest {'─' * (len(chart_data) - 12)} Newest[/dim]")

        # Alerts
        alerts = self.get_trend_alerts(daily_tacos)
        for alert in alerts:
            color = "red" if alert["severity"] == "high" else "green"
            console.print(f"\n  [{color}][{alert['type']}][/{color}] {alert['message']}")

    def display_asin_tacos(self, asin_data: Optional[pd.DataFrame]) -> None:
        """Display per-ASIN TACoS breakdown."""
        if asin_data is None or len(asin_data) == 0:
            return

        c = self.currency
        table = Table(title="TACoS by ASIN", show_lines=True)
        table.add_column("ASIN", style="cyan")
        table.add_column("Total Sales", justify="right")
        table.add_column("Ad Spend", justify="right")
        table.add_column("PPC Sales", justify="right")
        table.add_column("Organic Sales", justify="right")
        table.add_column("Organic %", justify="right")
        table.add_column("TACoS", justify="right")

        for _, row in asin_data.head(20).iterrows():
            tacos_color = "green" if row["TACoS"] < 15 else "yellow" if row["TACoS"] < 25 else "red"
            org_color = "green" if row["Organic_Pct"] > 50 else "yellow"

            table.add_row(
                str(row["ASIN"]),
                f"{c}{row['Total_Sales']:,.2f}",
                f"[red]{c}{row['Ad_Spend']:,.2f}[/red]",
                f"{c}{row['PPC_Sales']:,.2f}",
                f"[green]{c}{row['Organic_Sales']:,.2f}[/green]",
                f"[{org_color}]{row['Organic_Pct']:.1f}%[/{org_color}]",
                f"[{tacos_color}]{row['TACoS']:.1f}%[/{tacos_color}]",
            )

        console.print(table)

    def _find_date_col(self, df: pd.DataFrame) -> Optional[str]:
        """Find the date column in a DataFrame."""
        for col in df.columns:
            if col.lower() in ("date", "start date", "report date", "day"):
                return col
        return None
