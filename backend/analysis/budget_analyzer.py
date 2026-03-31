"""Budget waste detection and recommendations."""

from database import get_db


def find_waste(target_acos: float = 25.0, waste_threshold: float = 150.0) -> dict:
    conn = get_db()
    rows = conn.execute("""
        SELECT search_term, campaign, ad_group, match_type,
               SUM(impressions) as impressions, SUM(clicks) as clicks,
               SUM(spend) as spend, SUM(sales) as sales, SUM(orders) as orders
        FROM keyword_data WHERE search_term != ''
        GROUP BY search_term, campaign, ad_group, match_type
    """).fetchall()
    conn.close()

    zero_orders = []
    high_acos = []

    for r in rows:
        d = dict(r)
        spend = d["spend"]
        sales = d["sales"]
        orders = d["orders"]
        clicks = d["clicks"]
        impressions = d["impressions"]
        acos = (spend / sales * 100) if sales > 0 else 0
        d["acos"] = round(acos, 2)
        d["ctr"] = round((clicks / impressions * 100) if impressions > 0 else 0, 2)

        if spend > 0 and orders == 0:
            if clicks >= 20 and spend > 10:
                d["action"] = "PAUSE"
                d["reason"] = f"Spent ${spend:.2f} with {int(clicks)} clicks, 0 orders"
            elif clicks >= 10:
                d["action"] = "LOWER BID"
                d["reason"] = f"{int(clicks)} clicks, 0 conversions — reduce bid 50%"
            elif impressions > 1000 and clicks < 5:
                d["action"] = "NEGATIVE"
                d["reason"] = f"Low relevance: {int(impressions)} impressions, {int(clicks)} clicks"
            else:
                d["action"] = "MONITOR"
                d["reason"] = f"Low data ({int(clicks)} clicks) — needs more time"
            zero_orders.append(d)

        elif orders > 0 and acos > waste_threshold:
            excess = spend - (sales * target_acos / 100)
            d["action"] = "PAUSE" if acos > 300 else "LOWER BID"
            d["reason"] = f"ACoS {acos:.0f}% >> target {target_acos}%"
            d["excess_spend"] = round(max(0, excess), 2)
            high_acos.append(d)

    zero_orders.sort(key=lambda x: x["spend"], reverse=True)
    high_acos.sort(key=lambda x: x["spend"], reverse=True)

    zero_waste = sum(z["spend"] for z in zero_orders)
    high_waste = sum(h.get("excess_spend", 0) for h in high_acos)
    total_waste = zero_waste + high_waste

    total_spend_row = get_db().execute("SELECT COALESCE(SUM(spend),0) as s FROM keyword_data").fetchone()
    total_spend = dict(total_spend_row)["s"]

    return {
        "zero_orders": zero_orders[:50],
        "high_acos": high_acos[:30],
        "zero_order_waste": round(zero_waste, 2),
        "high_acos_waste": round(high_waste, 2),
        "total_waste": round(total_waste, 2),
        "total_spend": round(total_spend, 2),
        "waste_pct": round((total_waste / total_spend * 100) if total_spend > 0 else 0, 1),
    }
