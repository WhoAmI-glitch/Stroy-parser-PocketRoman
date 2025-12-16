# 🚀 СтройПарсер Webhook API

FastAPI service for web scraping via n8n webhooks. Uses Claude AI + Bright Data MCP.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Check env vars |
| `/webhook/scrape` | POST | Main scraping endpoint |
| `/webhook/scrape-city` | POST | Quick city scrape |

## n8n Integration

### HTTP Request Node Setup:

**URL:** `https://your-app.up.railway.app/webhook/scrape`

**Method:** POST

**Body (JSON):**
```json
{
    "query": "Найди строительные компании в Самаре на rusprofile.ru",
    "city": "Самара",
    "ring": 1,
    "max_results": 50
}
```

## Environment Variables (Railway)

```
ANTHROPIC_API_KEY=sk-ant-...
API_TOKEN=your-bright-data-token
BROWSER_AUTH=your-browser-auth
WEB_UNLOCKER_ZONE=your-zone
```

## Deploy to Railway

1. Push to GitHub
2. Connect repo in Railway
3. Add environment variables
4. Generate domain
5. Use URL in n8n!
