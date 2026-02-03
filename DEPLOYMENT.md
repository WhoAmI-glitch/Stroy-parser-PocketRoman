# СтройПарсер v2.0 - Deployment Guide

## Overview

This application scrapes Russian construction company data using:
- **AI Agent**: Claude 3.5 Haiku via Anthropic API
- **Web Scraping**: Bright Data MCP for 2gis.ru, yandex.ru/maps
- **Data Enrichment**: Rusprofile.ru for premium data (revenue, employees, court cases)
- **Database**: PostgreSQL for persistence
- **Frontend**: FastAPI + Jinja2 templates

## Architecture

```
User → FastAPI → AI Agent (Claude) → Bright Data MCP → Web (2GIS, Yandex, Rusprofile)
                     ↓
                  Database (PostgreSQL)
                     ↓
                  Results (JSON/HTML)
```

## Prerequisites

### 1. Anthropic API Key (REQUIRED)
- Sign up: https://console.anthropic.com/
- Create API key: https://console.anthropic.com/settings/keys
- Cost: ~$0.01 per search (Claude 3.5 Haiku)

### 2. Bright Data Account (REQUIRED)
- Sign up: https://brightdata.com/
- Create a Web Unlocker zone: https://brightdata.com/cp/zones
- Get your credentials:
  - `API_TOKEN`: Your API token
  - `BROWSER_AUTH`: Browser authentication string
  - `WEB_UNLOCKER_ZONE`: Zone name

### 3. Rusprofile Account (OPTIONAL but recommended)
- Sign up: https://www.rusprofile.ru/
- Free account works, premium gives better data
- Provides: revenue, employees, founders, court cases

### 4. Railway Account (for deployment)
- Sign up: https://railway.app/

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
# Database (Railway auto-provides this)
DATABASE_URL=postgresql://...

# REQUIRED: Anthropic API
ANTHROPIC_API_KEY=sk-ant-api03-...

# REQUIRED: Bright Data
API_TOKEN=your_brightdata_token
BROWSER_AUTH=brd-customer-...:...
WEB_UNLOCKER_ZONE=your_zone

# OPTIONAL: Rusprofile (for premium data)
RUSPROFILE_EMAIL=your_email@example.com
RUSPROFILE_PASSWORD=your_password

# Server (Railway auto-sets)
PORT=8000
```

## Deployment to Railway

### Step 1: Push Code to GitHub

```bash
cd "/Users/nikolai.gaichenia/Desktop/custom agent set up/NEW commit/stroyparser"

# Initialize git if needed
git init
git add -A
git commit -m "Deploy: СтройПарсер v2.0 with AI scraping"
git branch -M main
git remote add origin https://github.com/WhoAmI-glitch/Stroy-parser-PocketRoman.git
git push -u origin main --force
```

### Step 2: Connect Railway to GitHub

1. Go to https://railway.app/dashboard
2. Click on your project
3. Click on the "website" service
4. Go to Settings → Service → Source
5. Click "Connect to GitHub"
6. Select repository: `WhoAmI-glitch/Stroy-parser-PocketRoman`
7. Branch: `main`
8. Root directory: `/` (or leave empty)

### Step 3: Add Environment Variables

In Railway dashboard → Variables → Raw Editor:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
API_TOKEN=your_brightdata_token
BROWSER_AUTH=brd-customer-...
WEB_UNLOCKER_ZONE=your_zone
RUSPROFILE_EMAIL=your_email@example.com
RUSPROFILE_PASSWORD=your_password
```

**DATABASE_URL** is auto-injected by Railway from the Postgres-eKit service.

### Step 4: Deploy

Railway will auto-deploy when you push to GitHub.

Check deployment logs:
1. Click on the "website" service
2. Click "Deployments"
3. View logs for the latest deployment

### Step 5: Verify

Once deployed, visit:
- `https://your-app.up.railway.app/` - Dashboard
- `https://your-app.up.railway.app/health` - Health check
- `https://your-app.up.railway.app/api/stats` - Stats

## Local Development

### Install Dependencies

**IMPORTANT**: Use Python 3.12 (not 3.14 - too new, packages don't have wheels yet)

```bash
# Create virtual environment with Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Set up Database

Option 1: Use Railway's DB (recommended)

```bash
# Get connection string from Railway → Postgres-eKit → Connect
export DATABASE_URL="postgresql://postgres:password@host:port/railway"
```

Option 2: Local PostgreSQL with Docker

```bash
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=test \
  -p 5432:5432 \
  postgres:15

export DATABASE_URL="postgresql://postgres:test@localhost:5432/postgres"
```

### Run Locally

```bash
# Set environment variables
export ANTHROPIC_API_KEY=sk-ant-api03-...
export API_TOKEN=your_brightdata_token
export BROWSER_AUTH=your_browser_auth
export WEB_UNLOCKER_ZONE=your_zone
export RUSPROFILE_EMAIL=your_email
export RUSPROFILE_PASSWORD=your_password
export DATABASE_URL=postgresql://...

# Run server
python main.py
```

Visit http://localhost:8000

## How It Works

### 1. User Submits Search

User fills in search form:
- Query: "строительные компании Самара"
- City: "Самара"
- Ring: 1

### 2. AI Agent Searches Web

Claude + Bright Data MCP scrapes:
- **2GIS**: Phone numbers, addresses, websites
- **Yandex Maps**: Additional phones, locations
- **Rusprofile**: INN, OGRN, legal data

### 3. Data Validation

- Phone numbers validated (Russian format: +7XXXXXXXXXX)
- INN validated (10 or 12 digits with checksum)
- Emails validated (regex)
- Duplicates removed

### 4. Rusprofile Enrichment

For each found INN:
- Login to Rusprofile (cached session)
- Fetch company page
- Extract premium data:
  - Revenue (Выручка)
  - Profit (Прибыль)
  - Employees (Сотрудники)
  - Founders (Учредители)
  - Court cases (Судебные дела)
  - Government contracts (Госконтракты)

### 5. Database Persistence

- Company data saved to `companies` table
- Search logged in `searches` table
- Results linked in `search_results` table
- Upsert by INN (no duplicates)

### 6. Results Returned

- JSON response with full company data
- Dashboard updated with new companies
- Statistics refreshed

## API Endpoints

### `POST /api/search`
Search for companies using AI agent

**Request:**
```json
{
  "query": "строительные компании Самара",
  "city": "Самара",
  "ring": 1,
  "max_results": 10
}
```

**Response:**
```json
{
  "success": true,
  "search_id": 123,
  "data": {
    "companies": [...],
    "total": 10,
    "scraped_new": 5
  },
  "timestamp": "2024-...",
  "latency_ms": 45000
}
```

### `GET /api/companies`
Get companies with filters

**Query params:**
- `limit`: Max results (default: 100)
- `offset`: Pagination offset
- `city`: Filter by city
- `ring`: Filter by ring (1-4)
- `priority`: Filter by priority (A/B/C)
- `has_email`: Filter companies with email
- `has_phone`: Filter companies with phone

### `POST /api/companies/bulk`
Bulk import companies (for n8n)

**Request:**
```json
{
  "companies": [...],
  "search_id": 123
}
```

### `GET /api/export/csv`
Export companies to CSV

## Troubleshooting

### No companies found
- Check Bright Data credentials (API_TOKEN, BROWSER_AUTH)
- Verify Anthropic API key is valid
- Check Railway logs for errors

### Bad/missing phone numbers
- Phone numbers are extracted from 2GIS and Yandex Maps
- Validation requires Russian format (+7XXXXXXXXXX)
- Check scraper.py logs to see what was extracted

### Rusprofile login fails
- Verify email/password in environment variables
- Check if account is active
- Session is cached for 128 hours in /tmp/.rusprofile_session.pkl

### Database errors
- Verify DATABASE_URL is set
- Check Railway → Postgres-eKit is running
- Ensure connection string format: `postgresql://...`

### Python 3.14 compatibility issues
- Use Python 3.12 instead: `python3.12 -m venv .venv`
- Packages don't have wheels for 3.14 yet
- Railway uses Python 3.11 by default (works fine)

## Cost Estimates

Per search (10 companies):
- **Claude API**: ~$0.01 (Haiku model)
- **Bright Data**: ~$0.05 (depends on zone)
- **Total**: ~$0.06 per search

Monthly (1000 searches):
- ~$60/month

## Security Notes

1. **NEVER commit .env file** - use .env.example only
2. **Rotate API keys** if exposed in git history
3. **Use Railway's secret management** for production
4. **Enable Railway's private networking** if needed

## Support

Issues: https://github.com/WhoAmI-glitch/Stroy-parser-PocketRoman/issues
