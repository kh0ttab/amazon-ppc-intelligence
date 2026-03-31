"""Configuration management for Amazon PPC Intelligence."""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports"
DATA_DIR = BASE_DIR / "data"
DB_DIR = BASE_DIR / "db"

DEFAULT_CONFIG = {
    "target_acos": 25.0,
    "break_even_acos": 35.0,
    "currency": "$",
    "marketplace": "US",
    "ollama_endpoint": "http://localhost:11434",
    "ollama_model": "qwen2.5:14b",
    "bleeding_acos_threshold": 100.0,
    "waste_acos_threshold": 150.0,
    "sleeping_days": 14,
    "new_keyword_days": 7,
    "bid_multiplier": 1.2,
    "max_scrape_results": 10,
    "log_file": str(LOG_DIR / "analysis.log"),
    # ASIN profitability
    "cogs_per_unit": 0.0,
    "fba_fee": 0.0,
    "referral_fee_pct": 15.0,
    # Search term harvesting thresholds
    "harvest_clicks_threshold": 8,
    "harvest_orders_threshold": 1,
    "negative_clicks_threshold": 5,
    "negative_spend_threshold": 3.0,
    # Competitor monitoring
    "competitor_asins": [],
    "competitor_price_alert_pct": 5.0,
    # Campaign lifecycle
    "campaign_stage": "auto",
    # Seasonality
    "seasonality_alert_days": 21,
}

# Amazon report column mappings
SEARCH_TERM_COLUMNS = {
    "search_term": "Customer Search Term",
    "impressions": "Impressions",
    "clicks": "Clicks",
    "spend": "Spend",
    "sales": "Sales",
    "orders": "Orders",
    "acos": "ACOS",
}

CAMPAIGN_COLUMNS = {
    "campaign": "Campaign Name",
    "ad_group": "Ad Group Name",
    "targeting": "Targeting",
    "match_type": "Match Type",
    "impressions": "Impressions",
    "clicks": "Clicks",
    "cpc": "CPC",
    "spend": "Spend",
    "sales": "Sales",
    "acos": "ACOS",
    "roas": "ROAS",
}

BUSINESS_REPORT_COLUMNS = {
    "asin": "ASIN",
    "title": "Title",
    "sessions": "Sessions",
    "units_ordered": "Units Ordered",
    "sales": "Ordered Product Sales",
}

PLACEMENT_COLUMNS = {
    "placement": "Placement",
    "impressions": "Impressions",
    "clicks": "Clicks",
    "spend": "Spend",
    "sales": "Sales",
    "orders": "Orders",
}

# Alternative column name patterns Amazon uses across different report versions
COLUMN_ALIASES = {
    "Customer Search Term": ["Customer Search Term", "Search Term", "Query"],
    "Impressions": ["Impressions", "Impr."],
    "Clicks": ["Clicks"],
    "Spend": ["Spend", "Cost", "Total Spend"],
    "Sales": ["Sales", "7 Day Total Sales", "14 Day Total Sales", "Total Advertising Sales"],
    "Orders": ["Orders", "7 Day Total Orders", "14 Day Total Orders", "Total Advertising Orders"],
    "ACOS": ["ACOS", "ACoS", "Total Advertising Cost of Sales (ACoS)"],
    "Campaign Name": ["Campaign Name", "Campaign"],
    "Ad Group Name": ["Ad Group Name", "Ad Group"],
    "Match Type": ["Match Type", "Keyword Match Type"],
    "Ordered Product Sales": ["Ordered Product Sales", "Product Sales"],
    "Units Ordered": ["Units Ordered", "Total Order Items"],
    "Sessions": ["Sessions", "Browser Sessions"],
    "ROAS": ["ROAS", "Total Return on Advertising Spend (RoAS)"],
    "CPC": ["CPC", "Cost Per Click", "Avg. CPC"],
    "Targeting": ["Targeting", "Keyword or Product Targeting"],
    "Placement": ["Placement", "Placement Type"],
    "Date": ["Date", "Start Date", "Report Date"],
}

# Amazon bulk upload template columns
BULK_UPLOAD_COLUMNS = {
    "add_keyword": [
        "Record Type", "Campaign Name", "Ad Group Name", "Keyword", "Match Type",
        "Bid", "State",
    ],
    "pause_keyword": [
        "Record Type", "Campaign Name", "Ad Group Name", "Keyword", "Match Type",
        "State",
    ],
    "negative_keyword": [
        "Record Type", "Campaign Name", "Ad Group Name", "Keyword", "Match Type",
        "State",
    ],
    "bid_change": [
        "Record Type", "Campaign Name", "Ad Group Name", "Keyword", "Match Type",
        "Bid",
    ],
}

# Amazon event calendar for seasonality
AMAZON_EVENTS = [
    {"name": "Valentine's Day", "month": 2, "day": 14, "budget_increase": 20, "bid_increase": 10},
    {"name": "Mother's Day", "month": 5, "day": 11, "budget_increase": 25, "bid_increase": 15},
    {"name": "Father's Day", "month": 6, "day": 15, "budget_increase": 20, "bid_increase": 10},
    {"name": "Prime Day", "month": 7, "day": 15, "budget_increase": 50, "bid_increase": 25},
    {"name": "Back to School", "month": 8, "day": 1, "budget_increase": 30, "bid_increase": 15},
    {"name": "Labor Day", "month": 9, "day": 1, "budget_increase": 15, "bid_increase": 10},
    {"name": "Halloween", "month": 10, "day": 31, "budget_increase": 20, "bid_increase": 10},
    {"name": "Black Friday", "month": 11, "day": 28, "budget_increase": 60, "bid_increase": 30},
    {"name": "Cyber Monday", "month": 12, "day": 1, "budget_increase": 60, "bid_increase": 30},
    {"name": "Christmas", "month": 12, "day": 25, "budget_increase": 50, "bid_increase": 25},
    {"name": "New Year", "month": 1, "day": 1, "budget_increase": 15, "bid_increase": 10},
]


def load_config() -> dict:
    """Load configuration from config.json, creating defaults if missing."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            user_config = json.load(f)
        merged = {**DEFAULT_CONFIG, **user_config}
        return merged
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save configuration to config.json."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def ensure_dirs() -> None:
    """Create required directories if they don't exist."""
    LOG_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    DB_DIR.mkdir(exist_ok=True)


# Initialize on import
ensure_dirs()
