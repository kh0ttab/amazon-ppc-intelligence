"""Parse Amazon PPC and Sales documents in various formats."""

import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console

from ingestion.csv_reader import load_csv, load_folder

logger = logging.getLogger(__name__)
console = Console()


class DocumentParser:
    """Unified parser for Amazon PPC and Sales documents."""

    def __init__(self):
        self.loaded_data: dict[str, list[dict]] = {
            "search_term": [],
            "campaign": [],
            "business": [],
            "placement": [],
            "bulk": [],
            "unknown": [],
        }

    def load_file(self, file_path: str) -> Optional[dict]:
        """Load a single file and categorize it."""
        result = load_csv(file_path)
        if result:
            report_type = result["type"]
            self.loaded_data[report_type].append(result)
            console.print(
                f"[green]Loaded:[/green] {result['label']} - "
                f"{result['summary']['rows']} rows from {result['summary']['file']}"
            )
        return result

    def load_directory(self, folder_path: str) -> list[dict]:
        """Load all files from a directory."""
        results = load_folder(folder_path)
        for result in results:
            report_type = result["type"]
            self.loaded_data[report_type].append(result)
        return results

    def get_combined_data(self, report_type: str) -> Optional[pd.DataFrame]:
        """Get combined DataFrame for a specific report type."""
        reports = self.loaded_data.get(report_type, [])
        if not reports:
            return None
        frames = [r["data"] for r in reports]
        return pd.concat(frames, ignore_index=True)

    def get_search_term_data(self) -> Optional[pd.DataFrame]:
        """Get combined search term report data."""
        return self.get_combined_data("search_term")

    def get_campaign_data(self) -> Optional[pd.DataFrame]:
        """Get combined campaign report data."""
        return self.get_combined_data("campaign")

    def get_business_data(self) -> Optional[pd.DataFrame]:
        """Get combined business report data."""
        return self.get_combined_data("business")

    def get_placement_data(self) -> Optional[pd.DataFrame]:
        """Get combined placement report data."""
        return self.get_combined_data("placement")

    def get_summary(self) -> dict:
        """Get summary of all loaded data."""
        summary = {}
        for rtype, reports in self.loaded_data.items():
            if reports:
                total_rows = sum(r["summary"]["rows"] for r in reports)
                summary[rtype] = {
                    "files": len(reports),
                    "total_rows": total_rows,
                    "file_names": [r["summary"]["file"] for r in reports],
                }
        return summary

    def has_data(self) -> bool:
        """Check if any data has been loaded."""
        return any(len(v) > 0 for v in self.loaded_data.values())

    def clear(self) -> None:
        """Clear all loaded data."""
        for key in self.loaded_data:
            self.loaded_data[key] = []
        console.print("[yellow]All loaded data cleared.[/yellow]")
