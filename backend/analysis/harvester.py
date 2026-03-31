"""Search term harvesting pipeline."""

import csv
import io
from database import get_db


def find_harvest_candidates(
    clicks_threshold: int = 8,
    orders_threshold: int = 1,
    neg_clicks: int = 5,
    neg_spend: float = 3.0,
    target_acos: float = 25.0,
) -> dict:
    conn = get_db()
    rows = conn.execute("""
        SELECT search_term, campaign, ad_group, match_type,
               SUM(impressions) as impressions, SUM(clicks) as clicks,
               SUM(spend) as spend, SUM(sales) as sales, SUM(orders) as orders
        FROM keyword_data WHERE search_term != ''
        GROUP BY search_term, campaign, ad_group, match_type
    """).fetchall()
    conn.close()

    promote = []
    negate = []
    standalone = []

    # Campaign averages for standalone detection
    campaign_acos = {}
    for r in rows:
        d = dict(r)
        camp = d["campaign"]
        if d["sales"] > 0:
            acos = d["spend"] / d["sales"] * 100
            campaign_acos.setdefault(camp, []).append(acos)

    camp_avg = {c: sum(v) / len(v) for c, v in campaign_acos.items() if v}

    for r in rows:
        d = dict(r)
        spend = d["spend"]
        clicks = d["clicks"]
        orders = d["orders"]
        sales = d["sales"]
        acos = (spend / sales * 100) if sales > 0 else 0
        d["acos"] = round(acos, 2)
        cpc = (spend / clicks) if clicks > 0 else 0.75

        is_auto = "auto" in d["campaign"].lower()

        # Rule 1: promote to exact
        if clicks >= clicks_threshold and orders >= orders_threshold:
            d["suggested_bid"] = round(cpc * 1.2, 2)
            if is_auto:
                promote.append(d)

        # Rule 2: add as negative
        if clicks >= neg_clicks and orders == 0 and spend > neg_spend:
            negate.append(d)

        # Rule 3: standalone candidate
        if orders >= 2 and acos > 0:
            avg = camp_avg.get(d["campaign"], target_acos)
            if acos < avg * 0.7:
                d["campaign_avg_acos"] = round(avg, 1)
                d["improvement"] = round(avg - acos, 1)
                standalone.append(d)

    promote.sort(key=lambda x: x["orders"], reverse=True)
    negate.sort(key=lambda x: x["spend"], reverse=True)
    standalone.sort(key=lambda x: x.get("improvement", 0), reverse=True)

    return {
        "promote": promote[:40],
        "negate": negate[:40],
        "standalone": standalone[:20],
        "promote_count": len(promote),
        "negate_count": len(negate),
        "standalone_count": len(standalone),
        "potential_savings": round(sum(n["spend"] for n in negate), 2),
    }


def generate_bulk_csv(harvest: dict) -> str:
    """Generate Amazon-format bulk upload CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "Record Type", "Campaign Name", "Ad Group Name",
        "Keyword", "Match Type", "Bid", "State",
    ])
    writer.writeheader()

    for item in harvest.get("promote", []):
        writer.writerow({
            "Record Type": "Keyword",
            "Campaign Name": "SP - Manual Exact - Harvested",
            "Ad Group Name": "Harvested Keywords",
            "Keyword": item["search_term"],
            "Match Type": "Exact",
            "Bid": item.get("suggested_bid", ""),
            "State": "enabled",
        })

    for item in harvest.get("negate", []):
        writer.writerow({
            "Record Type": "Keyword",
            "Campaign Name": item.get("campaign", ""),
            "Ad Group Name": item.get("ad_group", ""),
            "Keyword": item["search_term"],
            "Match Type": "Negative Exact",
            "Bid": "",
            "State": "enabled",
        })

    return output.getvalue()
