"""Amazon PPC Intelligence — Textual TUI Application."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
)

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_config, save_config, ensure_dirs
from ingestion.document_parser import DocumentParser
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
from ai.llm_client import LLMClient
from ai.weekly_briefing import WeeklyBriefing

from ui.tooltips import METRICS_RU, MENU_ITEMS, ALERT_TOOLTIPS_RU
from ui.widgets import (
    KPIDashboard,
    AlertBox,
    StatusLegend,
    MetricCard,
    AnalysisTable,
    SubMenuBar,
    build_keyword_table,
    build_campaign_table,
    build_waste_table,
    build_harvest_table,
    status_color,
    acos_color,
    tip,
)

# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────

APP_CSS = """
Tooltip {
    background: #1a1a2e;
    color: #e0e0e0;
    border: round #4a4a8a;
    padding: 1 2;
    max-width: 50;
}

#app-grid {
    height: 100%;
}

#sidebar {
    width: 30;
    border-right: solid $primary-darken-2;
    overflow-y: auto;
    padding: 0;
}

#sidebar-title {
    text-align: center;
    text-style: bold;
    color: $accent;
    padding: 1 0;
    background: $primary-darken-3;
}

.menu-btn {
    width: 100%;
    min-width: 26;
    height: 1;
    border: none;
    background: transparent;
    margin: 0;
    padding: 0 1;
    text-align: left;
}
.menu-btn:hover {
    background: $primary-darken-1;
}
.menu-btn:focus {
    background: $primary;
    text-style: bold;
}

#sidebar-legend {
    border-top: solid $primary-darken-3;
    margin-top: 1;
}

#content {
    overflow-y: auto;
    padding: 1 2;
}

.section-title {
    text-style: bold;
    margin: 1 0 0 0;
    padding: 0 1;
    background: $primary-darken-3;
    width: 100%;
}

.sub-text {
    margin: 0 0 1 0;
    color: $text-muted;
}

.input-row {
    height: 3;
    margin: 0 0 1 0;
}
.input-row Input {
    width: 1fr;
}
.input-row Button {
    width: 12;
    margin-left: 1;
}

#status-bar {
    dock: bottom;
    height: 1;
    background: $surface-darken-2;
    padding: 0 2;
    color: $text-muted;
}

/* Chat screen */
#chat-log {
    height: 1fr;
    border: round $accent-darken-1;
    margin: 0 0 1 0;
}
#chat-input-row {
    height: 3;
    dock: bottom;
}
#chat-input-row Input {
    width: 1fr;
}
#chat-input-row Button {
    width: 10;
    margin-left: 1;
}

/* Settings screen */
.settings-row {
    height: 3;
    margin: 0 0 0 0;
}
.settings-row Label {
    width: 28;
    padding: 1 1;
    text-style: bold;
}
.settings-row Input {
    width: 1fr;
}

/* KPI cards */
KPIDashboard Horizontal {
    height: auto;
}
"""


# ─────────────────────────────────────────────────────────────
# AI Chat Screen (full-screen overlay)
# ─────────────────────────────────────────────────────────────

class AIChatScreen(ModalScreen[None]):
    """Full-screen AI chat with Ollama."""

    BINDINGS = [Binding("escape", "dismiss", "Back")]

    def __init__(self, config: dict, analyzed_data):
        super().__init__()
        self._config = config
        self._analyzed = analyzed_data
        self._llm = LLMClient(config)

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", wrap=True, markup=True)
        with Horizontal(id="chat-input-row"):
            yield Input(placeholder="Type your question or 1-5 for quick prompt...", id="chat-input")
            btn = Button("Send", id="chat-send", variant="primary")
            btn.tooltip = "Отправить вопрос AI ассистенту"
            yield btn
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#chat-log", RichLog)

        if not self._llm.check_connection():
            log.write(f"[red]Cannot connect to Ollama at {self._config['ollama_endpoint']}[/red]")
            log.write("[yellow]Start Ollama: ollama serve[/yellow]")
            return

        log.write("[bold cyan]AI PPC Assistant[/bold cyan] (Ollama)")
        log.write("[dim]Быстрые промпты:[/dim]")
        prompts = self._llm.get_quick_prompts()
        for k, v in prompts.items():
            log.write(f"  [yellow][{k}][/yellow] {v['label']}")
        log.write("[dim]Type 'exit' to return.[/dim]\n")

    @on(Button.Pressed, "#chat-send")
    def on_send(self) -> None:
        self._do_send()

    @on(Input.Submitted, "#chat-input")
    def on_submit(self) -> None:
        self._do_send()

    @work(thread=True)
    def _do_send(self) -> None:
        inp = self.query_one("#chat-input", Input)
        text = inp.value.strip()
        if not text:
            return
        self.call_from_thread(inp.clear)

        if text.lower() in ("exit", "quit", "q"):
            self.app.call_from_thread(self.dismiss)
            return

        log = self.query_one("#chat-log", RichLog)
        prompts = self._llm.get_quick_prompts()

        if text in prompts:
            self.call_from_thread(log.write, f"[dim]> {prompts[text]['label']}[/dim]")
            text = prompts[text]["prompt"]
        else:
            self.call_from_thread(log.write, f"[bold cyan]You:[/bold cyan] {text}")

        data_context = self._llm.build_data_context(self._analyzed)

        self.call_from_thread(log.write, "[bold magenta]AI:[/bold magenta]")
        response = self._llm.chat(text, data_context=data_context, stream=False)
        if response:
            self.call_from_thread(log.write, response)
        self.call_from_thread(log.write, "")


# ─────────────────────────────────────────────────────────────
# Settings Screen
# ─────────────────────────────────────────────────────────────

class SettingsScreen(ModalScreen[dict | None]):
    """Settings form as a modal screen."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    SETTINGS_FIELDS = [
        ("target_acos", "Target ACoS %", "ACoS"),
        ("break_even_acos", "Break-Even ACoS %", "Break-even"),
        ("currency", "Currency Symbol", ""),
        ("marketplace", "Marketplace", ""),
        ("cogs_per_unit", "COGS per Unit", "COGS"),
        ("fba_fee", "FBA Fee per Unit", ""),
        ("referral_fee_pct", "Referral Fee %", ""),
        ("harvest_clicks_threshold", "Harvest Clicks Thr.", "Harvesting"),
        ("harvest_orders_threshold", "Harvest Orders Thr.", "Harvesting"),
        ("negative_clicks_threshold", "Negative Clicks Thr.", "Negative"),
        ("negative_spend_threshold", "Negative Spend Thr. $", "Negative"),
        ("ollama_model", "Ollama Model", ""),
        ("ollama_endpoint", "Ollama Endpoint", ""),
        ("campaign_stage", "Stage (auto/LAUNCH/GROWTH/MATURE)", "Lifecycle"),
    ]

    def __init__(self, config: dict):
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static("[bold]Settings[/bold]", classes="section-title")
            for key, label, tip_key in self.SETTINGS_FIELDS:
                with Horizontal(classes="settings-row"):
                    lbl = Label(label)
                    if tip_key:
                        lbl.tooltip = tip(tip_key)
                    yield lbl
                    yield Input(
                        value=str(self._config.get(key, "")),
                        id=f"set-{key}",
                    )
            with Horizontal(classes="input-row"):
                save_btn = Button("Save", id="settings-save", variant="success")
                save_btn.tooltip = "Сохранить настройки в config.json"
                yield save_btn
                cancel_btn = Button("Cancel", id="settings-cancel")
                cancel_btn.tooltip = "Отменить изменения"
                yield cancel_btn
        yield Footer()

    @on(Button.Pressed, "#settings-save")
    def on_save(self) -> None:
        for key, _, _ in self.SETTINGS_FIELDS:
            inp = self.query_one(f"#set-{key}", Input)
            val = inp.value.strip()
            # Preserve original type
            orig = self._config.get(key)
            if isinstance(orig, float):
                try:
                    val = float(val)
                except ValueError:
                    pass
            elif isinstance(orig, int):
                try:
                    val = int(val)
                except ValueError:
                    pass
            self._config[key] = val
        self.dismiss(self._config)

    @on(Button.Pressed, "#settings-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────────────────────────
# Main Application
# ─────────────────────────────────────────────────────────────

class AmazonPPCApp(App):
    """Amazon PPC Intelligence Terminal Application."""

    TITLE = "Amazon PPC Intelligence v2.0"
    CSS = APP_CSS
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "focus_sidebar", "Menu", show=False),
    ]

    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.cfg = load_config()
        self.parser = DocumentParser()
        self.analyzed_data = None

    # ── Layout ───────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="app-grid"):
            with VerticalScroll(id="sidebar"):
                yield Static("AMAZON PPC", id="sidebar-title")
                for item in MENU_ITEMS:
                    btn = Button(
                        f" [{item['key']}] {item['label']}",
                        id=f"menu-{item['id']}",
                        classes="menu-btn",
                    )
                    btn.tooltip = item["tooltip"]
                    yield btn
                yield Static("", id="sidebar-legend")
                yield StatusLegend()
            with VerticalScroll(id="content"):
                yield Static(
                    "[bold cyan]Welcome to Amazon PPC Intelligence[/bold cyan]\n\n"
                    "Select an option from the menu.\n"
                    "Hover over any metric or status for a [italic]Russian explanation[/italic].",
                    id="welcome-msg",
                )
        yield Static("", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self._update_status_bar()
        # Startup seasonality alerts
        try:
            season = SeasonalityAnalyzer(self.cfg)
            alerts = season.check_startup_alerts()
            if alerts:
                content = self.query_one("#content")
                for a in alerts:
                    color = "red" if a["urgency"] == "HIGH" else "yellow"
                    await content.mount(AlertBox(
                        f"[bold {color}]{a['message']}[/bold {color}]",
                        tooltip_key="event_urgent",
                        variant="warning",
                    ))
        except Exception:
            pass

    def _update_status_bar(self) -> None:
        bar = self.query_one("#status-bar", Static)
        if self.parser.has_data():
            summary = self.parser.get_summary()
            parts = [f"{v['files']} {k} ({v['total_rows']}r)" for k, v in summary.items()]
            bar.update(f"[green]Data:[/green] {' | '.join(parts)}")
        else:
            bar.update("[yellow]No data loaded — start with [1] Load Reports[/yellow]")

    def action_focus_sidebar(self) -> None:
        try:
            first_btn = self.query_one("#menu-load", Button)
            first_btn.focus()
        except Exception:
            pass

    # ── Analyzed data cache ──────────────────────────────────

    def _get_analyzed(self):
        if self.analyzed_data is not None:
            return self.analyzed_data
        data = self.parser.get_search_term_data()
        if data is None:
            data = self.parser.get_campaign_data()
        if data is None:
            return None
        analyzer = PPCAnalyzer(self.cfg)
        self.analyzed_data = analyzer.analyze_keywords(data)
        return self.analyzed_data

    # ── Content area helpers ─────────────────────────────────

    async def _clear_content(self) -> VerticalScroll:
        content = self.query_one("#content", VerticalScroll)
        await content.remove_children()
        return content

    async def _show_no_data(self, content) -> None:
        await content.mount(AlertBox(
            "[yellow]No PPC data loaded. Use [1] Load Reports first.[/yellow]",
            variant="warning",
        ))

    # ── Menu dispatcher ──────────────────────────────────────

    @on(Button.Pressed, ".menu-btn")
    async def on_menu_pressed(self, event: Button.Pressed) -> None:
        menu_id = event.button.id.replace("menu-", "")
        handler = getattr(self, f"_screen_{menu_id}", None)
        if handler:
            await handler()
        self._update_status_bar()

    # ── 1. Load Reports ──────────────────────────────────────

    async def _screen_load(self) -> None:
        content = await self._clear_content()
        await content.mount(Static("[bold]Load Reports[/bold]", classes="section-title"))
        await content.mount(Static("[dim]Enter a CSV/TXT file path or folder path.[/dim]", classes="sub-text"))

        row = Horizontal(classes="input-row")
        inp = Input(placeholder="File or folder path...", id="load-path")
        btn_file = Button("Load File", id="load-file-btn", variant="primary")
        btn_file.tooltip = "Загрузить один файл отчёта"
        btn_folder = Button("Load Folder", id="load-folder-btn")
        btn_folder.tooltip = "Загрузить все CSV из папки"
        await content.mount(row)
        await row.mount(inp, btn_file, btn_folder)
        await content.mount(RichLog(id="load-log", wrap=True, markup=True))

    @on(Button.Pressed, "#load-file-btn")
    async def _do_load_file(self) -> None:
        path = self.query_one("#load-path", Input).value.strip().strip('"').strip("'")
        log = self.query_one("#load-log", RichLog)
        if not path:
            log.write("[red]Enter a file path.[/red]")
            return
        result = self.parser.load_file(path)
        self.analyzed_data = None
        if result:
            s = result["summary"]
            log.write(f"[green]Loaded:[/green] {s['label']} — {s['rows']} rows from {s['file']}")
        else:
            log.write(f"[red]Failed to load: {path}[/red]")
        self._update_status_bar()

    @on(Button.Pressed, "#load-folder-btn")
    async def _do_load_folder(self) -> None:
        path = self.query_one("#load-path", Input).value.strip().strip('"').strip("'")
        log = self.query_one("#load-log", RichLog)
        if not path:
            log.write("[red]Enter a folder path.[/red]")
            return
        results = self.parser.load_directory(path)
        self.analyzed_data = None
        if results:
            for r in results:
                s = r["summary"]
                log.write(f"[green]Loaded:[/green] {s['label']} — {s['rows']} rows from {s['file']}")
            log.write(f"\n[bold]{len(results)} file(s) loaded.[/bold]")
        else:
            log.write(f"[yellow]No CSV/TXT files found in {path}[/yellow]")
        self._update_status_bar()

    # ── 2. PPC Analysis ──────────────────────────────────────

    async def _screen_ppc(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        analyzer = PPCAnalyzer(self.cfg)
        kpis = analyzer.get_kpi_summary(analyzed)
        await content.mount(KPIDashboard(kpis, self.cfg))

        # Status breakdown
        total = kpis["total_keywords"] or 1
        status_text = (
            f"[green]Winners: {kpis['winners']}[/green] ({kpis['winners']/total*100:.0f}%)  "
            f"[red]Bleeding: {kpis['bleeding']}[/red]  "
            f"[dim]Sleeping: {kpis['sleeping']}[/dim]  "
            f"[yellow]Potential: {kpis['potential']}[/yellow]  "
            f"Total: {total}"
        )
        s = Static(status_text)
        s.tooltip = tip("Status")
        await content.mount(s)

        # Tables
        winners = analyzer.get_winners(analyzed)
        if len(winners) > 0:
            await content.mount(build_keyword_table(winners, "Top Winners", self.cfg))

        bleeding = analyzer.get_bleeding(analyzed)
        if len(bleeding) > 0:
            await content.mount(build_keyword_table(bleeding, "Bleeding Keywords", self.cfg))

        potential = analyzer.get_potential(analyzed)
        if len(potential) > 0:
            await content.mount(build_keyword_table(potential, "Potential Keywords", self.cfg, limit=10))

        # Sales breakdown
        business = self.parser.get_business_data()
        ppc = self.parser.get_search_term_data() or self.parser.get_campaign_data()
        if business is not None:
            sa = SalesAnalyzer(self.cfg)
            bd = sa.calculate_breakdown(ppc, business)
            c = self.cfg["currency"]
            await content.mount(AlertBox(
                f"[bold]PPC vs Organic:[/bold] PPC {c}{bd['ppc_sales']:,.2f} ({bd['ppc_pct']:.1f}%) | "
                f"Organic {c}{bd['organic_sales']:,.2f} ({bd['organic_pct']:.1f}%) | "
                f"TACoS {bd['tacos']:.1f}%",
                tooltip_key="tacos_rising" if bd["tacos"] > 20 else "",
                variant="info",
            ))

    # ── 3. Budget Waste ──────────────────────────────────────

    async def _screen_waste(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        ba = BudgetAnalyzer(self.cfg)
        waste = ba.find_waste(analyzed)
        c = self.cfg["currency"]

        await content.mount(AlertBox(
            f"[bold red]Total Waste: {c}{waste['total_waste']:,.2f}[/bold red] "
            f"({waste['waste_pct']:.1f}% of {c}{waste['total_spend']:,.2f} spend)\n"
            f"Zero-order waste: {c}{waste['zero_order_waste']:,.2f} | "
            f"High-ACoS excess: {c}{waste['high_acos_waste']:,.2f}",
            tooltip_key="waste_summary",
        ))

        if len(waste["zero_orders"]) > 0:
            await content.mount(build_waste_table(waste["zero_orders"], self.cfg))

        recs = ba.get_recommendations(waste)
        if recs:
            cols = [
                ("#", "Rank", 4), ("Keyword", "Customer Search Term", 24),
                ("Waste", "Waste", 10), ("Action", "Action", 12), ("Reason", "", 30),
            ]
            rows = []
            for i, r in enumerate(recs[:20]):
                rows.append([
                    str(i+1), str(r["keyword"])[:24],
                    f"{c}{r['spend']:,.2f}", r["action"], r["reason"][:30],
                ])
            await content.mount(AnalysisTable("Recommended Actions", cols, rows))

    # ── 4. Competitor Research ────────────────────────────────

    async def _screen_competitor(self) -> None:
        content = await self._clear_content()
        await content.mount(Static("[bold]Competitor Research[/bold]", classes="section-title"))
        await content.mount(SubMenuBar([
            ("comp-search", "Search Keyword", "Поиск по ключевому слову на Amazon"),
            ("comp-prices", "Check Prices", "Проверить цены конкурентов по ASIN"),
        ]))
        row = Horizontal(classes="input-row")
        await content.mount(row)
        inp = Input(placeholder="Enter keyword or ASIN...", id="comp-input")
        btn = Button("Go", id="comp-go", variant="primary")
        await row.mount(inp, btn)
        await content.mount(RichLog(id="comp-log", wrap=True, markup=True))

    @on(Button.Pressed, "#comp-go")
    @work(thread=True)
    def _do_competitor_search(self) -> None:
        text = self.query_one("#comp-input", Input).value.strip()
        log = self.query_one("#comp-log", RichLog)
        if not text:
            return

        self.call_from_thread(log.write, f"[dim]Searching for '{text}'...[/dim]")
        scraper = CompetitorScraper(self.cfg)
        data = scraper.search_keyword(text)

        if data.get("error"):
            self.call_from_thread(log.write, f"[red]Error: {data['error']}[/red]")
            return

        for r in data.get("organic", [])[:10]:
            self.call_from_thread(
                log.write,
                f"[cyan]#{r['position']}[/cyan] {r['title'][:50]} | {r['price']} | {r['asin']}",
            )

        if data.get("sponsored"):
            self.call_from_thread(log.write, f"\n[yellow]Sponsored: {len(data['sponsored'])} results[/yellow]")

        keywords = scraper.extract_keywords_from_titles(data.get("organic", []))
        if keywords:
            self.call_from_thread(log.write, f"\n[green]Extracted {len(keywords)} competitor keywords:[/green]")
            for kw in keywords[:20]:
                self.call_from_thread(log.write, f"  {kw}")

    @on(Button.Pressed, "#comp-prices")
    @work(thread=True)
    def _do_price_check(self) -> None:
        text = self.query_one("#comp-input", Input).value.strip()
        log = self.query_one("#comp-log", RichLog)
        asins = [a.strip() for a in text.split(",") if a.strip()] if text else self.cfg.get("competitor_asins", [])
        if not asins:
            self.call_from_thread(log.write, "[yellow]Enter ASINs or configure in Settings.[/yellow]")
            return

        monitor = PriceMonitor(self.cfg)
        results = monitor.check_all_competitors(asins)
        c = self.cfg["currency"]
        for r in results:
            alert_str = ""
            if r.get("alert"):
                alert_str = f" [red]{r['alert']['message']}[/red]"
            self.call_from_thread(
                log.write,
                f"[cyan]{r['asin']}[/cyan] {c}{r['price']:.2f} {r.get('title', '')[:30]}{alert_str}",
            )

    # ── 5. Bids & Budget ─────────────────────────────────────

    async def _screen_bids(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        estimator = BidEstimator(self.cfg)
        c = self.cfg["currency"]

        potential = analyzed[analyzed["Status"].isin(["POTENTIAL", "WINNER"])].copy()
        if len(potential) == 0:
            await content.mount(Static("[yellow]No winning/potential keywords to suggest bids for.[/yellow]"))
            return

        keyword_col = "Customer Search Term" if "Customer Search Term" in potential.columns else potential.columns[0]
        keywords = potential[keyword_col].tolist()[:20]
        estimates = estimator.estimate_from_search_data(keywords, analyzed)

        cols = [
            ("#", "Rank", 4), ("Keyword", "Customer Search Term", 24),
            ("Est. CPC", "CPC", 9), ("Suggested Bid", "Suggested Bid", 12),
            ("Match", "Match Type", 8), ("Competition", "", 10),
        ]
        rows = []
        for i, e in enumerate(estimates):
            rows.append([
                str(i+1), e["keyword"][:24],
                f"{c}{e['estimated_cpc']:.2f}", f"{c}{e['suggested_bid']:.2f}",
                e["match_type"], e["competition"].upper(),
            ])
        await content.mount(AnalysisTable("Bid Suggestions for Top Keywords", cols, rows))

    # ── 6. Harvester ─────────────────────────────────────────

    async def _screen_harvest(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        harvester = SearchTermHarvester(self.cfg)
        result = harvester.harvest(analyzed)
        c = self.cfg["currency"]

        await content.mount(AlertBox(
            f"[green]Promote to Exact:[/green] {result['promote_count']} terms | "
            f"[red]Add Negative:[/red] {result['negative_count']} terms | "
            f"[cyan]Standalone:[/cyan] {result['standalone_count']} terms\n"
            f"Potential Savings: [bold green]{c}{result['potential_savings']:,.2f}[/bold green]",
            tooltip_key="harvest_promote",
            variant="success",
        ))

        if result["promote_count"] > 0:
            await content.mount(build_harvest_table(result["promote_exact"], "Promote to Manual Exact", self.cfg))

        if result["negative_count"] > 0:
            await content.mount(build_harvest_table(result["add_negative"], "Add as Negative Exact", self.cfg))

        btn = Button("Export Bulk CSV", id="harvest-export", variant="success")
        btn.tooltip = "Выгрузить CSV для массовой загрузки\nв Amazon Seller Central"
        await content.mount(btn)
        self._harvest_result = result

    @on(Button.Pressed, "#harvest-export")
    def _do_harvest_export(self) -> None:
        if hasattr(self, "_harvest_result"):
            harvester = SearchTermHarvester(self.cfg)
            path = harvester.generate_bulk_csv(self._harvest_result)
            self.notify(f"Exported to {path}", title="Bulk CSV Ready")

    # ── 7. Cannibalization ───────────────────────────────────

    async def _screen_cannibal(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        detector = CannibalizationDetector(self.cfg)
        result = detector.detect(analyzed)
        c = self.cfg["currency"]

        if result["term_count"] == 0:
            await content.mount(AlertBox(
                "[green]No cannibalization detected.[/green]",
                variant="success",
            ))
            return

        await content.mount(AlertBox(
            f"[red]{result['term_count']}[/red] search terms in multiple campaigns\n"
            f"Estimated waste: [bold red]{c}{result['total_waste']:,.2f}[/bold red]",
            tooltip_key="cannibal_summary",
        ))

        recs = result["recommendations"][:20]
        if recs:
            cols = [
                ("#", "Rank", 4), ("Search Term", "Customer Search Term", 20),
                ("Owner", "Campaign Name", 16), ("Duplicate", "Campaign Name", 16),
                ("Dup Spend", "Spend", 10), ("Est. Waste", "Waste", 10),
            ]
            rows = []
            for i, r in enumerate(recs):
                rows.append([
                    str(i+1), str(r["search_term"])[:20],
                    str(r["owner_campaign"])[:16], str(r["duplicate_campaign"])[:16],
                    f"{c}{r['duplicate_spend']:,.2f}", f"{c}{r['estimated_waste']:,.2f}",
                ])
            await content.mount(AnalysisTable("Cannibalization Actions", cols, rows))

    # ── 8. Negative Audit ────────────────────────────────────

    async def _screen_negatives(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        auditor = NegativeKeywordAuditor(self.cfg)
        result = auditor.audit(analyzed)
        c = self.cfg["currency"]

        await content.mount(AlertBox(
            f"[bold]{result['total_count']}[/bold] negative keyword candidates\n"
            f"Wasted: [red]{c}{result['total_waste']:,.2f}[/red] | "
            f"Monthly savings: [green]{c}{result['estimated_monthly_savings']:,.2f}[/green]",
            tooltip_key="harvest_negate",
        ))

        # Group summary
        groups = result["groups"]
        if groups:
            cols = [
                ("#", "Rank", 4), ("Root", "Negative", 16),
                ("Terms", "", 6), ("Total Spend", "Spend", 10),
                ("Samples", "", 28),
            ]
            rows = []
            for i, (name, data) in enumerate(list(groups.items())[:15]):
                samples = ", ".join(t["term"][:15] for t in data["terms"][:2])
                rows.append([
                    str(i+1), name.replace("root:", "").title()[:16],
                    str(data["count"]), f"{c}{data['total_spend']:,.2f}", samples[:28],
                ])
            await content.mount(AnalysisTable("Waste by Root Word Group", cols, rows))

        btn = Button("Export Negative List", id="neg-export", variant="error")
        btn.tooltip = "Выгрузить список минус-слов\nдля загрузки в Amazon"
        await content.mount(btn)
        self._neg_result = result

    @on(Button.Pressed, "#neg-export")
    def _do_neg_export(self) -> None:
        if hasattr(self, "_neg_result"):
            auditor = NegativeKeywordAuditor(self.cfg)
            path = auditor.export_negative_list(self._neg_result)
            self.notify(f"Exported to {path}", title="Negative Keywords Ready")

    # ── 9. Placement & Dayparting ────────────────────────────

    async def _screen_placement(self) -> None:
        content = await self._clear_content()
        await content.mount(Static("[bold]Placement & Dayparting[/bold]", classes="section-title"))
        await content.mount(SubMenuBar([
            ("place-perf", "Placements", "Анализ размещений: Верх поиска / Карточки / Остальное"),
            ("place-day", "Day-of-Week", "Эффективность по дням недели"),
        ]))
        await content.mount(Static("", id="placement-out"))

    @on(Button.Pressed, "#place-perf")
    async def _do_placement(self) -> None:
        content = self.query_one("#content", VerticalScroll)
        out = self.query_one("#placement-out", Static)

        data = self.parser.get_placement_data()
        if data is None:
            data = self.parser.get_campaign_data()
        if data is None or "Placement" not in (data.columns if data is not None else []):
            out.update("[yellow]No Placement data. Load a Placement Report.[/yellow]")
            return

        pa = PlacementAnalyzer(self.cfg)
        result = pa.analyze(data)
        placements = result["placements"]
        c = self.cfg["currency"]

        cols = [
            ("Placement", "Placement", 18), ("Spend", "Spend", 10),
            ("Revenue", "Sales", 10), ("ACoS", "ACoS", 8),
            ("ROAS", "ROAS", 7), ("CTR", "CTR", 7), ("CVR", "CVR", 7),
        ]
        labels = {"top": "Top of Search", "product": "Product Pages", "rest": "Rest of Search"}
        rows = []
        for _, row in placements.iterrows():
            p = row["Placement_Normalized"]
            rows.append([
                labels.get(p, p), f"{c}{row['Spend']:,.2f}",
                f"{c}{row['Sales']:,.2f}", f"{row['ACoS']:.1f}%",
                f"{row['ROAS']:.2f}x", f"{row['CTR']:.2f}%", f"{row['CVR']:.1f}%",
            ])

        try:
            await content.mount(AnalysisTable("Placement Performance", cols, rows))
        except Exception:
            out.update("Placement data displayed above.")

    @on(Button.Pressed, "#place-day")
    async def _do_dayparting(self) -> None:
        content = self.query_one("#content", VerticalScroll)
        out = self.query_one("#placement-out", Static)
        analyzed = self._get_analyzed()
        if analyzed is None:
            out.update("[yellow]No data loaded.[/yellow]")
            return

        dp = DaypartingAnalyzer(self.cfg)
        day_data = dp.analyze_by_day(analyzed)
        if day_data is None:
            out.update("[yellow]No date column in data for day-of-week analysis.[/yellow]")
            return

        c = self.cfg["currency"]
        cols = [
            ("Day", "Dayparting", 6), ("Orders", "Orders", 7),
            ("Spend", "Spend", 10), ("Revenue", "Sales", 10),
            ("ACoS", "ACoS", 8), ("CVR", "CVR", 7), ("CPC", "CPC", 7),
        ]
        rows = []
        for _, row in day_data.iterrows():
            rows.append([
                str(row.get("DayName", "?")), str(int(row["Orders"])),
                f"{c}{row['Spend']:,.2f}", f"{c}{row['Sales']:,.2f}",
                f"{row['ACoS']:.1f}%", f"{row['CVR']:.1f}%", f"{c}{row['CPC']:.2f}",
            ])

        try:
            await content.mount(AnalysisTable("Day-of-Week Performance", cols, rows))
        except Exception:
            pass

        schedule = dp.get_bid_schedule(day_data)
        if schedule:
            sched_text = "\n".join(
                f"  {s['day']}: {'[green]+' if s['adjustment']>0 else '[red]'}{s['adjustment']}%{'[/green]' if s['adjustment']>0 else '[/red]'} — {s['reason']}"
                for s in schedule
            )
            try:
                ab = AlertBox(f"[bold]Bid Schedule Recommendations:[/bold]\n{sched_text}", tooltip_key="", variant="info")
                ab.tooltip = METRICS_RU.get("Dayparting", "")
                await content.mount(ab)
            except Exception:
                pass

    # ── 10. TACoS Tracker ────────────────────────────────────

    async def _screen_tacos(self) -> None:
        content = await self._clear_content()
        ppc = self.parser.get_search_term_data() or self.parser.get_campaign_data()
        biz = self.parser.get_business_data()
        if ppc is None:
            await self._show_no_data(content)
            return

        tracker = TACOSTracker(self.cfg)
        c = self.cfg["currency"]

        # Per-ASIN TACoS
        if biz is not None:
            asin_data = tracker.calculate_asin_tacos(ppc, biz)
            if asin_data is not None and len(asin_data) > 0:
                cols = [
                    ("ASIN", "ASIN", 12), ("Total Sales", "Sales", 12),
                    ("Ad Spend", "Ad_Spend", 10), ("Organic %", "Organic", 9),
                    ("TACoS", "TACoS", 8),
                ]
                rows = []
                for _, row in asin_data.head(15).iterrows():
                    rows.append([
                        str(row["ASIN"]), f"{c}{row['Total_Sales']:,.2f}",
                        f"{c}{row['Ad_Spend']:,.2f}", f"{row['Organic_Pct']:.1f}%",
                        f"{row['TACoS']:.1f}%",
                    ])
                await content.mount(AnalysisTable("TACoS by ASIN", cols, rows))

            # Trend
            daily = tracker.calculate_daily_tacos(ppc, biz)
            if daily is not None:
                avg_t = daily["TACoS"].mean()
                tc = "green" if avg_t < 15 else "yellow" if avg_t < 25 else "red"
                await content.mount(AlertBox(
                    f"[bold]Average TACoS: [{tc}]{avg_t:.1f}%[/{tc}][/bold] | "
                    f"Range: {daily['TACoS'].min():.1f}% - {daily['TACoS'].max():.1f}% | "
                    f"Data points: {len(daily)}",
                    tooltip_key="tacos_rising" if avg_t > 20 else "tacos_falling",
                    variant="info",
                ))

                alerts = tracker.get_trend_alerts(daily)
                for a in alerts:
                    variant = "warning" if a["severity"] == "high" else "success"
                    await content.mount(AlertBox(
                        f"[bold]{a['type']}:[/bold] {a['message']}",
                        tooltip_key="tacos_rising" if "increas" in a["message"] else "tacos_falling",
                        variant=variant,
                    ))
        else:
            await content.mount(Static("[yellow]Load Business Report for TACoS analysis.[/yellow]"))

    # ── 11. Profitability ────────────────────────────────────

    async def _screen_profit(self) -> None:
        content = await self._clear_content()
        biz = self.parser.get_business_data()
        if biz is None:
            await content.mount(AlertBox("[red]Need Business Report with ASIN data.[/red]"))
            return

        ppc = self.parser.get_search_term_data() or self.parser.get_campaign_data()
        calc = ProfitabilityCalculator(self.cfg)
        profit = calc.calculate(biz, ppc)
        c = self.cfg["currency"]

        if len(profit) == 0:
            await content.mount(Static("[yellow]No profitability data.[/yellow]"))
            return

        total_rev = profit["Revenue"].sum()
        total_profit = profit["Net_Profit"].sum()
        margin = (total_profit / total_rev * 100) if total_rev > 0 else 0
        pc = "green" if total_profit > 0 else "red"

        await content.mount(AlertBox(
            f"Revenue: [green]{c}{total_rev:,.2f}[/green] | "
            f"Net Profit: [{pc}]{c}{total_profit:,.2f}[/{pc}] | "
            f"Margin: [{pc}]{margin:.1f}%[/{pc}]",
            tooltip_key="profit_alert" if total_profit < 0 else "",
            variant="success" if total_profit > 0 else "",
        ))

        cols = [
            ("ASIN", "ASIN", 12), ("Revenue", "Revenue", 10),
            ("Ad Spend", "Ad_Spend", 10), ("Profit", "Net_Profit", 10),
            ("Margin", "Profit_Margin", 8), ("Curr ACoS", "ACoS", 9),
            ("BE ACoS", "Break_Even_ACoS", 9), ("Status", "Status", 12),
        ]
        rows = []
        for _, row in profit.head(15).iterrows():
            sc = status_color(row["Status"])
            rows.append([
                str(row["ASIN"]),
                f"{c}{row['Revenue']:,.2f}",
                f"{c}{row['Ad_Spend']:,.2f}",
                f"{c}{row['Net_Profit']:,.2f}",
                f"{row['Profit_Margin']:.1f}%",
                f"{row['Current_ACoS']:.1f}%",
                f"{row['Break_Even_ACoS']:.1f}%",
                row["Status"],
            ])
        await content.mount(AnalysisTable("ASIN Profitability", cols, rows))

    # ── 12. Lifecycle ────────────────────────────────────────

    async def _screen_lifecycle(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        detector = LifecycleDetector(self.cfg)
        result = detector.detect_stage(analyzed)
        info = result["info"]
        color = info["color"]

        tt_key = f"lifecycle_{result['stage'].lower()}"

        await content.mount(AlertBox(
            f"[bold {color}]Stage: {info['label'].upper()}[/bold {color}]\n\n"
            f"{info['description']}\n\n"
            f"Break-even ACoS: {result['break_even_acos']:.1f}% | "
            f"Adjusted Target: {result['adjusted_target_acos']:.1f}% (x{info['acos_multiplier']})\n"
            f"Bid Strategy: {info['bid_strategy']}\n"
            f"Confidence: {result['confidence']}",
            tooltip_key=tt_key,
            variant="info",
        ))

        actions_text = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(info["actions"]))
        await content.mount(Static(f"[bold]Recommended Actions:[/bold]\n{actions_text}"))

        # Stage comparison
        cols = [("", "", 14)] + [(s["label"], "Lifecycle", 14) for s in STAGES.values()]
        rows = [
            ["ACoS Mult."] + [f"{s['acos_multiplier']}x" for s in STAGES.values()],
            ["Target ACoS"] + [f"{result['break_even_acos'] * s['acos_multiplier']:.0f}%" for s in STAGES.values()],
        ]
        await content.mount(AnalysisTable("Stage Comparison", cols, rows))

    # ── 13. SP/SB/SD Split ───────────────────────────────────

    async def _screen_adtype(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        splitter = AdTypeSplitAnalyzer(self.cfg)
        summaries = splitter.analyze_all(analyzed)
        c = self.cfg["currency"]

        labels = {"SP": "Sponsored Products", "SB": "Sponsored Brands", "SD": "Sponsored Display"}

        for ad_type, data in summaries.items():
            label = labels.get(ad_type, ad_type)
            await content.mount(MetricCard(
                f"{label} ({data['campaigns']} campaigns)",
                f"Spend {c}{data['spend']:,.2f} | Rev {c}{data['sales']:,.2f} | "
                f"ACoS {data['acos']:.1f}% | ROAS {data['roas']:.2f}x",
                tooltip_key=ad_type,
                color=acos_color(data["acos"], self.cfg["target_acos"]),
            ))

        recs = splitter.get_type_recommendations(summaries)
        for ad_type, rec_list in recs.items():
            for rec in rec_list:
                ab = AlertBox(f"[bold]{labels.get(ad_type, ad_type)}:[/bold] {rec}", variant="info")
                ab.tooltip = tip(ad_type)
                await content.mount(ab)

        await content.mount(AlertBox(
            "[yellow]Never average ACoS across ad types. SP/SB/SD have different KPIs.[/yellow]",
            variant="warning",
        ))

    # ── 14. Seasonality ──────────────────────────────────────

    async def _screen_season(self) -> None:
        content = await self._clear_content()
        season = SeasonalityAnalyzer(self.cfg)

        events = season.get_upcoming_events(90)
        if events:
            cols = [
                ("Event", "Seasonality", 16), ("Date", "", 12),
                ("Days", "", 6), ("Budget +%", "Budget", 10),
                ("Bid +%", "Bid", 8), ("Status", "", 10),
            ]
            rows = []
            for e in events:
                status = "URGENT" if e["days_until"] <= 7 else "PREPARE" if e["days_until"] <= 14 else "PLAN" if e["days_until"] <= 21 else "Upcoming"
                rows.append([
                    e["name"], str(e["date"]), str(e["days_until"]),
                    f"+{e['budget_increase']}%", f"+{e['bid_increase']}%", status,
                ])
            await content.mount(AnalysisTable("Amazon Event Calendar (90 days)", cols, rows))

        alerts = season.get_alerts()
        for a in alerts:
            color = "red" if a["urgency"] == "HIGH" else "yellow" if a["urgency"] == "MEDIUM" else "cyan"
            actions_text = "\n".join(f"  {i+1}. {act}" for i, act in enumerate(a["actions"]))
            await content.mount(AlertBox(
                f"[bold {color}]{a['urgency']}:[/bold {color}] {a['message']}\n{actions_text}",
                tooltip_key="event_urgent",
                variant="warning" if a["urgency"] != "LOW" else "info",
            ))

        if not events and not alerts:
            await content.mount(Static("[green]No upcoming events in the next 90 days.[/green]"))

    # ── 15. Reports ──────────────────────────────────────────

    async def _screen_reports(self) -> None:
        content = await self._clear_content()
        await content.mount(Static("[bold]Reports[/bold]", classes="section-title"))
        await content.mount(SubMenuBar([
            ("rpt-weekly", "Weekly Report", "Еженедельный отчёт по эффективности"),
            ("rpt-audit", "Keyword Audit", "Полный аудит всех ключевых слов"),
            ("rpt-budget", "Budget Report", "Отчёт по оптимизации бюджета"),
            ("rpt-briefing", "AI Briefing", "AI брифинг — резюме от менеджера"),
        ]))
        await content.mount(RichLog(id="rpt-log", wrap=True, markup=True))

    @on(Button.Pressed, "#rpt-briefing")
    @work(thread=True)
    def _do_briefing(self) -> None:
        log = self.query_one("#rpt-log", RichLog)
        analyzed = self._get_analyzed()
        if analyzed is None:
            self.call_from_thread(log.write, "[yellow]No data loaded.[/yellow]")
            return

        self.call_from_thread(log.write, "[dim]Generating AI briefing...[/dim]")
        briefing = WeeklyBriefing(self.cfg)
        text = briefing.generate(analyzed)
        if text:
            self.call_from_thread(log.write, text)
        else:
            self.call_from_thread(log.write, "[yellow]Could not generate briefing.[/yellow]")

    @on(Button.Pressed, "#rpt-weekly")
    @work(thread=True)
    def _do_weekly_report(self) -> None:
        log = self.query_one("#rpt-log", RichLog)
        ppc = self.parser.get_search_term_data() or self.parser.get_campaign_data()
        if ppc is None:
            self.call_from_thread(log.write, "[red]No data.[/red]")
            return
        self.call_from_thread(log.write, "[dim]Generating weekly report...[/dim]")
        gen = ReportGenerator(self.cfg)
        text = gen.weekly_performance_report(ppc, self.parser.get_business_data())
        self.call_from_thread(log.write, f"[green]Report saved to reports/ folder.[/green]")

    @on(Button.Pressed, "#rpt-audit")
    @work(thread=True)
    def _do_audit_report(self) -> None:
        log = self.query_one("#rpt-log", RichLog)
        ppc = self.parser.get_search_term_data() or self.parser.get_campaign_data()
        if ppc is None:
            self.call_from_thread(log.write, "[red]No data.[/red]")
            return
        self.call_from_thread(log.write, "[dim]Generating keyword audit...[/dim]")
        gen = ReportGenerator(self.cfg)
        gen.keyword_audit_report(ppc)
        self.call_from_thread(log.write, f"[green]Audit report saved to reports/ folder.[/green]")

    @on(Button.Pressed, "#rpt-budget")
    @work(thread=True)
    def _do_budget_report(self) -> None:
        log = self.query_one("#rpt-log", RichLog)
        ppc = self.parser.get_search_term_data() or self.parser.get_campaign_data()
        if ppc is None:
            self.call_from_thread(log.write, "[red]No data.[/red]")
            return
        self.call_from_thread(log.write, "[dim]Generating budget report...[/dim]")
        gen = ReportGenerator(self.cfg)
        gen.budget_optimization_report(ppc, self.parser.get_campaign_data())
        self.call_from_thread(log.write, f"[green]Budget report saved to reports/ folder.[/green]")

    # ── 16. AI Chat ──────────────────────────────────────────

    async def _screen_ai(self) -> None:
        analyzed = self._get_analyzed()
        screen = AIChatScreen(self.cfg, analyzed)
        self.push_screen(screen)

    # ── 17. Bulk Upload ──────────────────────────────────────

    async def _screen_bulk(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        await content.mount(Static("[bold]Bulk Upload Generator[/bold]", classes="section-title"))
        await content.mount(SubMenuBar([
            ("bulk-all", "All Actions", "Все действия: пауза + ставки + минус-слова"),
            ("bulk-pause", "Pause Only", "Только приостановка убыточных ключей"),
            ("bulk-neg", "Negatives Only", "Только минус-слова"),
            ("bulk-promote", "Bid Up Winners", "Повышение ставок на победителей"),
        ]))
        await content.mount(RichLog(id="bulk-log", wrap=True, markup=True))

    @on(Button.Pressed, "#bulk-all")
    def _do_bulk_all(self) -> None:
        self._run_bulk("all")

    @on(Button.Pressed, "#bulk-pause")
    def _do_bulk_pause(self) -> None:
        self._run_bulk("pause")

    @on(Button.Pressed, "#bulk-neg")
    def _do_bulk_neg(self) -> None:
        self._run_bulk("negative")

    @on(Button.Pressed, "#bulk-promote")
    def _do_bulk_promote(self) -> None:
        self._run_bulk("promote")

    def _run_bulk(self, action: str) -> None:
        analyzed = self._get_analyzed()
        if analyzed is None:
            return
        log = self.query_one("#bulk-log", RichLog)
        gen = BulkUploadGenerator(self.cfg)
        files = gen.generate_from_analysis(analyzed, action_type=action)
        for f in files:
            if f and f.exists():
                log.write(f"[green]Created:[/green] {f.name}")
        if not files:
            log.write("[yellow]No actions to generate.[/yellow]")

    # ── 18. Export ────────────────────────────────────────────

    async def _screen_export(self) -> None:
        content = await self._clear_content()
        analyzed = self._get_analyzed()
        if analyzed is None:
            await self._show_no_data(content)
            return

        await content.mount(Static("[bold]Export Data[/bold]", classes="section-title"))
        await content.mount(SubMenuBar([
            ("exp-csv", "Keywords CSV", "Экспорт ключевых слов с метриками"),
            ("exp-waste", "Waste CSV", "Экспорт отчёта по потерям"),
            ("exp-txt", "Full Report TXT", "Полный отчёт в текстовом формате"),
        ]))
        await content.mount(RichLog(id="exp-log", wrap=True, markup=True))

    @on(Button.Pressed, "#exp-csv")
    def _do_exp_csv(self) -> None:
        analyzed = self._get_analyzed()
        if analyzed is None:
            return
        log = self.query_one("#exp-log", RichLog)
        exporter = Exporter()
        ranker = KeywordRanker(self.cfg)
        ranked = ranker.score_keywords(analyzed)
        path = exporter.export_analyzed_keywords(ranked)
        log.write(f"[green]Exported:[/green] {path}")

    @on(Button.Pressed, "#exp-waste")
    def _do_exp_waste(self) -> None:
        analyzed = self._get_analyzed()
        if analyzed is None:
            return
        log = self.query_one("#exp-log", RichLog)
        ba = BudgetAnalyzer(self.cfg)
        waste = ba.find_waste(analyzed)
        recs = ba.get_recommendations(waste)
        exporter = Exporter()
        path = exporter.export_waste_report(waste, recs)
        log.write(f"[green]Exported:[/green] {path}")

    @on(Button.Pressed, "#exp-txt")
    def _do_exp_txt(self) -> None:
        analyzed = self._get_analyzed()
        if analyzed is None:
            return
        log = self.query_one("#exp-log", RichLog)
        ppc = self.parser.get_search_term_data() or self.parser.get_campaign_data()
        gen = ReportGenerator(self.cfg)
        text = gen.keyword_audit_report(ppc)
        exporter = Exporter()
        path = exporter.to_txt(text, "full_report")
        log.write(f"[green]Exported:[/green] {path}")

    # ── 19. Settings ─────────────────────────────────────────

    async def _screen_settings(self) -> None:
        def on_dismiss(result: dict | None) -> None:
            if result is not None:
                self.cfg = result
                save_config(self.cfg)
                self.analyzed_data = None
                self.notify("Settings saved", title="Settings")
                self._update_status_bar()

        screen = SettingsScreen(self.cfg.copy())
        self.push_screen(screen, callback=on_dismiss)
