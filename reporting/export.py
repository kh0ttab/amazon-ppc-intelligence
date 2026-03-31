"""Export data and reports to CSV/TXT/PDF formats."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console

from config import REPORT_DIR

logger = logging.getLogger(__name__)
console = Console()


class Exporter:
    """Export analysis data and reports to various formats."""

    def __init__(self):
        self.export_dir = REPORT_DIR

    def to_csv(self, df: pd.DataFrame, filename: str, include_timestamp: bool = True) -> Path:
        """Export DataFrame to CSV file."""
        if include_timestamp:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"{filename}_{ts}.csv"
        else:
            name = f"{filename}.csv"

        filepath = self.export_dir / name
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        console.print(f"[green]Exported CSV:[/green] {filepath}")
        logger.info(f"CSV exported: {filepath}")
        return filepath

    def to_txt(self, content: str, filename: str, include_timestamp: bool = True) -> Path:
        """Export text content to TXT file."""
        if include_timestamp:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"{filename}_{ts}.txt"
        else:
            name = f"{filename}.txt"

        filepath = self.export_dir / name
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"[green]Exported TXT:[/green] {filepath}")
        logger.info(f"TXT exported: {filepath}")
        return filepath

    def to_pdf(self, content: str, filename: str, include_timestamp: bool = True) -> Optional[Path]:
        """Export content to PDF using matplotlib for rendering."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_pdf import PdfPages
        except ImportError:
            console.print("[yellow]matplotlib not available for PDF export. Falling back to TXT.[/yellow]")
            return self.to_txt(content, filename, include_timestamp)

        if include_timestamp:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"{filename}_{ts}.pdf"
        else:
            name = f"{filename}.pdf"

        filepath = self.export_dir / name

        try:
            with PdfPages(str(filepath)) as pdf:
                # Split content into pages (roughly 50 lines per page)
                lines = content.split("\n")
                lines_per_page = 45
                pages = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)]

                for page_lines in pages:
                    fig, ax = plt.subplots(figsize=(8.5, 11))
                    ax.axis("off")
                    text = "\n".join(page_lines)
                    ax.text(
                        0.05, 0.95, text,
                        transform=ax.transAxes,
                        fontsize=8,
                        fontfamily="monospace",
                        verticalalignment="top",
                    )
                    pdf.savefig(fig, bbox_inches="tight")
                    plt.close(fig)

            console.print(f"[green]Exported PDF:[/green] {filepath}")
            logger.info(f"PDF exported: {filepath}")
            return filepath

        except Exception as e:
            console.print(f"[red]PDF export failed: {e}[/red]")
            console.print("[yellow]Falling back to TXT export.[/yellow]")
            return self.to_txt(content, filename, include_timestamp)

    def export_analyzed_keywords(self, df: pd.DataFrame, prefix: str = "keywords") -> Path:
        """Export analyzed keywords with all metrics to CSV."""
        # Select and order columns for clean export
        export_cols = []
        preferred_order = [
            "Customer Search Term", "Targeting", "Campaign Name", "Ad Group Name",
            "Match Type", "Status", "Grade", "Total_Score",
            "Impressions", "Clicks", "Spend", "Sales", "Orders",
            "ACoS", "ROAS", "CTR", "CPC", "Conv_Rate",
        ]
        for col in preferred_order:
            if col in df.columns:
                export_cols.append(col)

        # Add any remaining columns
        for col in df.columns:
            if col not in export_cols and not col.endswith("_Score"):
                export_cols.append(col)

        export_df = df[export_cols].copy()
        return self.to_csv(export_df, prefix)

    def export_waste_report(self, waste_data: dict, recommendations: list[dict]) -> Path:
        """Export waste report data to CSV."""
        rows = []
        for rec in recommendations:
            rows.append({
                "Keyword": rec["keyword"],
                "Wasted Spend": rec["spend"],
                "Action": rec["action"],
                "Reason": rec["reason"],
            })

        df = pd.DataFrame(rows)
        return self.to_csv(df, "waste_report")

    def export_bid_suggestions(self, estimates: list[dict]) -> Path:
        """Export bid suggestions to CSV."""
        df = pd.DataFrame(estimates)
        return self.to_csv(df, "bid_suggestions")
