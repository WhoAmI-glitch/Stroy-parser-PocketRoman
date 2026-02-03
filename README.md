# СтройПарсер v2.0 - AI-Powered Company Scraper

Intelligent Russian construction company data scraper using Claude AI + Bright Data MCP + Rusprofile enrichment.

## Features

✅ **AI-Powered Search**: Claude 3.5 Haiku automatically searches 2GIS, Yandex Maps, Rusprofile
✅ **Phone Validation**: Extracts and validates Russian phone numbers (+7XXXXXXXXXX)
✅ **Premium Data**: Revenue, employees, founders, court cases from Rusprofile
✅ **Database Persistence**: PostgreSQL with INN-based deduplication
✅ **Web Dashboard**: Real-time search with loading states and statistics
✅ **Export**: CSV export with filters
✅ **REST API**: Full API for integrations (n8n, Zapier, etc.)

## Quick Start

### Prerequisites

1. **Python 3.12** (not 3.14 - too new)
2. **Anthropic API Key**: https://console.anthropic.com/settings/keys
3. **Bright Data Account**: https://brightdata.com/
4. **PostgreSQL** (or use Railway)

### Installation

```bash
# Clone repo
git clone https://github.com/WhoAmI-glitch/Stroy-parser-PocketRoman.git
cd Stroy-parser-PocketRoman

# Create virtual environment with Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials

# Run server (creates tables automatically)
python main.py
```

Visit http://localhost:8000

## Environment Setup

```bash
# Required
export ANTHROPIC_API_KEY=sk-ant-api03-...
export API_TOKEN=your_brightdata_token
export BROWSER_AUTH=brd-customer-...
export DATABASE_URL=postgresql://user:pass@host:port/db

# Optional (for premium data)
export RUSPROFILE_EMAIL=your_email@example.com
export RUSPROFILE_PASSWORD=your_password
```

## How It Works

### Search Flow

```
User Query → Claude AI → Bright Data MCP → Web Scraping (2GIS, Yandex, Rusprofile)
                ↓
          Phone Validation + INN Validation
                ↓
          Rusprofile Enrichment (revenue, employees, etc.)
                ↓
          PostgreSQL Database (upsert by INN)
                ↓
          JSON Response + Dashboard Update
```

### Example Search

**Input:**
```json
{
  "query": "строительные компании Самара",
  "city": "Самара",
  "ring": 1,
  "max_results": 10
}
```

**What Happens:**
1. Claude searches 2GIS for construction companies in Samara
2. Extracts: company name, address, phones, website
3. Searches Rusprofile for each company by INN
4. Validates and normalizes phone numbers
5. Enriches with premium data: revenue, employees, founders
6. Saves to database with deduplication by INN
7. Returns results with statistics

**Output:**
```json
{
  "success": true,
  "data": {
    "companies": [
      {
        "название_компании": "ООО СтройМастер",
        "инн": "6315123456",
        "телефон": "+78462345678",
        "email": "info@stroymaster.ru",
        "адрес": "г. Самара, ул. Ленинская, 123",
        "оборот": 150000000,
        "сайт": "https://stroymaster.ru"
      }
    ],
    "total": 10,
    "scraped_new": 5
  }
}
```

## API Documentation

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/health` | GET | Health check with DB status |
| `/api/stats` | GET | Dashboard statistics |
| `/api/companies` | GET | List companies with filters |
| `/api/companies` | POST | Create/update company |
| `/api/companies/bulk` | POST | Bulk create companies |
| `/api/search` | POST | **AI search with web scraping** |
| `/api/history` | GET | Search history |
| `/api/cities` | GET | List cities |
| `/api/export/csv` | GET | Export to CSV |
| `/webhook/save-results` | POST | n8n webhook for saving data |

### Search Companies (AI-Powered)

```http
POST /api/search
Content-Type: application/json

{
  "query": "строительные компании Самара",
  "city": "Самара",
  "ring": 1,
  "max_results": 10
}
```

### Get Companies

```http
GET /api/companies?city=Самара&has_phone=true&limit=50
```

### Export CSV

```http
GET /api/export/csv?city=Самара&priority=A
```

Full API docs: http://localhost:8000/docs

## Database Schema

### companies
- `inn` (UNIQUE) - Russian tax ID
- `название_компании` - Company name
- `телефон` - Phone (validated)
- `email` - Email
- `адрес` - Legal address
- `оборот` - Revenue
- `сайт` - Website
- Premium fields: revenue, employees, founders, etc.

### searches
- `query` - Search query
- `status` - pending/completed/failed
- `result_count` - Number of results
- `latency_ms` - Search duration

### search_results
- Links searches to companies (many-to-many)

## Phone Number Validation

Accepts:
- `+7 (846) 123-45-67`
- `8 (846) 123-45-67`
- `+78461234567`
- `88461234567`

Normalizes to: `+78461234567`

Validates:
- Length (11 digits)
- Area code (3-9 for Russian regions)

## Deployment to Railway

See [DEPLOYMENT.md](DEPLOYMENT.md) for full guide.

**Quick Deploy:**

```bash
# Push to GitHub
git add -A
git commit -m "Deploy СтройПарсер v2.0"
git push

# In Railway:
# 1. Connect GitHub repo
# 2. Add environment variables (see .env.example)
# 3. Deploy
```

## File Structure

```
stroyparser/
├── main.py              # FastAPI app + routes
├── database.py          # PostgreSQL layer
├── scraper.py           # AI agent + Rusprofile
├── utils.py             # Phone/email validation
├── requirements.txt     # Dependencies
├── templates/
│   └── index.html       # Dashboard UI
├── static/
│   └── styles.css       # CSS
├── .env.example         # Environment template
├── DEPLOYMENT.md        # Full deploy guide
└── README.md            # This file
```

## Troubleshooting

### "No module named 'fastapi'"
```bash
pip install -r requirements.txt
```

### "No companies found"
- Check Bright Data credentials (API_TOKEN, BROWSER_AUTH)
- Verify Anthropic API key is valid
- Check logs for errors

### "Phone numbers missing"
- Phone numbers come from 2GIS/Yandex Maps
- Not all companies have public phones
- Check scraper logs to see what was extracted

### "Python 3.14 package errors"
```bash
# Use Python 3.12 instead
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Cost

Per search (10 companies):
- Claude API: ~$0.01 (Haiku model)
- Bright Data: ~$0.05 (depends on zone)
- **Total: ~$0.06**

Monthly (1000 searches): ~$60/month

## License

MIT

## Support

Issues: https://github.com/WhoAmI-glitch/Stroy-parser-PocketRoman/issues
