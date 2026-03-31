"""Sales velocity tracker — daily and weekly units sold.

Data sources (in priority order):
1. Amazon SP-API (automatic, if configured)
2. Business Report CSV (manual upload)
3. Existing business_data table

Stores snapshots in sales_snapshots table for trending.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
import database


def get_daily_sales(days: int = 30) -> list[dict]:
    """Get daily sales from sales_snapshots table."""
    db = database.get_db()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = db.execute(
        """
        SELECT snapshot_date, SUM(units_ordered) as units, SUM(ordered_product_sales) as revenue,
               SUM(sessions) as sessions, SUM(order_count) as orders
        FROM sales_snapshots
        WHERE snapshot_date >= ?
        GROUP BY snapshot_date
        ORDER BY snapshot_date DESC
        """,
        (cutoff,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_weekly_sales(weeks: int = 12) -> list[dict]:
    """Aggregate daily snapshots into weekly buckets."""
    db = database.get_db()
    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    rows = db.execute(
        """
        SELECT
            strftime('%Y-W%W', snapshot_date) as week_label,
            MIN(snapshot_date) as week_start,
            MAX(snapshot_date) as week_end,
            SUM(units_ordered) as units,
            SUM(ordered_product_sales) as revenue,
            SUM(sessions) as sessions,
            SUM(order_count) as orders,
            ROUND(AVG(units_ordered), 1) as avg_daily_units
        FROM sales_snapshots
        WHERE snapshot_date >= ?
        GROUP BY week_label
        ORDER BY week_label DESC
        """,
        (cutoff,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_sales_velocity() -> dict:
    """Calculate sales velocity metrics for dashboard."""
    db = database.get_db()

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    week_start = (date.today() - timedelta(days=7)).isoformat()
    prev_week_start = (date.today() - timedelta(days=14)).isoformat()
    month_start = (date.today() - timedelta(days=30)).isoformat()

    def fetch_sum(start, end, field="units_ordered"):
        row = db.execute(
            f"SELECT SUM({field}) as v FROM sales_snapshots WHERE snapshot_date BETWEEN ? AND ?",
            (start, end),
        ).fetchone()
        return row["v"] or 0 if row else 0

    # Today vs yesterday
    today_units = fetch_sum(today, today)
    yesterday_units = fetch_sum(yesterday, yesterday)

    # This week vs last week
    this_week_units = fetch_sum(week_start, today)
    last_week_units = fetch_sum(prev_week_start, week_start)

    # Revenue
    today_rev = fetch_sum(today, today, "ordered_product_sales")
    week_rev = fetch_sum(week_start, today, "ordered_product_sales")
    month_rev = fetch_sum(month_start, today, "ordered_product_sales")
    month_units = fetch_sum(month_start, today)

    db.close()

    def pct_change(new, old):
        if old == 0:
            return None
        return round((new - old) / old * 100, 1)

    return {
        "today_units": today_units,
        "yesterday_units": yesterday_units,
        "today_vs_yesterday_pct": pct_change(today_units, yesterday_units),
        "this_week_units": this_week_units,
        "last_week_units": last_week_units,
        "week_over_week_pct": pct_change(this_week_units, last_week_units),
        "today_revenue": today_rev,
        "week_revenue": week_rev,
        "month_revenue": month_rev,
        "month_units": month_units,
        "avg_daily_units_30d": round(month_units / 30, 1) if month_units else 0,
        "avg_daily_revenue_30d": round(month_rev / 30, 2) if month_rev else 0,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


def store_daily_snapshot(
    snapshot_date: str,
    asin: Optional[str],
    units_ordered: float,
    ordered_product_sales: float,
    sessions: float = 0,
    order_count: int = 0,
    source: str = "manual",
) -> None:
    """Upsert a daily sales snapshot for a given ASIN (or total if asin=None)."""
    db = database.get_db()
    db.execute(
        """
        INSERT INTO sales_snapshots
            (snapshot_date, asin, units_ordered, ordered_product_sales, sessions, order_count, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_date, asin) DO UPDATE SET
            units_ordered = excluded.units_ordered,
            ordered_product_sales = excluded.ordered_product_sales,
            sessions = excluded.sessions,
            order_count = excluded.order_count,
            source = excluded.source
        """,
        (
            snapshot_date,
            asin or "__total__",
            units_ordered,
            ordered_product_sales,
            sessions,
            order_count,
            source,
            datetime.utcnow().isoformat(),
        ),
    )
    db.commit()
    db.close()


def sync_from_sp_api(cfg: dict) -> dict:
    """Pull daily/weekly sales from SP-API and store snapshots."""
    try:
        from integrations.sp_api import build_client_from_config
    except ImportError:
        return {"error": "SP-API module not available"}

    client = build_client_from_config(cfg)
    if not client:
        return {"error": "SP-API credentials not configured"}

    try:
        daily = client.get_daily_sales(days_back=30)
        stored = 0
        for d in daily:
            store_daily_snapshot(
                snapshot_date=d["date"],
                asin=None,
                units_ordered=d["units_ordered"],
                ordered_product_sales=d.get("avg_unit_price", 0) * d.get("units_ordered", 0),
                sessions=0,
                order_count=d.get("order_count", 0),
                source="sp_api",
            )
            stored += 1
        return {"status": "ok", "days_synced": stored, "source": "sp_api"}
    except Exception as e:
        return {"error": str(e)}


def sync_from_business_data() -> dict:
    """
    Backfill sales_snapshots from existing business_data table (CSV imports).
    """
    db = database.get_db()
    rows = db.execute(
        """
        SELECT report_date, asin,
               SUM(units_ordered) as units,
               SUM(ordered_product_sales) as revenue,
               SUM(sessions) as sessions
        FROM business_data
        WHERE report_date IS NOT NULL
        GROUP BY report_date, asin
        """
    ).fetchall()
    db.close()

    count = 0
    for r in rows:
        store_daily_snapshot(
            snapshot_date=r["report_date"],
            asin=r["asin"],
            units_ordered=r["units"] or 0,
            ordered_product_sales=r["revenue"] or 0,
            sessions=r["sessions"] or 0,
            order_count=0,
            source="csv_import",
        )
        count += 1

    return {"status": "ok", "rows_synced": count, "source": "business_data"}


def get_top_asins_by_sales(days: int = 30, limit: int = 10) -> list[dict]:
    """Return top ASINs by units sold in the last N days."""
    db = database.get_db()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = db.execute(
        """
        SELECT asin,
               SUM(units_ordered) as total_units,
               SUM(ordered_product_sales) as total_revenue,
               COUNT(DISTINCT snapshot_date) as days_with_data,
               ROUND(AVG(units_ordered), 1) as avg_daily_units
        FROM sales_snapshots
        WHERE snapshot_date >= ? AND asin != '__total__'
        GROUP BY asin
        ORDER BY total_units DESC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]
