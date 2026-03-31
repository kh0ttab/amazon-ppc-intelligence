"""
MER (Marketing Efficiency Ratio) & Blended ROAS Tracker — TripleWhale-style.

MER = Total Revenue (all channels) / Total Ad Spend (all channels)
Blended ROAS = same as MER but expressed as Amazon+Facebook combined ROAS
nCAC = Facebook Ad Spend / New Customers from Shopify

This is the "north star" metric for DTC + Amazon sellers:
instead of looking at Amazon PPC ROAS or Facebook ROAS in isolation,
you see the TRUE efficiency of every dollar you spend across all channels.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
import database


def get_mer_summary(days: int = 30) -> dict:
    """
    Compute MER, Blended ROAS, nCAC for the last N days.
    Uses stored data from channel_spend and shopify_orders tables.
    """
    db = database.get_db()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Total Facebook spend
    fb_row = db.execute(
        "SELECT SUM(spend) as s FROM facebook_spend WHERE spend_date >= ?", (cutoff,)
    ).fetchone()
    fb_spend = fb_row["s"] or 0.0

    # Total Amazon PPC spend
    amz_row = db.execute(
        "SELECT SUM(spend) as s FROM keyword_data WHERE report_date >= ?", (cutoff,)
    ).fetchone()
    amz_spend = amz_row["s"] or 0.0

    # Total Shopify revenue
    sh_row = db.execute(
        "SELECT SUM(revenue) as r, SUM(order_count) as o, SUM(new_customers) as nc FROM shopify_daily WHERE date >= ?",
        (cutoff,),
    ).fetchone()
    shopify_revenue = sh_row["r"] or 0.0
    shopify_orders = sh_row["o"] or 0
    new_customers = sh_row["nc"] or 0

    # Total Amazon PPC sales
    amz_sales_row = db.execute(
        "SELECT SUM(sales) as s FROM keyword_data WHERE report_date >= ?", (cutoff,)
    ).fetchone()
    amz_sales = amz_sales_row["s"] or 0.0

    db.close()

    total_spend = fb_spend + amz_spend
    total_revenue = shopify_revenue + amz_sales

    mer = round(total_revenue / total_spend, 2) if total_spend > 0 else 0
    fb_roas = round(shopify_revenue / fb_spend, 2) if fb_spend > 0 else 0
    amz_roas = round(amz_sales / amz_spend, 2) if amz_spend > 0 else 0
    blended_roas = mer  # same concept
    ncac = round(fb_spend / new_customers, 2) if new_customers > 0 else 0

    return {
        "period_days": days,
        # Spend
        "fb_spend": round(fb_spend, 2),
        "amazon_spend": round(amz_spend, 2),
        "total_spend": round(total_spend, 2),
        # Revenue
        "shopify_revenue": round(shopify_revenue, 2),
        "amazon_revenue": round(amz_sales, 2),
        "total_revenue": round(total_revenue, 2),
        # Key metrics
        "mer": mer,
        "blended_roas": blended_roas,
        "fb_roas": fb_roas,
        "amazon_roas": amz_roas,
        # Customers
        "shopify_orders": shopify_orders,
        "new_customers": new_customers,
        "ncac": ncac,
        "avg_order_value": round(shopify_revenue / shopify_orders, 2) if shopify_orders else 0,
        # Health signals
        "fb_spend_pct": round(fb_spend / total_spend * 100, 1) if total_spend else 0,
        "amazon_spend_pct": round(amz_spend / total_spend * 100, 1) if total_spend else 0,
    }


def get_mer_trend(days: int = 30) -> list[dict]:
    """Daily MER trend: {date, fb_spend, amazon_spend, shopify_revenue, amazon_revenue, mer, blended_roas}"""
    db = database.get_db()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    fb_rows = db.execute(
        "SELECT spend_date as date, SUM(spend) as fb_spend, SUM(impressions) as impressions, "
        "SUM(clicks) as clicks, SUM(purchases) as purchases, SUM(purchase_value) as fb_revenue "
        "FROM facebook_spend WHERE spend_date >= ? GROUP BY spend_date ORDER BY spend_date",
        (cutoff,),
    ).fetchall()

    sh_rows = db.execute(
        "SELECT date, SUM(revenue) as shopify_revenue, SUM(order_count) as orders "
        "FROM shopify_daily WHERE date >= ? GROUP BY date ORDER BY date",
        (cutoff,),
    ).fetchall()

    amz_rows = db.execute(
        "SELECT report_date as date, SUM(spend) as amz_spend, SUM(sales) as amz_revenue "
        "FROM keyword_data WHERE report_date >= ? AND report_date != '' GROUP BY report_date ORDER BY report_date",
        (cutoff,),
    ).fetchall()

    db.close()

    # Merge by date
    data: dict[str, dict] = {}

    for r in fb_rows:
        d = r["date"]
        data.setdefault(d, {})["date"] = d
        data[d]["fb_spend"] = round(r["fb_spend"] or 0, 2)
        data[d]["fb_purchases"] = r["purchases"] or 0
        data[d]["fb_revenue"] = round(r["fb_revenue"] or 0, 2)
        data[d]["impressions"] = r["impressions"] or 0
        data[d]["clicks"] = r["clicks"] or 0

    for r in sh_rows:
        d = r["date"]
        data.setdefault(d, {})["date"] = d
        data[d]["shopify_revenue"] = round(r["shopify_revenue"] or 0, 2)
        data[d]["shopify_orders"] = r["orders"] or 0

    for r in amz_rows:
        d = r["date"]
        data.setdefault(d, {})["date"] = d
        data[d]["amazon_spend"] = round(r["amz_spend"] or 0, 2)
        data[d]["amazon_revenue"] = round(r["amz_revenue"] or 0, 2)

    result = []
    for d, row in sorted(data.items()):
        fb_s = row.get("fb_spend", 0)
        amz_s = row.get("amazon_spend", 0)
        shopify_r = row.get("shopify_revenue", 0)
        amz_r = row.get("amazon_revenue", 0)
        total_spend = fb_s + amz_s
        total_rev = shopify_r + amz_r
        mer = round(total_rev / total_spend, 2) if total_spend > 0 else 0
        row["total_spend"] = round(total_spend, 2)
        row["total_revenue"] = round(total_rev, 2)
        row["mer"] = mer
        result.append(row)

    return result


def get_channel_breakdown(days: int = 30) -> list[dict]:
    """Per-channel spend vs revenue breakdown."""
    summary = get_mer_summary(days)
    channels = []

    if summary["fb_spend"] > 0 or summary["shopify_revenue"] > 0:
        channels.append({
            "channel": "Facebook Ads",
            "spend": summary["fb_spend"],
            "revenue": summary["shopify_revenue"],
            "roas": summary["fb_roas"],
            "spend_pct": summary["fb_spend_pct"],
        })

    if summary["amazon_spend"] > 0 or summary["amazon_revenue"] > 0:
        channels.append({
            "channel": "Amazon PPC",
            "spend": summary["amazon_spend"],
            "revenue": summary["amazon_revenue"],
            "roas": summary["amazon_roas"],
            "spend_pct": summary["amazon_spend_pct"],
        })

    return channels


def detect_anomalies(days: int = 7) -> list[dict]:
    """
    Sonar-style anomaly detection — flag when MER, spend, or ROAS
    deviates more than 20% from the prior period.
    """
    current = get_mer_summary(days)
    prior = get_mer_summary(days * 2)

    # Prior period is days*2 back; actual prior = prior - current
    # Approximate: prior period values minus current
    prior_fb = max(prior["fb_spend"] - current["fb_spend"], 0)
    prior_shopify = max(prior["shopify_revenue"] - current["shopify_revenue"], 0)

    alerts = []

    def pct_change(new, old):
        if old == 0:
            return None
        return round((new - old) / old * 100, 1)

    mer_change = pct_change(current["mer"], prior["mer"] / 2 if prior["mer"] else 0)
    fb_change = pct_change(current["fb_spend"], prior_fb)
    rev_change = pct_change(current["shopify_revenue"], prior_shopify)

    if mer_change is not None and abs(mer_change) > 20:
        alerts.append({
            "type": "MER",
            "severity": "high" if abs(mer_change) > 40 else "medium",
            "message": f"MER {'increased' if mer_change > 0 else 'dropped'} {abs(mer_change)}% vs prior period",
            "current": current["mer"],
            "change_pct": mer_change,
        })

    if fb_change is not None and fb_change > 30:
        alerts.append({
            "type": "SPEND_SPIKE",
            "severity": "medium",
            "message": f"Facebook spend up {fb_change}% vs prior {days} days",
            "current": current["fb_spend"],
            "change_pct": fb_change,
        })

    if current["mer"] < 1.0 and current["total_spend"] > 0:
        alerts.append({
            "type": "BELOW_BREAKEVEN",
            "severity": "high",
            "message": f"MER {current['mer']:.2f}x — spending more than earning across all channels",
            "current": current["mer"],
            "change_pct": None,
        })

    if current["ncac"] > 0 and current["avg_order_value"] > 0:
        if current["ncac"] > current["avg_order_value"]:
            alerts.append({
                "type": "NCAC_TOO_HIGH",
                "severity": "high",
                "message": f"nCAC ${current['ncac']:.2f} exceeds AOV ${current['avg_order_value']:.2f} — acquiring customers at a loss",
                "current": current["ncac"],
                "change_pct": None,
            })

    return alerts


def store_facebook_spend(
    spend_date: str,
    spend: float,
    impressions: int = 0,
    clicks: int = 0,
    purchases: int = 0,
    purchase_value: float = 0.0,
    reach: int = 0,
    campaign_name: str = "__total__",
) -> None:
    db = database.get_db()
    db.execute(
        """INSERT INTO facebook_spend
           (spend_date, campaign_name, spend, impressions, clicks, purchases, purchase_value, reach, synced_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(spend_date, campaign_name) DO UPDATE SET
               spend=excluded.spend, impressions=excluded.impressions,
               clicks=excluded.clicks, purchases=excluded.purchases,
               purchase_value=excluded.purchase_value, reach=excluded.reach""",
        (spend_date, campaign_name, spend, impressions, clicks, purchases, purchase_value, reach),
    )
    db.commit()
    db.close()


def store_shopify_daily(
    snapshot_date: str,
    revenue: float,
    order_count: int,
    new_customers: int = 0,
    avg_order_value: float = 0.0,
) -> None:
    db = database.get_db()
    db.execute(
        """INSERT INTO shopify_daily
           (date, revenue, order_count, new_customers, avg_order_value, synced_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(date) DO UPDATE SET
               revenue=excluded.revenue, order_count=excluded.order_count,
               new_customers=excluded.new_customers, avg_order_value=excluded.avg_order_value""",
        (snapshot_date, revenue, order_count, new_customers, avg_order_value),
    )
    db.commit()
    db.close()


def sync_facebook_data(cfg: dict) -> dict:
    """Pull Facebook spend data and store it."""
    from integrations.facebook_ads import build_client_from_config
    client = build_client_from_config(cfg)
    if not client:
        return {"error": "Facebook Ads API not configured"}
    try:
        daily = client.get_spend_by_day(days_back=30)
        for d in daily:
            store_facebook_spend(
                spend_date=d["date"],
                spend=d["spend"],
                impressions=d["impressions"],
                clicks=d["clicks"],
                purchases=d["purchases"],
                purchase_value=d["purchase_value"],
                reach=d.get("reach", 0),
            )
        return {"status": "ok", "days_synced": len(daily)}
    except Exception as e:
        return {"error": str(e)}


def sync_shopify_data(cfg: dict) -> dict:
    """Pull Shopify revenue data and store it."""
    from integrations.shopify_api import build_client_from_config
    client = build_client_from_config(cfg)
    if not client:
        return {"error": "Shopify API not configured"}
    try:
        daily = client.get_daily_revenue(days_back=30)
        for d in daily:
            store_shopify_daily(
                snapshot_date=d["date"],
                revenue=d["revenue"],
                order_count=d["orders"],
                new_customers=d["new_customers"],
                avg_order_value=d["avg_order_value"],
            )
        return {"status": "ok", "days_synced": len(daily)}
    except Exception as e:
        return {"error": str(e)}
