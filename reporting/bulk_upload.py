"""Amazon-ready bulk upload file generator for all recommendation actions."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config, REPORT_DIR

logger = logging.getLogger(__name__)
console = Console()

# Amazon Bulk Operations CSV headers
BULK_HEADERS = [
    "Record Type", "Campaign Name", "Ad Group Name",
    "Keyword", "Match Type", "Bid", "State",
]


class BulkUploadGenerator:
    """Generate Amazon-ready bulk upload CSV files from analysis recommendations."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]

    def generate_add_keywords(
        self,
        keywords: list[dict],
        campaign_name: str = "SP - Manual Exact",
        ad_group_name: str = "Keywords",
    ) -> Path:
        """Generate bulk CSV for adding new keywords.

        Each keyword dict should have: keyword, bid, match_type (optional).
        """
        rows = []
        for kw in keywords:
            rows.append({
                "Record Type": "Keyword",
                "Campaign Name": kw.get("campaign", campaign_name),
                "Ad Group Name": kw.get("ad_group", ad_group_name),
                "Keyword": kw["keyword"],
                "Match Type": kw.get("match_type", "Exact"),
                "Bid": kw.get("bid", ""),
                "State": "enabled",
            })

        return self._save_csv(rows, "bulk_add_keywords")

    def generate_pause_keywords(self, keywords: list[dict]) -> Path:
        """Generate bulk CSV for pausing keywords.

        Each keyword dict should have: keyword, campaign, ad_group, match_type.
        """
        rows = []
        for kw in keywords:
            rows.append({
                "Record Type": "Keyword",
                "Campaign Name": kw.get("campaign", ""),
                "Ad Group Name": kw.get("ad_group", ""),
                "Keyword": kw["keyword"],
                "Match Type": kw.get("match_type", "Exact"),
                "Bid": "",
                "State": "paused",
            })

        return self._save_csv(rows, "bulk_pause_keywords")

    def generate_bid_changes(self, keywords: list[dict]) -> Path:
        """Generate bulk CSV for bid changes.

        Each keyword dict should have: keyword, campaign, ad_group, match_type, new_bid.
        """
        rows = []
        for kw in keywords:
            rows.append({
                "Record Type": "Keyword",
                "Campaign Name": kw.get("campaign", ""),
                "Ad Group Name": kw.get("ad_group", ""),
                "Keyword": kw["keyword"],
                "Match Type": kw.get("match_type", "Exact"),
                "Bid": kw["new_bid"],
                "State": "",
            })

        return self._save_csv(rows, "bulk_bid_changes")

    def generate_negative_keywords(self, keywords: list[dict]) -> Path:
        """Generate bulk CSV for negative keywords.

        Each keyword dict should have: keyword, campaign (optional), match_type (defaults to Negative Exact).
        """
        rows = []
        for kw in keywords:
            rows.append({
                "Record Type": "Keyword",
                "Campaign Name": kw.get("campaign", ""),
                "Ad Group Name": kw.get("ad_group", ""),
                "Keyword": kw["keyword"],
                "Match Type": kw.get("match_type", "Negative Exact"),
                "Bid": "",
                "State": "enabled",
            })

        return self._save_csv(rows, "bulk_negative_keywords")

    def generate_from_analysis(
        self,
        analyzed_data: pd.DataFrame,
        action_type: str = "all",
    ) -> list[Path]:
        """Generate bulk upload files from analyzed PPC data.

        action_type: 'all', 'pause', 'bid_down', 'negative', 'promote'
        """
        files = []
        keyword_col = "Customer Search Term" if "Customer Search Term" in analyzed_data.columns else "Targeting"

        # Pause bleeding keywords
        if action_type in ("all", "pause"):
            bleeding = analyzed_data[analyzed_data["Status"] == "BLEEDING"]
            if len(bleeding) > 0:
                pause_list = []
                for _, row in bleeding.iterrows():
                    pause_list.append({
                        "keyword": row[keyword_col],
                        "campaign": row.get("Campaign Name", ""),
                        "ad_group": row.get("Ad Group Name", ""),
                        "match_type": row.get("Match Type", "Exact"),
                    })
                if pause_list:
                    files.append(self.generate_pause_keywords(pause_list))

        # Bid reductions for high-ACoS keywords
        if action_type in ("all", "bid_down"):
            target_acos = self.config["target_acos"]
            high_acos = analyzed_data[
                (analyzed_data.get("ACoS", pd.Series(dtype=float)) > target_acos * 1.5) &
                (analyzed_data.get("Orders", pd.Series(dtype=float)) > 0)
            ] if "ACoS" in analyzed_data.columns else pd.DataFrame()

            if len(high_acos) > 0:
                bid_changes = []
                for _, row in high_acos.iterrows():
                    current_cpc = row.get("CPC", 0)
                    current_acos = row.get("ACoS", 0)
                    if current_cpc > 0 and current_acos > 0:
                        new_bid = round(current_cpc * (target_acos / current_acos), 2)
                        bid_changes.append({
                            "keyword": row[keyword_col],
                            "campaign": row.get("Campaign Name", ""),
                            "ad_group": row.get("Ad Group Name", ""),
                            "match_type": row.get("Match Type", "Exact"),
                            "new_bid": new_bid,
                        })
                if bid_changes:
                    files.append(self.generate_bid_changes(bid_changes))

        # Negative keywords for zero-conversion terms
        if action_type in ("all", "negative"):
            neg_threshold = self.config["negative_clicks_threshold"]
            spend_threshold = self.config["negative_spend_threshold"]

            zero_conv = analyzed_data[
                (analyzed_data["Clicks"] >= neg_threshold) &
                (analyzed_data["Orders"] == 0) &
                (analyzed_data["Spend"] > spend_threshold)
            ] if all(c in analyzed_data.columns for c in ["Clicks", "Orders", "Spend"]) else pd.DataFrame()

            if len(zero_conv) > 0:
                neg_list = []
                for _, row in zero_conv.iterrows():
                    neg_list.append({
                        "keyword": row[keyword_col],
                        "campaign": row.get("Campaign Name", ""),
                        "ad_group": row.get("Ad Group Name", ""),
                    })
                if neg_list:
                    files.append(self.generate_negative_keywords(neg_list))

        # Promote winners (bid up)
        if action_type in ("all", "promote"):
            winners = analyzed_data[analyzed_data["Status"] == "WINNER"] if "Status" in analyzed_data.columns else pd.DataFrame()
            if len(winners) > 0:
                promote_list = []
                for _, row in winners.iterrows():
                    current_cpc = row.get("CPC", 0)
                    if current_cpc > 0:
                        new_bid = round(current_cpc * self.config["bid_multiplier"], 2)
                        promote_list.append({
                            "keyword": row[keyword_col],
                            "campaign": row.get("Campaign Name", ""),
                            "ad_group": row.get("Ad Group Name", ""),
                            "match_type": row.get("Match Type", "Exact"),
                            "new_bid": new_bid,
                        })
                if promote_list:
                    files.append(self.generate_bid_changes(promote_list))

        if files:
            console.print(Panel(
                f"[green]{len(files)} bulk upload file(s) generated[/green]\n"
                f"Location: {REPORT_DIR}",
                title="Bulk Upload Files Ready",
                border_style="green",
            ))
        else:
            console.print("[yellow]No actions to generate bulk files for.[/yellow]")

        return files

    def _save_csv(self, rows: list[dict], prefix: str) -> Path:
        """Save rows as a properly formatted bulk upload CSV."""
        if not rows:
            console.print(f"[yellow]No data for {prefix}.[/yellow]")
            return Path()

        df = pd.DataFrame(rows, columns=BULK_HEADERS)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = REPORT_DIR / f"{prefix}_{timestamp}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8-sig")

        console.print(f"[green]Saved:[/green] {filepath} ({len(rows)} operations)")
        logger.info(f"Bulk upload: {filepath} ({len(rows)} rows)")
        return filepath

    def display_summary(self, files: list[Path]) -> None:
        """Display summary of generated bulk upload files."""
        if not files:
            return

        table = Table(title="Generated Bulk Upload Files", show_lines=True)
        table.add_column("#", width=4)
        table.add_column("File", style="cyan")
        table.add_column("Type")
        table.add_column("Instructions", max_width=40)

        type_map = {
            "add": ("Add Keywords", "Upload via Seller Central > Bulk Operations > Upload"),
            "pause": ("Pause Keywords", "Upload to pause specified keywords"),
            "bid": ("Bid Changes", "Upload to update bids for specified keywords"),
            "negative": ("Negative Keywords", "Upload to add negative keywords"),
            "harvest": ("Harvest Actions", "Combined promote + negate operations"),
        }

        for i, f in enumerate(files):
            if not f or not f.exists():
                continue
            name = f.name
            file_type = "Unknown"
            instructions = "Upload via Seller Central > Bulk Operations"

            for key, (label, instr) in type_map.items():
                if key in name:
                    file_type = label
                    instructions = instr
                    break

            table.add_row(str(i + 1), name, file_type, instructions)

        console.print(table)
        console.print("\n[dim]Upload these files at: Seller Central > Advertising > Bulk Operations > Upload[/dim]")
