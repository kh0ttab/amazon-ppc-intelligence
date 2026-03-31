"""Parse TXT/TSV Amazon bulk operation files."""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from ingestion.csv_reader import load_csv

logger = logging.getLogger(__name__)


def load_txt(file_path: str) -> Optional[dict]:
    """Load a TXT/TSV file (same logic as CSV with tab separator)."""
    return load_csv(file_path)


def parse_bulk_file(file_path: str) -> Optional[dict]:
    """Parse Amazon Bulk Operations file specifically.

    These files are tab-separated with a 'Record Type' column that indicates
    whether a row is a Campaign, Ad Group, Keyword, or Product Ad.
    """
    result = load_csv(file_path)
    if result is None:
        return None

    df = result["data"]

    if "Record Type" not in df.columns:
        logger.warning(f"No 'Record Type' column in {file_path}, treating as generic report")
        return result

    # Separate by record type
    campaigns = df[df["Record Type"] == "Campaign"].copy()
    ad_groups = df[df["Record Type"] == "Ad Group"].copy()
    keywords = df[df["Record Type"] == "Keyword"].copy()
    product_ads = df[df["Record Type"] == "Product Ad"].copy()

    result["campaigns"] = campaigns
    result["ad_groups"] = ad_groups
    result["keywords"] = keywords
    result["product_ads"] = product_ads
    result["summary"]["campaigns_count"] = len(campaigns)
    result["summary"]["keywords_count"] = len(keywords)

    logger.info(
        f"Bulk file parsed: {len(campaigns)} campaigns, "
        f"{len(ad_groups)} ad groups, {len(keywords)} keywords"
    )
    return result
