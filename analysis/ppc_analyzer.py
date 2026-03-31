"""PPC keyword performance analysis engine."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()


class PPCAnalyzer:
    """Analyze PPC keyword and search term performance."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.target_acos = self.config["target_acos"]
        self.bleeding_threshold = self.config["bleeding_acos_threshold"]
        self.waste_threshold = self.config["waste_acos_threshold"]

    def analyze_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all PPC metrics and classify keywords.

        Expects columns: Customer Search Term, Impressions, Clicks, Spend, Sales, Orders
        Returns DataFrame with added metric and status columns.
        """
        result = df.copy()

        # Ensure numeric
        for col in ["Impressions", "Clicks", "Spend", "Sales", "Orders"]:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)

        # Calculate metrics
        result["ACoS"] = result.apply(
            lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 0, axis=1
        )
        result["ROAS"] = result.apply(
            lambda r: (r["Sales"] / r["Spend"]) if r["Spend"] > 0 else 0, axis=1
        )
        result["CTR"] = result.apply(
            lambda r: (r["Clicks"] / r["Impressions"] * 100) if r["Impressions"] > 0 else 0, axis=1
        )
        result["CPC"] = result.apply(
            lambda r: (r["Spend"] / r["Clicks"]) if r["Clicks"] > 0 else 0, axis=1
        )
        result["Conv_Rate"] = result.apply(
            lambda r: (r["Orders"] / r["Clicks"] * 100) if r["Clicks"] > 0 else 0, axis=1
        )

        # Classify status
        result["Status"] = result.apply(self._classify_keyword, axis=1)

        logger.info(f"Analyzed {len(result)} keywords/search terms")
        return result

    def _classify_keyword(self, row) -> str:
        """Classify keyword status based on performance metrics."""
        spend = row.get("Spend", 0)
        orders = row.get("Orders", 0)
        impressions = row.get("Impressions", 0)
        clicks = row.get("Clicks", 0)
        acos = row.get("ACoS", 0)

        if impressions > 0 and clicks == 0:
            return "SLEEPING"

        if spend > 0 and orders == 0:
            return "BLEEDING"

        if orders > 0 and acos <= self.target_acos:
            return "WINNER"

        if orders > 0 and acos > self.bleeding_threshold:
            return "BLEEDING"

        if orders > 0 and spend < 10 and row.get("ROAS", 0) > 1:
            return "POTENTIAL"

        if orders > 0 and acos > self.target_acos:
            return "POTENTIAL"

        if impressions == 0 and clicks == 0:
            return "NEW"

        return "POTENTIAL"

    def get_winners(self, df: pd.DataFrame) -> pd.DataFrame:
        """Get winning keywords sorted by revenue."""
        return df[df["Status"] == "WINNER"].sort_values("Sales", ascending=False)

    def get_bleeding(self, df: pd.DataFrame) -> pd.DataFrame:
        """Get bleeding keywords sorted by spend (worst first)."""
        return df[df["Status"] == "BLEEDING"].sort_values("Spend", ascending=False)

    def get_sleeping(self, df: pd.DataFrame) -> pd.DataFrame:
        """Get sleeping keywords sorted by impressions."""
        return df[df["Status"] == "SLEEPING"].sort_values("Impressions", ascending=False)

    def get_potential(self, df: pd.DataFrame) -> pd.DataFrame:
        """Get potential keywords sorted by ROAS."""
        return df[df["Status"] == "POTENTIAL"].sort_values("ROAS", ascending=False)

    def get_kpi_summary(self, df: pd.DataFrame) -> dict:
        """Calculate top-level KPIs from analyzed data."""
        return {
            "total_spend": df["Spend"].sum(),
            "total_sales": df["Sales"].sum(),
            "total_orders": df["Orders"].sum(),
            "total_impressions": df["Impressions"].sum(),
            "total_clicks": df["Clicks"].sum(),
            "overall_acos": (df["Spend"].sum() / df["Sales"].sum() * 100) if df["Sales"].sum() > 0 else 0,
            "overall_roas": (df["Sales"].sum() / df["Spend"].sum()) if df["Spend"].sum() > 0 else 0,
            "overall_ctr": (df["Clicks"].sum() / df["Impressions"].sum() * 100) if df["Impressions"].sum() > 0 else 0,
            "overall_cpc": (df["Spend"].sum() / df["Clicks"].sum()) if df["Clicks"].sum() > 0 else 0,
            "overall_conv_rate": (df["Orders"].sum() / df["Clicks"].sum() * 100) if df["Clicks"].sum() > 0 else 0,
            "winners": len(df[df["Status"] == "WINNER"]),
            "bleeding": len(df[df["Status"] == "BLEEDING"]),
            "sleeping": len(df[df["Status"] == "SLEEPING"]),
            "potential": len(df[df["Status"] == "POTENTIAL"]),
            "total_keywords": len(df),
        }

    def display_kpi_dashboard(self, kpis: dict, currency: str = "$") -> None:
        """Display a rich KPI dashboard panel."""
        c = currency
        dashboard = Table(show_header=False, box=None, padding=(0, 2))
        dashboard.add_column("Metric", style="bold")
        dashboard.add_column("Value", justify="right")
        dashboard.add_column("Metric", style="bold")
        dashboard.add_column("Value", justify="right")

        dashboard.add_row(
            "Total Spend", f"[red]{c}{kpis['total_spend']:,.2f}[/red]",
            "Total Revenue", f"[green]{c}{kpis['total_sales']:,.2f}[/green]",
        )
        dashboard.add_row(
            "Total Orders", f"[cyan]{kpis['total_orders']:,.0f}[/cyan]",
            "Total Clicks", f"[cyan]{kpis['total_clicks']:,.0f}[/cyan]",
        )

        acos_color = "green" if kpis["overall_acos"] <= self.target_acos else "red"
        dashboard.add_row(
            "ACoS", f"[{acos_color}]{kpis['overall_acos']:.1f}%[/{acos_color}]",
            "ROAS", f"[green]{kpis['overall_roas']:.2f}x[/green]",
        )
        dashboard.add_row(
            "CTR", f"[yellow]{kpis['overall_ctr']:.2f}%[/yellow]",
            "Avg CPC", f"[yellow]{c}{kpis['overall_cpc']:.2f}[/yellow]",
        )
        dashboard.add_row(
            "Conv Rate", f"[cyan]{kpis['overall_conv_rate']:.1f}%[/cyan]",
            "Impressions", f"[dim]{kpis['total_impressions']:,.0f}[/dim]",
        )

        console.print(Panel(dashboard, title="KPI Dashboard", border_style="blue"))

        # Status breakdown
        status_table = Table(title="Keyword Status Breakdown", show_lines=True)
        status_table.add_column("Status", style="bold")
        status_table.add_column("Count", justify="right")
        status_table.add_column("% of Total", justify="right")

        total = kpis["total_keywords"] or 1
        statuses = [
            ("WINNER", kpis["winners"], "green"),
            ("BLEEDING", kpis["bleeding"], "red"),
            ("SLEEPING", kpis["sleeping"], "dim"),
            ("POTENTIAL", kpis["potential"], "yellow"),
        ]
        for name, count, color in statuses:
            pct = count / total * 100
            status_table.add_row(f"[{color}]{name}[/{color}]", str(count), f"{pct:.1f}%")

        console.print(status_table)

    def display_keyword_table(self, df: pd.DataFrame, title: str, limit: int = 10,
                              currency: str = "$") -> None:
        """Display a rich table of keywords with metrics."""
        c = currency
        table = Table(title=title, show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Keyword/Search Term", style="cyan", max_width=35)
        table.add_column("Spend", justify="right")
        table.add_column("Revenue", justify="right")
        table.add_column("Orders", justify="right")
        table.add_column("ACoS", justify="right")
        table.add_column("ROAS", justify="right")
        table.add_column("CTR", justify="right")
        table.add_column("CPC", justify="right")
        table.add_column("Conv%", justify="right")
        table.add_column("Status", justify="center")

        status_colors = {
            "WINNER": "green",
            "BLEEDING": "red",
            "SLEEPING": "dim",
            "POTENTIAL": "yellow",
            "NEW": "blue",
        }

        keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else df.columns[0]

        for i, (_, row) in enumerate(df.head(limit).iterrows()):
            acos_val = row.get("ACoS", 0)
            acos_color = "green" if acos_val <= self.target_acos else "red" if acos_val > self.bleeding_threshold else "yellow"
            status = row.get("Status", "")
            s_color = status_colors.get(status, "white")

            table.add_row(
                str(i + 1),
                str(row.get(keyword_col, "N/A"))[:35],
                f"{c}{row.get('Spend', 0):,.2f}",
                f"[green]{c}{row.get('Sales', 0):,.2f}[/green]",
                str(int(row.get("Orders", 0))),
                f"[{acos_color}]{acos_val:.1f}%[/{acos_color}]",
                f"{row.get('ROAS', 0):.2f}x",
                f"{row.get('CTR', 0):.2f}%",
                f"{c}{row.get('CPC', 0):.2f}",
                f"{row.get('Conv_Rate', 0):.1f}%",
                f"[{s_color}]{status}[/{s_color}]",
            )

        console.print(table)
