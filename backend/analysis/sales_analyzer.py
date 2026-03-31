"""PPC vs Organic sales breakdown."""

from database import get_db


def get_sales_breakdown() -> dict:
    conn = get_db()

    ppc = conn.execute("""
        SELECT COALESCE(SUM(spend),0) as spend, COALESCE(SUM(sales),0) as sales,
               COALESCE(SUM(orders),0) as orders
        FROM keyword_data
    """).fetchone()

    biz = conn.execute("""
        SELECT COALESCE(SUM(ordered_product_sales),0) as total_sales,
               COALESCE(SUM(units_ordered),0) as total_orders
        FROM business_data
    """).fetchone()
    conn.close()

    ppc_sales = dict(ppc)["sales"]
    ppc_orders = dict(ppc)["orders"]
    total_spend = dict(ppc)["spend"]
    biz_sales = dict(biz)["total_sales"]
    biz_orders = dict(biz)["total_orders"]

    total_sales = biz_sales if biz_sales > 0 else ppc_sales
    total_orders = biz_orders if biz_orders > 0 else ppc_orders

    organic_sales = max(0, total_sales - ppc_sales)
    organic_orders = max(0, total_orders - ppc_orders)

    return {
        "ppc_sales": round(ppc_sales, 2),
        "ppc_orders": int(ppc_orders),
        "organic_sales": round(organic_sales, 2),
        "organic_orders": int(organic_orders),
        "total_sales": round(total_sales, 2),
        "total_orders": int(total_orders),
        "ppc_pct": round((ppc_sales / total_sales * 100) if total_sales > 0 else 0, 1),
        "organic_pct": round((organic_sales / total_sales * 100) if total_sales > 0 else 0, 1),
        "total_spend": round(total_spend, 2),
        "tacos": round((total_spend / total_sales * 100) if total_sales > 0 else 0, 1),
    }
