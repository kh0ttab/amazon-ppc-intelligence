"""Amazon PPC Intelligence — FastAPI Backend."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

import database
from ingestion.doc_parser import ingest_file
from analysis.ppc_analyzer import (
    analyze_keywords, get_kpis, get_top_keywords, get_status_counts, get_date_ranges,
)
from analysis.sales_analyzer import get_sales_breakdown
from analysis.budget_analyzer import find_waste
from analysis.harvester import find_harvest_candidates, generate_bulk_csv
from analysis.cannibalization import detect_cannibalization
from analysis.sales_tracker import (
    get_daily_sales, get_weekly_sales, get_sales_velocity,
    get_top_asins_by_sales, sync_from_business_data,
)
from analysis.mer_tracker import (
    get_mer_summary, get_mer_trend, get_channel_breakdown,
    detect_anomalies, sync_facebook_data, sync_shopify_data,
)
from competitor.scraper import search_amazon, extract_keywords, compare_keywords
from competitor.bid_estimator import estimate_bids
from reporting.report_generator import generate_report

# Claude AI client (primary)
from ai.claude_client import (
    check_claude, stream_chat, build_data_context,
    QUICK_PROMPTS, analyze_competitor_keywords_with_claude,
)

# Ollama client (fallback)
try:
    from ai.ollama_client import check_ollama, stream_chat as ollama_stream_chat
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    def check_ollama(ep): return {"online": False, "models": []}

CONFIG_PATH = Path(__file__).parent / "config.json"
CONFIG_EXAMPLE = Path(__file__).parent / "config.example.json"

# On first run (production), copy example config if none exists
if not CONFIG_PATH.exists() and CONFIG_EXAMPLE.exists():
    import shutil
    shutil.copy(CONFIG_EXAMPLE, CONFIG_PATH)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


app = FastAPI(title="Amazon PPC Intelligence", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start background scheduler
_scheduler = None

@app.on_event("startup")
def startup():
    global _scheduler
    import logging
    log = logging.getLogger("main")

    # Initialise database in a background thread so uvicorn starts accepting
    # requests immediately (Docker health check can pass while DB connects).
    import threading
    def _init_db():
        try:
            database.init_db()
            log.info("Database initialised")
        except Exception as e:
            log.error(f"Database init failed — update DATABASE_URL to Supabase pooler URL: {e}")
    threading.Thread(target=_init_db, daemon=True).start()

    try:
        from scheduler import start_scheduler
        _scheduler = start_scheduler()
    except Exception as e:
        log.warning(f"Scheduler not started: {e}")

    # Backfill sales_snapshots from existing business_data on first run
    try:
        sync_from_business_data()
    except Exception:
        pass


@app.on_event("shutdown")
def shutdown():
    if _scheduler:
        _scheduler.shutdown()


# ── Health ───────────────────────────────────────────────────

@app.get("/api/health")
def health():
    """Lightweight liveness probe — always responds quickly for Docker healthcheck."""
    return {"status": "ok"}


@app.get("/api/status")
def status():
    """Full status check including DB and Claude connectivity (may be slow)."""
    cfg = load_config()
    api_key = cfg.get("claude_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    claude_status = check_claude(api_key)

    # DB stats — gracefully degrade if DB is unreachable
    kw_count = upload_count = snapshot_count = 0
    db_error = None
    try:
        db = database.get_db()
        kw_count = db.execute("SELECT COUNT(*) as c FROM keyword_data").fetchone()["c"]
        upload_count = db.execute("SELECT COUNT(*) as c FROM uploads").fetchone()["c"]
        snapshot_count = db.execute("SELECT COUNT(DISTINCT snapshot_date) as c FROM sales_snapshots").fetchone()["c"]
        db.close()
    except Exception as e:
        db_error = str(e)

    ollama = {"online": False, "models": []}
    if OLLAMA_AVAILABLE:
        ollama = check_ollama(cfg.get("ollama_endpoint", "http://localhost:11434"))

    ads_configured = bool(cfg.get("amazon_ads_api", {}).get("client_id"))
    sp_configured = bool(cfg.get("sp_api", {}).get("client_id"))

    return {
        "status": "ok" if not db_error else "degraded",
        "db_error": db_error,
        "claude_online": claude_status["online"],
        "claude_model": claude_status.get("model"),
        "claude_error": claude_status.get("error"),
        "ollama_online": ollama["online"],
        "ollama_models": ollama.get("models", []),
        "keywords_loaded": kw_count,
        "uploads": upload_count,
        "sales_days_tracked": snapshot_count,
        "amazon_ads_api_configured": ads_configured,
        "sp_api_configured": sp_configured,
    }


# ── Upload ───────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...)):
    try:
        original_name = file.filename or "upload.csv"
        suffix = Path(original_name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            result = ingest_file(tmp_path)
        finally:
            os.unlink(tmp_path)

        if "error" in result:
            return {"error": result["error"]}

        result["filename"] = original_name

        # Backfill sales snapshots after business report upload
        try:
            sync_from_business_data()
        except Exception:
            pass

        return result
    except Exception as e:
        return {"error": f"Upload failed: {str(e)}"}


@app.get("/api/uploads")
def list_uploads():
    return get_date_ranges()


# ── Dashboard ────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard(date_from: str = Query(None), date_to: str = Query(None)):
    cfg = load_config()
    target = cfg.get("target_acos", 25.0)

    kpis = get_kpis(target, date_from, date_to)
    status = get_status_counts(target)
    winners = get_top_keywords(target, "WINNER", 5)
    bleeders = get_top_keywords(target, "BLEEDING", 5)
    breakdown = get_sales_breakdown()
    velocity = get_sales_velocity()

    return {
        "kpis": kpis,
        "status_counts": status,
        "top_winners": winners,
        "top_bleeders": bleeders,
        "sales_breakdown": breakdown,
        "sales_velocity": velocity,
    }


# ── Keywords ─────────────────────────────────────────────────

@app.get("/api/keywords")
def keywords(
    status: str = Query(None),
    campaign: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    sort_by: str = Query("spend"),
    sort_dir: str = Query("desc"),
    limit: int = Query(200),
):
    cfg = load_config()
    target = cfg.get("target_acos", 25.0)
    filters = {}
    if status:
        filters["status"] = status
    if campaign:
        filters["campaign"] = campaign
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    data = analyze_keywords(target, filters)
    reverse = sort_dir == "desc"
    data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
    return {"keywords": data[:limit], "total": len(data)}


@app.get("/api/keywords/campaigns")
def list_campaigns():
    db = database.get_db()
    rows = db.execute("SELECT DISTINCT campaign FROM keyword_data WHERE campaign != ''").fetchall()
    db.close()
    return {"campaigns": [r["campaign"] for r in rows]}


# ── Waste ────────────────────────────────────────────────────

@app.get("/api/waste")
def waste():
    cfg = load_config()
    return find_waste(cfg.get("target_acos", 25.0), cfg.get("waste_acos_threshold", 150.0))


@app.get("/api/waste/export")
def waste_export():
    cfg = load_config()
    w = find_waste(cfg.get("target_acos", 25.0))
    import csv, io
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "Record Type", "Campaign Name", "Ad Group Name", "Keyword", "Match Type", "State",
    ])
    writer.writeheader()
    for item in w["zero_orders"][:100]:
        writer.writerow({
            "Record Type": "Keyword",
            "Campaign Name": item.get("campaign", ""),
            "Ad Group Name": item.get("ad_group", ""),
            "Keyword": item["search_term"],
            "Match Type": "Negative Exact",
            "State": "enabled",
        })
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=negative_keywords.csv"},
    )


# ── Harvest ──────────────────────────────────────────────────

@app.get("/api/harvest")
def harvest():
    cfg = load_config()
    return find_harvest_candidates(
        cfg.get("harvest_clicks_threshold", 8),
        cfg.get("harvest_orders_threshold", 1),
        cfg.get("negative_clicks_threshold", 5),
        cfg.get("negative_spend_threshold", 3.0),
        cfg.get("target_acos", 25.0),
    )


@app.get("/api/harvest/export")
def harvest_export():
    cfg = load_config()
    h = find_harvest_candidates(
        cfg.get("harvest_clicks_threshold", 8),
        cfg.get("harvest_orders_threshold", 1),
        cfg.get("negative_clicks_threshold", 5),
        cfg.get("negative_spend_threshold", 3.0),
        cfg.get("target_acos", 25.0),
    )
    csv_str = generate_bulk_csv(h)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=harvest_bulk_upload.csv"},
    )


# ── Cannibalization ──────────────────────────────────────────

@app.get("/api/cannibalization")
def cannibalization():
    return detect_cannibalization()


# ── Competitors ──────────────────────────────────────────────

@app.post("/api/competitors/analyze")
def analyze_competitor(keyword: str = Query(...)):
    cfg = load_config()
    marketplace = cfg.get("marketplace", "US")
    api_key = cfg.get("claude_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")

    results = search_amazon(keyword, marketplace)
    if results.get("error"):
        return results

    all_items = results["organic"] + results["sponsored"]
    comp_kws = extract_keywords(all_items)

    db = database.get_db()
    user_kws = [r["search_term"] for r in db.execute(
        "SELECT DISTINCT search_term FROM keyword_data WHERE search_term != ''"
    ).fetchall()]
    db.close()

    comparison = compare_keywords(comp_kws, user_kws) if user_kws else {
        "gap": comp_kws, "shared": [], "unique": []
    }

    sponsored_count = len(results["sponsored"])
    competition = "high" if sponsored_count >= 5 else "medium" if sponsored_count >= 2 else "low"
    bids = estimate_bids(
        comparison["gap"][:20], competition=competition,
        bid_multiplier=cfg.get("bid_multiplier", 1.2)
    )

    # Claude AI deep analysis
    ai_intel = None
    if api_key:
        ai_intel = analyze_competitor_keywords_with_claude(
            keyword=keyword,
            organic_results=results["organic"],
            sponsored_results=results["sponsored"],
            your_keywords=user_kws[:50],
            api_key=api_key,
        )
        # Store in DB
        if ai_intel and not ai_intel.get("error"):
            _store_competitor_intel(keyword, ai_intel)

    return {
        "organic": results["organic"],
        "sponsored": results["sponsored"],
        "competitor_keywords": comp_kws[:30],
        "comparison": comparison,
        "bid_suggestions": bids,
        "ai_intel": ai_intel,
    }


def _store_competitor_intel(keyword: str, intel: dict):
    """Persist Claude's competitor analysis to DB."""
    try:
        db = database.get_db()
        db.execute(
            """INSERT INTO competitor_keyword_intel
               (keyword, analyzed_at, competition_level, competition_score, market_insight,
                competitor_strategies, keyword_gaps, long_tail_opportunities,
                negative_suggestions, bid_recommendation, action_plan)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                keyword,
                datetime.utcnow().isoformat(),
                intel.get("competition_level"),
                intel.get("competition_score"),
                intel.get("market_insight"),
                json.dumps(intel.get("competitor_strategies", [])),
                json.dumps(intel.get("keyword_gaps", [])),
                json.dumps(intel.get("long_tail_opportunities", [])),
                json.dumps(intel.get("negative_keyword_suggestions", [])),
                json.dumps(intel.get("bid_recommendation", {})),
                json.dumps(intel.get("action_plan", [])),
            ),
        )
        db.commit()
        db.close()
    except Exception:
        pass


@app.get("/api/competitors/history")
def competitor_history(limit: int = Query(20)):
    """Return past competitor intelligence analyses."""
    db = database.get_db()
    rows = db.execute(
        "SELECT * FROM competitor_keyword_intel ORDER BY analyzed_at DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        row = dict(r)
        for field in ["competitor_strategies", "keyword_gaps", "long_tail_opportunities",
                      "negative_suggestions", "bid_recommendation", "action_plan"]:
            if row.get(field):
                try:
                    row[field] = json.loads(row[field])
                except Exception:
                    pass
        result.append(row)
    return {"history": result}


# ── Sales Tracker ─────────────────────────────────────────────

@app.get("/api/sales/velocity")
def sales_velocity():
    """Sales velocity KPIs: today vs yesterday, this week vs last week."""
    return get_sales_velocity()


@app.get("/api/sales/daily")
def sales_daily(days: int = Query(30)):
    """Daily units sold and revenue for the last N days."""
    return {"daily": get_daily_sales(days)}


@app.get("/api/sales/weekly")
def sales_weekly(weeks: int = Query(12)):
    """Weekly aggregated units sold for the last N weeks."""
    return {"weekly": get_weekly_sales(weeks)}


@app.get("/api/sales/top-asins")
def sales_top_asins(days: int = Query(30), limit: int = Query(10)):
    """Top ASINs by units sold in the last N days."""
    return {"asins": get_top_asins_by_sales(days, limit)}


@app.post("/api/sales/sync")
def sales_sync():
    """Manually trigger SP-API sales sync."""
    cfg = load_config()
    from analysis.sales_tracker import sync_from_sp_api
    result = sync_from_sp_api(cfg)
    return result


# ── Amazon Ads API — Manual Actions ──────────────────────────

@app.post("/api/ads/pause-keyword")
async def pause_keyword_via_api(body: dict):
    """Pause a keyword via Amazon Advertising API."""
    cfg = load_config()
    from integrations.amazon_ads_api import build_client_from_config
    client = build_client_from_config(cfg)
    if not client:
        return {"error": "Amazon Ads API not configured"}
    try:
        result = client.pause_keyword(body["keyword_id"])
        return {"status": "paused", "result": result}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/ads/update-bid")
async def update_bid_via_api(body: dict):
    """Update keyword bid via Amazon Advertising API."""
    cfg = load_config()
    from integrations.amazon_ads_api import build_client_from_config
    client = build_client_from_config(cfg)
    if not client:
        return {"error": "Amazon Ads API not configured"}
    try:
        result = client.update_keyword_bid(body["keyword_id"], float(body["new_bid"]))
        return {"status": "updated", "result": result}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/ads/sync")
def ads_sync():
    """Manually trigger Amazon Ads API data sync."""
    from scheduler import sync_ads_data
    try:
        sync_ads_data()
        return {"status": "ok", "message": "Ads data sync triggered"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/sync/log")
def sync_log(limit: int = Query(20)):
    """Return automation sync history."""
    from scheduler import get_sync_log
    return {"log": get_sync_log(limit)}


# ── Reports ──────────────────────────────────────────────────

@app.get("/api/reports/generate")
def reports(report_type: str = Query("weekly")):
    cfg = load_config()
    return generate_report(report_type, cfg.get("target_acos", 25.0))


# ── AI Chat ──────────────────────────────────────────────────

@app.get("/api/ai/prompts")
def ai_prompts():
    return {"prompts": QUICK_PROMPTS}


@app.post("/api/ai/chat")
async def ai_chat(body: dict):
    message = body.get("message", "")
    if not message:
        return {"error": "No message provided"}

    cfg = load_config()
    target = cfg.get("target_acos", 25.0)
    api_key = cfg.get("claude_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")

    try:
        kpis = get_kpis(target)
        winners = get_top_keywords(target, "WINNER", 5)
        bleeders = get_top_keywords(target, "BLEEDING", 5)
        velocity = get_sales_velocity()
        data_ctx = build_data_context(kpis, winners, bleeders)

        # Append sales velocity to context
        if velocity.get("today_units") is not None:
            data_ctx += (
                f"\n\nSales Today: {velocity.get('today_units', 0)} units | "
                f"This Week: {velocity.get('this_week_units', 0)} units | "
                f"WoW Change: {velocity.get('week_over_week_pct', 'N/A')}%"
            )
    except Exception:
        data_ctx = ""

    async def event_generator():
        async for token in stream_chat(message, data_ctx, api_key):
            yield {"data": json.dumps({"token": token})}
        yield {"data": json.dumps({"done": True})}

    return EventSourceResponse(event_generator())


# ── MER / Blended ROAS / TripleWhale-style ────────────────────

@app.get("/api/mer/summary")
def mer_summary(days: int = Query(30)):
    """MER, Blended ROAS, nCAC summary across Amazon + Facebook + Shopify."""
    return get_mer_summary(days)


@app.get("/api/mer/trend")
def mer_trend(days: int = Query(30)):
    """Daily MER trend for charts."""
    return {"trend": get_mer_trend(days)}


@app.get("/api/mer/channels")
def mer_channels(days: int = Query(30)):
    """Per-channel spend vs revenue breakdown."""
    return {"channels": get_channel_breakdown(days)}


@app.get("/api/mer/anomalies")
def mer_anomalies():
    """Sonar-style anomaly alerts."""
    return {"alerts": detect_anomalies()}


@app.post("/api/mer/sync-facebook")
def sync_fb():
    """Pull Facebook Ads spend data."""
    cfg = load_config()
    return sync_facebook_data(cfg)


@app.post("/api/mer/sync-shopify")
def sync_shopify():
    """Pull Shopify revenue data."""
    cfg = load_config()
    return sync_shopify_data(cfg)


@app.post("/api/mer/sync-all")
def sync_all():
    """Sync all channels at once."""
    cfg = load_config()
    fb = sync_facebook_data(cfg)
    sh = sync_shopify_data(cfg)
    return {"facebook": fb, "shopify": sh}


# ── Facebook Ads ──────────────────────────────────────────────

@app.get("/api/facebook/spend")
def fb_spend(days: int = Query(30)):
    """Daily Facebook ad spend."""
    db = database.get_db()
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = db.execute(
        "SELECT spend_date as date, SUM(spend) as spend, SUM(impressions) as impressions, "
        "SUM(clicks) as clicks, SUM(purchases) as purchases, SUM(purchase_value) as purchase_value "
        "FROM facebook_spend WHERE spend_date >= ? GROUP BY spend_date ORDER BY spend_date DESC",
        (cutoff,),
    ).fetchall()
    db.close()
    return {"spend": [dict(r) for r in rows]}


@app.get("/api/facebook/creatives")
def fb_creatives():
    """Facebook creative performance for Creative Cockpit."""
    db = database.get_db()
    rows = db.execute(
        "SELECT * FROM facebook_creatives ORDER BY spend DESC LIMIT 50"
    ).fetchall()
    db.close()
    return {"creatives": [dict(r) for r in rows]}


@app.post("/api/facebook/sync-creatives")
def fb_sync_creatives():
    """Pull creative-level performance from Facebook Ads API."""
    cfg = load_config()
    from integrations.facebook_ads import build_client_from_config
    client = build_client_from_config(cfg)
    if not client:
        return {"error": "Facebook Ads API not configured"}
    try:
        creatives = client.get_creative_performance(days_back=14)
        db = database.get_db()
        db.execute("DELETE FROM facebook_creatives")
        for c in creatives:
            db.execute(
                """INSERT INTO facebook_creatives
                   (ad_id, ad_name, campaign_name, adset_name, spend, impressions, clicks,
                    purchases, purchase_value, roas, cpa, ctr, cpc, reach,
                    thumbnail_url, title, body, image_url, synced_at, period_days)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),14)""",
                (
                    c["ad_id"], c["ad_name"], c["campaign_name"], c["adset_name"],
                    c["spend"], c["impressions"], c["clicks"], c["purchases"],
                    c["purchase_value"], c["roas"], c["cpa"], c["ctr"], c["cpc"],
                    c["reach"], c.get("thumbnail_url"), c.get("title"),
                    c.get("body"), c.get("image_url"),
                ),
            )
        db.commit()
        db.close()
        return {"status": "ok", "ads_synced": len(creatives)}
    except Exception as e:
        return {"error": str(e)}


# ── Shopify ───────────────────────────────────────────────────

@app.get("/api/shopify/revenue")
def shopify_revenue(days: int = Query(30)):
    """Daily Shopify revenue."""
    db = database.get_db()
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = db.execute(
        "SELECT * FROM shopify_daily WHERE date >= ? ORDER BY date DESC", (cutoff,)
    ).fetchall()
    db.close()
    return {"revenue": [dict(r) for r in rows]}


@app.get("/api/shopify/attribution")
def shopify_attribution():
    """UTM-based attribution: where Shopify orders come from."""
    cfg = load_config()
    from integrations.shopify_api import build_client_from_config
    client = build_client_from_config(cfg)
    if not client:
        return {"error": "Shopify API not configured", "attribution": []}
    try:
        data = client.get_utm_attribution(days_back=30)
        return {"attribution": data}
    except Exception as e:
        return {"error": str(e), "attribution": []}


# ── Config — extended with new credential sections ────────────

@app.get("/api/config")
def get_config():
    cfg = load_config()
    masked = {**cfg}
    secret_sections = ["amazon_ads_api", "sp_api", "facebook_ads", "shopify"]
    for section in secret_sections:
        if section in masked and isinstance(masked[section], dict):
            s = dict(masked[section])
            for key in ["client_secret", "refresh_token", "access_token", "app_secret"]:
                if s.get(key):
                    s[key] = s[key][:6] + "***"
            masked[section] = s
    if masked.get("claude_api_key"):
        masked["claude_api_key"] = masked["claude_api_key"][:8] + "***"
    return masked


@app.post("/api/config")
async def save_config(body: dict):
    existing = load_config()
    secret_sections = ["amazon_ads_api", "sp_api", "facebook_ads", "shopify"]
    for section in secret_sections:
        if section in body and section in existing:
            for key in ["client_secret", "refresh_token", "access_token", "app_secret"]:
                if body[section].get(key, "").endswith("***"):
                    body[section][key] = existing.get(section, {}).get(key, "")
    if body.get("claude_api_key", "").endswith("***"):
        body["claude_api_key"] = existing.get("claude_api_key", "")
    CONFIG_PATH.write_text(json.dumps(body, indent=2))
    return {"status": "saved"}


# ── Data Reset ───────────────────────────────────────────────

@app.post("/api/reset")
def reset_data():
    db = database.get_db()
    db.executescript(
        "DELETE FROM keyword_data; DELETE FROM business_data; DELETE FROM uploads;"
        "DELETE FROM sales_snapshots WHERE source IN ('csv_import', 'sp_api');"
        "DELETE FROM facebook_spend; DELETE FROM shopify_daily; DELETE FROM facebook_creatives;"
    )
    db.commit()
    db.close()
    return {"status": "cleared"}


# ── Serve React frontend (production) ────────────────────────
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(str(_static_dir / "index.html"))
