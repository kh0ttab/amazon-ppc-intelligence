"""PPC keyword performance analysis engine with date filtering."""

from database import get_db


def _classify(row: dict, target_acos: float) -> str:
    spend = row["spend"]
    orders = row["orders"]
    impressions = row["impressions"]
    clicks = row["clicks"]
    acos = row["acos"]

    if impressions > 0 and clicks == 0:
        return "SLEEPING"
    if spend > 0 and orders == 0:
        return "BLEEDING"
    if orders > 0 and acos <= target_acos:
        return "WINNER"
    if orders > 0 and acos > target_acos * 3:
        return "BLEEDING"
    if orders > 0 and spend < 10 and (row["sales"] / spend if spend > 0 else 0) > 1:
        return "POTENTIAL"
    if orders > 0:
        return "POTENTIAL"
    if impressions == 0:
        return "NEW"
    return "POTENTIAL"


def _date_filter_sql(date_from: str = None, date_to: str = None) -> tuple[str, list]:
    """Build WHERE clause for date filtering."""
    clauses = []
    params = []
    if date_from:
        clauses.append("report_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("report_date <= ?")
        params.append(date_to)
    sql = (" AND " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def analyze_keywords(target_acos: float = 25.0, filters: dict | None = None) -> list[dict]:
    conn = get_db()
    date_sql, date_params = _date_filter_sql(
        filters.get("date_from") if filters else None,
        filters.get("date_to") if filters else None,
    )

    query = f"""
        SELECT search_term, campaign, ad_group, match_type,
               SUM(impressions) as impressions, SUM(clicks) as clicks,
               SUM(spend) as spend, SUM(sales) as sales, SUM(orders) as orders,
               MIN(report_date) as first_date, MAX(report_date) as last_date
        FROM keyword_data
        WHERE search_term != '' {date_sql}
    """
    params = list(date_params)
    if filters:
        if filters.get("campaign"):
            query += " AND campaign = ?"
            params.append(filters["campaign"])
    query += " GROUP BY search_term, campaign, ad_group, match_type"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        spend = d["spend"]
        sales = d["sales"]
        clicks = d["clicks"]
        impressions = d["impressions"]
        orders = d["orders"]

        d["acos"] = round((spend / sales * 100) if sales > 0 else 0, 2)
        d["roas"] = round((sales / spend) if spend > 0 else 0, 2)
        d["ctr"] = round((clicks / impressions * 100) if impressions > 0 else 0, 2)
        d["cpc"] = round((spend / clicks) if clicks > 0 else 0, 2)
        d["cvr"] = round((orders / clicks * 100) if clicks > 0 else 0, 2)
        d["status"] = _classify(d, target_acos)
        results.append(d)

    if filters and filters.get("status"):
        results = [r for r in results if r["status"] == filters["status"]]

    return results


def get_kpis(target_acos: float = 25.0, date_from: str = None, date_to: str = None) -> dict:
    conn = get_db()
    date_sql, date_params = _date_filter_sql(date_from, date_to)

    row = conn.execute(f"""
        SELECT COALESCE(SUM(spend),0) as total_spend,
               COALESCE(SUM(sales),0) as total_sales,
               COALESCE(SUM(orders),0) as total_orders,
               COALESCE(SUM(clicks),0) as total_clicks,
               COALESCE(SUM(impressions),0) as total_impressions,
               COUNT(DISTINCT search_term) as total_keywords
        FROM keyword_data WHERE search_term != '' {date_sql}
    """, date_params).fetchone()

    biz_date_sql = date_sql.replace("report_date", "report_date")
    biz = conn.execute(f"""
        SELECT COALESCE(SUM(ordered_product_sales),0) as total_biz_sales,
               COALESCE(SUM(units_ordered),0) as total_biz_orders
        FROM business_data WHERE 1=1 {biz_date_sql}
    """, date_params).fetchone()
    conn.close()

    d = dict(row)
    spend = d["total_spend"]
    sales = d["total_sales"]
    clicks = d["total_clicks"]
    impressions = d["total_impressions"]
    ppc_orders = d["total_orders"]
    biz_d = dict(biz)
    biz_sales = biz_d["total_biz_sales"]
    biz_orders = biz_d["total_biz_orders"]

    total_revenue = biz_sales if biz_sales > 0 else sales
    total_orders = biz_orders if biz_orders > 0 else ppc_orders
    organic_sales = max(0, total_revenue - sales)
    organic_orders = max(0, total_orders - ppc_orders)

    return {
        "total_spend": round(spend, 2),
        "total_sales": round(sales, 2),
        "total_orders": int(total_orders),
        "ppc_orders": int(ppc_orders),
        "organic_orders": int(organic_orders),
        "total_clicks": int(clicks),
        "total_impressions": int(impressions),
        "total_keywords": d["total_keywords"],
        "acos": round((spend / sales * 100) if sales > 0 else 0, 1),
        "roas": round((sales / spend) if spend > 0 else 0, 2),
        "ctr": round((clicks / impressions * 100) if impressions > 0 else 0, 2),
        "cpc": round((spend / clicks) if clicks > 0 else 0, 2),
        "cvr": round((ppc_orders / clicks * 100) if clicks > 0 else 0, 1),
        "tacos": round((spend / total_revenue * 100) if total_revenue > 0 else 0, 1),
        "organic_sales": round(organic_sales, 2),
        "ppc_sales": round(sales, 2),
        "total_revenue": round(total_revenue, 2),
        "organic_pct": round((organic_sales / total_revenue * 100) if total_revenue > 0 else 0, 1),
        "ppc_pct": round((sales / total_revenue * 100) if total_revenue > 0 else 0, 1),
    }


def get_status_counts(target_acos: float = 25.0) -> dict:
    keywords = analyze_keywords(target_acos)
    counts = {"WINNER": 0, "BLEEDING": 0, "SLEEPING": 0, "POTENTIAL": 0, "NEW": 0}
    for kw in keywords:
        counts[kw["status"]] = counts.get(kw["status"], 0) + 1
    return counts


def get_top_keywords(target_acos: float = 25.0, status: str = "WINNER", limit: int = 5) -> list[dict]:
    keywords = analyze_keywords(target_acos)
    filtered = [k for k in keywords if k["status"] == status]
    sort_key = "sales" if status == "WINNER" else "spend"
    filtered.sort(key=lambda x: x[sort_key], reverse=True)
    return filtered[:limit]


def get_date_ranges() -> list[dict]:
    """Get all available date ranges from uploaded data."""
    conn = get_db()
    uploads = conn.execute("""
        SELECT id, filename, report_type, rows_count, date_start, date_end, uploaded_at
        FROM uploads ORDER BY uploaded_at DESC
    """).fetchall()

    # Also get the actual min/max dates from data
    kw_range = conn.execute("""
        SELECT MIN(report_date) as min_date, MAX(report_date) as max_date
        FROM keyword_data WHERE report_date != ''
    """).fetchone()

    biz_range = conn.execute("""
        SELECT MIN(report_date) as min_date, MAX(report_date) as max_date
        FROM business_data WHERE report_date != ''
    """).fetchone()

    # Get distinct weeks
    weeks = conn.execute("""
        SELECT DISTINCT strftime('%Y-W%W', report_date) as week,
               MIN(report_date) as week_start, MAX(report_date) as week_end,
               SUM(spend) as spend, SUM(sales) as sales, SUM(orders) as orders
        FROM keyword_data
        WHERE report_date != ''
        GROUP BY week
        ORDER BY week DESC
    """).fetchall()
    conn.close()

    kw_d = dict(kw_range) if kw_range else {}
    biz_d = dict(biz_range) if biz_range else {}

    return {
        "uploads": [dict(u) for u in uploads],
        "keyword_range": {"min": kw_d.get("min_date"), "max": kw_d.get("max_date")},
        "business_range": {"min": biz_d.get("min_date"), "max": biz_d.get("max_date")},
        "weeks": [dict(w) for w in weeks],
    }
