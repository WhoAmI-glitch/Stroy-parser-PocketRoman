# 🤖 Bright Data Web Scraping Agent

A conversational AI agent that can scrape websites using natural language commands.

## What It Does

This tool lets you chat with an AI agent (Claude) that has access to Bright Data's web scraping capabilities. Simply ask it to scrape a website, and it will:

1. Understand your request
2. Use Bright Data's tools to fetch the data
3. Return the results in a readable format

**Example conversation:**
```
You: Scrape construction companies from rusprofile.ru in Samara
Agent: [fetches data and returns company names, phones, addresses...]
```

## Requirements

- Python 3.14+
- Node.js (for npx)
- Anthropic API key
- Bright Data account with API credentials

## Setup

1. **Clone the repo:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/stroyparser.git
   cd stroyparser
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   
   Or with uv:
   ```bash
   uv sync
   ```

3. **Create `.env` file:**
   ```env
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   API_TOKEN=your-bright-data-api-token
   BROWSER_AUTH=your-bright-data-browser-auth
   WEB_UNLOCKER_ZONE=your-bright-data-zone
   ```

4. **Run the agent:**
   ```bash
   python main.py
   ```

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   You       │ ──▶ │   Claude    │ ──▶ │ Bright Data │
│  (chat)     │     │   (AI)      │     │  (scraper)  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    Returns scraped
                        data
```

- **MCP (Model Context Protocol)** — Connects Claude to external tools
- **LangChain** — Framework for building AI agents
- **Bright Data** — Web scraping infrastructure (proxies, browser automation)

## Tech Stack

| Component | Purpose |
|-----------|---------|
| `langchain-anthropic` | Claude AI model |
| `langchain-mcp-adapters` | Connect MCP tools to LangChain |
| `langgraph` | Agent orchestration |
| `@brightdata/mcp` | Bright Data scraping tools |

## Commands

Type your scraping requests naturally:

- `"Scrape company info from example.com"`
- `"Get phone numbers from this page: https://..."`
- `"Find construction companies in Samara"`

Type `exit` or `quit` to end the session.

## License

MIT
