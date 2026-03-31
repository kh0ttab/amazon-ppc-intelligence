"""Keyword scoring and ranking engine."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()


class KeywordRanker:
    """Score and rank keywords based on multiple performance factors."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.target_acos = self.config["target_acos"]
        self.currency = self.config["currency"]

        # Scoring weights (total = 100)
        self.weights = {
            "revenue": 25,
            "roas": 25,
            "conversion": 20,
            "volume": 15,
            "efficiency": 15,
        }

    def score_keywords(self, df: pd.DataFrame) -> pd.DataFrame:
        """Score each keyword on a 0-100 scale based on weighted metrics."""
        result = df.copy()

        for col in ["Spend", "Sales", "Orders", "Clicks", "Impressions"]:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)

        # Calculate base metrics if not already present
        if "ROAS" not in result.columns:
            result["ROAS"] = result.apply(
                lambda r: r["Sales"] / r["Spend"] if r["Spend"] > 0 else 0, axis=1
            )
        if "Conv_Rate" not in result.columns:
            result["Conv_Rate"] = result.apply(
                lambda r: r["Orders"] / r["Clicks"] * 100 if r["Clicks"] > 0 else 0, axis=1
            )
        if "ACoS" not in result.columns:
            result["ACoS"] = result.apply(
                lambda r: r["Spend"] / r["Sales"] * 100 if r["Sales"] > 0 else 0, axis=1
            )

        # Normalize each metric to 0-100 using percentile ranking
        result["Revenue_Score"] = self._percentile_score(result["Sales"])
        result["ROAS_Score"] = self._percentile_score(result["ROAS"])
        result["Conv_Score"] = self._percentile_score(result["Conv_Rate"])
        result["Volume_Score"] = self._percentile_score(result["Clicks"])

        # Efficiency: inverse of ACoS (lower is better)
        max_acos = result["ACoS"].max()
        if max_acos > 0:
            result["Efficiency_Score"] = ((max_acos - result["ACoS"]) / max_acos * 100).clip(0, 100)
        else:
            result["Efficiency_Score"] = 50

        # Weighted total score
        result["Total_Score"] = (
            result["Revenue_Score"] * self.weights["revenue"] / 100
            + result["ROAS_Score"] * self.weights["roas"] / 100
            + result["Conv_Score"] * self.weights["conversion"] / 100
            + result["Volume_Score"] * self.weights["volume"] / 100
            + result["Efficiency_Score"] * self.weights["efficiency"] / 100
        )

        # Grade assignment
        result["Grade"] = result["Total_Score"].apply(self._assign_grade)

        return result.sort_values("Total_Score", ascending=False)

    def _percentile_score(self, series: pd.Series) -> pd.Series:
        """Convert a series to percentile-based 0-100 scores."""
        if series.max() == series.min():
            return pd.Series([50] * len(series), index=series.index)
        return series.rank(pct=True) * 100

    def _assign_grade(self, score: float) -> str:
        """Assign letter grade based on score."""
        if score >= 85:
            return "A+"
        elif score >= 75:
            return "A"
        elif score >= 65:
            return "B+"
        elif score >= 55:
            return "B"
        elif score >= 45:
            return "C+"
        elif score >= 35:
            return "C"
        elif score >= 25:
            return "D"
        else:
            return "F"

    def display_rankings(self, df: pd.DataFrame, limit: int = 20) -> None:
        """Display keyword rankings as a rich table."""
        c = self.currency
        table = Table(title="Keyword Performance Rankings", show_lines=True)
        table.add_column("Rank", width=5)
        table.add_column("Keyword", style="cyan", max_width=30)
        table.add_column("Score", justify="right", style="bold")
        table.add_column("Grade", justify="center")
        table.add_column("Revenue", justify="right")
        table.add_column("ROAS", justify="right")
        table.add_column("ACoS", justify="right")
        table.add_column("Conv%", justify="right")
        table.add_column("Clicks", justify="right")

        grade_colors = {
            "A+": "bold green", "A": "green", "B+": "cyan", "B": "blue",
            "C+": "yellow", "C": "yellow", "D": "red", "F": "bold red",
        }

        keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else df.columns[0]

        for i, (_, row) in enumerate(df.head(limit).iterrows()):
            grade = row.get("Grade", "?")
            g_color = grade_colors.get(grade, "white")
            acos_color = "green" if row.get("ACoS", 0) <= self.target_acos else "red"

            table.add_row(
                str(i + 1),
                str(row.get(keyword_col, "N/A"))[:30],
                f"{row.get('Total_Score', 0):.1f}",
                f"[{g_color}]{grade}[/{g_color}]",
                f"[green]{c}{row.get('Sales', 0):,.2f}[/green]",
                f"{row.get('ROAS', 0):.2f}x",
                f"[{acos_color}]{row.get('ACoS', 0):.1f}%[/{acos_color}]",
                f"{row.get('Conv_Rate', 0):.1f}%",
                str(int(row.get("Clicks", 0))),
            )

        console.print(table)
