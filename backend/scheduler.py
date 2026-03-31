"""Automated scheduler — daily/weekly data sync from Amazon APIs.

Uses APScheduler for background job management.
Jobs:
  - Daily 6AM: Pull yesterday's keyword report from Amazon Ads API
  - Daily 6AM: Pull daily sales metrics from SP-API
  - Weekly Monday 7AM: Pull weekly sales report + generate briefing

To start: called from main.py on FastAPI startup.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("scheduler")

CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _log_sync(sync_type: str, status: str, records: int = 0, error: str = None,
              started_at: str = None):
    """Write sync result to api_sync_log table."""
    try:
        import database
        db = database.get_db()
        db.execute(
            """INSERT INTO api_sync_log
               (sync_type, status, records_synced, error_message, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sync_type, status, records, error, started_at or datetime.utcnow().isoformat(),
             datetime.utcnow().isoformat()),
        )
        db.commit()
        db.close()
    except Exception as e:
        logger.warning(f"Failed to log sync: {e}")


def sync_ads_data():
    """Pull yesterday's PPC data from Amazon Advertising API."""
    started = datetime.utcnow().isoformat()
    cfg = _load_config()

    try:
        from integrations.amazon_ads_api import build_client_from_config
        client = build_client_from_config(cfg)
        if not client:
            logger.info("Amazon Ads API not configured — skipping sync")
            return

        from ingestion.doc_parser import ingest_ads_api_data

        # Fetch keyword report
        kw_data = client.fetch_keyword_report()
        if kw_data:
            count = ingest_ads_api_data(kw_data, "keyword_report")
            logger.info(f"Ads API sync: {count} keyword rows ingested")
            _log_sync("ads_keywords", "ok", count, started_at=started)

        # Fetch search term report
        st_data = client.fetch_search_term_report()
        if st_data:
            count = ingest_ads_api_data(st_data, "search_term_report")
            logger.info(f"Ads API sync: {count} search term rows ingested")
            _log_sync("ads_search_terms", "ok", count, started_at=started)

    except Exception as e:
        logger.error(f"Ads API sync failed: {e}")
        _log_sync("ads_keywords", "error", 0, str(e), started_at=started)


def sync_sales_data():
    """Pull daily sales data from SP-API."""
    started = datetime.utcnow().isoformat()
    cfg = _load_config()

    try:
        from analysis.sales_tracker import sync_from_sp_api
        result = sync_from_sp_api(cfg)

        if result.get("error"):
            if "not configured" in result["error"]:
                logger.info("SP-API not configured — skipping sales sync")
                return
            raise RuntimeError(result["error"])

        days = result.get("days_synced", 0)
        logger.info(f"SP-API sync: {days} days of sales data updated")
        _log_sync("sp_api_sales", "ok", days, started_at=started)

    except Exception as e:
        logger.error(f"SP-API sales sync failed: {e}")
        _log_sync("sp_api_sales", "error", 0, str(e), started_at=started)


def generate_weekly_briefing():
    """Generate AI-powered weekly briefing every Monday."""
    cfg = _load_config()
    try:
        from analysis.ppc_analyzer import get_kpis, get_top_keywords
        from ai.claude_client import analyze_sync

        target = cfg.get("target_acos", 25.0)
        kpis = get_kpis(target)
        winners = get_top_keywords(target, "WINNER", 5)
        bleeders = get_top_keywords(target, "BLEEDING", 5)

        prompt = f"""Generate a concise weekly PPC performance briefing for a senior Amazon seller.

ACCOUNT DATA:
Spend: ${kpis.get('total_spend', 0):.2f} | Sales: ${kpis.get('total_sales', 0):.2f}
ACoS: {kpis.get('acos', 0):.1f}% | ROAS: {kpis.get('roas', 0):.2f}x
Orders: {kpis.get('total_orders', 0)} | Clicks: {kpis.get('total_clicks', 0)}

Top Winners: {', '.join(w.get('search_term', '') for w in winners[:3])}
Top Bleeders: {', '.join(b.get('search_term', '') for b in bleeders[:3])}

Format: Executive summary (2 sentences), Top 3 wins this week, Top 3 issues to fix,
Top 3 actions for next week. Keep it under 300 words."""

        api_key = cfg.get("claude_api_key", "")
        briefing = analyze_sync(prompt, api_key=api_key)

        # Store to file
        reports_dir = Path(__file__).parent.parent / "reports"
        reports_dir.mkdir(exist_ok=True)
        fname = reports_dir / f"weekly_briefing_{datetime.now().strftime('%Y%m%d')}.txt"
        fname.write_text(briefing)
        logger.info(f"Weekly briefing generated: {fname}")
        _log_sync("weekly_briefing", "ok", 1)

    except Exception as e:
        logger.error(f"Weekly briefing failed: {e}")
        _log_sync("weekly_briefing", "error", 0, str(e))


def _sync_channels():
    """Daily Facebook Ads + Shopify sync."""
    started = datetime.utcnow().isoformat()
    cfg = _load_config()
    try:
        from analysis.mer_tracker import sync_facebook_data, sync_shopify_data
        fb = sync_facebook_data(cfg)
        sh = sync_shopify_data(cfg)
        fb_days = fb.get("days_synced", 0) if not fb.get("error") else 0
        sh_days = sh.get("days_synced", 0) if not sh.get("error") else 0
        logger.info(f"Channel sync: Facebook {fb_days} days, Shopify {sh_days} days")
        _log_sync("channels", "ok", fb_days + sh_days, started_at=started)
    except Exception as e:
        logger.error(f"Channel sync failed: {e}")
        _log_sync("channels", "error", 0, str(e), started_at=started)


def get_sync_log(limit: int = 20) -> list[dict]:
    """Return recent sync log entries."""
    try:
        import database
        db = database.get_db()
        rows = db.execute(
            "SELECT * FROM api_sync_log ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def start_scheduler():
    """Start APScheduler background scheduler."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("apscheduler not installed — automated sync disabled. Run: pip install apscheduler")
        return None

    scheduler = BackgroundScheduler()

    # Daily at 6:00 AM UTC — pull PPC data
    scheduler.add_job(
        sync_ads_data,
        CronTrigger(hour=6, minute=0),
        id="sync_ads_daily",
        name="Daily Amazon Ads API Sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Daily at 6:15 AM UTC — pull sales data
    scheduler.add_job(
        sync_sales_data,
        CronTrigger(hour=6, minute=15),
        id="sync_sales_daily",
        name="Daily SP-API Sales Sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Daily at 6:30 AM UTC — pull Facebook + Shopify data
    scheduler.add_job(
        _sync_channels,
        CronTrigger(hour=6, minute=30),
        id="sync_channels_daily",
        name="Daily Facebook + Shopify Sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Every Monday at 7:00 AM UTC — weekly briefing
    scheduler.add_job(
        generate_weekly_briefing,
        CronTrigger(day_of_week="mon", hour=7, minute=0),
        id="weekly_briefing",
        name="Weekly AI Briefing",
        replace_existing=True,
        misfire_grace_time=7200,
    )

    scheduler.start()
    logger.info("Scheduler started: daily sync at 6:00 AM UTC, weekly briefing on Mondays")
    return scheduler
