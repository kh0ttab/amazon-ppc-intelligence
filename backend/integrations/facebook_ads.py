"""Facebook Marketing API client.

Pulls ad spend, performance, and creative data from Facebook/Meta Ads.

Setup:
  1. Go to developers.facebook.com → Create App → Business type
  2. Add Marketing API product
  3. Get your App ID, App Secret
  4. Generate a long-lived User Access Token:
     - Short-lived token (from Graph API Explorer) → exchange for 60-day token
     - POST https://graph.facebook.com/oauth/access_token
       ?grant_type=fb_exchange_token&client_id={APP_ID}&client_secret={APP_SECRET}
       &fb_exchange_token={SHORT_TOKEN}
  5. Get your Ad Account ID from Business Manager → Ad Accounts
     Format: "act_1234567890"

Docs: https://developers.facebook.com/docs/marketing-api/insights
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Optional
import requests

GRAPH_URL = "https://graph.facebook.com/v21.0"

# Key metrics to pull from insights
INSIGHT_METRICS = [
    "spend",
    "impressions",
    "clicks",
    "ctr",
    "cpc",
    "cpp",
    "reach",
    "frequency",
    "actions",          # conversions (purchases, add_to_cart, etc.)
    "action_values",    # revenue attributed to purchases
    "roas",             # purchase ROAS from Meta
    "cost_per_action_type",
    "inline_link_clicks",
    "website_purchase_roas",
    "purchase_roas",
    "conversions",
    "conversion_values",
]

# Creative fields
CREATIVE_FIELDS = [
    "id", "name", "title", "body", "image_url",
    "thumbnail_url", "object_type", "effective_object_story_id",
]


class FacebookAdsClient:
    """Meta Marketing API client."""

    def __init__(self, access_token: str, ad_account_id: str, app_id: str = "", app_secret: str = ""):
        self.access_token = access_token
        # Ensure account ID has act_ prefix
        self.ad_account_id = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"
        self.app_id = app_id
        self.app_secret = app_secret

    def _get(self, endpoint: str, params: dict = None) -> dict:
        p = {"access_token": self.access_token}
        if params:
            p.update(params)
        resp = requests.get(f"{GRAPH_URL}/{endpoint}", params=p, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Facebook API error: {data['error'].get('message', data['error'])}")
        return data

    def _paginate(self, endpoint: str, params: dict = None) -> list[dict]:
        """Fetch all pages from a paginated endpoint."""
        results = []
        p = {"access_token": self.access_token, "limit": 500}
        if params:
            p.update(params)
        url = f"{GRAPH_URL}/{endpoint}"

        while url:
            resp = requests.get(url, params=p, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"Facebook API error: {data['error'].get('message')}")
            results.extend(data.get("data", []))
            paging = data.get("paging", {})
            url = paging.get("next")
            p = {}  # next URL already has params
        return results

    # ── Account Info ──────────────────────────────────────────

    def get_account_info(self) -> dict:
        return self._get(self.ad_account_id, {"fields": "id,name,currency,timezone_name,account_status"})

    # ── Campaigns ────────────────────────────────────────────

    def get_campaigns(self, status: str = "ACTIVE") -> list[dict]:
        return self._paginate(
            f"{self.ad_account_id}/campaigns",
            {"fields": "id,name,status,objective,daily_budget,lifetime_budget,start_time,stop_time", "effective_status": [status]},
        )

    # ── Insights (spend + performance) ────────────────────────

    def get_account_insights(
        self,
        days_back: int = 30,
        breakdown: str = "day",  # 'day' | 'week' | 'month'
    ) -> list[dict]:
        """Account-level daily spend + performance."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days_back)
        return self._paginate(
            f"{self.ad_account_id}/insights",
            {
                "fields": ",".join(INSIGHT_METRICS),
                "time_increment": 1 if breakdown == "day" else (7 if breakdown == "week" else "monthly"),
                "time_range": f'{{"since":"{start}","until":"{end}"}}',
                "level": "account",
            },
        )

    def get_campaign_insights(self, days_back: int = 30) -> list[dict]:
        """Per-campaign spend + ROAS breakdown."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days_back)
        return self._paginate(
            f"{self.ad_account_id}/insights",
            {
                "fields": ",".join(INSIGHT_METRICS) + ",campaign_name,campaign_id",
                "time_increment": 1,
                "time_range": f'{{"since":"{start}","until":"{end}"}}',
                "level": "campaign",
            },
        )

    def get_ad_insights(self, days_back: int = 14) -> list[dict]:
        """Per-ad (creative-level) spend + performance for Creative Cockpit."""
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days_back)
        return self._paginate(
            f"{self.ad_account_id}/insights",
            {
                "fields": ",".join(INSIGHT_METRICS) + ",ad_name,ad_id,adset_name,campaign_name,creative{thumbnail_url,title,body,image_url}",
                "time_increment": "all_days",
                "time_range": f'{{"since":"{start}","until":"{end}"}}',
                "level": "ad",
            },
        )

    def get_ads(self) -> list[dict]:
        """List all active ads with creative info."""
        return self._paginate(
            f"{self.ad_account_id}/ads",
            {"fields": "id,name,status,creative{id,thumbnail_url,title,body,image_url},adset_id,campaign_id"},
        )

    # ── Parsed helpers ────────────────────────────────────────

    def get_spend_by_day(self, days_back: int = 30) -> list[dict]:
        """
        Returns daily spend with key metrics.
        Each item: {date, spend, impressions, clicks, ctr, purchases, purchase_value, roas}
        """
        raw = self.get_account_insights(days_back=days_back, breakdown="day")
        result = []
        for row in raw:
            purchases = 0
            purchase_value = 0.0
            for action in row.get("actions", []):
                if action.get("action_type") == "purchase":
                    purchases = float(action.get("value", 0))
            for av in row.get("action_values", []):
                if av.get("action_type") == "purchase":
                    purchase_value = float(av.get("value", 0))

            spend = float(row.get("spend", 0))
            fb_roas = float(row.get("website_purchase_roas", [{}])[0].get("value", 0)) if row.get("website_purchase_roas") else 0

            result.append({
                "date": row.get("date_start"),
                "spend": spend,
                "impressions": int(row.get("impressions", 0)),
                "clicks": int(row.get("clicks", 0)),
                "ctr": float(row.get("ctr", 0)),
                "cpc": float(row.get("cpc", 0)),
                "reach": int(row.get("reach", 0)),
                "purchases": int(purchases),
                "purchase_value": purchase_value,
                "fb_roas": fb_roas,
            })
        return sorted(result, key=lambda x: x["date"])

    def get_creative_performance(self, days_back: int = 14) -> list[dict]:
        """
        Returns per-ad creative performance for Creative Cockpit.
        """
        raw = self.get_ad_insights(days_back=days_back)
        result = []
        for row in raw:
            purchases = 0
            purchase_value = 0.0
            for action in (row.get("actions") or []):
                if action.get("action_type") == "purchase":
                    purchases = float(action.get("value", 0))
            for av in (row.get("action_values") or []):
                if av.get("action_type") == "purchase":
                    purchase_value = float(av.get("value", 0))

            spend = float(row.get("spend", 0))
            creative = row.get("creative") or {}

            result.append({
                "ad_id": row.get("ad_id"),
                "ad_name": row.get("ad_name"),
                "adset_name": row.get("adset_name"),
                "campaign_name": row.get("campaign_name"),
                "spend": spend,
                "impressions": int(row.get("impressions", 0)),
                "clicks": int(row.get("clicks", 0)),
                "ctr": float(row.get("ctr", 0)),
                "cpc": float(row.get("cpc", 0)),
                "reach": int(row.get("reach", 0)),
                "purchases": int(purchases),
                "purchase_value": purchase_value,
                "roas": round(purchase_value / spend, 2) if spend > 0 else 0,
                "cpa": round(spend / purchases, 2) if purchases > 0 else 0,
                "thumbnail_url": creative.get("thumbnail_url"),
                "title": creative.get("title"),
                "body": creative.get("body"),
                "image_url": creative.get("image_url"),
            })
        return sorted(result, key=lambda x: x["spend"], reverse=True)

    def get_total_spend(self, days_back: int = 30) -> float:
        """Quick: total spend in last N days."""
        rows = self.get_account_insights(days_back=days_back)
        return sum(float(r.get("spend", 0)) for r in rows)


def build_client_from_config(cfg: dict) -> Optional[FacebookAdsClient]:
    fb = cfg.get("facebook_ads", {})
    required = ["access_token", "ad_account_id"]
    if not all(fb.get(k) for k in required):
        return None
    return FacebookAdsClient(
        access_token=fb["access_token"],
        ad_account_id=fb["ad_account_id"],
        app_id=fb.get("app_id", ""),
        app_secret=fb.get("app_secret", ""),
    )
