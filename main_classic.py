"""Amazon PPC Intelligence Terminal — Classic Rich CLI (menu-driven interface).

This is the original Rich-based CLI that provides all 19 analysis tools
through a numbered menu loop. Launch via:
    python main.py --classic
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt, FloatPrompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config, save_config, ensure_dirs
from ingestion.csv_reader import load_csv, load_folder, display_load_summary
from analysis.ppc_analyzer import PPCAnalyzer
from analysis.sales_analyzer import SalesAnalyzer
from analysis.budget_analyzer import BudgetAnalyzer
from analysis.keyword_ranker import KeywordRanker
from analysis.cannibalization import CannibalizationDetector
from analysis.harvester import SearchTermHarvester
from analysis.placement import PlacementAnalyzer
from analysis.dayparting import DaypartingAnalyzer
from analysis.tacos_tracker import TACOSTracker
from analysis.negative_audit import NegativeKeywordAuditor
from analysis.profitability import ProfitabilityCalculator
from analysis.lifecycle import LifecycleDetector, STAGES
from analysis.ad_type_split import AdTypeSplitAnalyzer
from analysis.seasonality import SeasonalityAnalyzer
from competitor.scraper import CompetitorScraper
from competitor.bid_estimator import BidEstimator
from competitor.price_monitor import PriceMonitor
from reporting.report_generator import ReportGenerator
from reporting.export import Exporter
from reporting.bulk_upload import BulkUploadGenerator
from ai.llm_client import LLMClient, QUICK_PROMPTS

logger = logging.getLogger(__name__)
console = Console()

# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = r"""
[bold cyan]
    ╔═══════════════════════════════════════════════════════════╗
    ║     Amazon PPC Intelligence Terminal  v2.0                ║
    ║     ─────────────────────────────────────────             ║
    ║     Data-driven PPC optimization for Amazon sellers       ║
    ╚═══════════════════════════════════════════════════════════╝
[/bold cyan]"""

MENU = """
[bold white] ── Data ──────────────────────────────────────────────────[/bold white]
  [cyan] 1[/cyan]  Load CSV / Folder          Load Amazon report files
[bold white] ── Analysis ──────────────────────────────────────────────[/bold white]
  [cyan] 2[/cyan]  PPC Analysis               Keyword classification & KPI dashboard
  [cyan] 3[/cyan]  Budget Waste Detector       Find wasted ad spend & action items
  [cyan] 4[/cyan]  Competitor Research         Scrape Amazon SERPs & keyword gap
  [cyan] 5[/cyan]  Bid Suggestions             CPC estimates & budget calculator
  [cyan] 6[/cyan]  Search Term Harvester       Auto → manual keyword migration
  [cyan] 7[/cyan]  Cannibalization Detector    Find internal auction competition
  [cyan] 8[/cyan]  Negative Keyword Audit      Group & clean wasteful search terms
  [cyan] 9[/cyan]  Placement & Dayparting      Performance by placement / day-of-week
  [cyan]10[/cyan]  TACoS Tracker               Total ACoS trend over time
  [cyan]11[/cyan]  Profitability Calculator    True profit per ASIN after all costs
  [cyan]12[/cyan]  Campaign Lifecycle          Detect stage & adjust strategy
  [cyan]13[/cyan]  Ad Type Split (SP/SB/SD)    Performance breakdown by ad type
  [cyan]14[/cyan]  Seasonality & Events        Amazon event calendar & alerts
[bold white] ── Reports & Tools ───────────────────────────────────────[/bold white]
  [cyan]15[/cyan]  Generate Reports            Weekly / Audit / Budget reports
  [cyan]16[/cyan]  AI Chat (Ollama)            Ask AI about your PPC data
  [cyan]17[/cyan]  Bulk Upload Generator       Create Amazon-ready bulk CSVs
  [cyan]18[/cyan]  Export Data                 Export analysis to CSV / TXT / PDF
[bold white] ── Configuration ─────────────────────────────────────────[/bold white]
  [cyan]19[/cyan]  Settings                    Configure targets, costs & thresholds
  [cyan] 0[/cyan]  Exit
"""


# ── Application state ────────────────────────────────────────────────────────

class AppState:
    """Hold all loaded data and configuration for the session."""

    def __init__(self):
        self.config: dict = load_config()
        self.loaded_reports: list[dict] = []
        self.ppc_data: Optional[pd.DataFrame] = None
        self.business_data: Optional[pd.DataFrame] = None
        self.campaign_data: Optional[pd.DataFrame] = None
        self.placement_data: Optional[pd.DataFrame] = None
        self.analyzed_data: Optional[pd.DataFrame] = None
        self.currency: str = self.config.get("currency", "$")

    def refresh_config(self):
        self.config = load_config()
        self.currency = self.config.get("currency", "$")

    # Helper — pick best PPC data available
    @property
    def best_ppc(self) -> Optional[pd.DataFrame]:
        return self.ppc_data if self.ppc_data is not None else self.campaign_data


# ── Menu handlers ─────────────────────────────────────────────────────────────

def require_data(state: AppState, kind: str = "ppc") -> bool:
    """Return True if the required data is loaded, else print a warning."""
    if kind == "ppc" and state.best_ppc is None:
        console.print("[red]No PPC data loaded. Please load a Search Term or Campaign report first (option 1).[/red]")
        return False
    if kind == "business" and state.business_data is None:
        console.print("[red]No Business Report loaded. Please load one first (option 1).[/red]")
        return False
    return True


# ── 1. Load ──────────────────────────────────────────────────────────────────

def handle_load(state: AppState):
    console.print(Rule("Load Amazon Report Data", style="cyan"))
    console.print("  [cyan]1[/cyan] Load a single CSV file")
    console.print("  [cyan]2[/cyan] Load all CSVs from a folder")
    choice = Prompt.ask("Select", choices=["1", "2"], default="1")

    if choice == "1":
        file_path = Prompt.ask("[cyan]Enter file path[/cyan]").strip().strip('"')
        result = load_csv(file_path)
        if result:
            state.loaded_reports.append(result)
            _assign_report(state, result)
    else:
        folder = Prompt.ask("[cyan]Enter folder path[/cyan]").strip().strip('"')
        results = load_folder(folder)
        for r in results:
            state.loaded_reports.append(r)
            _assign_report(state, r)

    if state.loaded_reports:
        display_load_summary(state.loaded_reports)
        _show_data_status(state)


def _assign_report(state: AppState, report: dict):
    """Route a loaded report to the correct slot based on detected type."""
    rtype = report["type"]
    df = report["data"]
    if rtype == "search_term":
        state.ppc_data = df
        console.print(f"[green]Search Term Report assigned ({len(df)} rows)[/green]")
    elif rtype == "campaign":
        state.campaign_data = df
        if state.ppc_data is None:
            state.ppc_data = df
        console.print(f"[green]Campaign Report assigned ({len(df)} rows)[/green]")
    elif rtype == "business":
        state.business_data = df
        console.print(f"[green]Business Report assigned ({len(df)} rows)[/green]")
    elif rtype == "placement":
        state.placement_data = df
        console.print(f"[green]Placement Report assigned ({len(df)} rows)[/green]")
    else:
        # Best-effort: if it has common PPC columns, treat as PPC
        if "Spend" in df.columns and "Clicks" in df.columns:
            if state.ppc_data is None:
                state.ppc_data = df
            console.print(f"[yellow]Unknown report type — assigned as PPC data ({len(df)} rows)[/yellow]")
        else:
            console.print(f"[yellow]Unknown report type — stored but not assigned ({len(df)} rows)[/yellow]")


def _show_data_status(state: AppState):
    table = Table(title="Data Slots", show_lines=True)
    table.add_column("Slot", style="bold")
    table.add_column("Status", justify="right")
    table.add_column("Rows", justify="right")
    for label, df in [
        ("PPC / Search Term", state.ppc_data),
        ("Campaign", state.campaign_data),
        ("Business Report", state.business_data),
        ("Placement", state.placement_data),
    ]:
        if df is not None:
            table.add_row(label, "[green]Loaded[/green]", str(len(df)))
        else:
            table.add_row(label, "[dim]Empty[/dim]", "-")
    console.print(table)


# ── 2. PPC Analysis ─────────────────────────────────────────────────────────

def handle_ppc_analysis(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("PPC Keyword Analysis", style="green"))

    analyzer = PPCAnalyzer(state.config)
    analyzed = analyzer.analyze_keywords(state.best_ppc)
    state.analyzed_data = analyzed

    kpis = analyzer.get_kpi_summary(analyzed)
    analyzer.display_kpi_dashboard(kpis, state.currency)

    # Winners
    winners = analyzer.get_winners(analyzed)
    if len(winners) > 0:
        console.print(Rule("Top Winners", style="green"))
        analyzer.display_keyword_table(winners, "Winning Keywords", limit=15, currency=state.currency)

    # Bleeding
    bleeding = analyzer.get_bleeding(analyzed)
    if len(bleeding) > 0:
        console.print(Rule("Bleeding Keywords", style="red"))
        analyzer.display_keyword_table(bleeding, "Bleeding Keywords", limit=15, currency=state.currency)

    # Sleeping
    sleeping = analyzer.get_sleeping(analyzed)
    if len(sleeping) > 0:
        console.print(Rule("Sleeping Keywords", style="dim"))
        analyzer.display_keyword_table(sleeping, "Sleeping Keywords", limit=10, currency=state.currency)

    # Potential
    potential = analyzer.get_potential(analyzed)
    if len(potential) > 0:
        console.print(Rule("Potential Keywords", style="yellow"))
        analyzer.display_keyword_table(potential, "Potential Keywords", limit=10, currency=state.currency)

    # Keyword rankings
    ranker = KeywordRanker(state.config)
    ranked = ranker.score_keywords(analyzed)
    console.print(Rule("Keyword Rankings", style="cyan"))
    ranker.display_rankings(ranked, limit=20)


# ── 3. Budget Waste Detector ─────────────────────────────────────────────────

def handle_waste(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("Budget Waste Detector", style="red"))

    budget = BudgetAnalyzer(state.config)
    waste = budget.find_waste(state.best_ppc.copy())
    budget.display_waste_report(waste)

    # Campaign allocation
    data_for_camps = state.campaign_data if state.campaign_data is not None else state.best_ppc
    camp_alloc = budget.get_campaign_budget_allocation(data_for_camps)
    if camp_alloc is not None and len(camp_alloc) > 0:
        console.print(Rule("Campaign Budget Allocation", style="yellow"))
        c = state.currency
        alloc_table = Table(title="Budget by Campaign", show_lines=True)
        alloc_table.add_column("Campaign", style="cyan", max_width=30)
        alloc_table.add_column("Spend", justify="right")
        alloc_table.add_column("% Budget", justify="right")
        alloc_table.add_column("Revenue", justify="right")
        alloc_table.add_column("ACoS", justify="right")
        alloc_table.add_column("ROAS", justify="right")
        for _, row in camp_alloc.iterrows():
            acos_color = "green" if row["ACoS"] <= state.config["target_acos"] else "red"
            alloc_table.add_row(
                str(row["Campaign Name"])[:30],
                f"{c}{row['Spend']:,.2f}",
                f"{row['Budget_Pct']:.1f}%",
                f"[green]{c}{row['Sales']:,.2f}[/green]",
                f"[{acos_color}]{row['ACoS']:.1f}%[/{acos_color}]",
                f"{row['ROAS']:.2f}x",
            )
        console.print(alloc_table)

        suggestions = budget.suggest_reallocation(camp_alloc)
        if suggestions:
            console.print(Rule("Reallocation Suggestions", style="green"))
            for i, s in enumerate(suggestions):
                console.print(
                    f"  [cyan]{i+1}.[/cyan] Move [bold]{c}{s['amount']:,.2f}[/bold] "
                    f"from [red]{s['from_campaign']}[/red] to [green]{s['to_campaign']}[/green] "
                    f"— {s['reason']}"
                )


# ── 4. Competitor Research ───────────────────────────────────────────────────

def handle_competitor(state: AppState):
    console.print(Rule("Competitor Research", style="magenta"))
    console.print("  [cyan]1[/cyan] Search Amazon for a keyword (scrape SERP)")
    console.print("  [cyan]2[/cyan] Keyword gap analysis (requires loaded PPC data)")
    console.print("  [cyan]3[/cyan] Competitor price monitor")
    choice = Prompt.ask("Select", choices=["1", "2", "3"], default="1")

    if choice == "1":
        keyword = Prompt.ask("[cyan]Enter keyword to search[/cyan]")
        scraper = CompetitorScraper(state.config)
        results = scraper.search_keyword(keyword)
        scraper.display_search_results(results)

        if results.get("organic"):
            comp_keywords = scraper.extract_keywords_from_titles(results["organic"])
            if comp_keywords:
                console.print(f"\n[bold]Keywords extracted from competitor titles ({len(comp_keywords)}):[/bold]")
                for i, kw in enumerate(comp_keywords[:20]):
                    console.print(f"  [dim]{i+1}.[/dim] {kw}")

    elif choice == "2":
        keyword = Prompt.ask("[cyan]Enter keyword to search for competitors[/cyan]")
        scraper = CompetitorScraper(state.config)
        results = scraper.search_keyword(keyword)

        if results.get("organic"):
            comp_keywords = scraper.extract_keywords_from_titles(results["organic"])

            your_keywords = []
            if state.best_ppc is not None:
                kw_col = "Customer Search Term" if "Customer Search Term" in state.best_ppc.columns else state.best_ppc.columns[0]
                your_keywords = state.best_ppc[kw_col].dropna().unique().tolist()

            comparison = scraper.compare_keywords(comp_keywords, your_keywords)
            scraper.display_keyword_comparison(comparison)

            # Bid estimates for gap keywords
            if comparison["gap"]:
                estimator = BidEstimator(state.config)
                sponsored_count = len(results.get("sponsored", []))
                estimates = estimator.estimate_from_search_data(
                    comparison["gap"],
                    existing_data=state.best_ppc,
                    sponsored_count=sponsored_count,
                )
                estimator.display_bid_suggestions(estimates)
        else:
            console.print("[yellow]No organic results found to extract competitor keywords.[/yellow]")

    elif choice == "3":
        monitor = PriceMonitor(state.config)
        console.print("  [cyan]1[/cyan] Check all tracked competitor ASINs")
        console.print("  [cyan]2[/cyan] Check a specific ASIN")
        console.print("  [cyan]3[/cyan] View price history for an ASIN")
        sub = Prompt.ask("Select", choices=["1", "2", "3"], default="1")

        if sub == "1":
            results = monitor.check_all_competitors()
            monitor.display_report(results)
        elif sub == "2":
            asin = Prompt.ask("[cyan]Enter ASIN[/cyan]")
            price = monitor.fetch_price(asin)
            if price:
                console.print(f"[green]{price['asin']}[/green]: {state.currency}{price['price']:.2f} — {price.get('title', '')[:60]}")
        else:
            asin = Prompt.ask("[cyan]Enter ASIN[/cyan]")
            days = IntPrompt.ask("Days of history", default=30)
            monitor.display_price_history(asin, days)


# ── 5. Bid Suggestions ──────────────────────────────────────────────────────

def handle_bids(state: AppState):
    console.print(Rule("Bid Suggestions & Budget Calculator", style="green"))
    console.print("  [cyan]1[/cyan] Estimate bids for keywords (from file or manual)")
    console.print("  [cyan]2[/cyan] Daily budget calculator")
    choice = Prompt.ask("Select", choices=["1", "2"], default="1")

    estimator = BidEstimator(state.config)

    if choice == "1":
        kw_input = Prompt.ask("[cyan]Enter keywords (comma-separated)[/cyan]")
        keywords = [k.strip() for k in kw_input.split(",") if k.strip()]
        if not keywords:
            console.print("[yellow]No keywords entered.[/yellow]")
            return

        estimates = estimator.estimate_from_search_data(
            keywords,
            existing_data=state.best_ppc,
            sponsored_count=3,  # default medium competition
        )
        estimator.display_bid_suggestions(estimates)

    else:
        c = state.currency
        target_acos = FloatPrompt.ask("Target ACoS (%)", default=state.config["target_acos"])
        avg_order = FloatPrompt.ask(f"Average order value ({c})", default=25.0)
        daily_orders = IntPrompt.ask("Target daily PPC orders", default=5)
        conv_rate = FloatPrompt.ask("Expected conversion rate (%)", default=10.0)

        budget = estimator.calculate_daily_budget(target_acos, avg_order, daily_orders, conv_rate)
        estimator.display_budget_suggestion(budget)


# ── 6. Search Term Harvester ─────────────────────────────────────────────────

def handle_harvester(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("Search Term Harvester", style="green"))

    harvester = SearchTermHarvester(state.config)
    result = harvester.harvest(state.best_ppc.copy())
    harvester.display_report(result)

    if result["promote_count"] > 0 or result["negative_count"] > 0:
        if Confirm.ask("Generate Amazon bulk upload CSV?", default=True):
            campaign = Prompt.ask("Manual campaign name", default="SP - Manual Exact - Harvested")
            ad_group = Prompt.ask("Ad group name", default="Harvested Keywords")
            harvester.generate_bulk_csv(result, campaign, ad_group)


# ── 7. Cannibalization Detector ──────────────────────────────────────────────

def handle_cannibalization(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("Cannibalization Detector", style="red"))

    detector = CannibalizationDetector(state.config)
    result = detector.detect(state.best_ppc.copy())
    detector.display_report(result)


# ── 8. Negative Keyword Audit ────────────────────────────────────────────────

def handle_negative_audit(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("Negative Keyword Audit", style="red"))

    auditor = NegativeKeywordAuditor(state.config)
    result = auditor.audit(state.best_ppc.copy())
    auditor.display_report(result)

    if result["total_count"] > 0:
        if Confirm.ask("Export negative keyword list as Amazon bulk CSV?", default=True):
            campaign = Prompt.ask("Campaign name (blank = per-term)", default="")
            auditor.export_negative_list(result, campaign)


# ── 9. Placement & Dayparting ────────────────────────────────────────────────

def handle_placement_dayparting(state: AppState):
    console.print(Rule("Placement & Dayparting Analysis", style="yellow"))
    console.print("  [cyan]1[/cyan] Placement performance (Top of Search / Product Pages / Rest)")
    console.print("  [cyan]2[/cyan] Day-of-week performance")
    console.print("  [cyan]3[/cyan] Both")
    choice = Prompt.ask("Select", choices=["1", "2", "3"], default="3")

    if choice in ("1", "3"):
        placement_df = state.placement_data if state.placement_data is not None else state.best_ppc
        if placement_df is None:
            console.print("[red]No placement or PPC data loaded.[/red]")
        else:
            placement_analyzer = PlacementAnalyzer(state.config)
            result = placement_analyzer.analyze(placement_df.copy())
            placement_analyzer.display_report(result)

    if choice in ("2", "3"):
        if not require_data(state):
            return
        dayparting = DaypartingAnalyzer(state.config)
        day_data = dayparting.analyze_by_day(state.best_ppc.copy())
        dayparting.display_day_report(day_data)

        hour_data = dayparting.analyze_by_hour(state.best_ppc.copy())
        if hour_data is not None:
            dayparting.display_hour_heatmap(hour_data)


# ── 10. TACoS Tracker ───────────────────────────────────────────────────────

def handle_tacos_tracker(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("TACoS Tracker", style="blue"))

    tracker = TACOSTracker(state.config)

    # Daily trend
    biz_data = state.business_data if state.business_data is not None else state.best_ppc
    daily = tracker.calculate_daily_tacos(state.best_ppc, biz_data)
    tracker.display_trend(daily)

    # Per-ASIN TACoS
    if state.business_data is not None:
        asin_tacos = tracker.calculate_asin_tacos(state.best_ppc, state.business_data)
        tracker.display_asin_tacos(asin_tacos)

    # Overall PPC vs Organic
    sales_analyzer = SalesAnalyzer(state.config)
    breakdown = sales_analyzer.calculate_breakdown(state.best_ppc, state.business_data)
    sales_analyzer.display_breakdown(breakdown)


# ── 11. Profitability Calculator ─────────────────────────────────────────────

def handle_profitability(state: AppState):
    if state.business_data is None:
        console.print("[red]Profitability requires a Business Report with ASIN data. Load one first (option 1).[/red]")
        return
    console.print(Rule("ASIN Profitability Calculator", style="green"))

    # Let the user set per-session COGS if desired
    c = state.currency
    if Confirm.ask(f"Current COGS={c}{state.config['cogs_per_unit']:.2f}, FBA Fee={c}{state.config['fba_fee']:.2f}. Update?", default=False):
        state.config["cogs_per_unit"] = FloatPrompt.ask(f"COGS per unit ({c})", default=state.config["cogs_per_unit"])
        state.config["fba_fee"] = FloatPrompt.ask(f"FBA fee per unit ({c})", default=state.config["fba_fee"])
        state.config["referral_fee_pct"] = FloatPrompt.ask("Referral fee %", default=state.config["referral_fee_pct"])

    calc = ProfitabilityCalculator(state.config)
    result = calc.calculate(state.business_data, state.best_ppc)
    calc.display_report(result)


# ── 12. Campaign Lifecycle ───────────────────────────────────────────────────

def handle_lifecycle(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("Campaign Lifecycle Detection", style="cyan"))

    detector = LifecycleDetector(state.config)

    review_count = None
    listing_age = None
    if Confirm.ask("Do you know your review count and listing age? (improves accuracy)", default=False):
        review_count = IntPrompt.ask("Number of reviews", default=0)
        listing_age = IntPrompt.ask("Listing age in days", default=90)

    result = detector.detect_stage(state.best_ppc.copy(), review_count, listing_age)
    detector.display_report(result)

    # Stage-adjusted recommendations
    if state.analyzed_data is not None:
        recs = detector.get_adjusted_recommendations(result, state.analyzed_data)
        if recs["keywords_to_pause"]:
            console.print(f"\n[red]Keywords to pause ({len(recs['keywords_to_pause'])}):[/red]")
            for kw in recs["keywords_to_pause"][:15]:
                console.print(f"  [red]-[/red] {kw}")
        if recs["keywords_to_scale"]:
            console.print(f"\n[green]Keywords to scale ({len(recs['keywords_to_scale'])}):[/green]")
            for kw in recs["keywords_to_scale"][:15]:
                console.print(f"  [green]+[/green] {kw}")


# ── 13. Ad Type Split ────────────────────────────────────────────────────────

def handle_ad_type_split(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("Ad Type Split Analysis (SP / SB / SD)", style="yellow"))

    splitter = AdTypeSplitAnalyzer(state.config)
    summaries = splitter.analyze_all(state.best_ppc.copy())
    splitter.display_report(summaries)


# ── 14. Seasonality & Events ────────────────────────────────────────────────

def handle_seasonality(state: AppState):
    console.print(Rule("Amazon Seasonality & Event Calendar", style="magenta"))

    analyzer = SeasonalityAnalyzer(state.config)
    analyzer.display_calendar()
    analyzer.display_alerts()


# ── 15. Generate Reports ─────────────────────────────────────────────────────

def handle_reports(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("Report Generator", style="blue"))
    console.print("  [cyan]1[/cyan] Weekly Performance Report")
    console.print("  [cyan]2[/cyan] Keyword Audit Report")
    console.print("  [cyan]3[/cyan] Budget Optimization Report")
    choice = Prompt.ask("Select", choices=["1", "2", "3"], default="1")

    gen = ReportGenerator(state.config)

    if choice == "1":
        gen.weekly_performance_report(state.best_ppc, state.business_data)
    elif choice == "2":
        gen.keyword_audit_report(state.best_ppc)
    elif choice == "3":
        gen.budget_optimization_report(state.best_ppc, state.campaign_data)


# ── 16. AI Chat ──────────────────────────────────────────────────────────────

def handle_ai_chat(state: AppState):
    console.print(Rule("AI Chat (Ollama)", style="magenta"))

    llm = LLMClient(state.config)
    if not llm.check_connection():
        console.print("[red]Cannot connect to Ollama. Is it running?[/red]")
        console.print("[dim]Start Ollama with: ollama serve[/dim]")
        console.print(f"[dim]Configured endpoint: {state.config['ollama_endpoint']}[/dim]")
        console.print(f"[dim]Configured model: {state.config['ollama_model']}[/dim]")
        return

    if not llm.check_model_available():
        console.print(f"[yellow]Model '{state.config['ollama_model']}' not found in Ollama.[/yellow]")
        console.print(f"[dim]Pull it with: ollama pull {state.config['ollama_model']}[/dim]")
        return

    console.print(f"[green]Connected to Ollama ({state.config['ollama_model']})[/green]")

    # Build data context
    data_context = ""
    if state.analyzed_data is not None:
        data_context = llm.build_data_context(state.analyzed_data)
    elif state.best_ppc is not None:
        analyzer = PPCAnalyzer(state.config)
        analyzed = analyzer.analyze_keywords(state.best_ppc)
        data_context = llm.build_data_context(analyzed)

    # Show quick prompts
    console.print("\n[bold]Quick prompts:[/bold]")
    for key, prompt_info in QUICK_PROMPTS.items():
        console.print(f"  [cyan]{key}[/cyan] {prompt_info['label']}")
    console.print("  [dim]Or type your own question. Type 'exit' to return to menu.[/dim]\n")

    while True:
        user_input = Prompt.ask("[bold magenta]You[/bold magenta]").strip()
        if not user_input or user_input.lower() in ("exit", "quit", "back", "q"):
            break

        # Check for quick prompt
        if user_input in QUICK_PROMPTS:
            user_input = QUICK_PROMPTS[user_input]["prompt"]

        if user_input.lower() == "clear":
            llm.clear_history()
            continue

        console.print(Rule(style="dim"))
        llm.chat(user_input, data_context=data_context, stream=True)
        console.print(Rule(style="dim"))


# ── 17. Bulk Upload Generator ────────────────────────────────────────────────

def handle_bulk_upload(state: AppState):
    if not require_data(state):
        return
    console.print(Rule("Bulk Upload Generator", style="green"))

    # Ensure we have analyzed data
    if state.analyzed_data is None:
        analyzer = PPCAnalyzer(state.config)
        state.analyzed_data = analyzer.analyze_keywords(state.best_ppc)

    console.print("  [cyan]1[/cyan] Generate ALL bulk actions (pause + bid changes + negatives + promote)")
    console.print("  [cyan]2[/cyan] Pause bleeding keywords only")
    console.print("  [cyan]3[/cyan] Bid reductions for high-ACoS keywords")
    console.print("  [cyan]4[/cyan] Negative keywords only")
    console.print("  [cyan]5[/cyan] Promote winners (bid up)")
    choice = Prompt.ask("Select", choices=["1", "2", "3", "4", "5"], default="1")

    action_map = {"1": "all", "2": "pause", "3": "bid_down", "4": "negative", "5": "promote"}
    action = action_map[choice]

    gen = BulkUploadGenerator(state.config)
    files = gen.generate_from_analysis(state.analyzed_data, action_type=action)
    gen.display_summary(files)


# ── 18. Export Data ──────────────────────────────────────────────────────────

def handle_export(state: AppState):
    console.print(Rule("Export Data", style="cyan"))
    console.print("  [cyan]1[/cyan] Export analyzed keywords to CSV")
    console.print("  [cyan]2[/cyan] Export waste report to CSV")
    console.print("  [cyan]3[/cyan] Export all loaded PPC data to CSV")
    console.print("  [cyan]4[/cyan] Export bid suggestions to CSV")
    choice = Prompt.ask("Select", choices=["1", "2", "3", "4"], default="1")

    exporter = Exporter()

    if choice == "1":
        if state.analyzed_data is None:
            if not require_data(state):
                return
            analyzer = PPCAnalyzer(state.config)
            state.analyzed_data = analyzer.analyze_keywords(state.best_ppc)
        exporter.export_analyzed_keywords(state.analyzed_data, prefix="analyzed_keywords")

    elif choice == "2":
        if not require_data(state):
            return
        budget = BudgetAnalyzer(state.config)
        waste = budget.find_waste(state.best_ppc.copy())
        recs = budget.get_recommendations(waste)
        exporter.export_waste_report(waste, recs)

    elif choice == "3":
        if not require_data(state):
            return
        exporter.to_csv(state.best_ppc, "ppc_data_export")

    elif choice == "4":
        kw_input = Prompt.ask("[cyan]Enter keywords (comma-separated)[/cyan]")
        keywords = [k.strip() for k in kw_input.split(",") if k.strip()]
        if keywords:
            estimator = BidEstimator(state.config)
            estimates = estimator.estimate_from_search_data(keywords, state.best_ppc)
            exporter.export_bid_suggestions(estimates)
        else:
            console.print("[yellow]No keywords entered.[/yellow]")


# ── 19. Settings ─────────────────────────────────────────────────────────────

def handle_settings(state: AppState):
    console.print(Rule("Settings & Configuration", style="yellow"))

    cfg = state.config
    c = cfg["currency"]

    # Display current settings
    table = Table(title="Current Settings", show_lines=True)
    table.add_column("Setting", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Description", style="dim")

    settings_display = [
        ("target_acos", f"{cfg['target_acos']}%", "Target ACoS for keyword classification"),
        ("break_even_acos", f"{cfg['break_even_acos']}%", "Break-even ACoS (max before loss)"),
        ("currency", cfg["currency"], "Currency symbol"),
        ("marketplace", cfg["marketplace"], "Amazon marketplace"),
        ("cogs_per_unit", f"{c}{cfg['cogs_per_unit']:.2f}", "Cost of goods per unit"),
        ("fba_fee", f"{c}{cfg['fba_fee']:.2f}", "FBA fee per unit"),
        ("referral_fee_pct", f"{cfg['referral_fee_pct']}%", "Amazon referral fee percentage"),
        ("bleeding_acos_threshold", f"{cfg['bleeding_acos_threshold']}%", "ACoS threshold for 'bleeding' status"),
        ("waste_acos_threshold", f"{cfg['waste_acos_threshold']}%", "ACoS threshold for waste detection"),
        ("harvest_clicks_threshold", str(cfg["harvest_clicks_threshold"]), "Min clicks for harvest promotion"),
        ("harvest_orders_threshold", str(cfg["harvest_orders_threshold"]), "Min orders for harvest promotion"),
        ("negative_clicks_threshold", str(cfg["negative_clicks_threshold"]), "Min clicks for negative suggestion"),
        ("negative_spend_threshold", f"{c}{cfg['negative_spend_threshold']:.2f}", "Min spend for negative suggestion"),
        ("bid_multiplier", f"{cfg['bid_multiplier']}x", "Multiplier for suggested bids"),
        ("ollama_endpoint", cfg["ollama_endpoint"], "Ollama API endpoint"),
        ("ollama_model", cfg["ollama_model"], "Ollama LLM model"),
        ("campaign_stage", cfg.get("campaign_stage", "auto"), "Campaign lifecycle stage (auto/LAUNCH/GROWTH/MATURE)"),
        ("seasonality_alert_days", str(cfg.get("seasonality_alert_days", 21)), "Days ahead for seasonality alerts"),
        ("competitor_asins", str(len(cfg.get("competitor_asins", []))) + " ASINs", "Tracked competitor ASINs"),
    ]

    for name, value, desc in settings_display:
        table.add_row(name, value, desc)
    console.print(table)

    if not Confirm.ask("Edit settings?", default=False):
        return

    console.print("\n[dim]Press Enter to keep current value.[/dim]\n")

    # Editable fields
    editable = [
        ("target_acos", "Target ACoS (%)", "float"),
        ("break_even_acos", "Break-even ACoS (%)", "float"),
        ("currency", "Currency symbol", "str"),
        ("marketplace", "Marketplace (US/UK/DE/FR/IT/ES/CA/AU/IN/JP)", "str"),
        ("cogs_per_unit", f"COGS per unit ({c})", "float"),
        ("fba_fee", f"FBA fee per unit ({c})", "float"),
        ("referral_fee_pct", "Referral fee %", "float"),
        ("bleeding_acos_threshold", "Bleeding ACoS threshold (%)", "float"),
        ("waste_acos_threshold", "Waste ACoS threshold (%)", "float"),
        ("harvest_clicks_threshold", "Harvest clicks threshold", "int"),
        ("harvest_orders_threshold", "Harvest orders threshold", "int"),
        ("negative_clicks_threshold", "Negative clicks threshold", "int"),
        ("negative_spend_threshold", f"Negative spend threshold ({c})", "float"),
        ("bid_multiplier", "Bid multiplier (e.g. 1.2)", "float"),
        ("ollama_endpoint", "Ollama endpoint URL", "str"),
        ("ollama_model", "Ollama model name", "str"),
        ("campaign_stage", "Campaign stage (auto/LAUNCH/GROWTH/MATURE)", "str"),
        ("seasonality_alert_days", "Seasonality alert days ahead", "int"),
    ]

    for key, label, dtype in editable:
        current = cfg[key]
        try:
            if dtype == "float":
                val = Prompt.ask(f"  {label}", default=str(current))
                if val != str(current):
                    cfg[key] = float(val)
            elif dtype == "int":
                val = Prompt.ask(f"  {label}", default=str(current))
                if val != str(current):
                    cfg[key] = int(val)
            else:
                val = Prompt.ask(f"  {label}", default=str(current))
                if val != str(current):
                    cfg[key] = val
        except (ValueError, KeyboardInterrupt):
            pass

    # Competitor ASINs
    if Confirm.ask("Edit competitor ASINs?", default=False):
        current_asins = cfg.get("competitor_asins", [])
        if current_asins:
            console.print(f"[dim]Current: {', '.join(current_asins)}[/dim]")
        asin_input = Prompt.ask("Enter ASINs (comma-separated, blank to keep current)", default="")
        if asin_input.strip():
            cfg["competitor_asins"] = [a.strip() for a in asin_input.split(",") if a.strip()]

    save_config(cfg)
    state.refresh_config()
    console.print("[green]Settings saved.[/green]")


# ── Main loop ─────────────────────────────────────────────────────────────────

HANDLERS = {
    "1": handle_load,
    "2": handle_ppc_analysis,
    "3": handle_waste,
    "4": handle_competitor,
    "5": handle_bids,
    "6": handle_harvester,
    "7": handle_cannibalization,
    "8": handle_negative_audit,
    "9": handle_placement_dayparting,
    "10": handle_tacos_tracker,
    "11": handle_profitability,
    "12": handle_lifecycle,
    "13": handle_ad_type_split,
    "14": handle_seasonality,
    "15": handle_reports,
    "16": handle_ai_chat,
    "17": handle_bulk_upload,
    "18": handle_export,
    "19": handle_settings,
}


def main():
    """Run the classic Rich CLI menu loop."""
    ensure_dirs()
    state = AppState()

    console.print(BANNER)

    # Startup seasonality check
    try:
        season = SeasonalityAnalyzer(state.config)
        startup_alerts = season.check_startup_alerts()
        if startup_alerts:
            console.print()
            for alert in startup_alerts:
                color = "red" if alert["urgency"] == "HIGH" else "yellow"
                console.print(f"  [{color}][{alert['urgency']}][/{color}] {alert['message']}")
            console.print()
    except Exception:
        pass

    while True:
        console.print(MENU)
        try:
            choice = Prompt.ask(
                "[bold cyan]Select option[/bold cyan]",
                default="0",
            ).strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice in ("0", "exit", "quit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break

        handler = HANDLERS.get(choice)
        if handler:
            try:
                handler(state)
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted.[/yellow]")
            except Exception as e:
                console.print(f"\n[red]Error: {e}[/red]")
                logger.exception(f"Handler {choice} error")
        else:
            console.print(f"[yellow]Invalid option: {choice}[/yellow]")

        console.print()


if __name__ == "__main__":
    main()
