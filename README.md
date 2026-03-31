---
title: Amazon PPC Intelligence
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
app_port: 7860
---

# Amazon PPC Intelligence

Full-stack Amazon PPC + Multi-channel attribution platform (TripleWhale-style).

## Features
- Amazon PPC keyword analysis, waste detection, search term harvesting
- Facebook Ads spend tracking + Creative Cockpit
- Shopify revenue + UTM attribution
- MER (Marketing Efficiency Ratio) / Blended ROAS dashboard
- Claude AI-powered competitor keyword intelligence
- Daily/weekly sales velocity tracking

## Environment Variables

Set these in **Space Settings → Variables and secrets** (use the lock icon for secrets):

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude API key — console.anthropic.com |
| `DATABASE_URL` | Yes | Supabase PostgreSQL connection string |
