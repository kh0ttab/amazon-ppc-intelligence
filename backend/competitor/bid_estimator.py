"""Bid estimation for keywords."""


def estimate_bids(keywords: list[str], avg_cpc: float = 0, competition: str = "medium",
                  bid_multiplier: float = 1.2) -> list[dict]:
    base_rates = {"low": 0.50, "medium": 1.00, "high": 1.75}
    base = avg_cpc if avg_cpc > 0 else base_rates.get(competition, 1.0)
    comp_mult = {"low": 0.8, "medium": 1.0, "high": 1.3}.get(competition, 1.0)

    results = []
    for kw in keywords:
        word_count = len(kw.split())
        length_mult = max(0.5, 1.0 - (word_count - 2) * 0.1)
        est_cpc = base * length_mult * comp_mult
        suggested = est_cpc * bid_multiplier

        if word_count <= 2:
            match = "Exact"
        elif word_count <= 4:
            match = "Phrase"
        else:
            match = "Broad"

        results.append({
            "keyword": kw,
            "estimated_cpc": round(est_cpc, 2),
            "suggested_bid": round(suggested, 2),
            "match_type": match,
            "competition": competition,
            "word_count": word_count,
        })

    return results
