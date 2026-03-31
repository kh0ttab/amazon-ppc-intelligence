"""Shopify Admin API client.

Pulls orders, revenue, customer data (new vs returning) for attribution.

Setup (Private App — simplest for your own store):
  1. Go to Shopify Admin → Settings → Apps and sales channels → Develop apps
  2. Create a private app → set API access scopes:
     - read_orders, read_customers, read_analytics, read_reports
  3. Install app → copy the Admin API access token
  4. Your store URL: yourstore.myshopify.com

API Docs: https://shopify.dev/docs/api/admin-rest
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Optional
import requests

API_VERSION = "2024-10"


class ShopifyClient:
    """Shopify Admin REST API client."""

    def __init__(self, shop_domain: str, access_token: str):
        # Normalize domain
        if not shop_domain.endswith(".myshopify.com"):
            shop_domain = f"{shop_domain}.myshopify.com"
        self.base_url = f"https://{shop_domain}/admin/api/{API_VERSION}"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: dict = None) -> dict:
        resp = requests.get(
            f"{self.base_url}/{endpoint}",
            headers=self.headers,
            params=params or {},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, endpoint: str, root_key: str, params: dict = None) -> list[dict]:
        """Cursor-based pagination for Shopify REST API."""
        results = []
        p = {"limit": 250, **(params or {})}
        url = f"{self.base_url}/{endpoint}"

        while url:
            resp = requests.get(url, headers=self.headers, params=p, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            items = data.get(root_key, [])
            results.extend(items)

            # Shopify cursor pagination via Link header
            link = resp.headers.get("Link", "")
            next_url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    break

            url = next_url
            p = {}  # URL already has all params when paginating
            if len(items) < 250:
                break

        return results

    # ── Orders ───────────────────────────────────────────────

    def get_orders(
        self,
        days_back: int = 30,
        status: str = "any",
        financial_status: str = "paid",
    ) -> list[dict]:
        """Fetch orders from last N days."""
        since = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._paginate(
            "orders.json",
            "orders",
            {
                "created_at_min": since,
                "status": status,
                "financial_status": financial_status,
                "fields": "id,created_at,total_price,subtotal_price,customer,source_name,"
                          "referring_site,landing_site,utm_parameters,total_discounts,"
                          "line_items,tags,note_attributes,customer_id",
            },
        )

    def get_daily_revenue(self, days_back: int = 30) -> list[dict]:
        """
        Aggregate daily revenue and order count from Shopify orders.
        Returns: [{date, revenue, orders, avg_order_value, new_customers, returning_customers}]
        """
        orders = self.get_orders(days_back=days_back)
        daily: dict[str, dict] = {}

        for order in orders:
            day = order.get("created_at", "")[:10]
            if not day:
                continue

            if day not in daily:
                daily[day] = {
                    "date": day,
                    "revenue": 0.0,
                    "orders": 0,
                    "new_customers": 0,
                    "returning_customers": 0,
                }

            daily[day]["revenue"] += float(order.get("total_price", 0))
            daily[day]["orders"] += 1

            # New vs returning customer
            customer = order.get("customer") or {}
            orders_count = customer.get("orders_count", 1)
            if orders_count <= 1:
                daily[day]["new_customers"] += 1
            else:
                daily[day]["returning_customers"] += 1

        result = sorted(daily.values(), key=lambda x: x["date"])
        for d in result:
            d["avg_order_value"] = round(d["revenue"] / d["orders"], 2) if d["orders"] > 0 else 0
        return result

    def get_weekly_revenue(self, weeks_back: int = 12) -> list[dict]:
        """Weekly aggregated Shopify revenue."""
        from collections import defaultdict
        from datetime import date

        orders = self.get_orders(days_back=weeks_back * 7)
        weeks: dict[str, dict] = {}

        for order in orders:
            day_str = order.get("created_at", "")[:10]
            if not day_str:
                continue
            d = date.fromisoformat(day_str)
            # ISO week label
            week = d.strftime("%Y-W%W")
            if week not in weeks:
                # Find Monday of this week
                mon = d - timedelta(days=d.weekday())
                sun = mon + timedelta(days=6)
                weeks[week] = {
                    "week_label": week,
                    "week_start": mon.isoformat(),
                    "week_end": sun.isoformat(),
                    "revenue": 0.0,
                    "orders": 0,
                    "new_customers": 0,
                }
            weeks[week]["revenue"] += float(order.get("total_price", 0))
            weeks[week]["orders"] += 1
            customer = order.get("customer") or {}
            if (customer.get("orders_count") or 1) <= 1:
                weeks[week]["new_customers"] += 1

        result = sorted(weeks.values(), key=lambda x: x["week_start"])
        for w in result:
            w["avg_order_value"] = round(w["revenue"] / w["orders"], 2) if w["orders"] > 0 else 0
        return result

    def get_customers(self, days_back: int = 30) -> list[dict]:
        """Fetch recent customers with new vs. returning info."""
        since = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._paginate(
            "customers.json",
            "customers",
            {
                "created_at_min": since,
                "fields": "id,created_at,orders_count,total_spent,tags",
            },
        )

    def get_total_revenue(self, days_back: int = 30) -> dict:
        """Quick summary: total revenue, orders, new customers in last N days."""
        daily = self.get_daily_revenue(days_back=days_back)
        total_rev = sum(d["revenue"] for d in daily)
        total_orders = sum(d["orders"] for d in daily)
        new_cust = sum(d["new_customers"] for d in daily)
        return {
            "total_revenue": round(total_rev, 2),
            "total_orders": total_orders,
            "new_customers": new_cust,
            "avg_order_value": round(total_rev / total_orders, 2) if total_orders else 0,
        }

    def get_products(self) -> list[dict]:
        """Fetch all products."""
        return self._paginate(
            "products.json",
            "products",
            {"fields": "id,title,vendor,product_type,status,variants"},
        )

    def get_utm_attribution(self, days_back: int = 30) -> list[dict]:
        """
        Extract UTM attribution from orders.
        Returns orders grouped by utm_source/utm_medium/utm_campaign.
        Facebook traffic typically shows as: utm_source=facebook, utm_medium=paid
        """
        orders = self.get_orders(days_back=days_back)
        attribution: dict[str, dict] = {}

        for order in orders:
            referring = order.get("referring_site", "") or ""
            landing = order.get("landing_site", "") or ""

            # Parse UTM from landing_site URL
            utm = _parse_utm(landing)
            source = utm.get("utm_source") or _infer_source(referring)
            medium = utm.get("utm_medium", "organic")
            campaign = utm.get("utm_campaign", "(not set)")

            key = f"{source}|{medium}|{campaign}"
            if key not in attribution:
                attribution[key] = {
                    "source": source,
                    "medium": medium,
                    "campaign": campaign,
                    "orders": 0,
                    "revenue": 0.0,
                    "new_customers": 0,
                }
            attribution[key]["orders"] += 1
            attribution[key]["revenue"] += float(order.get("total_price", 0))
            customer = order.get("customer") or {}
            if (customer.get("orders_count") or 1) <= 1:
                attribution[key]["new_customers"] += 1

        result = sorted(attribution.values(), key=lambda x: x["revenue"], reverse=True)
        for r in result:
            r["revenue"] = round(r["revenue"], 2)
        return result


def _parse_utm(url: str) -> dict:
    """Extract UTM parameters from a URL string."""
    if not url:
        return {}
    utm = {}
    for param in ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]:
        if param + "=" in url:
            try:
                val = url.split(param + "=")[1].split("&")[0].split("#")[0]
                utm[param] = val.lower()
            except IndexError:
                pass
    return utm


def _infer_source(referring_site: str) -> str:
    """Infer traffic source from referrer URL."""
    if not referring_site:
        return "direct"
    ref = referring_site.lower()
    if "facebook.com" in ref or "fb.com" in ref or "instagram.com" in ref:
        return "facebook"
    if "google.com" in ref:
        return "google"
    if "tiktok.com" in ref:
        return "tiktok"
    if "pinterest.com" in ref:
        return "pinterest"
    if "youtube.com" in ref:
        return "youtube"
    if "email" in ref or "klaviyo" in ref:
        return "email"
    return "referral"


def build_client_from_config(cfg: dict) -> Optional[ShopifyClient]:
    sh = cfg.get("shopify", {})
    required = ["shop_domain", "access_token"]
    if not all(sh.get(k) for k in required):
        return None
    return ShopifyClient(
        shop_domain=sh["shop_domain"],
        access_token=sh["access_token"],
    )
