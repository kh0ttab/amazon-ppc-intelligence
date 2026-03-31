"""Cross-campaign cannibalization detector."""

from database import get_db


def detect_cannibalization() -> dict:
    conn = get_db()
    rows = conn.execute("""
        SELECT search_term, campaign,
               SUM(spend) as spend, SUM(sales) as sales, SUM(orders) as orders,
               SUM(clicks) as clicks
        FROM keyword_data
        WHERE search_term != '' AND campaign != ''
        GROUP BY search_term, campaign
    """).fetchall()
    conn.close()

    # Group by search term
    term_map: dict[str, list[dict]] = {}
    for r in rows:
        d = dict(r)
        d["acos"] = round((d["spend"] / d["sales"] * 100) if d["sales"] > 0 else 999, 2)
        term_map.setdefault(d["search_term"], []).append(d)

    # Find terms in 2+ campaigns
    conflicts = []
    total_waste = 0

    for term, campaigns in term_map.items():
        if len(campaigns) < 2:
            continue

        campaigns.sort(key=lambda x: x["acos"])
        best = campaigns[0]
        duplicates = campaigns[1:]

        for dup in duplicates:
            waste = dup["spend"] * 0.20  # ~20% CPC inflation from self-bidding
            total_waste += waste
            conflicts.append({
                "search_term": term,
                "owner_campaign": best["campaign"],
                "owner_acos": best["acos"],
                "duplicate_campaign": dup["campaign"],
                "duplicate_spend": round(dup["spend"], 2),
                "duplicate_acos": dup["acos"],
                "estimated_waste": round(waste, 2),
                "action": f"Add as NEGATIVE EXACT in '{dup['campaign']}'",
            })

    conflicts.sort(key=lambda x: x["estimated_waste"], reverse=True)

    return {
        "conflicts": conflicts[:50],
        "total_waste": round(total_waste, 2),
        "affected_terms": len([t for t, c in term_map.items() if len(c) >= 2]),
    }
