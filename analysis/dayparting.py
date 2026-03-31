"""Dayparting analysis - performance by day of week and hour."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class DaypartingAnalyzer:
    """Analyze performance by day of week and time of day."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.target_acos = self.config["target_acos"]

    def analyze_by_day(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Analyze performance by day of week.

        Expects a 'Date' column to extract day of week from.
        """
        date_col = None
        for col in df.columns:
            if col.lower() in ("date", "start date", "report date", "day"):
                date_col = col
                break

        if date_col is None:
            console.print("[yellow]No date column found. Day-of-week analysis requires dated reports.[/yellow]")
            return None

        data = df.copy()
        for col in ["Spend", "Sales", "Orders", "Clicks", "Impressions"]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

        data["_Date"] = pd.to_datetime(data[date_col], errors="coerce")
        data = data.dropna(subset=["_Date"])

        if len(data) == 0:
            console.print("[yellow]Could not parse dates from the data.[/yellow]")
            return None

        data["DayOfWeek"] = data["_Date"].dt.dayofweek  # 0=Mon, 6=Sun
        data["DayName"] = data["_Date"].dt.strftime("%a")

        day_data = data.groupby(["DayOfWeek", "DayName"]).agg({
            "Spend": "sum",
            "Sales": "sum",
            "Orders": "sum",
            "Clicks": "sum",
            "Impressions": "sum",
        }).reset_index()

        day_data = day_data.sort_values("DayOfWeek")

        # Calculate metrics
        day_data["ACoS"] = day_data.apply(
            lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 0, axis=1
        )
        day_data["CVR"] = day_data.apply(
            lambda r: (r["Orders"] / r["Clicks"] * 100) if r["Clicks"] > 0 else 0, axis=1
        )
        day_data["CPC"] = day_data.apply(
            lambda r: (r["Spend"] / r["Clicks"]) if r["Clicks"] > 0 else 0, axis=1
        )

        logger.info("Day-of-week analysis completed")
        return day_data

    def analyze_by_hour(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Analyze performance by hour of day if hourly data available."""
        hour_col = None
        for col in df.columns:
            if "hour" in col.lower():
                hour_col = col
                break

        if hour_col is None:
            return None

        data = df.copy()
        for col in ["Spend", "Sales", "Orders", "Clicks", "Impressions"]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

        data["Hour"] = pd.to_numeric(data[hour_col], errors="coerce").fillna(0).astype(int)

        hour_data = data.groupby("Hour").agg({
            "Spend": "sum",
            "Sales": "sum",
            "Orders": "sum",
            "Clicks": "sum",
            "Impressions": "sum",
        }).reset_index()

        hour_data["ACoS"] = hour_data.apply(
            lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 0, axis=1
        )
        hour_data["CVR"] = hour_data.apply(
            lambda r: (r["Orders"] / r["Clicks"] * 100) if r["Clicks"] > 0 else 0, axis=1
        )

        return hour_data

    def get_bid_schedule(self, day_data: pd.DataFrame) -> list[dict]:
        """Generate bid schedule recommendations based on day/hour performance."""
        recommendations = []

        if day_data is None or len(day_data) == 0:
            return recommendations

        avg_cvr = day_data["CVR"].mean()
        avg_acos = day_data["ACoS"].mean()

        for _, row in day_data.iterrows():
            day_name = row.get("DayName", f"Day {row.get('DayOfWeek', '?')}")
            cvr = row["CVR"]
            acos = row["ACoS"]

            if acos == 0 and row["Sales"] == 0:
                adjustment = -30
                reason = "No sales on this day"
            elif cvr > avg_cvr * 1.3 and acos < self.target_acos:
                adjustment = 15
                reason = f"High CVR ({cvr:.1f}%) + good ACoS ({acos:.0f}%)"
            elif cvr > avg_cvr * 1.1:
                adjustment = 5
                reason = f"Above-avg CVR ({cvr:.1f}%)"
            elif cvr < avg_cvr * 0.7:
                adjustment = -20
                reason = f"Low CVR ({cvr:.1f}% vs avg {avg_cvr:.1f}%)"
            elif acos > self.target_acos * 1.5:
                adjustment = -25
                reason = f"High ACoS ({acos:.0f}%)"
            else:
                adjustment = 0
                reason = "Performing at average"

            recommendations.append({
                "day": day_name,
                "adjustment": adjustment,
                "reason": reason,
                "acos": acos,
                "cvr": cvr,
                "orders": row["Orders"],
                "spend": row["Spend"],
            })

        return recommendations

    def display_day_report(self, day_data: Optional[pd.DataFrame]) -> None:
        """Display day-of-week performance table and recommendations."""
        c = self.currency

        if day_data is None or len(day_data) == 0:
            console.print("[yellow]No day-of-week data available.[/yellow]")
            return

        # Performance table
        table = Table(title="Day-of-Week Performance", show_lines=True)
        table.add_column("Day", style="bold", width=6)
        table.add_column("Orders", justify="right")
        table.add_column("Spend", justify="right")
        table.add_column("Revenue", justify="right")
        table.add_column("ACoS", justify="right")
        table.add_column("CVR", justify="right")
        table.add_column("CPC", justify="right")
        table.add_column("Performance", min_width=20)

        avg_orders = day_data["Orders"].mean()

        for _, row in day_data.iterrows():
            acos_color = "green" if row["ACoS"] <= self.target_acos else "red"
            orders = row["Orders"]

            # Performance bar
            if avg_orders > 0:
                bar_len = int(orders / avg_orders * 10)
                bar_len = max(1, min(bar_len, 25))
            else:
                bar_len = 1

            if orders > avg_orders * 1.2:
                bar_color = "green"
            elif orders < avg_orders * 0.8:
                bar_color = "red"
            else:
                bar_color = "yellow"

            bar = f"[{bar_color}]{'█' * bar_len}[/{bar_color}]"

            table.add_row(
                str(row.get("DayName", "?")),
                str(int(orders)),
                f"{c}{row['Spend']:,.2f}",
                f"[green]{c}{row['Sales']:,.2f}[/green]",
                f"[{acos_color}]{row['ACoS']:.1f}%[/{acos_color}]",
                f"{row['CVR']:.1f}%",
                f"{c}{row['CPC']:.2f}",
                bar,
            )

        console.print(table)

        # Bid schedule recommendations
        schedule = self.get_bid_schedule(day_data)
        if schedule:
            sched_table = Table(title="Bid Schedule Recommendations", show_lines=True)
            sched_table.add_column("Day", style="bold", width=6)
            sched_table.add_column("Bid Adjustment", justify="center")
            sched_table.add_column("Reason")

            for s in schedule:
                adj = s["adjustment"]
                if adj > 0:
                    adj_str = f"[green]+{adj}%[/green]"
                elif adj < 0:
                    adj_str = f"[red]{adj}%[/red]"
                else:
                    adj_str = "[dim]0%[/dim]"

                sched_table.add_row(s["day"], adj_str, s["reason"])

            console.print(sched_table)

    def display_hour_heatmap(self, hour_data: Optional[pd.DataFrame]) -> None:
        """Display hourly performance heatmap in terminal."""
        if hour_data is None or len(hour_data) == 0:
            return

        console.print("\n[bold]Hourly CVR Heatmap:[/bold]")

        max_cvr = hour_data["CVR"].max() if hour_data["CVR"].max() > 0 else 1

        # Build heatmap row
        hours = list(range(24))
        header = "Hour: " + " ".join(f"{h:2d}" for h in hours)
        console.print(f"[dim]{header}[/dim]")

        heat_chars = []
        for h in hours:
            row = hour_data[hour_data["Hour"] == h]
            if len(row) > 0:
                cvr = row.iloc[0]["CVR"]
                intensity = cvr / max_cvr
                if intensity > 0.75:
                    heat_chars.append("[bold green]██[/bold green]")
                elif intensity > 0.5:
                    heat_chars.append("[green]██[/green]")
                elif intensity > 0.25:
                    heat_chars.append("[yellow]██[/yellow]")
                elif intensity > 0:
                    heat_chars.append("[red]██[/red]")
                else:
                    heat_chars.append("[dim]░░[/dim]")
            else:
                heat_chars.append("[dim]░░[/dim]")

        console.print("CVR:  " + " ".join(heat_chars))
        console.print("[dim]      ██=High CVR  ██=Good  ██=Low  ░░=None[/dim]")

        # Suggest off-peak hours
        low_cvr_hours = hour_data[hour_data["CVR"] < hour_data["CVR"].mean() * 0.5]["Hour"].tolist()
        if low_cvr_hours:
            ranges = self._format_hour_ranges(low_cvr_hours)
            console.print(f"\n[yellow]Recommended: Reduce bids 30% during {ranges}[/yellow]")

    def _format_hour_ranges(self, hours: list[int]) -> str:
        """Format a list of hours into readable ranges."""
        if not hours:
            return ""
        hours = sorted(hours)
        ranges = []
        start = hours[0]
        end = hours[0]

        for h in hours[1:]:
            if h == end + 1:
                end = h
            else:
                ranges.append(f"{start}:00-{end+1}:00")
                start = end = h
        ranges.append(f"{start}:00-{end+1}:00")
        return ", ".join(ranges)
