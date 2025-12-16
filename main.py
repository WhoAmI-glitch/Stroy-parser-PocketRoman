from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import asyncio
import uvicorn
from datetime import datetime

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

app = FastAPI(title="СтройПарсер Webhook API", version="1.0.0")

# Store job results
job_results: Dict[str, Any] = {}


class ScrapeRequest(BaseModel):
    """Request body for scraping"""
    query: str  # e.g. "Scrape construction companies from rusprofile.ru in Samara"
    city: Optional[str] = None
    ring: Optional[int] = None
    max_results: Optional[int] = 50


class ScrapeResponse(BaseModel):
    """Response from scraping"""
    success: bool
    data: Any
    error: Optional[str] = None
    timestamp: str


def get_server_params():
    """Get MCP server parameters with env vars"""
    return StdioServerParameters(
        command="npx",
        env={
            "API_TOKEN": os.getenv("API_TOKEN"),
            "BROWSER_AUTH": os.getenv("BROWSER_AUTH"),
            "WEB_UNLOCKER_ZONE": os.getenv("WEB_UNLOCKER_ZONE"),
        },
        args=["@brightdata/mcp"],
    )


async def run_agent(query: str) -> str:
    """Run the MCP agent with a query"""
    model = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )
    
    server_params = get_server_params()
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            agent = create_react_agent(model, tools)
            
            messages = [
                {
                    "role": "system",
                    "content": """You are a web scraping assistant. Extract company information and return it as JSON.
                    
Always return data in this format:
{
    "companies": [
        {
            "название_компании": "Company Name",
            "телефон": "+7...",
            "email": "email@example.com",
            "адрес": "Address",
            "сайт": "https://...",
            "инн": "1234567890"
        }
    ],
    "total_found": 10,
    "source": "url scraped"
}"""
                },
                {"role": "user", "content": query}
            ]
            
            response = await agent.ainvoke({"messages": messages})
            return response["messages"][-1].content


@app.get("/")
def root():
    """Health check"""
    return {
        "status": "online",
        "service": "СтройПарсер Webhook API",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
def health():
    """Health check with env var validation"""
    return {
        "status": "healthy",
        "api_token_set": bool(os.getenv("API_TOKEN")),
        "browser_auth_set": bool(os.getenv("BROWSER_AUTH")),
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


@app.post("/webhook/scrape", response_model=ScrapeResponse)
async def webhook_scrape(request: ScrapeRequest):
    """
    Main webhook endpoint for n8n
    
    Example n8n HTTP Request:
    - Method: POST
    - URL: https://your-app.up.railway.app/webhook/scrape
    - Body (JSON):
        {
            "query": "Найди строительные компании в Самаре на rusprofile.ru",
            "city": "Самара",
            "ring": 1
        }
    """
    try:
        # Build the query
        query = request.query
        if request.city:
            query += f" в городе {request.city}"
        if request.max_results:
            query += f". Найди максимум {request.max_results} компаний."
        
        # Run the agent
        result = await run_agent(query)
        
        return ScrapeResponse(
            success=True,
            data=result,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        return ScrapeResponse(
            success=False,
            data=None,
            error=str(e),
            timestamp=datetime.now().isoformat()
        )


@app.post("/webhook/scrape-city")
async def webhook_scrape_city(city: str, category: str = "строительные компании"):
    """
    Simplified endpoint - just pass city name
    
    Example: POST /webhook/scrape-city?city=Самара&category=строительные компании
    """
    query = f"Найди {category} в городе {city} на rusprofile.ru. Верни название, телефон, email, адрес, сайт, ИНН."
    
    try:
        result = await run_agent(query)
        return {
            "success": True,
            "city": city,
            "category": category,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "city": city,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
