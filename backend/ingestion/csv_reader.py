"""Amazon report parser — handles CSV, TSV, and XLSX with real Amazon column names."""

import re
from pathlib import Path
from typing import Optional

import pandas as pd

# Map every known Amazon column name variation to a canonical short name.
# Keys are canonical. Values are all known Amazon variations (case-sensitive with trailing spaces).
COLUMN_ALIASES = {
    "Date":       ["Start Date", "Date", "Report Date", "start date"],
    "End Date":   ["End Date"],
    "Campaign Name":  ["Campaign Name", "Campaign", "campaign name"],
    "Ad Group Name":  ["Ad Group Name", "Ad Group", "ad group name"],
    "Match Type":     ["Match Type", "Keyword Match Type", "match type"],
    "Targeting":      ["Targeting", "Keyword or Product Targeting", "targeting"],
    "Customer Search Term": [
        "Customer Search Term", "Search Term", "Query",
        "customer search term", "search term",
    ],
    "Impressions": ["Impressions", "Impr.", "impressions"],
    "Clicks":      ["Clicks", "clicks"],
    "CTR":         ["Click-Thru Rate (CTR)", "Click-Through Rate", "CTR", "ctr"],
    "CPC":         [
        "Cost Per Click (CPC)", "CPC", "Cost Per Click", "Avg. CPC", "cpc",
    ],
    "Spend":       ["Spend", "Cost", "Total Spend", "spend"],
    "Sales":       [
        "7 Day Total Sales ", "7 Day Total Sales", "14 Day Total Sales",
        "Sales", "Total Advertising Sales", "sales",
    ],
    "ACOS":        [
        "Total Advertising Cost of Sales (ACOS) ",
        "Total Advertising Cost of Sales (ACOS)",
        "Total Advertising Cost of Sales (ACoS) ",
        "Total Advertising Cost of Sales (ACoS)",
        "ACOS", "ACoS", "acos",
    ],
    "ROAS":        [
        "Total Return on Advertising Spend (ROAS)",
        "Total Return on Advertising Spend (RoAS)",
        "ROAS", "roas",
    ],
    "Orders":      [
        "7 Day Total Orders (#)", "7 Day Total Orders",
        "14 Day Total Orders (#)", "14 Day Total Orders",
        "Orders", "Total Advertising Orders", "orders",
    ],
    "Units":       [
        "7 Day Total Units (#)", "7 Day Total Units",
        "Units Ordered", "Total Order Items", "units ordered",
    ],
    "Conversion Rate": [
        "7 Day Conversion Rate", "Conversion Rate", "conversion rate",
    ],
    "Advertised SKU Sales": [
        "7 Day Advertised SKU Sales ", "7 Day Advertised SKU Sales",
    ],
    "Other SKU Sales": [
        "7 Day Other SKU Sales ", "7 Day Other SKU Sales",
    ],
    # Business Report columns
    "ASIN":        ["ASIN", "asin", "(Child) ASIN", "(Parent) ASIN"],
    "Title":       ["Title", "title"],
    "Sessions":    [
        "Sessions", "Sessions - Total", "Browser Sessions", "sessions",
    ],
    "Ordered Product Sales": [
        "Ordered Product Sales", "Product Sales", "ordered product sales",
    ],
    "Units Ordered": [
        "Units Ordered", "Total Order Items", "units ordered", "total order items",
    ],
    "Page Views": [
        "Page Views - Total", "Page Views", "page views",
    ],
    # Placement
    "Placement":   ["Placement", "Placement Type", "placement"],
    # Extra
    "Portfolio":   ["Portfolio name", "Portfolio"],
    "Currency":    ["Currency"],
    "Country":     ["Country"],
    "Retailer":    ["Retailer"],
}

REPORT_SIGNATURES = {
    "search_term": ["Customer Search Term", "Impressions", "Clicks", "Spend"],
    "campaign":    ["Campaign Name", "Impressions", "Clicks", "Spend"],
    "business":    ["Ordered Product Sales", "Sessions"],
    "placement":   ["Placement", "Impressions", "Clicks", "Spend"],
}


def _normalize(col: str) -> str:
    """Map an Amazon column name to its canonical form."""
    s = col.strip()
    for canonical, aliases in COLUMN_ALIASES.items():
        # Check exact match first (some have trailing spaces)
        if s in aliases or s.strip() in [a.strip() for a in aliases]:
            return canonical
    return s


def _clean_numeric(val):
    """Remove currency symbols, commas, percent signs from a value."""
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        cleaned = (
            val.replace("$", "").replace("€", "").replace("£", "")
            .replace(",", "").replace("%", "").replace('"', "").strip()
        )
        try:
            return float(cleaned)
        except ValueError:
            return 0
    try:
        if pd.isna(val):
            return 0
    except (ValueError, TypeError):
        pass
    return 0


def detect_type(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    for rtype, required in REPORT_SIGNATURES.items():
        if all(r in cols for r in required):
            return rtype
    # Fuzzy fallback
    cols_lower = {c.lower() for c in cols}
    if any("search term" in c for c in cols_lower):
        return "search_term"
    if any("campaign" in c for c in cols_lower) and any("impression" in c for c in cols_lower):
        return "campaign"
    if any("asin" in c for c in cols_lower):
        return "business"
    return "unknown"


def _find_header_row(filepath: str, encoding: str = "utf-8") -> int:
    """Find the actual header row in a CSV file (Amazon reports have metadata rows on top)."""
    indicators = [
        "customer search term", "campaign name", "impressions",
        "targeting", "match type", "ad group", "clicks", "spend",
        "asin", "sessions", "units ordered", "placement", "start date",
    ]
    try:
        with open(filepath, "r", encoding=encoding, errors="replace") as f:
            for i, line in enumerate(f):
                lower = line.lower().strip()
                if not lower:
                    continue
                matches = sum(1 for kw in indicators if kw in lower)
                if matches >= 2:
                    return i
                if i > 20:
                    break
    except Exception:
        pass
    return 0


def parse_file(filepath: str) -> Optional[dict]:
    """Parse any Amazon report file — CSV, TSV, TXT, or XLSX."""
    path = Path(filepath)
    if not path.exists():
        return None

    ext = path.suffix.lower()
    df = None

    # ── XLSX / XLS ──
    if ext in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(path, dtype=str, engine="openpyxl" if ext == ".xlsx" else None)
        except Exception:
            try:
                df = pd.read_excel(path, dtype=str)
            except Exception:
                return None

    # ── CSV / TSV / TXT ──
    else:
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "cp1251"]:
            header_row = _find_header_row(str(path), enc)
            for sep in ["\t", ",", ";"]:
                try:
                    candidate = pd.read_csv(
                        path, sep=sep, encoding=enc, dtype=str,
                        on_bad_lines="skip", header=header_row,
                    )
                    if len(candidate.columns) > 2 and len(candidate) > 0:
                        df = candidate.dropna(how="all", axis=1)
                        break
                except Exception:
                    continue
            if df is not None:
                break

    if df is None or len(df.columns) <= 1:
        return None

    # Normalize column names — handle duplicates by appending suffix
    new_cols = []
    seen = {}
    for c in df.columns:
        norm = _normalize(c)
        if norm in seen:
            seen[norm] += 1
            new_cols.append(f"{norm}_{seen[norm]}")
        else:
            seen[norm] = 0
            new_cols.append(norm)
    df.columns = new_cols
    df = df.dropna(how="all", axis=1)

    report_type = detect_type(df)

    # Clean numeric columns
    numeric_cols = [
        "Impressions", "Clicks", "Spend", "Sales", "Orders", "CPC", "Units",
        "Sessions", "Ordered Product Sales", "Advertised SKU Sales", "Other SKU Sales",
        "Units Ordered", "Page Views",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(_clean_numeric)
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    for col in ["ACOS", "ROAS", "CTR", "Conversion Rate"]:
        if col in df.columns:
            df[col] = df[col].apply(_clean_numeric)
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Detect date range
    date_range = None
    if "Date" in df.columns:
        try:
            dates = pd.to_datetime(df["Date"], errors="coerce", format="mixed").dropna()
            if len(dates) > 0:
                date_range = {"start": str(dates.min().date()), "end": str(dates.max().date())}
        except Exception:
            pass

    return {
        "type": report_type,
        "data": df,
        "rows": len(df),
        "columns": len(df.columns),
        "filename": path.name,
        "date_range": date_range,
    }


# Keep old name as alias
parse_csv = parse_file
