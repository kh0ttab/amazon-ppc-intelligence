"""Amazon Selling Partner API (SP-API) client.

Handles:
  - Orders API  — daily/weekly units sold, revenue
  - Sales API   — order metrics with granularity (day/week)
  - Reports API — Business reports (sessions, units ordered by ASIN)

SP-API Docs: https://developer-docs.amazon.com/sp-api/

Setup:
  1. Register as developer at https://developer.amazonservices.com/
  2. Create a self-authorized app (for your own store)
  3. Note: Client ID, Client Secret, Refresh Token, Seller ID
  4. No AWS credentials needed for self-authorized apps
     (AWS SigV4 is required only for calling marketplace apps;
      self-authorized apps use LWA tokens directly via the Selling Partner API)

Marketplace endpoint mapping:
  - North America: https://sellingpartnerapi-na.amazon.com
  - Europe:        https://sellingpartnerapi-eu.amazon.com
  - Far East:      https://sellingpartnerapi-fe.amazon.com
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from typing import Optional
import requests

from .lwa_auth import get_access_token

ENDPOINTS = {
    "NA": "https://sellingpartnerapi-na.amazon.com",
    "EU": "https://sellingpartnerapi-eu.amazon.com",
    "FE": "https://sellingpartnerapi-fe.amazon.com",
}

MARKETPLACE_IDS = {
    "US": "ATVPDKIKX0DER",
    "CA": "A2EUQ1WTGCTBG2",
    "MX": "A1AM78C64UM0Y8",
    "UK": "A1F83G8C2ARO7P",
    "DE": "A1PA6795UKMFR9",
    "FR": "A13V1IB3VIYZZH",
    "IT": "APJ6JRA9NG5V4",
    "ES": "A1RKKUPIHCS9HS",
    "JP": "A1VC38T7YXB528",
    "AU": "A39IBJ37TRP1C6",
    "IN": "A21TJRUUN4KGV",
}

MARKETPLACE_TO_REGION = {
    "US": "NA", "CA": "NA", "MX": "NA",
    "UK": "EU", "DE": "EU", "FR": "EU", "IT": "EU", "ES": "EU", "IN": "EU",
    "JP": "FE", "AU": "FE",
}


class SPAPIClient:
    """Amazon Selling Partner API client (self-authorized, LWA only)."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 seller_id: str, marketplace: str = "US"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.seller_id = seller_id
        self.marketplace = marketplace
        self.marketplace_id = MARKETPLACE_IDS.get(marketplace, MARKETPLACE_IDS["US"])
        region = MARKETPLACE_TO_REGION.get(marketplace, "NA")
        self.base_url = ENDPOINTS[region]

    def _headers(self) -> dict:
        token = get_access_token(self.client_id, self.client_secret, self.refresh_token)
        return {
            "x-amz-access-token": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── Orders API ────────────────────────────────────────────

    def get_orders(
        self,
        days_back: int = 7,
        order_statuses: list = None,
    ) -> list[dict]:
        """Fetch orders from the last N days."""
        if order_statuses is None:
            order_statuses = ["Unshipped", "PartiallyShipped", "Shipped", "Canceled"]

        created_after = (datetime.utcnow() - timedelta(days=days_back)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        params = {
            "MarketplaceIds": self.marketplace_id,
            "CreatedAfter": created_after,
            "OrderStatuses": ",".join(order_statuses),
            "MaxResultsPerPage": 100,
        }
        orders = []
        next_token = None

        while True:
            if next_token:
                params["NextToken"] = next_token
            resp = requests.get(
                f"{self.base_url}/orders/v0/orders",
                headers=self._headers(),
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json().get("payload", {})
            orders.extend(payload.get("Orders", []))
            next_token = payload.get("NextToken")
            if not next_token:
                break
            time.sleep(0.5)  # rate limit

        return orders

    def get_order_items(self, order_id: str) -> list[dict]:
        """Get line items for a specific order."""
        resp = requests.get(
            f"{self.base_url}/orders/v0/orders/{order_id}/orderItems",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("payload", {}).get("OrderItems", [])

    # ── Sales API ─────────────────────────────────────────────

    def get_order_metrics(
        self,
        granularity: str = "Day",  # 'Hour' | 'Day' | 'Week' | 'Month' | 'Year' | 'Total'
        days_back: int = 30,
        asin: Optional[str] = None,
    ) -> list[dict]:
        """Get aggregated order metrics by time granularity."""
        end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=days_back)

        params = {
            "marketplaceIds": self.marketplace_id,
            "interval": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}--{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "granularity": granularity,
        }
        if asin:
            params["asin"] = asin

        resp = requests.get(
            f"{self.base_url}/sales/v1/orderMetrics",
            headers=self._headers(),
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("payload", [])

    # ── Reports API ───────────────────────────────────────────

    def request_business_report(
        self,
        report_type: str = "GET_SALES_AND_TRAFFIC_REPORT",
        days_back: int = 30,
    ) -> str:
        """Request async business report. Returns report ID."""
        end = date.today()
        start = end - timedelta(days=days_back)

        payload = {
            "reportType": report_type,
            "marketplaceIds": [self.marketplace_id],
            "dataStartTime": start.strftime("%Y-%m-%dT00:00:00Z"),
            "dataEndTime": end.strftime("%Y-%m-%dT00:00:00Z"),
        }
        if report_type == "GET_SALES_AND_TRAFFIC_REPORT":
            payload["reportOptions"] = {"dateGranularity": "DAY", "asinGranularity": "PARENT"}

        resp = requests.post(
            f"{self.base_url}/reports/2021-06-30/reports",
            headers=self._headers(),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["reportId"]

    def poll_report(self, report_id: str, max_wait: int = 300) -> Optional[str]:
        """Poll until report is done. Returns document ID."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            resp = requests.get(
                f"{self.base_url}/reports/2021-06-30/reports/{report_id}",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("processingStatus")
            if status == "DONE":
                return data["reportDocumentId"]
            elif status in ("CANCELLED", "FATAL"):
                raise RuntimeError(f"Report {report_id} failed: {status}")
            time.sleep(10)
        raise TimeoutError(f"Report not ready after {max_wait}s")

    def download_report(self, document_id: str) -> str:
        """Download a report document. Returns raw content."""
        resp = requests.get(
            f"{self.base_url}/reports/2021-06-30/documents/{document_id}",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        url = resp.json()["url"]
        dl = requests.get(url, timeout=60)
        dl.raise_for_status()
        return dl.text

    def get_daily_sales(self, days_back: int = 30) -> list[dict]:
        """
        Get daily sales metrics: units_ordered, ordered_product_sales, sessions.
        Uses Sales API orderMetrics.
        Returns list of {date, units_ordered, ordered_product_sales, avg_unit_price, session_count}
        """
        metrics = self.get_order_metrics(granularity="Day", days_back=days_back)
        result = []
        for m in metrics:
            interval = m.get("interval", "")
            day = interval.split("T")[0] if "T" in interval else interval.split("--")[0][:10]
            result.append({
                "date": day,
                "units_ordered": m.get("unitCount", 0),
                "ordered_product_sales": float(m.get("totalOrderCount", 0)),
                "avg_unit_price": float(m.get("averageSellingPrice", {}).get("amount", 0)),
                "order_count": m.get("orderCount", 0),
            })
        return result

    def get_weekly_sales(self, weeks_back: int = 12) -> list[dict]:
        """Get weekly aggregated sales metrics."""
        metrics = self.get_order_metrics(granularity="Week", days_back=weeks_back * 7)
        result = []
        for m in metrics:
            interval = m.get("interval", "")
            parts = interval.split("--")
            week_start = parts[0][:10] if parts else ""
            week_end = parts[1][:10] if len(parts) > 1 else ""
            result.append({
                "week_start": week_start,
                "week_end": week_end,
                "units_ordered": m.get("unitCount", 0),
                "order_count": m.get("orderCount", 0),
                "avg_unit_price": float(m.get("averageSellingPrice", {}).get("amount", 0)),
                "total_sales": float(m.get("totalOrderCount", 0)),
            })
        return result


def build_client_from_config(cfg: dict) -> Optional[SPAPIClient]:
    """Build SP-API client from app config. Returns None if credentials missing."""
    sp = cfg.get("sp_api", {})
    required = ["client_id", "client_secret", "refresh_token", "seller_id"]
    if not all(sp.get(k) for k in required):
        return None
    return SPAPIClient(
        client_id=sp["client_id"],
        client_secret=sp["client_secret"],
        refresh_token=sp["refresh_token"],
        seller_id=sp["seller_id"],
        marketplace=cfg.get("marketplace", "US"),
    )
