"""Report generation engine."""

from datetime import datetime
from analysis.ppc_analyzer import get_kpis, get_top_keywords, get_status_counts
from analysis.budget_analyzer import find_waste
from analysis.sales_analyzer import get_sales_breakdown


def generate_report(report_type: str = "weekly", target_acos: float = 25.0) -> dict:
    kpis = get_kpis(target_acos)
    status = get_status_counts(target_acos)
    winners = get_top_keywords(target_acos, "WINNER", 10)
    bleeders = get_top_keywords(target_acos, "BLEEDING", 10)

    report = {
        "type": report_type,
        "generated_at": datetime.now().isoformat(),
        "kpis": kpis,
        "status_counts": status,
        "top_winners": winners,
        "top_bleeders": bleeders,
    }

    if report_type == "weekly":
        report["sales_breakdown"] = get_sales_breakdown()

    if report_type in ("weekly", "budget"):
        waste = find_waste(target_acos)
        report["waste"] = {
            "total_waste": waste["total_waste"],
            "waste_pct": waste["waste_pct"],
            "zero_order_count": len(waste["zero_orders"]),
            "high_acos_count": len(waste["high_acos"]),
        }

    return report
