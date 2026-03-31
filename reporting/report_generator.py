"""Full report generation engine with rich terminal output."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

from config import load_config, REPORT_DIR
from analysis.ppc_analyzer import PPCAnalyzer
from analysis.sales_analyzer import SalesAnalyzer
from analysis.budget_analyzer import BudgetAnalyzer
from analysis.keyword_ranker import KeywordRanker
from ai.llm_client import LLMClient

logger = logging.getLogger(__name__)
console = Console()


class ReportGenerator:
    """Generate comprehensive PPC reports."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.currency = self.config["currency"]
        self.ppc = PPCAnalyzer(self.config)
        self.sales = SalesAnalyzer(self.config)
        self.budget = BudgetAnalyzer(self.config)
        self.ranker = KeywordRanker(self.config)
        self.llm = LLMClient(self.config)
        self.llm_available = self.llm.check_connection()

    def _get_ai_insight(self, prompt: str, data_context: str = "") -> str:
        """Get an AI-generated insight, or return empty string if unavailable."""
        if not self.llm_available:
            return ""
        try:
            return self.llm.chat(prompt, data_context=data_context, stream=False)
        except Exception as e:
            logger.warning(f"AI insight failed: {e}")
            return ""

    def weekly_performance_report(
        self,
        ppc_data: pd.DataFrame,
        business_data: Optional[pd.DataFrame] = None,
        previous_week: Optional[pd.DataFrame] = None,
    ) -> str:
        """Generate a weekly performance report.

        Returns the report as a string for export.
        """
        report_lines = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        console.print(Rule("Weekly Performance Report", style="bold blue"))
        console.print(f"[dim]Generated: {timestamp}[/dim]\n")
        report_lines.append(f"WEEKLY PERFORMANCE REPORT - {timestamp}\n{'='*60}\n")

        # 1. KPI Dashboard
        analyzed = self.ppc.analyze_keywords(ppc_data)
        kpis = self.ppc.get_kpi_summary(analyzed)
        self.ppc.display_kpi_dashboard(kpis, self.currency)

        c = self.currency
        report_lines.append("KPI SUMMARY:")
        report_lines.append(f"  Total Spend: {c}{kpis['total_spend']:,.2f}")
        report_lines.append(f"  Total Revenue: {c}{kpis['total_sales']:,.2f}")
        report_lines.append(f"  ACoS: {kpis['overall_acos']:.1f}%")
        report_lines.append(f"  ROAS: {kpis['overall_roas']:.2f}x")
        report_lines.append(f"  Orders: {kpis['total_orders']:,.0f}")
        report_lines.append(f"  CTR: {kpis['overall_ctr']:.2f}%")
        report_lines.append(f"  CPC: {c}{kpis['overall_cpc']:.2f}")
        report_lines.append(f"  Conv Rate: {kpis['overall_conv_rate']:.1f}%\n")

        # 2. Sales Breakdown
        breakdown = self.sales.calculate_breakdown(ppc_data, business_data)
        self.sales.display_breakdown(breakdown)
        report_lines.append(f"TACoS: {breakdown['tacos']:.1f}%")
        report_lines.append(f"PPC Sales: {c}{breakdown['ppc_sales']:,.2f} ({breakdown['ppc_pct']:.1f}%)")
        report_lines.append(f"Organic Sales: {c}{breakdown['organic_sales']:,.2f} ({breakdown['organic_pct']:.1f}%)\n")

        # 3. Top 10 Winners
        console.print(Rule("Top 10 Winning Keywords", style="green"))
        winners = self.ppc.get_winners(analyzed)
        self.ppc.display_keyword_table(winners, "Top Winners", limit=10, currency=self.currency)
        report_lines.append("\nTOP 10 WINNERS:")
        keyword_col = "Customer Search Term" if "Customer Search Term" in winners.columns else winners.columns[0]
        for i, (_, row) in enumerate(winners.head(10).iterrows()):
            report_lines.append(
                f"  {i+1}. {row.get(keyword_col, 'N/A')} | "
                f"Revenue: {c}{row['Sales']:,.2f} | ACoS: {row['ACoS']:.1f}% | "
                f"ROAS: {row['ROAS']:.2f}x | Orders: {int(row['Orders'])}"
            )

        # 4. Top 10 Bleeding
        console.print(Rule("Top 10 Bleeding Keywords", style="red"))
        bleeding = self.ppc.get_bleeding(analyzed)
        self.ppc.display_keyword_table(bleeding, "Top Bleeding Keywords", limit=10, currency=self.currency)
        report_lines.append("\nTOP 10 BLEEDING:")
        for i, (_, row) in enumerate(bleeding.head(10).iterrows()):
            report_lines.append(
                f"  {i+1}. {row.get(keyword_col, 'N/A')} | "
                f"Spend: {c}{row['Spend']:,.2f} | ACoS: {row['ACoS']:.1f}% | "
                f"Orders: {int(row['Orders'])}"
            )

        # 5. Week-over-week comparison
        if previous_week is not None:
            console.print(Rule("Week-over-Week Comparison", style="yellow"))
            prev_analyzed = self.ppc.analyze_keywords(previous_week)
            prev_kpis = self.ppc.get_kpi_summary(prev_analyzed)
            self._display_wow_comparison(kpis, prev_kpis)
            report_lines.append("\nWEEK-OVER-WEEK CHANGES:")
            for metric in ["total_spend", "total_sales", "overall_acos", "total_orders"]:
                curr = kpis[metric]
                prev = prev_kpis[metric]
                change = ((curr - prev) / prev * 100) if prev > 0 else 0
                report_lines.append(f"  {metric}: {change:+.1f}%")

        # 6. AI Summary
        if self.llm_available:
            console.print(Rule("AI-Generated Summary", style="magenta"))
            data_context = self.llm.build_data_context(analyzed)
            insight = self._get_ai_insight(
                "Provide a concise weekly performance summary. Highlight the most important "
                "trend, the biggest opportunity, and the most urgent action item. Keep it to "
                "3-4 sentences.",
                data_context,
            )
            if insight:
                console.print(Panel(insight, title="AI Insight", border_style="magenta"))
                report_lines.append(f"\nAI SUMMARY:\n{insight}")

        report_text = "\n".join(report_lines)
        self._save_report(report_text, "weekly_performance")
        return report_text

    def keyword_audit_report(self, ppc_data: pd.DataFrame) -> str:
        """Generate a full keyword audit report."""
        report_lines = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        console.print(Rule("Keyword Audit Report", style="bold blue"))
        console.print(f"[dim]Generated: {timestamp}[/dim]\n")
        report_lines.append(f"KEYWORD AUDIT REPORT - {timestamp}\n{'='*60}\n")

        analyzed = self.ppc.analyze_keywords(ppc_data)
        ranked = self.ranker.score_keywords(analyzed)

        # Display full ranked list
        self.ranker.display_rankings(ranked, limit=30)

        # Status breakdown tables
        for status, color, label in [
            ("WINNER", "green", "Winners - Keep & Scale"),
            ("POTENTIAL", "yellow", "Potential - Test & Optimize"),
            ("BLEEDING", "red", "Bleeding - Fix or Pause"),
            ("SLEEPING", "dim", "Sleeping - Low Engagement"),
        ]:
            subset = ranked[ranked["Status"] == status]
            if len(subset) > 0:
                console.print(Rule(f"{label} ({len(subset)} keywords)", style=color))
                self.ppc.display_keyword_table(subset, label, limit=15, currency=self.currency)

                report_lines.append(f"\n{label.upper()} ({len(subset)} keywords):")
                keyword_col = "Customer Search Term" if "Customer Search Term" in subset.columns else subset.columns[0]
                for i, (_, row) in enumerate(subset.head(15).iterrows()):
                    report_lines.append(
                        f"  {i+1}. {row.get(keyword_col, 'N/A')} | "
                        f"Score: {row.get('Total_Score', 0):.0f} | "
                        f"Grade: {row.get('Grade', '?')} | "
                        f"ACoS: {row.get('ACoS', 0):.1f}%"
                    )

        # AI insight per section
        if self.llm_available:
            data_context = self.llm.build_data_context(ranked)
            insight = self._get_ai_insight(
                "Provide a keyword audit summary. What patterns do you see? "
                "Which keyword categories need immediate attention?",
                data_context,
            )
            if insight:
                console.print(Panel(insight, title="AI Audit Insight", border_style="magenta"))
                report_lines.append(f"\nAI AUDIT INSIGHT:\n{insight}")

        report_text = "\n".join(report_lines)
        self._save_report(report_text, "keyword_audit")
        return report_text

    def budget_optimization_report(
        self,
        ppc_data: pd.DataFrame,
        campaign_data: Optional[pd.DataFrame] = None,
    ) -> str:
        """Generate a budget optimization report."""
        report_lines = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        console.print(Rule("Budget Optimization Report", style="bold blue"))
        report_lines.append(f"BUDGET OPTIMIZATION REPORT - {timestamp}\n{'='*60}\n")

        c = self.currency

        # Waste detection
        analyzed = self.ppc.analyze_keywords(ppc_data)
        waste = self.budget.find_waste(analyzed)
        self.budget.display_waste_report(waste)

        report_lines.append(f"Total Spend: {c}{waste['total_spend']:,.2f}")
        report_lines.append(f"Total Waste: {c}{waste['total_waste']:,.2f} ({waste['waste_pct']:.1f}%)")

        # Campaign allocation
        data_for_campaigns = campaign_data if campaign_data is not None else ppc_data
        campaign_alloc = self.budget.get_campaign_budget_allocation(data_for_campaigns)

        if campaign_alloc is not None and len(campaign_alloc) > 0:
            console.print(Rule("Campaign Budget Allocation", style="yellow"))

            alloc_table = Table(title="Current Budget Allocation", show_lines=True)
            alloc_table.add_column("Campaign", style="cyan", max_width=30)
            alloc_table.add_column("Spend", justify="right")
            alloc_table.add_column("% of Budget", justify="right")
            alloc_table.add_column("Revenue", justify="right")
            alloc_table.add_column("ACoS", justify="right")
            alloc_table.add_column("ROAS", justify="right")

            for _, row in campaign_alloc.iterrows():
                acos_color = "green" if row["ACoS"] <= self.config["target_acos"] else "red"
                alloc_table.add_row(
                    str(row["Campaign Name"])[:30],
                    f"{c}{row['Spend']:,.2f}",
                    f"{row['Budget_Pct']:.1f}%",
                    f"[green]{c}{row['Sales']:,.2f}[/green]",
                    f"[{acos_color}]{row['ACoS']:.1f}%[/{acos_color}]",
                    f"{row['ROAS']:.2f}x",
                )
            console.print(alloc_table)

            # Reallocation suggestions
            suggestions = self.budget.suggest_reallocation(campaign_alloc)
            if suggestions:
                console.print(Rule("Budget Reallocation Suggestions", style="green"))
                sug_table = Table(title="Recommended Moves", show_lines=True)
                sug_table.add_column("#", width=4)
                sug_table.add_column("From Campaign", style="red", max_width=25)
                sug_table.add_column("To Campaign", style="green", max_width=25)
                sug_table.add_column("Amount", justify="right", style="bold")
                sug_table.add_column("Reason", max_width=40)

                for i, sug in enumerate(suggestions):
                    sug_table.add_row(
                        str(i + 1),
                        str(sug["from_campaign"])[:25],
                        str(sug["to_campaign"])[:25],
                        f"{c}{sug['amount']:,.2f}",
                        sug["reason"],
                    )
                console.print(sug_table)

                report_lines.append("\nREALLOCATION SUGGESTIONS:")
                for sug in suggestions:
                    report_lines.append(
                        f"  Move {c}{sug['amount']:,.2f} from '{sug['from_campaign']}' "
                        f"to '{sug['to_campaign']}' - {sug['reason']}"
                    )

        # AI insight
        if self.llm_available:
            data_context = self.llm.build_data_context(analyzed)
            insight = self._get_ai_insight(
                "Analyze the budget allocation and waste. What's the single most impactful "
                "budget change this seller should make today? Be specific with dollar amounts.",
                data_context,
            )
            if insight:
                console.print(Panel(insight, title="AI Budget Insight", border_style="magenta"))
                report_lines.append(f"\nAI BUDGET INSIGHT:\n{insight}")

        report_text = "\n".join(report_lines)
        self._save_report(report_text, "budget_optimization")
        return report_text

    def competitor_gap_report(
        self,
        gap_keywords: list[str],
        shared_keywords: list[str],
        bid_estimates: list[dict],
    ) -> str:
        """Generate a competitor gap report."""
        report_lines = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        console.print(Rule("Competitor Gap Report", style="bold blue"))
        report_lines.append(f"COMPETITOR GAP REPORT - {timestamp}\n{'='*60}\n")

        c = self.currency

        # Gap keywords with bid suggestions
        if gap_keywords:
            table = Table(title=f"Missing Keywords ({len(gap_keywords)} found)", show_lines=True)
            table.add_column("#", width=4)
            table.add_column("Keyword", style="green", max_width=35)
            table.add_column("Est. CPC", justify="right")
            table.add_column("Suggested Bid", justify="right", style="bold")
            table.add_column("Match Type", justify="center")
            table.add_column("Traffic Est.", justify="center")

            bid_map = {b["keyword"]: b for b in bid_estimates}

            for i, kw in enumerate(gap_keywords[:30]):
                bid_data = bid_map.get(kw, {})
                word_count = len(kw.split())
                traffic = "HIGH" if word_count <= 2 else "MEDIUM" if word_count <= 4 else "LOW"
                t_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}[traffic]

                table.add_row(
                    str(i + 1),
                    kw[:35],
                    f"{c}{bid_data.get('estimated_cpc', 0):.2f}",
                    f"[green]{c}{bid_data.get('suggested_bid', 0):.2f}[/green]",
                    bid_data.get("match_type", "Broad"),
                    f"[{t_color}]{traffic}[/{t_color}]",
                )
            console.print(table)

            report_lines.append(f"\nGAP KEYWORDS ({len(gap_keywords)}):")
            for kw in gap_keywords:
                bid_data = bid_map.get(kw, {})
                report_lines.append(
                    f"  {kw} | Bid: {c}{bid_data.get('suggested_bid', 0):.2f} | "
                    f"Match: {bid_data.get('match_type', 'Broad')}"
                )

        # Campaign structure suggestion
        if gap_keywords:
            console.print(Rule("Suggested Campaign Structure", style="cyan"))

            exact_kws = [kw for kw in gap_keywords if len(kw.split()) <= 3]
            phrase_kws = [kw for kw in gap_keywords if 2 <= len(kw.split()) <= 4]
            broad_kws = [kw for kw in gap_keywords if len(kw.split()) >= 3]

            struct = Table(title="New Campaign Structure", show_lines=True)
            struct.add_column("Campaign", style="bold")
            struct.add_column("Match Type", justify="center")
            struct.add_column("Keywords", justify="right")
            struct.add_column("Strategy")

            struct.add_row("SP - Gap Exact", "[green]Exact[/green]", str(len(exact_kws)),
                           "High-intent, proven competitor terms")
            struct.add_row("SP - Gap Phrase", "[cyan]Phrase[/cyan]", str(len(phrase_kws)),
                           "Medium intent, broader coverage")
            struct.add_row("SP - Gap Discovery", "[yellow]Broad[/yellow]", str(len(broad_kws)),
                           "Long-tail discovery, low bids")
            console.print(struct)

        report_text = "\n".join(report_lines)
        self._save_report(report_text, "competitor_gap")
        return report_text

    def _display_wow_comparison(self, current: dict, previous: dict) -> None:
        """Display week-over-week comparison table."""
        c = self.currency
        table = Table(title="Week-over-Week Comparison", show_lines=True)
        table.add_column("Metric", style="bold")
        table.add_column("This Week", justify="right")
        table.add_column("Last Week", justify="right")
        table.add_column("Change", justify="right")

        metrics = [
            ("Spend", "total_spend", True, False),
            ("Revenue", "total_sales", True, False),
            ("Orders", "total_orders", False, False),
            ("ACoS", "overall_acos", False, True),
            ("ROAS", "overall_roas", False, False),
            ("CTR", "overall_ctr", False, False),
            ("CPC", "overall_cpc", True, True),
        ]

        for label, key, is_currency, lower_better in metrics:
            curr = current[key]
            prev = previous[key]
            change = ((curr - prev) / prev * 100) if prev > 0 else 0

            if is_currency:
                curr_str = f"{c}{curr:,.2f}"
                prev_str = f"{c}{prev:,.2f}"
            elif "acos" in key or "ctr" in key or "conv" in key:
                curr_str = f"{curr:.1f}%"
                prev_str = f"{prev:.1f}%"
            elif "roas" in key:
                curr_str = f"{curr:.2f}x"
                prev_str = f"{prev:.2f}x"
            else:
                curr_str = f"{curr:,.0f}"
                prev_str = f"{prev:,.0f}"

            # Color: green if improving, red if worsening
            if lower_better:
                color = "green" if change < 0 else "red" if change > 0 else "white"
            else:
                color = "green" if change > 0 else "red" if change < 0 else "white"

            change_str = f"[{color}]{change:+.1f}%[/{color}]"
            table.add_row(label, curr_str, prev_str, change_str)

        console.print(table)

    def _save_report(self, report_text: str, report_type: str) -> Path:
        """Save report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_type}_{timestamp}.txt"
        filepath = REPORT_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_text)

        console.print(f"\n[dim]Report saved: {filepath}[/dim]")
        logger.info(f"Report saved: {filepath}")
        return filepath
