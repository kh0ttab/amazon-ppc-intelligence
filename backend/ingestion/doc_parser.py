"""Document parser — wraps csv_reader, stores in DB."""

from datetime import datetime
from database import get_db
from ingestion.csv_reader import parse_file


def _safe_float(val, default=0.0):
    try:
        v = float(val)
        return v if v == v else default  # NaN check
    except (ValueError, TypeError):
        return default


def _safe_str(val):
    s = str(val) if val is not None else ""
    return "" if s == "nan" or s == "None" else s


def ingest_file(filepath: str) -> dict:
    """Parse a file and store results in the database."""
    try:
        result = parse_file(filepath)
    except Exception as e:
        return {"error": f"Parse error: {str(e)}"}

    if result is None:
        return {"error": "Could not parse file. Supported: CSV, TSV, XLSX (Amazon reports)"}

    df = result["data"]
    rtype = result["type"]
    date_range = result.get("date_range")
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO uploads (filename, report_type, rows_count, date_start, date_end, uploaded_at) VALUES (?,?,?,?,?,?)",
        (
            result["filename"], rtype, result["rows"],
            date_range["start"] if date_range else None,
            date_range["end"] if date_range else None,
            datetime.now().isoformat(),
        ),
    )
    upload_id = cur.lastrowid

    if rtype in ("search_term", "campaign"):
        kw_col = None
        for c in ["Customer Search Term", "Targeting"]:
            if c in df.columns:
                kw_col = c
                break
        date_col = "Date" if "Date" in df.columns else None

        for _, row in df.iterrows():
            cur.execute(
                """INSERT INTO keyword_data
                   (upload_id, search_term, campaign, ad_group, match_type,
                    impressions, clicks, spend, sales, orders, report_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    upload_id,
                    _safe_str(row.get(kw_col)) if kw_col else "",
                    _safe_str(row.get("Campaign Name")),
                    _safe_str(row.get("Ad Group Name")),
                    _safe_str(row.get("Match Type")),
                    _safe_float(row.get("Impressions")),
                    _safe_float(row.get("Clicks")),
                    _safe_float(row.get("Spend")),
                    _safe_float(row.get("Sales")),
                    _safe_float(row.get("Orders")),
                    _safe_str(row.get(date_col)) if date_col else "",
                ),
            )

    elif rtype == "business":
        # Business Report: may have ASIN column or be date-level aggregate
        date_col = "Date" if "Date" in df.columns else None
        sales_col = next((c for c in ["Ordered Product Sales", "Sales"] if c in df.columns), None)
        units_col = next((c for c in ["Units Ordered", "Units", "Orders"] if c in df.columns), None)
        sessions_col = "Sessions" if "Sessions" in df.columns else None
        asin_col = "ASIN" if "ASIN" in df.columns else None

        for _, row in df.iterrows():
            cur.execute(
                """INSERT INTO business_data
                   (upload_id, asin, title, sessions, units_ordered, ordered_product_sales, report_date)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    upload_id,
                    _safe_str(row.get(asin_col)) if asin_col else "",
                    _safe_str(row.get("Title")),
                    _safe_float(row.get(sessions_col)) if sessions_col else 0,
                    _safe_float(row.get(units_col)) if units_col else 0,
                    _safe_float(row.get(sales_col)) if sales_col else 0,
                    _safe_str(row.get(date_col)) if date_col else "",
                ),
            )

    conn.commit()
    conn.close()

    return {
        "upload_id": upload_id,
        "type": rtype,
        "type_label": {
            "search_term": "Sponsored Products Search Term Report",
            "campaign": "Campaign Performance Report",
            "business": "Business Report",
            "placement": "Placement Report",
            "unknown": "Unknown Report",
        }.get(rtype, rtype),
        "filename": result["filename"],
        "rows": result["rows"],
        "date_range": date_range,
    }


def ingest_ads_api_data(rows: list, data_type: str = "keyword_report") -> int:
    """
    Ingest data pulled directly from Amazon Advertising API
    (list of dicts from keyword or search-term report).
    Returns count of rows inserted.
    """
    from datetime import date as _date
    today = _date.today().isoformat()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO uploads (filename, report_type, rows_count, date_start, date_end, uploaded_at) VALUES (?,?,?,?,?,?)",
        (f"ads_api_{data_type}_{today}", data_type, len(rows), today, today, datetime.now().isoformat()),
    )
    upload_id = cur.lastrowid

    count = 0
    for row in rows:
        # Amazon Ads API field names vary slightly — handle both v2 and v3 naming
        search_term = (
            row.get("query") or row.get("keywordText") or row.get("keyword") or ""
        )
        cur.execute(
            """INSERT INTO keyword_data
               (upload_id, search_term, campaign, ad_group, match_type,
                impressions, clicks, spend, sales, orders, report_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                upload_id,
                _safe_str(search_term),
                _safe_str(row.get("campaignName")),
                _safe_str(row.get("adGroupName")),
                _safe_str(row.get("matchType")),
                _safe_float(row.get("impressions")),
                _safe_float(row.get("clicks")),
                _safe_float(row.get("cost")),
                _safe_float(row.get("attributedSales14d") or row.get("sales14d")),
                _safe_float(row.get("attributedConversions14d") or row.get("purchases14d")),
                today,
            ),
        )
        count += 1

    conn.commit()
    conn.close()
    return count
