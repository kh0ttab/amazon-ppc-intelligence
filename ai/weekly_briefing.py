"""Weekly AI briefing generator - Monday Morning PPC Manager style."""

import logging
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from config import load_config
from ai.llm_client import LLMClient
from analysis.ppc_analyzer import PPCAnalyzer
from analysis.budget_analyzer import BudgetAnalyzer
from analysis.seasonality import SeasonalityAnalyzer

logger = logging.getLogger(__name__)
console = Console()

BRIEFING_PROMPT = """Generate a concise "Monday Morning Briefing" for an Amazon seller based on this data.

Write it as if you're their senior PPC manager giving a verbal update. Be direct, specific, and action-oriented.

Format EXACTLY like this:

**WEEKLY PPC BRIEFING**

📊 **Performance Snapshot:**
[1-2 sentences summarizing spend, revenue, ACoS, and trend direction]

🔥 **TOP 3 Actions for Today:**
1. [Most urgent action with specific keyword/campaign name and dollar amount]
2. [Second priority action]
3. [Third priority action]

💰 **Budget Alert:**
[Which campaign is burning money fastest, with specific dollar waste amount]

🚀 **Scaling Opportunity:**
[Which keyword or campaign is ready to scale, with ROAS and suggested bid increase]

⚠️ **Risk Watch:**
[Any concerning trends - rising ACoS, declining CVR, competitor activity]

Keep it under 200 words. Use actual numbers from the data. No generic advice."""


class WeeklyBriefing:
    """Generate AI-powered weekly briefing from loaded data."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]

    def generate(self, analyzed_data: Optional[pd.DataFrame]) -> str:
        """Generate the weekly briefing via Ollama.

        Returns the briefing text, or a data-only fallback if Ollama unavailable.
        """
        llm = LLMClient(self.config)

        if analyzed_data is None or len(analyzed_data) == 0:
            return ""

        # Build rich data context
        data_context = self._build_briefing_context(analyzed_data)

        # Check for seasonality alerts
        season = SeasonalityAnalyzer(self.config)
        alerts = season.check_startup_alerts()
        if alerts:
            alert_text = "\n".join(f"EVENT ALERT: {a['message']}" for a in alerts)
            data_context += f"\n\nUPCOMING EVENTS:\n{alert_text}"

        if llm.check_connection():
            try:
                briefing = llm.chat(
                    BRIEFING_PROMPT,
                    data_context=data_context,
                    stream=False,
                )
                return briefing
            except Exception as e:
                logger.warning(f"AI briefing failed: {e}")

        # Fallback: data-only briefing
        return self._generate_fallback(analyzed_data)

    def _build_briefing_context(self, df: pd.DataFrame) -> str:
        """Build comprehensive data context for the briefing prompt."""
        for col in ["Spend", "Sales", "Orders", "Clicks", "Impressions"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        c = self.currency
        total_spend = df["Spend"].sum()
        total_sales = df["Sales"].sum()
        total_orders = df["Orders"].sum()
        total_clicks = df["Clicks"].sum()
        acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
        roas = (total_sales / total_spend) if total_spend > 0 else 0
        cvr = (total_orders / total_clicks * 100) if total_clicks > 0 else 0
        cpc = (total_spend / total_clicks) if total_clicks > 0 else 0

        lines = [
            f"OVERALL: Spend={c}{total_spend:.2f}, Revenue={c}{total_sales:.2f}, "
            f"Orders={total_orders:.0f}, ACoS={acos:.1f}%, ROAS={roas:.2f}x, "
            f"CVR={cvr:.1f}%, CPC={c}{cpc:.2f}",
        ]

        keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else df.columns[0]

        # Top 5 winners
        if "ACoS" in df.columns:
            winners = df[(df["Orders"] > 0) & (df["ACoS"] <= self.config["target_acos"])].nlargest(5, "Sales")
            if len(winners) > 0:
                lines.append("\nTOP WINNERS:")
                for _, r in winners.iterrows():
                    lines.append(
                        f"  {r[keyword_col]}: Revenue={c}{r['Sales']:.2f}, "
                        f"ACoS={r['ACoS']:.1f}%, ROAS={r.get('ROAS', 0):.2f}x, "
                        f"Orders={int(r['Orders'])}"
                    )

        # Top 5 bleeders
        bleeders = df[(df["Spend"] > 0) & (df["Orders"] == 0)].nlargest(5, "Spend")
        if len(bleeders) > 0:
            lines.append("\nTOP BLEEDERS (spend, 0 orders):")
            for _, r in bleeders.iterrows():
                lines.append(
                    f"  {r[keyword_col]}: Spend={c}{r['Spend']:.2f}, "
                    f"Clicks={int(r['Clicks'])}"
                )

        # Waste summary
        waste = df[df["Orders"] == 0]["Spend"].sum()
        lines.append(f"\nTOTAL WASTE (zero-order spend): {c}{waste:.2f} ({waste/total_spend*100:.1f}% of total)" if total_spend > 0 else "")

        # Campaign breakdown if available
        if "Campaign Name" in df.columns:
            camp_data = df.groupby("Campaign Name").agg({
                "Spend": "sum", "Sales": "sum", "Orders": "sum",
            }).reset_index()
            camp_data["ACoS"] = camp_data.apply(
                lambda r: (r["Spend"] / r["Sales"] * 100) if r["Sales"] > 0 else 0, axis=1
            )
            camp_data = camp_data.sort_values("Spend", ascending=False)

            lines.append("\nCAMPAIGN BREAKDOWN:")
            for _, r in camp_data.head(8).iterrows():
                lines.append(
                    f"  {r['Campaign Name']}: Spend={c}{r['Spend']:.2f}, "
                    f"Revenue={c}{r['Sales']:.2f}, ACoS={r['ACoS']:.1f}%"
                )

        return "\n".join(lines)

    def _generate_fallback(self, df: pd.DataFrame) -> str:
        """Generate a data-only briefing when Ollama is unavailable."""
        c = self.currency
        total_spend = df["Spend"].sum()
        total_sales = df["Sales"].sum()
        total_orders = df["Orders"].sum()
        acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
        waste = df[df["Orders"] == 0]["Spend"].sum()

        keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else df.columns[0]

        top_bleeder = df[df["Orders"] == 0].nlargest(1, "Spend")
        bleeder_text = ""
        if len(top_bleeder) > 0:
            b = top_bleeder.iloc[0]
            bleeder_text = f"'{b[keyword_col]}' spent {c}{b['Spend']:.2f} with 0 orders"

        top_winner = df[df["Orders"] > 0].nlargest(1, "Sales")
        winner_text = ""
        if len(top_winner) > 0:
            w = top_winner.iloc[0]
            winner_text = f"'{w[keyword_col]}' earned {c}{w['Sales']:.2f}"

        return (
            f"WEEKLY SNAPSHOT: Spent {c}{total_spend:,.2f}, "
            f"earned {c}{total_sales:,.2f}, ACoS {acos:.1f}%, "
            f"{int(total_orders)} orders.\n\n"
            f"BUDGET ALERT: {c}{waste:,.2f} wasted on zero-conversion terms.\n"
            f"Top waste: {bleeder_text}\n\n"
            f"OPPORTUNITY: {winner_text}\n\n"
            f"[Ollama offline - connect for full AI analysis]"
        )

    def display_briefing(self, analyzed_data: Optional[pd.DataFrame]) -> None:
        """Generate and display the weekly briefing."""
        if analyzed_data is None:
            console.print("[dim]No data loaded for briefing.[/dim]")
            return

        console.print(Rule("Monday Morning Briefing", style="bold cyan"))

        briefing = self.generate(analyzed_data)
        if briefing:
            console.print(Panel(
                briefing,
                title="Your PPC Manager Briefing",
                border_style="cyan",
                padding=(1, 2),
            ))
        else:
            console.print("[yellow]Could not generate briefing. Load data first.[/yellow]")
