"""Claude API client — replaces Ollama for all AI features."""

from __future__ import annotations

import json
import os
from typing import AsyncGenerator, Optional

QUICK_PROMPTS = [
    {"label": "What should I pause?",         "text": "Which keywords should I pause immediately and why? Focus on highest waste first."},
    {"label": "Scale winners",                 "text": "Which keywords are top performers I should scale? Give bid increase % and budget recommendations."},
    {"label": "Find keyword gaps",             "text": "Based on my current keywords, what gaps exist that competitors likely target? What should I add?"},
    {"label": "Harvest opportunities",         "text": "Which search terms from auto campaigns should I promote to manual? What bids?"},
    {"label": "Budget reallocation",           "text": "How should I reallocate my budget across campaigns for maximum ROAS? Give specific $ amounts."},
    {"label": "Negative keyword audit",        "text": "Which negative keywords should I add to prevent wasted spend? List them with match types."},
    {"label": "Bid strategy review",           "text": "Review my overall bid strategy. Where am I overbidding or underbidding?"},
    {"label": "TACoS optimization",            "text": "Analyze my TACoS trends. What PPC changes will improve total profitability?"},
    {"label": "Campaign structure advice",     "text": "Is my campaign structure optimal? What restructuring would improve performance?"},
    {"label": "Prime Day prep",                "text": "How should I adjust bids and budgets to maximize Prime Day performance?"},
]


def _get_client():
    """Get Anthropic client. Raises if API key not set."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")
    return anthropic.Anthropic(api_key=api_key)


def check_claude(api_key: str = "") -> dict:
    """Check if Claude API is accessible."""
    try:
        import anthropic
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return {"online": False, "model": None, "error": "No API key configured"}
        client = anthropic.Anthropic(api_key=key)
        # Lightweight ping — list models is not available; use a minimal message
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return {"online": True, "model": "claude-sonnet-4-6", "error": None}
    except Exception as e:
        return {"online": False, "model": None, "error": str(e)}


def build_data_context(kpis: dict, winners: list, bleeders: list) -> str:
    """Build concise PPC data summary for Claude context."""
    ctx_parts = ["=== CURRENT PPC ACCOUNT DATA ==="]

    if kpis:
        ctx_parts.append(
            f"Total Spend: ${kpis.get('total_spend', 0):.2f} | "
            f"Total Sales: ${kpis.get('total_sales', 0):.2f} | "
            f"ACoS: {kpis.get('acos', 0):.1f}% | "
            f"ROAS: {kpis.get('roas', 0):.2f}x | "
            f"Orders: {kpis.get('total_orders', 0)} | "
            f"Clicks: {kpis.get('total_clicks', 0)} | "
            f"CTR: {kpis.get('ctr', 0):.2f}%"
        )

    if winners:
        ctx_parts.append("\nTop 5 Winners:")
        for w in winners:
            ctx_parts.append(
                f"  • {w.get('search_term', 'N/A')} — ACoS {w.get('acos', 0):.1f}% | "
                f"Sales ${w.get('sales', 0):.2f} | Spend ${w.get('spend', 0):.2f}"
            )

    if bleeders:
        ctx_parts.append("\nTop 5 Bleeders:")
        for b in bleeders:
            ctx_parts.append(
                f"  • {b.get('search_term', 'N/A')} — ACoS {b.get('acos', 0):.1f}% | "
                f"Spend ${b.get('spend', 0):.2f} | Orders {b.get('orders', 0)}"
            )

    return "\n".join(ctx_parts)


SYSTEM_PROMPT = """You are an elite Amazon PPC strategist managing million-dollar advertising accounts.
You have deep expertise in:
- Keyword research, match types, and bid optimization
- Campaign structure (single keyword campaigns, broad → exact funnels)
- Search term harvesting and negative keyword strategy
- TACoS vs ACoS optimization and true profitability analysis
- Competitive positioning on Amazon SERP
- Budget allocation for maximum ROAS
- Seasonal strategies (Prime Day, Q4, etc.)
- Sponsored Products, Sponsored Brands, Sponsored Display strategy

When given account data, provide specific, actionable recommendations with exact numbers where possible.
Be direct and strategic. Think like a $1M+ seller's PPC manager."""


async def stream_chat(
    message: str,
    data_context: str = "",
    api_key: str = "",
    model: str = "claude-sonnet-4-6",
) -> AsyncGenerator[str, None]:
    """Stream Claude response tokens."""
    try:
        import anthropic
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            yield "Error: ANTHROPIC_API_KEY not configured. Add it in Settings."
            return

        client = anthropic.Anthropic(api_key=key)

        user_content = message
        if data_context:
            user_content = f"{data_context}\n\n{message}"

        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    except Exception as e:
        yield f"\n[Error from Claude API: {str(e)}]"


def analyze_sync(prompt: str, api_key: str = "", model: str = "claude-sonnet-4-6") -> str:
    """Synchronous Claude call — for backend analysis tasks."""
    try:
        import anthropic
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return "Error: ANTHROPIC_API_KEY not configured."

        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        return f"Claude API error: {str(e)}"


def analyze_competitor_keywords_with_claude(
    keyword: str,
    organic_results: list,
    sponsored_results: list,
    your_keywords: list,
    api_key: str = "",
    model: str = "claude-sonnet-4-6",
) -> dict:
    """
    Deep competitor keyword analysis using Claude.
    Returns structured intelligence: strategy, gaps, recommendations.
    """
    import anthropic

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    # Build competitor data summary
    organic_titles = [r.get("title", "") for r in organic_results[:10]]
    sponsored_titles = [r.get("title", "") for r in sponsored_results[:10]]
    sponsored_asins = [r.get("asin", "") for r in sponsored_results if r.get("asin")]
    sponsored_count = len(sponsored_results)

    prompt = f"""Analyze this Amazon SERP data for keyword: "{keyword}"

SPONSORED RESULTS ({sponsored_count} ads):
{chr(10).join(f'  {i+1}. [{r.get("asin","")}] {r.get("title","")} — {r.get("price","")}' for i, r in enumerate(sponsored_results[:8]))}

ORGANIC RESULTS (top 10):
{chr(10).join(f'  {i+1}. [{r.get("asin","")}] {r.get("title","")} — {r.get("price","")}' for i, r in enumerate(organic_results[:10]))}

MY CURRENT KEYWORDS (sample): {', '.join(your_keywords[:30])}

Respond ONLY with valid JSON in this exact structure:
{{
  "competition_level": "high|medium|low",
  "competition_score": 0-100,
  "market_insight": "2-3 sentence overview of competitive landscape",
  "competitor_strategies": [
    {{"strategy": "name", "description": "what competitors are doing", "keywords_used": ["kw1", "kw2"]}}
  ],
  "keyword_gaps": [
    {{"keyword": "kw", "priority": "high|medium|low", "rationale": "why you need this", "suggested_bid": 0.00, "match_type": "exact|phrase|broad"}}
  ],
  "long_tail_opportunities": ["kw1", "kw2", "kw3"],
  "negative_keyword_suggestions": ["kw1", "kw2"],
  "bid_recommendation": {{
    "min_bid": 0.00,
    "max_bid": 0.00,
    "suggested_bid": 0.00,
    "rationale": "explanation"
  }},
  "action_plan": [
    {{"priority": 1, "action": "specific action", "expected_impact": "outcome"}}
  ]
}}"""

    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Extract JSON if wrapped in markdown
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse Claude response: {str(e)}", "raw": raw[:500]}
    except Exception as e:
        return {"error": str(e)}
