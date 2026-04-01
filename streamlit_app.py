"""
Amazon PPC Intelligence — Streamlit Frontend
============================================
Production-quality Streamlit app that wraps the backend analysis engine.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

# ── Path setup (must happen before any backend imports) ──────────────────────
_ROOT = Path(__file__).parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── Push st.secrets → os.environ BEFORE importing backend modules ─────────────
def _setup_env() -> None:
    """Copy Streamlit secrets into os.environ (setdefault so local env wins)."""
    try:
        secrets = st.secrets
        flat_keys = [
            "ANTHROPIC_API_KEY",
            "DATABASE_URL",
            "DB_PATH",
        ]
        for key in flat_keys:
            val = secrets.get(key, "")
            if val:
                os.environ.setdefault(key, val)
    except Exception:
        pass


_setup_env()

# ── Page config (must be first Streamlit call after secrets) ─────────────────
st.set_page_config(
    page_title="Amazon PPC Intelligence",
    page_icon="📊",
    layout="wide",
)

# ── Config helpers ────────────────────────────────────────────────────────────
_CONFIG_PATH = _BACKEND / "config.json"


def get_config() -> dict:
    """Read backend/config.json, then overlay st.secrets values."""
    cfg: dict = {}
    try:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH, "r") as f:
                cfg = json.load(f)
    except Exception:
        pass

    # Overlay top-level secrets
    try:
        for k in ["target_acos", "marketplace", "currency", "claude_model"]:
            v = st.secrets.get(k, "")
            if v != "":
                cfg[k] = v
        ak = st.secrets.get("ANTHROPIC_API_KEY", "")
        if ak:
            cfg["claude_api_key"] = ak
        # Nested sections
        for section in ["amazon_ads_api", "sp_api", "facebook_ads", "shopify"]:
            try:
                sec = st.secrets[section]
                if section not in cfg:
                    cfg[section] = {}
                for k, v in sec.items():
                    if v:
                        cfg[section][k] = v
            except Exception:
                pass
    except Exception:
        pass

    return cfg


def _save_config(updates: dict) -> None:
    """Merge updates into backend/config.json."""
    cfg: dict = {}
    try:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH, "r") as f:
                cfg = json.load(f)
    except Exception:
        pass
    cfg.update(updates)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Database init (cached across sessions) ────────────────────────────────────
@st.cache_resource
def init_database():
    try:
        import database
        database.init_db()
        return True
    except Exception as e:
        return str(e)


_db_status = init_database()

# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 PPC Intelligence")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        [
            "Dashboard",
            "MER / Blended ROAS",
            "Sales Tracker",
            "Creative Cockpit",
            "Keywords",
            "Budget Waste",
            "Harvesting",
            "Competitors",
            "AI Chat",
            "Upload",
            "Settings",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    if isinstance(_db_status, str):
        st.error(f"DB Error: {_db_status}")
    else:
        st.success("Database ready")

# ── Shared cached fetchers ────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _cached_kpis(target_acos: float) -> dict:
    try:
        from analysis.ppc_analyzer import get_kpis
        return get_kpis(target_acos)
    except Exception as e:
        return {"_error": str(e)}


@st.cache_data(ttl=60)
def _cached_status_counts(target_acos: float) -> dict:
    try:
        from analysis.ppc_analyzer import get_status_counts
        return get_status_counts(target_acos)
    except Exception as e:
        return {}


@st.cache_data(ttl=60)
def _cached_top_keywords(target_acos: float, status: str, limit: int) -> list:
    try:
        from analysis.ppc_analyzer import get_top_keywords
        return get_top_keywords(target_acos, status, limit)
    except Exception as e:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
def page_dashboard() -> None:
    st.header("📊 Dashboard")
    cfg = get_config()
    target_acos = float(cfg.get("target_acos", 25.0))
    currency = cfg.get("currency", "$")

    # ── KPIs ──────────────────────────────────────────────────────────────────
    kpis = _cached_kpis(target_acos)
    if "_error" in kpis:
        st.error(f"Could not load KPIs: {kpis['_error']}")
        kpis = {}

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    spend = kpis.get("total_spend", 0)
    sales = kpis.get("total_sales", 0)
    acos = kpis.get("acos", 0)
    roas = kpis.get("roas", 0)
    tacos = kpis.get("tacos", 0)
    orders = kpis.get("total_orders", 0)

    c1.metric("Total Spend", f"{currency}{spend:,.2f}")
    c2.metric("Total Sales", f"{currency}{sales:,.2f}")
    acos_delta = round(acos - target_acos, 1)
    c3.metric(
        "ACoS",
        f"{acos:.1f}%",
        delta=f"{acos_delta:+.1f}% vs target",
        delta_color="inverse",
    )
    c4.metric("ROAS", f"{roas:.2f}x")
    c5.metric("TACoS", f"{tacos:.1f}%")
    c6.metric("Orders", f"{orders:,}")

    st.markdown("---")

    # ── Status counts ─────────────────────────────────────────────────────────
    counts = _cached_status_counts(target_acos)
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("🟢 Winners", counts.get("WINNER", 0))
    sc2.metric("🔴 Bleeders", counts.get("BLEEDING", 0))
    sc3.metric("😴 Sleeping", counts.get("SLEEPING", 0))
    sc4.metric("🟡 Potential", counts.get("POTENTIAL", 0))
    sc5.metric("🆕 New", counts.get("NEW", 0))

    st.markdown("---")

    # ── Top Winners & Bleeders ────────────────────────────────────────────────
    import pandas as pd

    col_w, col_b = st.columns(2)

    with col_w:
        st.subheader("🟢 Top Winners")
        winners = _cached_top_keywords(target_acos, "WINNER", 10)
        if winners:
            df_w = pd.DataFrame(winners)[
                ["search_term", "sales", "spend", "acos", "roas", "orders"]
            ]
            df_w.columns = ["Search Term", "Sales", "Spend", "ACoS%", "ROAS", "Orders"]
            df_w["Sales"] = df_w["Sales"].apply(lambda x: f"{currency}{x:,.2f}")
            df_w["Spend"] = df_w["Spend"].apply(lambda x: f"{currency}{x:,.2f}")
            df_w["ACoS%"] = df_w["ACoS%"].apply(lambda x: f"{x:.1f}%")
            df_w["ROAS"] = df_w["ROAS"].apply(lambda x: f"{x:.2f}x")
            st.dataframe(df_w, use_container_width=True, hide_index=True)
        else:
            st.info("No winner data yet — upload a Search Term Report.")

    with col_b:
        st.subheader("🔴 Top Bleeders")
        bleeders = _cached_top_keywords(target_acos, "BLEEDING", 10)
        if bleeders:
            df_b = pd.DataFrame(bleeders)[
                ["search_term", "spend", "acos", "orders", "clicks"]
            ]
            df_b.columns = ["Search Term", "Spend", "ACoS%", "Orders", "Clicks"]
            df_b["Spend"] = df_b["Spend"].apply(lambda x: f"{currency}{x:,.2f}")
            df_b["ACoS%"] = df_b["ACoS%"].apply(lambda x: f"{x:.1f}%")
            st.dataframe(df_b, use_container_width=True, hide_index=True)
        else:
            st.info("No bleeder data yet — upload a Search Term Report.")

    st.markdown("---")

    # ── Sales velocity ────────────────────────────────────────────────────────
    st.subheader("📈 Sales Velocity")
    try:
        from analysis.sales_tracker import get_sales_velocity
        vel = get_sales_velocity()
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Today Units", vel.get("today_units", 0))
        v2.metric("This Week Units", vel.get("this_week_units", 0))
        v3.metric("Week Revenue", f"{currency}{vel.get('week_revenue', 0):,.2f}")
        v4.metric("Avg Daily Units (30d)", vel.get("avg_daily_units_30d", 0))
    except ImportError as e:
        st.error(f"Sales tracker module not available: {e}")
    except Exception as e:
        st.error(f"Could not load sales velocity: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: MER / BLENDED ROAS
# ─────────────────────────────────────────────────────────────────────────────
def page_mer() -> None:
    st.header("📡 MER / Blended ROAS")

    try:
        from analysis.mer_tracker import (
            get_mer_summary,
            get_mer_trend,
            get_channel_breakdown,
            detect_anomalies,
            sync_facebook_data,
            sync_shopify_data,
        )
    except ImportError as e:
        st.error(f"MER tracker module not available: {e}")
        return

    import pandas as pd
    import plotly.graph_objects as go

    cfg = get_config()
    currency = cfg.get("currency", "$")

    days = st.selectbox("Period", [7, 14, 30, 60, 90], index=2, format_func=lambda d: f"Last {d} days")

    # ── Anomaly alerts ─────────────────────────────────────────────────────────
    try:
        alerts = detect_anomalies(days)
        for alert in alerts:
            msg = f"**{alert['type']}**: {alert['message']}"
            if alert.get("severity") == "high":
                st.error(msg)
            else:
                st.warning(msg)
    except Exception as e:
        st.warning(f"Could not check anomalies: {e}")

    # ── Summary metrics ────────────────────────────────────────────────────────
    try:
        summary = get_mer_summary(days)
    except Exception as e:
        st.error(f"Could not load MER summary: {e}")
        return

    st.subheader("Key Metrics")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("MER", f"{summary.get('mer', 0):.2f}x")
    m2.metric("Blended ROAS", f"{summary.get('blended_roas', 0):.2f}x")
    m3.metric("Amazon ROAS", f"{summary.get('amazon_roas', 0):.2f}x")
    m4.metric("Facebook ROAS", f"{summary.get('fb_roas', 0):.2f}x")
    m5.metric("nCAC", f"{currency}{summary.get('ncac', 0):.2f}")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Total Spend", f"{currency}{summary.get('total_spend', 0):,.2f}")
    s2.metric("Total Revenue", f"{currency}{summary.get('total_revenue', 0):,.2f}")
    s3.metric("Amazon Spend", f"{currency}{summary.get('amazon_spend', 0):,.2f}")
    s4.metric("Facebook Spend", f"{currency}{summary.get('fb_spend', 0):,.2f}")

    st.markdown("---")

    # ── Trend chart ────────────────────────────────────────────────────────────
    try:
        trend = get_mer_trend(days)
        if trend:
            df_t = pd.DataFrame(trend)
            fig = go.Figure()
            fig.add_bar(
                x=df_t["date"],
                y=df_t.get("amazon_spend", [0] * len(df_t)),
                name="Amazon Spend",
                marker_color="#f59e0b",
            )
            fig.add_bar(
                x=df_t["date"],
                y=df_t.get("fb_spend", [0] * len(df_t)),
                name="Facebook Spend",
                marker_color="#3b82f6",
            )
            fig.add_scatter(
                x=df_t["date"],
                y=df_t.get("total_revenue", [0] * len(df_t)),
                name="Total Revenue",
                yaxis="y2",
                line=dict(color="#10b981", width=2),
                mode="lines+markers",
            )
            fig.update_layout(
                barmode="stack",
                yaxis=dict(title="Spend ($)"),
                yaxis2=dict(title="Revenue ($)", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.1),
                height=400,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No trend data yet. Sync Facebook or Shopify data first.")
    except Exception as e:
        st.error(f"Could not render trend chart: {e}")

    # ── Channel breakdown ──────────────────────────────────────────────────────
    try:
        breakdown = get_channel_breakdown(days)
        if breakdown:
            df_ch = pd.DataFrame(breakdown)
            df_ch.columns = [c.replace("_", " ").title() for c in df_ch.columns]
            st.subheader("Channel Breakdown")
            st.dataframe(df_ch, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not load channel breakdown: {e}")

    # ── Sync buttons ───────────────────────────────────────────────────────────
    st.markdown("---")
    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("Sync Facebook Data", use_container_width=True):
            with st.spinner("Syncing Facebook Ads data..."):
                try:
                    result = sync_facebook_data(cfg)
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success(f"Synced {result.get('days_synced', 0)} days of Facebook data.")
                        st.cache_data.clear()
                except Exception as e:
                    st.error(f"Sync failed: {e}")
    with bc2:
        if st.button("Sync Shopify Data", use_container_width=True):
            with st.spinner("Syncing Shopify data..."):
                try:
                    result = sync_shopify_data(cfg)
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success(f"Synced {result.get('days_synced', 0)} days of Shopify data.")
                        st.cache_data.clear()
                except Exception as e:
                    st.error(f"Sync failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: SALES TRACKER
# ─────────────────────────────────────────────────────────────────────────────
def page_sales() -> None:
    st.header("📈 Sales Tracker")

    try:
        from analysis.sales_tracker import (
            get_daily_sales,
            get_weekly_sales,
            get_top_asins_by_sales,
            sync_from_sp_api,
        )
    except ImportError as e:
        st.error(f"Sales tracker module not available: {e}")
        return

    import pandas as pd
    import plotly.graph_objects as go

    cfg = get_config()
    currency = cfg.get("currency", "$")

    tab_daily, tab_weekly, tab_asins = st.tabs(["Daily", "Weekly", "Top ASINs"])

    with tab_daily:
        days_d = st.slider("Days back", 7, 90, 30, key="sales_daily_slider")
        try:
            daily = get_daily_sales(days_d)
            if daily:
                df_d = pd.DataFrame(daily).sort_values("snapshot_date")
                fig = go.Figure()
                fig.add_bar(
                    x=df_d["snapshot_date"],
                    y=df_d.get("units", df_d.get("units_ordered", 0)),
                    name="Units",
                    marker_color="#3b82f6",
                )
                fig.add_scatter(
                    x=df_d["snapshot_date"],
                    y=df_d.get("revenue", df_d.get("ordered_product_sales", 0)),
                    name="Revenue",
                    yaxis="y2",
                    line=dict(color="#10b981", width=2),
                    mode="lines+markers",
                )
                fig.update_layout(
                    yaxis=dict(title="Units"),
                    yaxis2=dict(title=f"Revenue ({currency})", overlaying="y", side="right"),
                    legend=dict(orientation="h", y=1.1),
                    height=380,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(df_d, use_container_width=True, hide_index=True)
            else:
                st.info("No daily sales data yet. Upload a Business Report or sync via SP-API.")
        except Exception as e:
            st.error(f"Could not load daily sales: {e}")

    with tab_weekly:
        weeks_w = st.slider("Weeks back", 4, 26, 12, key="sales_weekly_slider")
        try:
            weekly = get_weekly_sales(weeks_w)
            if weekly:
                df_w = pd.DataFrame(weekly).sort_values("week_label")
                fig2 = go.Figure()
                fig2.add_bar(
                    x=df_w["week_label"],
                    y=df_w.get("units", df_w.get("units_ordered", 0)),
                    name="Units",
                    marker_color="#f59e0b",
                )
                fig2.update_layout(
                    yaxis=dict(title="Units"),
                    height=360,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig2, use_container_width=True)
                st.dataframe(df_w, use_container_width=True, hide_index=True)
            else:
                st.info("No weekly data yet.")
        except Exception as e:
            st.error(f"Could not load weekly sales: {e}")

    with tab_asins:
        days_a = st.slider("Days back", 7, 90, 30, key="sales_asins_slider")
        try:
            asins = get_top_asins_by_sales(days_a)
            if asins:
                st.dataframe(pd.DataFrame(asins), use_container_width=True, hide_index=True)
            else:
                st.info("No per-ASIN data yet.")
        except Exception as e:
            st.error(f"Could not load ASIN data: {e}")

    st.markdown("---")
    if st.button("Sync Sales via SP-API", use_container_width=False):
        with st.spinner("Syncing from SP-API..."):
            try:
                result = sync_from_sp_api(cfg)
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.success(f"Synced {result.get('days_synced', 0)} days from {result.get('source','SP-API')}.")
                    st.cache_data.clear()
            except Exception as e:
                st.error(f"Sync failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: CREATIVE COCKPIT
# ─────────────────────────────────────────────────────────────────────────────
def page_creatives() -> None:
    st.header("🎨 Creative Cockpit")

    import pandas as pd

    cfg = get_config()
    currency = cfg.get("currency", "$")

    # ── Load creatives from DB ────────────────────────────────────────────────
    creatives: list[dict] = []
    try:
        import database
        db = database.get_db()
        rows = db.execute(
            "SELECT * FROM facebook_creatives ORDER BY spend DESC LIMIT 100"
        ).fetchall()
        db.close()
        creatives = [dict(r) for r in rows]
    except Exception as e:
        st.error(f"Could not load creatives: {e}")

    # ── KPIs ──────────────────────────────────────────────────────────────────
    if creatives:
        total_spend = sum(c.get("spend", 0) for c in creatives)
        total_purchases = sum(c.get("purchases", 0) for c in creatives)
        total_value = sum(c.get("purchase_value", 0) for c in creatives)
        blended_roas = round(total_value / total_spend, 2) if total_spend > 0 else 0

        k1, k2, k3 = st.columns(3)
        k1.metric("Total Spend", f"{currency}{total_spend:,.2f}")
        k2.metric("Total Purchases", f"{total_purchases:,}")
        k3.metric("Blended ROAS", f"{blended_roas:.2f}x")
        st.markdown("---")

    # ── Creative cards ─────────────────────────────────────────────────────────
    if creatives:
        st.subheader("Creative Performance")
        for creative in creatives[:20]:
            ad_name = creative.get("ad_name") or creative.get("ad_id", "Unknown Ad")
            with st.expander(f"📢 {ad_name}", expanded=False):
                col_img, col_metrics = st.columns([1, 2])
                with col_img:
                    thumb = creative.get("thumbnail_url") or creative.get("image_url")
                    if thumb:
                        try:
                            st.image(thumb, use_container_width=True)
                        except Exception:
                            st.caption("(image unavailable)")
                    else:
                        st.caption("No thumbnail")
                with col_metrics:
                    spend = creative.get("spend", 0)
                    roas = creative.get("roas", 0)
                    cpa = creative.get("cpa", 0)
                    ctr = creative.get("ctr", 0)
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Spend", f"{currency}{spend:,.2f}")
                    m2.metric("ROAS", f"{roas:.2f}x")
                    m3.metric("CPA", f"{currency}{cpa:.2f}")
                    m4.metric("CTR", f"{ctr:.2f}%")
                    if creative.get("title"):
                        st.caption(f"**Headline:** {creative['title']}")
                    if creative.get("body"):
                        st.caption(f"**Body:** {creative['body'][:200]}")
    else:
        st.info("No creative data yet. Sync Facebook Creatives to get started.")

    # ── Sync button ───────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("Sync Facebook Creatives", use_container_width=False):
        with st.spinner("Fetching creative performance data..."):
            try:
                from integrations.facebook_ads import build_client_from_config
                import database

                fb_client = build_client_from_config(cfg)
                if not fb_client:
                    st.error("Facebook Ads API not configured. Add credentials in Settings.")
                else:
                    perf_list = fb_client.get_creative_performance(days_back=14)
                    db = database.get_db()
                    for p in perf_list:
                        db.execute(
                            """INSERT INTO facebook_creatives
                               (ad_id, ad_name, campaign_name, adset_name, spend, impressions,
                                clicks, purchases, purchase_value, roas, cpa, ctr, cpc, reach,
                                thumbnail_url, title, body, image_url, synced_at, period_days)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),14)
                               ON CONFLICT DO NOTHING""",
                            (
                                p.get("ad_id", ""), p.get("ad_name", ""),
                                p.get("campaign_name", ""), p.get("adset_name", ""),
                                p.get("spend", 0), p.get("impressions", 0),
                                p.get("clicks", 0), p.get("purchases", 0),
                                p.get("purchase_value", 0), p.get("roas", 0),
                                p.get("cpa", 0), p.get("ctr", 0), p.get("cpc", 0),
                                p.get("reach", 0), p.get("thumbnail_url", ""),
                                p.get("title", ""), p.get("body", ""), p.get("image_url", ""),
                            ),
                        )
                    db.commit()
                    db.close()
                    st.success(f"Synced {len(perf_list)} creatives.")
                    st.rerun()
            except ImportError as e:
                st.error(f"Facebook Ads module not available: {e}")
            except Exception as e:
                st.error(f"Sync failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: KEYWORDS
# ─────────────────────────────────────────────────────────────────────────────
def page_keywords() -> None:
    st.header("🔑 Keyword Analysis")

    try:
        from analysis.ppc_analyzer import analyze_keywords
    except ImportError as e:
        st.error(f"PPC analyzer not available: {e}")
        return

    import pandas as pd

    cfg = get_config()
    target_acos = float(cfg.get("target_acos", 25.0))

    STATUS_EMOJI = {
        "WINNER": "🟢 WINNER",
        "BLEEDING": "🔴 BLEEDING",
        "SLEEPING": "😴 SLEEPING",
        "POTENTIAL": "🟡 POTENTIAL",
        "NEW": "🆕 NEW",
    }

    # ── Filters ────────────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns(3)
    with f1:
        status_options = ["All"] + list(STATUS_EMOJI.keys())
        status_filter = st.selectbox("Status", status_options)
    with f2:
        campaigns: list[str] = ["All"]
        try:
            import database
            db = database.get_db()
            camp_rows = db.execute(
                "SELECT DISTINCT campaign FROM keyword_data WHERE campaign != '' ORDER BY campaign"
            ).fetchall()
            db.close()
            campaigns += [r["campaign"] for r in camp_rows]
        except Exception:
            pass
        campaign_filter = st.selectbox("Campaign", campaigns)
    with f3:
        sort_by = st.selectbox("Sort by", ["spend", "sales", "acos", "roas", "orders", "clicks"])

    # ── Fetch & display ────────────────────────────────────────────────────────
    try:
        filters: dict = {}
        if status_filter != "All":
            filters["status"] = status_filter
        if campaign_filter != "All":
            filters["campaign"] = campaign_filter

        keywords = analyze_keywords(target_acos=target_acos, filters=filters)
        keywords.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

        st.metric("Keywords found", len(keywords))

        if keywords:
            df = pd.DataFrame(keywords)
            df["status"] = df["status"].map(lambda s: STATUS_EMOJI.get(s, s))
            display_cols = [
                "status", "search_term", "campaign", "match_type",
                "impressions", "clicks", "spend", "sales", "acos", "roas", "orders",
            ]
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available], use_container_width=True, hide_index=True)
        else:
            st.info("No keywords found. Upload a Search Term Report to get started.")
    except Exception as e:
        st.error(f"Could not load keyword data: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: BUDGET WASTE
# ─────────────────────────────────────────────────────────────────────────────
def page_waste() -> None:
    st.header("🗑️ Budget Waste Finder")

    try:
        from analysis.budget_analyzer import find_waste
    except ImportError as e:
        st.error(f"Budget analyzer not available: {e}")
        return

    import pandas as pd

    cfg = get_config()
    target_acos = float(cfg.get("target_acos", 25.0))
    currency = cfg.get("currency", "$")

    waste_threshold = st.slider(
        "High ACoS threshold (%)", 50, 500, int(target_acos * 3), step=10
    )

    try:
        waste = find_waste(target_acos=target_acos, waste_threshold=waste_threshold)
    except Exception as e:
        st.error(f"Could not calculate waste: {e}")
        return

    # ── KPI metrics ────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Zero-Order Waste", f"{currency}{waste.get('zero_order_waste', 0):,.2f}")
    k2.metric("High ACoS Waste", f"{currency}{waste.get('high_acos_waste', 0):,.2f}")
    k3.metric("Total Waste", f"{currency}{waste.get('total_waste', 0):,.2f}")
    k4.metric("Waste %", f"{waste.get('waste_pct', 0):.1f}%")

    st.markdown("---")

    tab_zero, tab_high = st.tabs(["Zero Orders", "High ACoS"])

    with tab_zero:
        zero = waste.get("zero_orders", [])
        if zero:
            df_z = pd.DataFrame(zero)
            cols = [c for c in ["search_term", "campaign", "spend", "clicks", "impressions", "action", "reason"] if c in df_z.columns]
            st.dataframe(df_z[cols], use_container_width=True, hide_index=True)
        else:
            st.success("No zero-order waste detected!")

    with tab_high:
        high = waste.get("high_acos", [])
        if high:
            df_h = pd.DataFrame(high)
            cols = [c for c in ["search_term", "campaign", "spend", "acos", "orders", "excess_spend", "action"] if c in df_h.columns]
            st.dataframe(df_h[cols], use_container_width=True, hide_index=True)
        else:
            st.success("No high-ACoS waste detected!")

    # ── Download negative keyword CSV ─────────────────────────────────────────
    st.markdown("---")
    all_waste = waste.get("zero_orders", []) + waste.get("high_acos", [])
    if all_waste:
        neg_lines = ["Keyword,Match Type,Campaign Name,Ad Group Name"]
        for item in all_waste:
            if item.get("action") in ("PAUSE", "NEGATIVE"):
                neg_lines.append(
                    f'"{item.get("search_term","")}","Negative Exact",'
                    f'"{item.get("campaign","")}","{item.get("ad_group","")}"'
                )
        csv_content = "\n".join(neg_lines)
        st.download_button(
            label="Download Negative Keywords CSV (Amazon Bulk Upload)",
            data=csv_content,
            file_name="negative_keywords_bulk.csv",
            mime="text/csv",
        )


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: HARVESTING
# ─────────────────────────────────────────────────────────────────────────────
def page_harvesting() -> None:
    st.header("🌾 Keyword Harvesting")

    try:
        from analysis.harvester import find_harvest_candidates, generate_bulk_csv
    except ImportError as e:
        st.error(f"Harvester module not available: {e}")
        return

    import pandas as pd

    cfg = get_config()
    currency = cfg.get("currency", "$")
    target_acos = float(cfg.get("target_acos", 25.0))

    st.subheader("Thresholds")
    th1, th2, th3, th4 = st.columns(4)
    with th1:
        clicks_threshold = st.number_input("Min Clicks (promote)", min_value=1, value=int(cfg.get("harvest_clicks_threshold", 8)))
    with th2:
        orders_threshold = st.number_input("Min Orders (promote)", min_value=1, value=int(cfg.get("harvest_orders_threshold", 1)))
    with th3:
        neg_clicks = st.number_input("Min Clicks (negate)", min_value=1, value=int(cfg.get("negative_clicks_threshold", 5)))
    with th4:
        neg_spend = st.number_input("Min Spend (negate $)", min_value=0.0, value=float(cfg.get("negative_spend_threshold", 3.0)), step=0.5)

    try:
        harvest = find_harvest_candidates(
            clicks_threshold=clicks_threshold,
            orders_threshold=orders_threshold,
            neg_clicks=neg_clicks,
            neg_spend=neg_spend,
            target_acos=target_acos,
        )
    except Exception as e:
        st.error(f"Could not run harvester: {e}")
        return

    # ── Metrics ────────────────────────────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    m1.metric("Promote to Exact", harvest.get("promote_count", 0))
    m2.metric("Add as Negative", harvest.get("negate_count", 0))
    m3.metric("Potential Savings", f"{currency}{harvest.get('potential_savings', 0):,.2f}")

    st.markdown("---")

    tab_promote, tab_negate, tab_standalone = st.tabs(
        ["Promote to Exact", "Add as Negative", "Standalone Campaigns"]
    )

    with tab_promote:
        promote = harvest.get("promote", [])
        if promote:
            df_p = pd.DataFrame(promote)
            cols = [c for c in ["search_term", "campaign", "clicks", "orders", "spend", "sales", "acos", "suggested_bid"] if c in df_p.columns]
            st.dataframe(df_p[cols], use_container_width=True, hide_index=True)
        else:
            st.info("No candidates for promotion yet — need more clicks/orders data.")

    with tab_negate:
        negate = harvest.get("negate", [])
        if negate:
            df_n = pd.DataFrame(negate)
            cols = [c for c in ["search_term", "campaign", "clicks", "spend", "impressions"] if c in df_n.columns]
            st.dataframe(df_n[cols], use_container_width=True, hide_index=True)
        else:
            st.info("No negation candidates yet.")

    with tab_standalone:
        standalone = harvest.get("standalone", [])
        if standalone:
            df_s = pd.DataFrame(standalone)
            cols = [c for c in ["search_term", "campaign", "orders", "acos", "campaign_avg_acos", "improvement"] if c in df_s.columns]
            st.dataframe(df_s[cols], use_container_width=True, hide_index=True)
        else:
            st.info("No standalone candidates yet.")

    # ── Download bulk CSV ──────────────────────────────────────────────────────
    st.markdown("---")
    if harvest.get("promote") or harvest.get("negate"):
        try:
            bulk_csv = generate_bulk_csv(harvest)
            st.download_button(
                label="Download Bulk Upload CSV (Amazon Ads)",
                data=bulk_csv,
                file_name="harvest_bulk_upload.csv",
                mime="text/csv",
            )
        except Exception as e:
            st.error(f"Could not generate bulk CSV: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: COMPETITORS
# ─────────────────────────────────────────────────────────────────────────────
def page_competitors() -> None:
    st.header("🔭 Competitor Intelligence")

    try:
        from competitor.scraper import search_amazon, extract_keywords, compare_keywords
        from competitor.bid_estimator import estimate_bids
        from ai.claude_client import analyze_competitor_keywords_with_claude
    except ImportError as e:
        st.error(f"Competitor module not available: {e}")
        return

    import json as _json
    import pandas as pd

    cfg = get_config()
    api_key = cfg.get("claude_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    model = cfg.get("claude_model", "claude-sonnet-4-6")

    col_kw, col_mkt = st.columns([3, 1])
    with col_kw:
        keyword = st.text_input("Search keyword", placeholder="e.g. stainless steel water bottle")
    with col_mkt:
        marketplace = st.selectbox("Marketplace", ["US", "UK", "DE", "CA"])

    if st.button("Analyze Competitors", type="primary") and keyword.strip():
        with st.spinner(f"Scraping Amazon {marketplace} for '{keyword}'..."):
            try:
                results = search_amazon(keyword.strip(), marketplace)
            except Exception as e:
                st.error(f"Scrape failed: {e}")
                return

        if results.get("error"):
            st.warning(f"Scrape warning: {results['error']}")

        organic = results.get("organic", [])
        sponsored = results.get("sponsored", [])

        col_org, col_spon = st.columns(2)
        with col_org:
            st.subheader(f"Organic Results ({len(organic)})")
            if organic:
                st.dataframe(
                    pd.DataFrame(organic)[["position", "title", "asin", "price"]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No organic results parsed.")

        with col_spon:
            st.subheader(f"Sponsored Results ({len(sponsored)})")
            if sponsored:
                st.dataframe(
                    pd.DataFrame(sponsored)[["position", "title", "asin", "price"]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No sponsored results parsed.")

        # ── Keyword gap analysis ───────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Keyword Gap Analysis")
        comp_keywords = extract_keywords(organic + sponsored)

        your_keywords: list[str] = []
        try:
            from analysis.ppc_analyzer import analyze_keywords
            your_kw_data = analyze_keywords()
            your_keywords = [k["search_term"] for k in your_kw_data if k.get("search_term")]
        except Exception:
            pass

        gap_data = compare_keywords(comp_keywords, your_keywords)
        g1, g2, g3 = st.columns(3)
        g1.metric("Keyword Gaps (competitor only)", len(gap_data.get("gap", [])))
        g2.metric("Shared Keywords", len(gap_data.get("shared", [])))
        g3.metric("Your Unique Keywords", len(gap_data.get("unique", [])))

        # ── Claude AI analysis ────────────────────────────────────────────────
        if api_key:
            st.markdown("---")
            st.subheader("AI Competitive Intelligence")
            with st.spinner("Analyzing with Claude AI..."):
                try:
                    analysis = analyze_competitor_keywords_with_claude(
                        keyword=keyword.strip(),
                        organic_results=organic,
                        sponsored_results=sponsored,
                        your_keywords=your_keywords[:50],
                        api_key=api_key,
                        model=model,
                    )
                    if "error" in analysis:
                        st.error(analysis["error"])
                    else:
                        comp_level = analysis.get("competition_level", "unknown")
                        comp_score = analysis.get("competition_score", 0)
                        st.markdown(
                            f"**Competition Level:** {comp_level.upper()} "
                            f"(Score: {comp_score}/100)"
                        )
                        if analysis.get("market_insight"):
                            st.info(analysis["market_insight"])

                        gaps = analysis.get("keyword_gaps", [])
                        if gaps:
                            st.subheader("Keyword Gaps to Target")
                            st.dataframe(
                                pd.DataFrame(gaps),
                                use_container_width=True,
                                hide_index=True,
                            )

                        action_plan = analysis.get("action_plan", [])
                        if action_plan:
                            st.subheader("Action Plan")
                            for step in action_plan:
                                st.markdown(
                                    f"{step.get('priority', '•')}. **{step.get('action','')}** — "
                                    f"*{step.get('expected_impact','')}*"
                                )

                        # Store to DB
                        try:
                            import database, datetime as _dt
                            db = database.get_db()
                            db.execute(
                                """INSERT INTO competitor_keyword_intel
                                   (keyword, analyzed_at, competition_level, competition_score,
                                    market_insight, keyword_gaps, action_plan, raw_response)
                                   VALUES (?,?,?,?,?,?,?,?)""",
                                (
                                    keyword.strip(),
                                    _dt.datetime.utcnow().isoformat() + "Z",
                                    analysis.get("competition_level"),
                                    analysis.get("competition_score"),
                                    analysis.get("market_insight"),
                                    _json.dumps(analysis.get("keyword_gaps", [])),
                                    _json.dumps(analysis.get("action_plan", [])),
                                    _json.dumps(analysis),
                                ),
                            )
                            db.commit()
                            db.close()
                        except Exception:
                            pass
                except Exception as e:
                    st.error(f"Claude analysis failed: {e}")
        else:
            st.info("Add your Anthropic API key in Settings for Claude AI analysis.")

    # ── History table ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Analysis History")
    try:
        import database
        db = database.get_db()
        hist_rows = db.execute(
            "SELECT keyword, analyzed_at, competition_level, competition_score, market_insight "
            "FROM competitor_keyword_intel ORDER BY analyzed_at DESC LIMIT 20"
        ).fetchall()
        db.close()
        if hist_rows:
            st.dataframe(
                pd.DataFrame([dict(r) for r in hist_rows]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No analysis history yet.")
    except Exception as e:
        st.error(f"Could not load history: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: AI CHAT
# ─────────────────────────────────────────────────────────────────────────────
def page_ai_chat() -> None:
    st.header("🤖 AI PPC Strategist")

    cfg = get_config()
    api_key = cfg.get("claude_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    model = cfg.get("claude_model", "claude-sonnet-4-6")

    if not api_key:
        st.warning(
            "Anthropic API key not configured. Add `ANTHROPIC_API_KEY` in Settings or Streamlit secrets."
        )

    try:
        from ai.claude_client import QUICK_PROMPTS, SYSTEM_PROMPT, build_data_context
    except ImportError as e:
        st.error(f"Claude client not available: {e}")
        return

    # ── Session state init ────────────────────────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "chat_prefill" not in st.session_state:
        st.session_state["chat_prefill"] = ""

    # ── Quick prompt buttons ──────────────────────────────────────────────────
    st.subheader("Quick Prompts")
    qp_cols = st.columns(5)
    for i, qp in enumerate(QUICK_PROMPTS[:5]):
        with qp_cols[i]:
            if st.button(qp["label"], use_container_width=True, key=f"qp_{i}"):
                st.session_state["chat_prefill"] = qp["text"]

    st.markdown("---")

    # ── Chat history ──────────────────────────────────────────────────────────
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Input ─────────────────────────────────────────────────────────────────
    prefill = st.session_state.pop("chat_prefill", "") if "chat_prefill" in st.session_state else ""
    user_input = st.chat_input("Ask your PPC strategist...", key="chat_input")

    # Apply prefill if no direct input
    if prefill and not user_input:
        user_input = prefill

    if user_input:
        st.session_state["messages"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            if not api_key:
                resp = "Please configure your Anthropic API key in Settings to use AI Chat."
                st.markdown(resp)
                st.session_state["messages"].append({"role": "assistant", "content": resp})
            else:
                # Build account context
                data_ctx = ""
                try:
                    kpis = _cached_kpis(float(cfg.get("target_acos", 25.0)))
                    winners = _cached_top_keywords(float(cfg.get("target_acos", 25.0)), "WINNER", 5)
                    bleeders = _cached_top_keywords(float(cfg.get("target_acos", 25.0)), "BLEEDING", 5)
                    data_ctx = build_data_context(kpis, winners, bleeders)
                except Exception:
                    pass

                # Build messages list for streaming
                history_msgs = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state["messages"][:-1]  # exclude current
                ]
                user_content = f"{data_ctx}\n\n{user_input}" if data_ctx else user_input
                history_msgs.append({"role": "user", "content": user_content})

                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=api_key)

                    def _stream():
                        with client.messages.stream(
                            model=model,
                            max_tokens=2048,
                            system=SYSTEM_PROMPT,
                            messages=history_msgs,
                        ) as s:
                            for text in s.text_stream:
                                yield text

                    response = st.write_stream(_stream())
                    st.session_state["messages"].append(
                        {"role": "assistant", "content": response}
                    )
                except Exception as e:
                    err = f"Claude API error: {e}"
                    st.error(err)
                    st.session_state["messages"].append({"role": "assistant", "content": err})

    # ── Clear chat ────────────────────────────────────────────────────────────
    if st.button("Clear Chat"):
        st.session_state["messages"] = []
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: UPLOAD
# ─────────────────────────────────────────────────────────────────────────────
def page_upload() -> None:
    st.header("📤 Upload Reports")

    uploaded_file = st.file_uploader(
        "Upload an Amazon report",
        type=["csv", "tsv", "xlsx", "xls", "txt"],
        help="Supported: Search Term Report, Campaign Report, Business Report (CSV/TSV/XLSX)",
    )

    if uploaded_file is not None:
        with st.spinner("Processing file..."):
            try:
                suffix = Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name

                from ingestion.doc_parser import ingest_file

                result = ingest_file(tmp_path)

                if "error" in result:
                    st.error(f"Ingest failed: {result['error']}")
                else:
                    rtype = result.get("type", "unknown")
                    rows = result.get("rows", 0)
                    date_range = result.get("date_range")

                    type_labels = {
                        "search_term": "Search Term Report",
                        "campaign": "Campaign Report",
                        "business": "Business Report",
                        "placement": "Placement Report",
                    }
                    type_label = type_labels.get(rtype, rtype.replace("_", " ").title())
                    date_str = ""
                    if date_range:
                        date_str = f" ({date_range.get('start','')} to {date_range.get('end','')})"

                    st.success(
                        f"Uploaded **{type_label}**: {rows:,} rows{date_str}"
                    )
                    st.cache_data.clear()

                    # If business report, backfill sales snapshots
                    if rtype == "business":
                        try:
                            from analysis.sales_tracker import sync_from_business_data
                            sync_result = sync_from_business_data()
                            st.info(f"Backfilled {sync_result.get('rows_synced', 0)} sales snapshots.")
                        except Exception as e:
                            st.warning(f"Could not backfill sales data: {e}")

                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

            except ImportError as e:
                st.error(f"Ingestion module not available: {e}")
            except Exception as e:
                st.error(f"Upload failed: {e}")

    # ── Upload history ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Upload History")
    try:
        import database
        import pandas as pd

        db = database.get_db()
        hist = db.execute(
            "SELECT filename, report_type, rows_count, date_start, date_end, uploaded_at "
            "FROM uploads ORDER BY uploaded_at DESC LIMIT 30"
        ).fetchall()
        db.close()
        if hist:
            st.dataframe(
                pd.DataFrame([dict(r) for r in hist]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No uploads yet.")
    except Exception as e:
        st.error(f"Could not load upload history: {e}")

    # ── Danger Zone ────────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("Danger Zone", expanded=False):
        st.warning("This will permanently delete ALL uploaded data from the database.")
        confirm = st.checkbox("I understand this is irreversible")
        if st.button("Reset All Data", type="primary", disabled=not confirm):
            try:
                import database
                db = database.get_db()
                for table in [
                    "keyword_data", "business_data", "uploads",
                    "sales_snapshots", "competitor_prices", "chat_history",
                ]:
                    try:
                        db.execute(f"DELETE FROM {table}")
                    except Exception:
                        pass
                db.commit()
                db.close()
                st.cache_data.clear()
                st.success("All data has been reset.")
                st.rerun()
            except Exception as e:
                st.error(f"Reset failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE: SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
def page_settings() -> None:
    st.header("⚙️ Settings")

    cfg = get_config()

    with st.form("settings_form"):
        st.subheader("General")
        col1, col2, col3 = st.columns(3)
        with col1:
            target_acos = st.number_input(
                "Target ACoS (%)", min_value=1.0, max_value=200.0,
                value=float(cfg.get("target_acos", 25.0)), step=0.5
            )
        with col2:
            marketplace = st.selectbox(
                "Marketplace",
                ["US", "UK", "DE", "CA", "FR", "IT", "ES", "AU", "JP", "IN"],
                index=["US", "UK", "DE", "CA", "FR", "IT", "ES", "AU", "JP", "IN"].index(
                    cfg.get("marketplace", "US")
                ) if cfg.get("marketplace", "US") in ["US", "UK", "DE", "CA", "FR", "IT", "ES", "AU", "JP", "IN"] else 0,
            )
        with col3:
            currency = st.text_input("Currency symbol", value=cfg.get("currency", "$"))

        st.subheader("Claude AI")
        claude_col1, claude_col2 = st.columns(2)
        with claude_col1:
            claude_key = st.text_input(
                "Anthropic API Key",
                value="",
                type="password",
                placeholder="sk-ant-... (leave blank to keep existing)",
            )
        with claude_col2:
            claude_model = st.text_input(
                "Claude Model",
                value=cfg.get("claude_model", "claude-sonnet-4-6"),
            )

        st.subheader("Harvesting Defaults")
        hv1, hv2, hv3, hv4 = st.columns(4)
        with hv1:
            waste_threshold = st.number_input(
                "Waste ACoS threshold (%)", min_value=50, max_value=999,
                value=int(float(cfg.get("target_acos", 25.0)) * 3)
            )
        with hv2:
            harvest_clicks = st.number_input(
                "Harvest min clicks", min_value=1,
                value=int(cfg.get("harvest_clicks_threshold", 8))
            )
        with hv3:
            neg_clicks = st.number_input(
                "Negative min clicks", min_value=1,
                value=int(cfg.get("negative_clicks_threshold", 5))
            )
        with hv4:
            neg_spend = st.number_input(
                "Negative min spend ($)", min_value=0.0,
                value=float(cfg.get("negative_spend_threshold", 3.0)), step=0.5
            )

        st.subheader("Amazon Ads API")
        amz = cfg.get("amazon_ads_api", {})
        a1, a2 = st.columns(2)
        with a1:
            amz_client_id = st.text_input("Client ID", value=amz.get("client_id", ""))
            amz_refresh = st.text_input(
                "Refresh Token", value="", type="password",
                placeholder="(leave blank to keep existing)"
            )
        with a2:
            amz_client_secret = st.text_input(
                "Client Secret", value="", type="password",
                placeholder="(leave blank to keep existing)"
            )
            amz_profile_id = st.text_input("Profile ID", value=amz.get("profile_id", ""))

        st.subheader("Facebook Ads")
        fb = cfg.get("facebook_ads", {})
        f1, f2 = st.columns(2)
        with f1:
            fb_app_id = st.text_input("App ID", value=fb.get("app_id", ""))
            fb_app_secret = st.text_input(
                "App Secret", value="", type="password",
                placeholder="(leave blank to keep existing)"
            )
        with f2:
            fb_access_token = st.text_input(
                "Access Token", value="", type="password",
                placeholder="(leave blank to keep existing)"
            )
            fb_ad_account = st.text_input(
                "Ad Account ID", value=fb.get("ad_account_id", ""),
                placeholder="act_XXXXXXXXXX"
            )

        st.subheader("Shopify")
        sh = cfg.get("shopify", {})
        sh1, sh2 = st.columns(2)
        with sh1:
            sh_domain = st.text_input("Shop Domain", value=sh.get("shop_domain", ""),
                                      placeholder="mystore.myshopify.com")
        with sh2:
            sh_token = st.text_input(
                "Access Token", value="", type="password",
                placeholder="(leave blank to keep existing)", key="sh_token"
            )

        submitted = st.form_submit_button("Save Settings", type="primary")

    if submitted:
        updates: dict = {
            "target_acos": target_acos,
            "marketplace": marketplace,
            "currency": currency,
            "claude_model": claude_model,
            "harvest_clicks_threshold": harvest_clicks,
            "negative_clicks_threshold": neg_clicks,
            "negative_spend_threshold": neg_spend,
            "amazon_ads_api": {
                **amz,
                "client_id": amz_client_id,
                "profile_id": amz_profile_id,
            },
            "facebook_ads": {
                **fb,
                "app_id": fb_app_id,
                "ad_account_id": fb_ad_account,
            },
            "shopify": {
                **sh,
                "shop_domain": sh_domain,
            },
        }

        # Only update password fields if non-empty
        if claude_key.strip():
            updates["claude_api_key"] = claude_key.strip()
        if amz_client_secret.strip():
            updates["amazon_ads_api"]["client_secret"] = amz_client_secret.strip()
        if amz_refresh.strip():
            updates["amazon_ads_api"]["refresh_token"] = amz_refresh.strip()
        if fb_app_secret.strip():
            updates["facebook_ads"]["app_secret"] = fb_app_secret.strip()
        if fb_access_token.strip():
            updates["facebook_ads"]["access_token"] = fb_access_token.strip()
        if sh_token.strip():
            updates["shopify"]["access_token"] = sh_token.strip()

        try:
            _save_config(updates)
            st.success("Settings saved to backend/config.json")
        except Exception as e:
            st.error(f"Could not save settings: {e}")

        # ── Streamlit secrets template ─────────────────────────────────────────
        ak_display = claude_key.strip() or "<your-anthropic-key>"
        toml_template = f"""# Paste into Streamlit Cloud → App Settings → Secrets
ANTHROPIC_API_KEY = "{ak_display}"
# DATABASE_URL = "postgresql://..."  # Optional

target_acos = {target_acos}
marketplace = "{marketplace}"
claude_model = "{claude_model}"

[amazon_ads_api]
client_id = "{amz_client_id}"
client_secret = ""
refresh_token = ""
profile_id = "{amz_profile_id}"

[facebook_ads]
app_id = "{fb_app_id}"
app_secret = ""
access_token = ""
ad_account_id = "{fb_ad_account}"

[shopify]
shop_domain = "{sh_domain}"
access_token = ""
"""
        st.subheader("Streamlit Secrets Template")
        st.code(toml_template, language="toml")


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────────────────────
ROUTER = {
    "Dashboard": page_dashboard,
    "MER / Blended ROAS": page_mer,
    "Sales Tracker": page_sales,
    "Creative Cockpit": page_creatives,
    "Keywords": page_keywords,
    "Budget Waste": page_waste,
    "Harvesting": page_harvesting,
    "Competitors": page_competitors,
    "AI Chat": page_ai_chat,
    "Upload": page_upload,
    "Settings": page_settings,
}

ROUTER[page]()
