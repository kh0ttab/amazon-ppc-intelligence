"""Campaign lifecycle detection - auto-detect stage and adjust recommendations."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config

logger = logging.getLogger(__name__)
console = Console()

STAGES = {
    "LAUNCH": {
        "label": "Launch Phase",
        "color": "cyan",
        "description": "Aggressive mode - prioritize impressions and rank building",
        "acos_multiplier": 2.0,
        "bid_strategy": "Bid aggressively to win top placements and gather data",
        "focus": "Impressions > Clicks > Sales. Gathering data is the priority.",
        "actions": [
            "Set target ACoS at 2x break-even (invest in rank)",
            "Run broad match discovery campaigns",
            "Maximize impressions for main keywords",
            "Don't pause keywords with < 20 clicks yet",
            "Focus on getting first 15-20 reviews",
        ],
    },
    "GROWTH": {
        "label": "Growth Phase",
        "color": "green",
        "description": "Balanced mode - harvest winners, cut bleeders, scale profitable terms",
        "acos_multiplier": 1.3,
        "bid_strategy": "Balance between growth and efficiency",
        "focus": "Optimize bid efficiency while maintaining rank trajectory.",
        "actions": [
            "Harvest winning search terms to manual exact campaigns",
            "Cut keywords bleeding for 14+ days",
            "Scale winning campaigns by 15-20% weekly",
            "Add negative keywords for zero-conversion terms",
            "Test Sponsored Brands for branded queries",
        ],
    },
    "MATURE": {
        "label": "Mature / Profit Phase",
        "color": "yellow",
        "description": "Profit mode - strict ACoS, maximize ROAS, cut non-performers",
        "acos_multiplier": 1.0,
        "bid_strategy": "Optimize for maximum profit margin",
        "focus": "Every dollar of ad spend must earn its place.",
        "actions": [
            "Strict ACoS target enforcement",
            "Pause any keyword with ACoS > target for 7+ days",
            "Reduce bids on declining terms weekly",
            "Focus budget on proven exact match winners",
            "Monitor TACoS - aim for decreasing trend",
            "Consider reducing bids on terms where organic rank is strong",
        ],
    },
}


class LifecycleDetector:
    """Detect campaign lifecycle stage and adjust strategies accordingly."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.configured_stage = self.config.get("campaign_stage", "auto")

    def detect_stage(
        self,
        ppc_data: pd.DataFrame,
        review_count: Optional[int] = None,
        listing_age_days: Optional[int] = None,
    ) -> dict:
        """Auto-detect campaign stage based on available signals.

        Args:
            ppc_data: PPC performance data
            review_count: Number of reviews (if known)
            listing_age_days: Listing age in days (if known)
        """
        if self.configured_stage != "auto" and self.configured_stage in STAGES:
            stage = self.configured_stage
            confidence = "manual"
        else:
            stage, confidence = self._auto_detect(ppc_data, review_count, listing_age_days)

        stage_info = STAGES[stage]
        break_even_acos = self.config["break_even_acos"]
        adjusted_target = break_even_acos * stage_info["acos_multiplier"]

        return {
            "stage": stage,
            "confidence": confidence,
            "info": stage_info,
            "adjusted_target_acos": adjusted_target,
            "break_even_acos": break_even_acos,
            "review_count": review_count,
            "listing_age_days": listing_age_days,
        }

    def _auto_detect(
        self,
        ppc_data: pd.DataFrame,
        review_count: Optional[int],
        listing_age_days: Optional[int],
    ) -> tuple[str, str]:
        """Auto-detect stage from data signals."""
        signals = {"LAUNCH": 0, "GROWTH": 0, "MATURE": 0}

        # Review count signal
        if review_count is not None:
            if review_count < 15:
                signals["LAUNCH"] += 3
            elif review_count < 50:
                signals["GROWTH"] += 2
            else:
                signals["MATURE"] += 2

        # Listing age signal
        if listing_age_days is not None:
            if listing_age_days < 60:
                signals["LAUNCH"] += 3
            elif listing_age_days < 180:
                signals["GROWTH"] += 2
            else:
                signals["MATURE"] += 2

        # Data volume signal
        for col in ["Clicks", "Orders", "Spend"]:
            if col in ppc_data.columns:
                ppc_data[col] = pd.to_numeric(ppc_data[col], errors="coerce").fillna(0)

        total_clicks = ppc_data["Clicks"].sum() if "Clicks" in ppc_data.columns else 0
        total_orders = ppc_data["Orders"].sum() if "Orders" in ppc_data.columns else 0
        total_spend = ppc_data["Spend"].sum() if "Spend" in ppc_data.columns else 0

        # Low data = likely launch
        if total_clicks < 500:
            signals["LAUNCH"] += 2
        elif total_clicks < 5000:
            signals["GROWTH"] += 1
        else:
            signals["MATURE"] += 1

        # Conversion rate signal
        if total_clicks > 100:
            cvr = total_orders / total_clicks * 100
            if cvr < 5:
                signals["LAUNCH"] += 1  # Low CVR = still optimizing
            elif cvr > 15:
                signals["MATURE"] += 1  # High CVR = well-optimized

        # Date range signal
        date_cols = [c for c in ppc_data.columns if c.lower() in ("date", "start date", "report date")]
        if date_cols:
            dates = pd.to_datetime(ppc_data[date_cols[0]], errors="coerce").dropna()
            if len(dates) > 0:
                date_range = (dates.max() - dates.min()).days
                if date_range < 30:
                    signals["LAUNCH"] += 1
                elif date_range > 90:
                    signals["MATURE"] += 1

        # Determine winner
        stage = max(signals, key=signals.get)
        total_signals = sum(signals.values())
        confidence = "high" if signals[stage] >= total_signals * 0.5 else "medium"

        return stage, confidence

    def get_adjusted_recommendations(self, stage_result: dict, analyzed_data: pd.DataFrame) -> dict:
        """Get stage-adjusted recommendations for the current data."""
        stage = stage_result["stage"]
        adjusted_acos = stage_result["adjusted_target_acos"]

        recs = {
            "target_acos": adjusted_acos,
            "keywords_to_pause": [],
            "keywords_to_scale": [],
            "bid_strategy": STAGES[stage]["bid_strategy"],
        }

        for col in ["ACoS", "Orders", "Clicks", "Spend", "Sales"]:
            if col in analyzed_data.columns:
                analyzed_data[col] = pd.to_numeric(analyzed_data[col], errors="coerce").fillna(0)

        keyword_col = "Customer Search Term" if "Customer Search Term" in analyzed_data.columns else "Targeting"

        if stage == "LAUNCH":
            # Only pause extreme bleeders in launch
            pause_mask = (
                (analyzed_data["Clicks"] >= 30) &
                (analyzed_data["Orders"] == 0) &
                (analyzed_data["Spend"] > 20)
            )
        elif stage == "GROWTH":
            # Moderate thresholds
            pause_mask = (
                (analyzed_data["Clicks"] >= 15) &
                (analyzed_data["Orders"] == 0) &
                (analyzed_data["Spend"] > 10)
            ) | (
                (analyzed_data["ACoS"] > adjusted_acos * 2) &
                (analyzed_data["Spend"] > 5)
            )
        else:  # MATURE
            # Strict thresholds
            pause_mask = (
                (analyzed_data["Clicks"] >= 8) &
                (analyzed_data["Orders"] == 0)
            ) | (
                (analyzed_data["ACoS"] > adjusted_acos * 1.5) &
                (analyzed_data["Spend"] > 3)
            )

        to_pause = analyzed_data[pause_mask]
        recs["keywords_to_pause"] = to_pause[keyword_col].tolist()[:30]

        # Scale recommendations
        scale_mask = (
            (analyzed_data["ACoS"] > 0) &
            (analyzed_data["ACoS"] < adjusted_acos * 0.7) &
            (analyzed_data["Orders"] >= 2)
        )
        to_scale = analyzed_data[scale_mask].sort_values("Sales", ascending=False)
        recs["keywords_to_scale"] = to_scale[keyword_col].tolist()[:20]

        return recs

    def display_report(self, stage_result: dict) -> None:
        """Display lifecycle stage detection and recommendations."""
        stage = stage_result["stage"]
        info = stage_result["info"]
        c = self.currency

        # Stage banner
        color = info["color"]
        console.print(Panel(
            f"[bold {color}]{info['label'].upper()}[/bold {color}]\n\n"
            f"{info['description']}\n\n"
            f"[bold]Detection confidence:[/bold] {stage_result['confidence']}\n"
            f"[bold]Break-even ACoS:[/bold] {stage_result['break_even_acos']:.1f}%\n"
            f"[bold]Adjusted Target ACoS:[/bold] [{color}]{stage_result['adjusted_target_acos']:.1f}%[/{color}] "
            f"(x{info['acos_multiplier']})\n"
            f"[bold]Bid Strategy:[/bold] {info['bid_strategy']}\n"
            f"[bold]Focus:[/bold] {info['focus']}",
            title=f"Campaign Stage: {info['label']}",
            border_style=color,
        ))

        # Input signals
        if stage_result.get("review_count") is not None or stage_result.get("listing_age_days") is not None:
            signals = []
            if stage_result.get("review_count") is not None:
                signals.append(f"Reviews: {stage_result['review_count']}")
            if stage_result.get("listing_age_days") is not None:
                signals.append(f"Listing age: {stage_result['listing_age_days']} days")
            console.print(f"[dim]Signals: {' | '.join(signals)}[/dim]")

        # Action items
        console.print(f"\n[bold {color}]Recommended Actions for {info['label']}:[/bold {color}]")
        for i, action in enumerate(info["actions"]):
            console.print(f"  [{color}]{i+1}.[/{color}] {action}")

        # Stage comparison
        console.print()
        comp_table = Table(title="Stage Comparison", show_lines=True)
        comp_table.add_column("", style="bold")
        for s_name, s_info in STAGES.items():
            style = f"bold {s_info['color']}" if s_name == stage else "dim"
            comp_table.add_column(s_info["label"], style=style, justify="center")

        comp_table.add_row(
            "ACoS Multiplier",
            *[f"{s['acos_multiplier']}x" for s in STAGES.values()]
        )
        comp_table.add_row(
            "Target ACoS",
            *[f"{stage_result['break_even_acos'] * s['acos_multiplier']:.0f}%" for s in STAGES.values()]
        )
        comp_table.add_row(
            "Pause Threshold",
            "30+ clicks, $20+", "15+ clicks, $10+", "8+ clicks"
        )

        console.print(comp_table)
