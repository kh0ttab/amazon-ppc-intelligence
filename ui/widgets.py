"""Reusable Textual widgets with Russian tooltip support."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import Static, Label, DataTable, Button
from textual.widget import Widget

from ui.tooltips import METRICS_RU, ALERT_TOOLTIPS_RU


# ── Helpers ──────────────────────────────────────────────────

def tip(key: str) -> str:
    """Look up a Russian tooltip by key. Returns empty string if missing."""
    return METRICS_RU.get(key, "")


def status_color(status: str) -> str:
    return {
        "WINNER": "green", "BLEEDING": "red", "SLEEPING": "dim",
        "POTENTIAL": "yellow", "NEW": "cyan",
        "PROFITABLE": "green", "MARGINAL": "yellow",
        "LOSING MONEY": "bold red", "BREAK EVEN": "dim",
    }.get(status, "white")


def acos_color(val: float, target: float) -> str:
    if val <= 0:
        return "dim"
    if val <= target:
        return "green"
    if val <= target * 2:
        return "yellow"
    return "red"


# ── MetricCard ───────────────────────────────────────────────

class MetricCard(Static):
    """Single KPI metric display with Russian hover tooltip."""

    DEFAULT_CSS = """
    MetricCard {
        width: 1fr;
        min-width: 14;
        height: 5;
        content-align: center middle;
        text-align: center;
        border: round $primary;
        margin: 0 1 1 0;
        padding: 1 1;
    }
    """

    def __init__(
        self,
        label: str,
        value: str,
        tooltip_key: str = "",
        color: str = "white",
        **kwargs,
    ):
        content = f"[bold {color}]{value}[/bold {color}]\n[dim]{label}[/dim]"
        super().__init__(content, **kwargs)
        if tooltip_key:
            self.tooltip = tip(tooltip_key)


# ── KPI Dashboard ────────────────────────────────────────────

class KPIDashboard(Widget):
    """Grid of MetricCards for top-level KPIs."""

    DEFAULT_CSS = """
    KPIDashboard {
        height: auto;
        margin: 0 0 1 0;
    }
    KPIDashboard Horizontal {
        height: auto;
    }
    """

    def __init__(self, kpis: dict, config: dict, **kwargs):
        super().__init__(**kwargs)
        self._kpis = kpis
        self._config = config

    def compose(self) -> ComposeResult:
        k = self._kpis
        c = self._config.get("currency", "$")
        target = self._config.get("target_acos", 25)
        ac = acos_color(k["overall_acos"], target)

        with Horizontal():
            yield MetricCard("Spend", f"{c}{k['total_spend']:,.2f}", "Spend", "red")
            yield MetricCard("Revenue", f"{c}{k['total_sales']:,.2f}", "Sales", "green")
            yield MetricCard("Orders", f"{k['total_orders']:,.0f}", "Orders", "cyan")
            yield MetricCard("ACoS", f"{k['overall_acos']:.1f}%", "ACoS", ac)

        with Horizontal():
            yield MetricCard("ROAS", f"{k['overall_roas']:.2f}x", "ROAS", "green")
            yield MetricCard("CTR", f"{k['overall_ctr']:.2f}%", "CTR", "yellow")
            yield MetricCard("CPC", f"{c}{k['overall_cpc']:.2f}", "CPC", "yellow")
            yield MetricCard("CVR", f"{k['overall_conv_rate']:.1f}%", "CVR", "cyan")


# ── StatusBadge ──────────────────────────────────────────────

class StatusBadge(Static):
    """Colored status text with Russian hover tooltip."""

    DEFAULT_CSS = """
    StatusBadge {
        width: auto;
        padding: 0 1;
    }
    """

    def __init__(self, status: str, **kwargs):
        color = status_color(status)
        super().__init__(f"[{color}]{status}[/{color}]", **kwargs)
        self.tooltip = tip(status)


# ── StatusLegend ─────────────────────────────────────────────

class StatusLegend(Vertical):
    """Sidebar legend: all statuses and metrics with Russian tooltips."""

    DEFAULT_CSS = """
    StatusLegend {
        height: auto;
        padding: 0 1;
    }
    StatusLegend .legend-section {
        margin: 1 0 0 0;
    }
    StatusLegend .legend-item {
        height: 1;
        padding: 0 1;
    }
    StatusLegend .legend-item:hover {
        background: $surface-lighten-1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[b dim]МЕТРИКИ[/b dim]", classes="legend-section")
        for key in ("ACoS", "ROAS", "CTR", "CPC", "CVR", "TACoS"):
            lbl = Static(f"[dim]{key}[/dim]  [dim italic]ℹ[/dim italic]", classes="legend-item")
            lbl.tooltip = tip(key)
            yield lbl

        yield Static("[b dim]СТАТУСЫ[/b dim]", classes="legend-section")
        for key in ("WINNER", "BLEEDING", "SLEEPING", "POTENTIAL", "NEW"):
            color = status_color(key)
            lbl = Static(f"[{color}]■[/{color}] [dim]{key}[/dim]", classes="legend-item")
            lbl.tooltip = tip(key)
            yield lbl

        yield Static("[b dim]ТИПЫ[/b dim]", classes="legend-section")
        for key in ("Exact", "Phrase", "Broad", "Negative"):
            lbl = Static(f"  [dim]{key}[/dim]", classes="legend-item")
            lbl.tooltip = tip(key)
            yield lbl


# ── AlertBox ─────────────────────────────────────────────────

class AlertBox(Static):
    """Alert / recommendation panel with Russian tooltip."""

    DEFAULT_CSS = """
    AlertBox {
        margin: 1 0;
        padding: 1 2;
        border: round $error;
        width: 100%;
    }
    AlertBox.warning { border: round $warning; }
    AlertBox.success { border: round $success; }
    AlertBox.info    { border: round $accent;  }
    """

    def __init__(
        self,
        content: str,
        tooltip_key: str = "",
        tooltip_text: str = "",
        variant: str = "",
        **kwargs,
    ):
        super().__init__(content, **kwargs)
        if variant:
            self.add_class(variant)
        if tooltip_key:
            self.tooltip = ALERT_TOOLTIPS_RU.get(tooltip_key, tip(tooltip_key))
        elif tooltip_text:
            self.tooltip = tooltip_text


# ── AnalysisTable ────────────────────────────────────────────

class AnalysisTable(Vertical):
    """DataTable with a separate row of tooltip-enabled header labels."""

    DEFAULT_CSS = """
    AnalysisTable {
        height: auto;
        max-height: 30;
        margin: 1 0;
    }
    AnalysisTable .at-title {
        text-style: bold;
        margin: 0 0 0 0;
        padding: 0 1;
        background: $primary-darken-3;
    }
    AnalysisTable .at-headers {
        height: 1;
        background: $surface-darken-1;
    }
    AnalysisTable .at-th {
        width: 1fr;
        padding: 0 1;
        text-style: bold;
    }
    AnalysisTable .at-th:hover {
        background: $surface-lighten-1;
    }
    """

    def __init__(
        self,
        title: str,
        columns: list[tuple[str, str, int]],
        rows: list[list[str]],
        **kwargs,
    ):
        """
        Args:
            title: Table title
            columns: [(label, tooltip_key, width), ...]
            rows: [[cell_str, ...], ...]
        """
        super().__init__(**kwargs)
        self._title = title
        self._columns = columns
        self._rows = rows

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="at-title")

        # Tooltip-enabled header row
        with Horizontal(classes="at-headers"):
            for label, tip_key, _width in self._columns:
                th = Static(f"[bold]{label}[/bold]", classes="at-th")
                th.tooltip = tip(tip_key) or tip(label)
                yield th

        # DataTable for the data rows (header hidden, we supply our own)
        yield DataTable(show_header=False, id="at-data", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#at-data", DataTable)
        for label, _tip_key, width in self._columns:
            table.add_column(label, width=width)
        for row in self._rows:
            table.add_row(*row)


# ── SubMenuBar ───────────────────────────────────────────────

class SubMenuBar(Horizontal):
    """Row of sub-action buttons with tooltips."""

    DEFAULT_CSS = """
    SubMenuBar {
        height: 3;
        margin: 0 0 1 0;
        dock: top;
    }
    SubMenuBar Button {
        margin: 0 1 0 0;
    }
    """

    def __init__(self, items: list[tuple[str, str, str]], **kwargs):
        """items: [(id, label, tooltip_ru), ...]"""
        super().__init__(**kwargs)
        self._items = items

    def compose(self) -> ComposeResult:
        for btn_id, label, tooltip_ru in self._items:
            btn = Button(label, id=btn_id)
            btn.tooltip = tooltip_ru
            yield btn


# ── Table builder helpers ────────────────────────────────────

def build_keyword_table(
    df,
    title: str,
    config: dict,
    limit: int = 15,
) -> AnalysisTable:
    """Build an AnalysisTable from an analyzed keyword DataFrame."""
    c = config.get("currency", "$")
    target = config.get("target_acos", 25)

    keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else (
        "Targeting" if "Targeting" in df.columns else df.columns[0]
    )

    columns = [
        ("#", "Rank", 4),
        ("Keyword", "Customer Search Term", 24),
        ("Spend", "Spend", 10),
        ("Revenue", "Sales", 10),
        ("Orders", "Orders", 7),
        ("ACoS", "ACoS", 8),
        ("ROAS", "ROAS", 7),
        ("CTR", "CTR", 7),
        ("CPC", "CPC", 7),
        ("CVR", "CVR", 6),
        ("Status", "Status", 10),
    ]

    rows = []
    for i, (_, row) in enumerate(df.head(limit).iterrows()):
        acos_val = row.get("ACoS", 0)
        sc = status_color(row.get("Status", ""))
        ac = acos_color(acos_val, target)
        rows.append([
            str(i + 1),
            str(row.get(keyword_col, ""))[:24],
            f"{c}{row.get('Spend', 0):,.2f}",
            f"{c}{row.get('Sales', 0):,.2f}",
            str(int(row.get("Orders", 0))),
            f"{acos_val:.1f}%",
            f"{row.get('ROAS', 0):.2f}x",
            f"{row.get('CTR', 0):.2f}%",
            f"{c}{row.get('CPC', 0):.2f}",
            f"{row.get('Conv_Rate', 0):.1f}%",
            str(row.get("Status", "")),
        ])

    return AnalysisTable(title=title, columns=columns, rows=rows)


def build_campaign_table(
    df,
    title: str,
    config: dict,
    limit: int = 15,
) -> AnalysisTable:
    """Build a campaign-level summary table."""
    c = config.get("currency", "$")

    columns = [
        ("#", "Rank", 4),
        ("Campaign", "Campaign Name", 24),
        ("Spend", "Spend", 10),
        ("Revenue", "Sales", 10),
        ("Orders", "Orders", 7),
        ("ACoS", "ACoS", 8),
        ("ROAS", "ROAS", 7),
    ]

    rows = []
    for i, (_, row) in enumerate(df.head(limit).iterrows()):
        rows.append([
            str(i + 1),
            str(row.get("Campaign Name", ""))[:24],
            f"{c}{row.get('Spend', 0):,.2f}",
            f"{c}{row.get('Sales', 0):,.2f}",
            str(int(row.get("Orders", 0))),
            f"{row.get('ACoS', 0):.1f}%",
            f"{row.get('ROAS', 0):.2f}x",
        ])

    return AnalysisTable(title=title, columns=columns, rows=rows)


def build_waste_table(df, config: dict, limit: int = 15) -> AnalysisTable:
    """Build a waste report table."""
    c = config.get("currency", "$")
    keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else (
        "Targeting" if "Targeting" in df.columns else df.columns[0]
    )

    columns = [
        ("#", "Rank", 4),
        ("Keyword", "Customer Search Term", 28),
        ("Spend", "Spend", 10),
        ("Clicks", "Clicks", 7),
        ("Impressions", "Impressions", 10),
    ]

    rows = []
    for i, (_, row) in enumerate(df.head(limit).iterrows()):
        rows.append([
            str(i + 1),
            str(row.get(keyword_col, ""))[:28],
            f"{c}{row.get('Spend', 0):,.2f}",
            str(int(row.get("Clicks", 0))),
            f"{int(row.get('Impressions', 0)):,}",
        ])

    return AnalysisTable(title="Zero-Order Keywords (Wasting Budget)", columns=columns, rows=rows)


def build_harvest_table(
    df,
    title: str,
    config: dict,
    limit: int = 20,
) -> AnalysisTable:
    """Build a harvest results table."""
    c = config.get("currency", "$")
    keyword_col = "Customer Search Term" if "Customer Search Term" in df.columns else (
        "Targeting" if "Targeting" in df.columns else df.columns[0]
    )

    columns = [
        ("#", "Rank", 4),
        ("Search Term", "Customer Search Term", 24),
        ("Campaign", "Campaign Name", 18),
        ("Clicks", "Clicks", 7),
        ("Orders", "Orders", 7),
        ("Revenue", "Sales", 10),
        ("ACoS", "ACoS", 8),
    ]

    rows = []
    for i, (_, row) in enumerate(df.head(limit).iterrows()):
        rows.append([
            str(i + 1),
            str(row.get(keyword_col, ""))[:24],
            str(row.get("Campaign Name", ""))[:18],
            str(int(row.get("Clicks", 0))),
            str(int(row.get("Orders", 0))),
            f"{c}{row.get('Sales', 0):,.2f}",
            f"{row.get('ACoS', 0):.1f}%",
        ])

    return AnalysisTable(title=title, columns=columns, rows=rows)
