# Amazon API Setup Guide

## Which APIs You Need

### 1. Amazon Advertising API (PPC auto-sync)
**Purpose:** Auto-pull keyword reports, search term reports daily — no more manual CSV exports.
Also enables direct bid updates and keyword pausing from the app.

**Get credentials:**
1. Go to https://advertising.amazon.com → Apps & Services → Manage Apps
2. Click "Create New App" → name it (e.g. "PPC Intel")
3. Note your **Client ID** and **Client Secret**
4. Complete the OAuth flow to get your **Refresh Token**
   - Authorization URL: `https://www.amazon.com/ap/oa?client_id={CLIENT_ID}&scope=advertising::campaign_management&response_type=code&redirect_uri={REDIRECT_URI}`
   - Exchange the code: POST to `https://api.amazon.com/auth/o2/token`
5. Get your **Profile ID**: call `GET https://advertising.amazon.com/v2/profiles` after authenticating
   - Find the profile matching your marketplace (e.g. `countryCode: "US"`)

**Add to Settings → Amazon Advertising API in the app.**

---

### 2. Amazon Selling Partner API — SP-API (Sales tracking)
**Purpose:** Daily/weekly units sold, revenue tracking. Auto-syncs at 6AM UTC.

**Get credentials:**
1. Go to https://developer.amazonservices.com/
2. Click "Register as developer" → fill the form (choose "Private Developer" for your own store)
3. After approval, go to "Apps & Services" → "Develop Apps" → "Add new app version"
4. Choose **Self-Authorized** (you authorize it for your own store, no marketplace approval needed)
5. Note your **Client ID**, **Client Secret**
6. Generate your **Refresh Token**:
   - Go to Seller Central → Apps & Services → Manage Your Apps
   - Find your app → Authorize → copy the Refresh Token
7. Your **Seller ID**: Seller Central → Account Info → Merchant Token

**Add to Settings → SP-API in the app.**

---

## Without Amazon APIs (Manual Mode)

You can still use all features by uploading CSV reports manually:

| Feature | Report to Download |
|---|---|
| Keyword & Search Term data | Seller Central → Reports → Advertising Reports → Search Term Report |
| Campaign performance | Seller Central → Reports → Advertising Reports → Campaign Report |
| Sales / units sold | Seller Central → Reports → Business Reports → Detail Page Sales and Traffic |

Upload via the Dashboard → Upload button.

---

## Claude AI Setup

1. Get your API key at https://console.anthropic.com/
2. Add it in **Settings → Claude AI → API Key**
3. Enables:
   - Deep competitor keyword intelligence
   - Smart AI chat with full account context
   - Automated weekly briefings (Monday 7AM)

---

## Automated Schedule

Once configured, the app runs automatically:
- **Daily 6:00 AM UTC** — Pull yesterday's PPC data from Amazon Ads API
- **Daily 6:15 AM UTC** — Pull sales metrics from SP-API
- **Monday 7:00 AM UTC** — Generate AI weekly briefing (saved to `/reports/`)

Check sync history: **Settings → Sync Log** or API: `GET /api/sync/log`
