"""Amazon Advertising API v3 client.

Handles automated pulling of:
  - Campaign performance reports
  - Keyword performance reports
  - Search term reports (for harvesting)

API Docs: https://advertising.amazon.com/API/docs/en-us/

Setup (in Amazon Advertising Console → Apps & Services → Manage Apps):
  1. Create a developer app
  2. Get Client ID and Client Secret
  3. Complete OAuth flow to get Refresh Token
  4. Set profile_id (your advertising profile — one per marketplace)

Marketplace profile IDs can be fetched via GET /v2/profiles
"""

from __future__ import annotations

import gzip
import io
import json
import time
from datetime import date, timedelta
from typing import Optional

import requests

from .lwa_auth import get_access_token

# Base URLs per region
BASE_URLS = {
    "NA": "https://advertising.amazon.com",  # US, CA, MX, BR
    "EU": "https://advertising.amazon.co.uk",  # UK, DE, FR, IT, ES, NL, SE, PL, TR, SA, UAE, EG, IN
    "FE": "https://advertising.amazon.co.jp",  # JP, AU, SG
}

MARKETPLACE_TO_REGION = {
    "US": "NA", "CA": "NA", "MX": "NA", "BR": "NA",
    "UK": "EU", "DE": "EU", "FR": "EU", "IT": "EU", "ES": "EU",
    "JP": "FE", "AU": "FE", "SG": "FE",
    "IN": "EU",
}


class AmazonAdsClient:
    """Amazon Advertising API client."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 profile_id: str, marketplace: str = "US"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.profile_id = profile_id
        self.marketplace = marketplace
        region = MARKETPLACE_TO_REGION.get(marketplace, "NA")
        self.base_url = BASE_URLS[region]

    def _headers(self) -> dict:
        token = get_access_token(self.client_id, self.client_secret, self.refresh_token)
        return {
            "Authorization": f"Bearer {token}",
            "Amazon-Advertising-API-ClientId": self.client_id,
            "Amazon-Advertising-API-Scope": self.profile_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_profiles(self) -> list[dict]:
        """List all advertising profiles (marketplaces) for this account."""
        resp = requests.get(f"{self.base_url}/v2/profiles", headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_campaigns(self, state: str = "enabled") -> list[dict]:
        """Get all Sponsored Products campaigns."""
        resp = requests.get(
            f"{self.base_url}/v2/sp/campaigns",
            headers=self._headers(),
            params={"stateFilter": state},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def request_keyword_report(
        self,
        date_str: Optional[str] = None,
        report_type: str = "keywords",  # 'keywords' | 'searchTerms' | 'campaigns'
    ) -> str:
        """Request an async report. Returns report ID."""
        if not date_str:
            date_str = (date.today() - timedelta(days=1)).strftime("%Y%m%d")

        metrics_map = {
            "keywords": [
                "campaignName", "adGroupName", "keywordText", "matchType",
                "impressions", "clicks", "cost", "attributedSales14d",
                "attributedConversions14d", "costPerClick", "clickThroughRate",
            ],
            "searchTerms": [
                "campaignName", "adGroupName", "query", "matchType",
                "impressions", "clicks", "cost", "attributedSales14d",
                "attributedConversions14d",
            ],
            "campaigns": [
                "campaignName", "impressions", "clicks", "cost",
                "attributedSales14d", "attributedConversions14d",
            ],
        }

        payload = {
            "reportDate": date_str,
            "metrics": ",".join(metrics_map.get(report_type, metrics_map["keywords"])),
        }
        if report_type == "searchTerms":
            payload["segment"] = "query"

        resp = requests.post(
            f"{self.base_url}/v2/sp/{report_type}/report",
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["reportId"]

    def poll_report(self, report_id: str, max_wait_seconds: int = 120) -> Optional[bytes]:
        """Poll until report is ready, then download and return raw gzipped bytes."""
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            resp = requests.get(
                f"{self.base_url}/v2/reports/{report_id}",
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")

            if status == "SUCCESS":
                dl_url = data.get("location")
                dl_resp = requests.get(dl_url, timeout=60)
                dl_resp.raise_for_status()
                return dl_resp.content  # gzipped JSON
            elif status == "FAILURE":
                raise RuntimeError(f"Report {report_id} failed: {data.get('statusDetails')}")

            time.sleep(5)
        raise TimeoutError(f"Report {report_id} not ready after {max_wait_seconds}s")

    def fetch_keyword_report(self, date_str: Optional[str] = None) -> list[dict]:
        """Full flow: request → poll → parse keyword report."""
        report_id = self.request_keyword_report(date_str, "keywords")
        raw = self.poll_report(report_id)
        data = gzip.decompress(raw)
        return json.loads(data)

    def fetch_search_term_report(self, date_str: Optional[str] = None) -> list[dict]:
        """Full flow: request → poll → parse search term report."""
        report_id = self.request_keyword_report(date_str, "searchTerms")
        raw = self.poll_report(report_id)
        data = gzip.decompress(raw)
        return json.loads(data)

    def update_keyword_bid(self, keyword_id: str, new_bid: float) -> dict:
        """Update a keyword's bid."""
        resp = requests.put(
            f"{self.base_url}/v2/sp/keywords",
            headers=self._headers(),
            json=[{"keywordId": keyword_id, "bid": round(new_bid, 2)}],
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def pause_keyword(self, keyword_id: str) -> dict:
        """Pause a keyword."""
        resp = requests.put(
            f"{self.base_url}/v2/sp/keywords",
            headers=self._headers(),
            json=[{"keywordId": keyword_id, "state": "paused"}],
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def add_negative_keyword(self, campaign_id: str, ad_group_id: str,
                              keyword_text: str, match_type: str = "negativeExact") -> dict:
        """Add a negative keyword to an ad group."""
        resp = requests.post(
            f"{self.base_url}/v2/sp/negativeKeywords",
            headers=self._headers(),
            json=[{
                "campaignId": campaign_id,
                "adGroupId": ad_group_id,
                "keywordText": keyword_text,
                "matchType": match_type,
                "state": "enabled",
            }],
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


def build_client_from_config(cfg: dict) -> Optional[AmazonAdsClient]:
    """Build client from app config dict. Returns None if credentials missing."""
    ads = cfg.get("amazon_ads_api", {})
    required = ["client_id", "client_secret", "refresh_token", "profile_id"]
    if not all(ads.get(k) for k in required):
        return None
    return AmazonAdsClient(
        client_id=ads["client_id"],
        client_secret=ads["client_secret"],
        refresh_token=ads["refresh_token"],
        profile_id=ads["profile_id"],
        marketplace=cfg.get("marketplace", "US"),
    )
