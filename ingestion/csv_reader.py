"""Amazon report CSV parser with auto-detection of report types."""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import COLUMN_ALIASES

logger = logging.getLogger(__name__)
console = Console()

REPORT_TYPES = {
    "search_term": {
        "required": ["Customer Search Term", "Impressions", "Clicks", "Spend"],
        "label": "Sponsored Products Search Term Report",
    },
    "campaign": {
        "required": ["Campaign Name", "Impressions", "Clicks", "Spend"],
        "label": "Campaign Performance Report",
    },
    "business": {
        "required": ["ASIN", "Sessions", "Units Ordered"],
        "label": "Business Report",
    },
    "placement": {
        "required": ["Placement", "Impressions", "Clicks", "Spend"],
        "label": "Placement Performance Report",
    },
    "bulk": {
        "required": ["Record Type", "Campaign Name"],
        "label": "Bulk Operations File",
    },
}


def _normalize_column(col: str) -> str:
    """Map an Amazon column name to its canonical form using aliases."""
    col_stripped = col.strip()
    for canonical, aliases in COLUMN_ALIASES.items():
        if col_stripped in aliases:
            return canonical
    return col_stripped


def _clean_currency(val):
    """Remove currency symbols and commas from monetary values."""
    if isinstance(val, str):
        cleaned = val.replace("$", "").replace("€", "").replace("£", "").replace(",", "").replace("%", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return val
    return val


def detect_report_type(df: pd.DataFrame) -> Optional[str]:
    """Auto-detect Amazon report type by matching column headers."""
    cols = set(df.columns)
    for report_type, spec in REPORT_TYPES.items():
        if all(req in cols for req in spec["required"]):
            return report_type
    return None


def load_csv(file_path: str, encoding: str = "utf-8") -> Optional[dict]:
    """Load and parse an Amazon report CSV file.

    Returns a dict with keys: 'type', 'label', 'data' (DataFrame), 'summary'.
    """
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return None

    if not path.suffix.lower() in (".csv", ".txt", ".tsv"):
        console.print(f"[red]Unsupported file format: {path.suffix}[/red]")
        return None

    # Try different separators and encodings
    for sep in [",", "\t", ";"]:
        for enc in [encoding, "utf-8-sig", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, dtype=str, on_bad_lines="skip")
                if len(df.columns) > 1 and len(df) > 0:
                    break
            except Exception:
                df = None
                continue
        if df is not None and len(df.columns) > 1:
            break

    if df is None or len(df.columns) <= 1:
        console.print(f"[red]Could not parse file: {file_path}[/red]")
        return None

    # Normalize column names
    df.columns = [_normalize_column(c) for c in df.columns]

    # Detect report type
    report_type = detect_report_type(df)
    if report_type is None:
        console.print(f"[yellow]Warning: Could not auto-detect report type for {path.name}[/yellow]")
        console.print(f"[dim]Columns found: {', '.join(df.columns[:10])}...[/dim]")
        report_type = "unknown"
        label = "Unknown Report"
    else:
        label = REPORT_TYPES[report_type]["label"]

    # Clean numeric columns
    numeric_cols = ["Impressions", "Clicks", "Spend", "Sales", "Orders", "CPC",
                    "Sessions", "Units Ordered", "Ordered Product Sales"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(_clean_currency)
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Clean percentage columns
    pct_cols = ["ACOS", "ROAS"]
    for col in pct_cols:
        if col in df.columns:
            df[col] = df[col].apply(_clean_currency)
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    summary = {
        "file": path.name,
        "rows": len(df),
        "columns": len(df.columns),
        "type": report_type,
        "label": label,
    }

    # Try to detect date range if date columns exist
    date_cols = [c for c in df.columns if "date" in c.lower() or "day" in c.lower()]
    if date_cols:
        try:
            dates = pd.to_datetime(df[date_cols[0]], errors="coerce")
            valid_dates = dates.dropna()
            if len(valid_dates) > 0:
                summary["date_start"] = str(valid_dates.min().date())
                summary["date_end"] = str(valid_dates.max().date())
        except Exception:
            pass

    logger.info(f"Loaded {label}: {len(df)} rows from {path.name}")
    return {"type": report_type, "label": label, "data": df, "summary": summary}


def load_folder(folder_path: str) -> list[dict]:
    """Scan a folder and load all CSV/TXT files."""
    path = Path(folder_path)
    if not path.is_dir():
        console.print(f"[red]Not a directory: {folder_path}[/red]")
        return []

    results = []
    files = list(path.glob("*.csv")) + list(path.glob("*.txt")) + list(path.glob("*.tsv"))

    if not files:
        console.print(f"[yellow]No CSV/TXT files found in {folder_path}[/yellow]")
        return []

    for f in files:
        result = load_csv(str(f))
        if result:
            results.append(result)

    return results


def display_load_summary(loaded_reports: list[dict]) -> None:
    """Display a rich summary of all loaded reports."""
    table = Table(title="Loaded Reports", show_lines=True)
    table.add_column("File", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Rows", justify="right", style="green")
    table.add_column("Date Range", style="yellow")

    for report in loaded_reports:
        s = report["summary"]
        date_range = ""
        if "date_start" in s:
            date_range = f"{s['date_start']} to {s['date_end']}"
        table.add_row(s["file"], s["label"], str(s["rows"]), date_range)

    console.print(table)
