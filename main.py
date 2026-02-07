"""
СтройПарсер v2.0 - БАЗА TD
FastAPI backend with PostgreSQL persistence
"""
import os
import time
import json
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import database as db
import scraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== PYDANTIC MODELS ====================

class CompanyCreate(BaseModel):
    название_компании: Optional[str] = None
    name: Optional[str] = None
    телефон: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    адрес: Optional[str] = None
    address: Optional[str] = None
    город: Optional[str] = None
    city: Optional[str] = None
    расстояние_км: Optional[int] = None
    кольцо: Optional[int] = None
    ring: Optional[int] = None
    категория: Optional[str] = None
    category: Optional[str] = None
    сайт: Optional[str] = None
    website: Optional[str] = None
    источник: Optional[str] = None
    source: Optional[str] = None
    инн: Optional[str] = None
    inn: Optional[str] = None
    огрн: Optional[str] = None
    ogrn: Optional[str] = None
    оборот: Optional[int] = None
    revenue: Optional[int] = None
    приоритет: Optional[str] = None
    priority: Optional[str] = None
    оквэд: Optional[str] = None
    okved: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    city: Optional[str] = None
    ring: Optional[int] = None
    max_results: Optional[int] = 50
    session_id: Optional[str] = None


class SearchResponse(BaseModel):
    success: bool
    search_id: Optional[int] = None
    data: Any = None
    error: Optional[str] = None
    timestamp: str
    latency_ms: Optional[int] = None


class BulkCompaniesRequest(BaseModel):
    companies: List[CompanyCreate]
    search_id: Optional[int] = None


# ==================== APP LIFECYCLE ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting СтройПарсер v2.0...")
    try:
        db.init_db()
        logger.info("Database initialized successfully")
        # Seed default cities if empty
        seed_default_cities()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    db.close_db()


app = FastAPI(
    title="СтройПарсер v2.0 - БАЗА TD",
    description="Construction company parser with PostgreSQL persistence",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def seed_default_cities():
    """Seed default cities if cities table is empty"""
    cities = db.get_cities()
    if not cities:
        default_cities = [
            ("Самара", 1, 0),
            ("Тольятти", 1, 100),
            ("Сызрань", 1, 180),
            ("Казань", 2, 350),
            ("Ульяновск", 2, 230),
            ("Саратов", 2, 440),
            ("Пенза", 2, 400),
            ("Москва", 3, 1050),
            ("Нижний Новгород", 3, 500),
            ("Екатеринбург", 4, 850),
            ("Уфа", 3, 550),
            ("Оренбург", 3, 500),
            ("Воронеж", 3, 700),
        ]
        for name, ring, distance in default_cities:
            db.upsert_city(name, ring, distance)
        logger.info(f"Seeded {len(default_cities)} default cities")


# ==================== ROUTES ====================

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve main dashboard"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    """Health check with database status"""
    try:
        # Test DB connection
        stats = db.get_company_count()
        return {
            "status": "healthy",
            "database": "connected",
            "companies_count": stats['total'] if stats else 0,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )


@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics"""
    try:
        stats = db.get_company_count()
        return {
            "success": True,
            "data": {
                "total": stats['total'] if stats else 0,
                "priority_a": stats['priority_a'] if stats else 0,
                "priority_b": stats['priority_b'] if stats else 0,
                "priority_c": stats['priority_c'] if stats else 0,
                "with_contact": stats['with_contact'] if stats else 0,
                "with_email": stats['with_email'] if stats else 0,
                "with_phone": stats['with_phone'] if stats else 0,
            }
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== COMPANY ENDPOINTS ====================

@app.get("/api/companies")
async def get_companies(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    city: Optional[str] = None,
    ring: Optional[int] = None,
    priority: Optional[str] = None,
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None
):
    """Get companies with filters"""
    try:
        companies = db.get_companies(
            limit=limit,
            offset=offset,
            city=city,
            ring=ring,
            priority=priority,
            has_email=has_email,
            has_phone=has_phone
        )
        return {
            "success": True,
            "data": companies,
            "count": len(companies),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error getting companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/companies")
async def create_company(company: CompanyCreate):
    """Create or update a single company"""
    try:
        company_id = db.upsert_company(company.model_dump())
        return {
            "success": True,
            "company_id": company_id,
            "message": "Company saved successfully"
        }
    except Exception as e:
        logger.error(f"Error creating company: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/companies/bulk")
async def bulk_create_companies(request: BulkCompaniesRequest):
    """Bulk create/update companies"""
    try:
        start_time = time.time()
        company_ids = []
        
        for company in request.companies:
            company_id = db.upsert_company(company.model_dump())
            if company_id:
                company_ids.append(company_id)
        
        # Link to search if provided
        if request.search_id and company_ids:
            db.link_search_results(request.search_id, company_ids)
        
        latency = int((time.time() - start_time) * 1000)
        
        return {
            "success": True,
            "saved_count": len(company_ids),
            "company_ids": company_ids,
            "latency_ms": latency
        }
    except Exception as e:
        logger.error(f"Error bulk creating companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/companies/{company_id}")
async def delete_company(company_id: int):
    """Delete a company"""
    try:
        deleted = db.delete_company(company_id)
        if deleted:
            return {"success": True, "message": "Company deleted"}
        raise HTTPException(status_code=404, detail="Company not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting company: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SEARCH ENDPOINTS ====================

@app.post("/api/search", response_model=SearchResponse)
async def search_companies(request: SearchRequest):
    """
    Search for companies using AI agent + Bright Data MCP
    Creates search record, scrapes web for companies, saves to DB
    """
    start_time = time.time()
    search_id = None

    try:
        # Create search record
        search_id = db.create_search(
            query=request.query,
            city=request.city,
            ring=request.ring,
            session_id=request.session_id
        )
        logger.info(f"Created search #{search_id}: {request.query}")

        # Run the scraper (AI agent + Bright Data MCP + Rusprofile)
        scraped_companies = await scraper.scrape_companies(
            query=request.query,
            max_results=request.max_results or 50,
            enrich=True  # Always enrich with Rusprofile premium data
        )

        logger.info(f"Scraper found {len(scraped_companies)} companies")

        # Save to database
        company_ids = []
        for company in scraped_companies:
            company_data = {
                'название_компании': company.short_name,
                'телефон': company.phones[0] if company.phones else None,
                'email': company.emails[0] if company.emails else None,
                'адрес': company.legal_address,
                'город': request.city or company.region,
                'кольцо': request.ring,
                'сайт': company.website,
                'источник': 'web_scraper',
                'инн': company.inn,
                'огрн': company.ogrn,
                'оборот': int(re.sub(r'\D', '', company.revenue or '0') or '0') if company.revenue else None,
                'оквэд': company.okved_main,
            }
            company_id = db.upsert_company(company_data)
            if company_id:
                company_ids.append(company_id)

        latency_ms = int((time.time() - start_time) * 1000)

        # Update search record
        db.update_search(
            search_id=search_id,
            status='completed',
            latency_ms=latency_ms,
            result_count=len(company_ids)
        )

        # Link results
        if company_ids:
            db.link_search_results(search_id, company_ids)

        # Get saved companies from DB
        companies = db.get_companies(limit=request.max_results or 50, offset=0)

        return SearchResponse(
            success=True,
            search_id=search_id,
            data={
                "companies": companies,
                "total": len(companies),
                "scraped_new": len(company_ids)
            },
            timestamp=datetime.now().isoformat(),
            latency_ms=latency_ms
        )

    except Exception as e:
        logger.error(f"Search error: {e}")
        import traceback
        traceback.print_exc()
        latency_ms = int((time.time() - start_time) * 1000)

        if search_id:
            db.update_search(search_id, 'failed', latency_ms, 0)

        return SearchResponse(
            success=False,
            search_id=search_id,
            error=str(e),
            timestamp=datetime.now().isoformat(),
            latency_ms=latency_ms
        )


@app.get("/api/history")
async def get_search_history(limit: int = Query(20, ge=1, le=100)):
    """Get recent search history"""
    try:
        searches = db.get_recent_searches(limit)
        return {
            "success": True,
            "data": searches,
            "count": len(searches)
        }
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CITY ENDPOINTS ====================

@app.get("/api/cities")
async def get_cities():
    """Get all cities"""
    try:
        cities = db.get_cities()
        return {
            "success": True,
            "data": cities
        }
    except Exception as e:
        logger.error(f"Error getting cities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== WEBHOOK ENDPOINT (for n8n) ====================

@app.post("/webhook/save-results")
async def webhook_save_results(request: Request):
    """
    Webhook endpoint for n8n to save scraped results
    Accepts companies in flexible format
    """
    try:
        body = await request.json()
        start_time = time.time()
        
        # Handle different payload formats
        companies = body.get('companies', [])
        if not companies and 'data' in body:
            data = body['data']
            if isinstance(data, list):
                companies = data
            elif isinstance(data, dict) and 'companies' in data:
                companies = data['companies']
        
        if not companies:
            return {"success": False, "error": "No companies in payload"}
        
        # Create search record for this import
        search_id = db.create_search(
            query=body.get('query', 'webhook import'),
            city=body.get('city'),
            ring=body.get('ring'),
            session_id=body.get('session_id', 'webhook')
        )
        
        # Save companies
        company_ids = []
        for company in companies:
            company_id = db.upsert_company(company)
            if company_id:
                company_ids.append(company_id)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Update search
        db.update_search(search_id, 'completed', latency_ms, len(company_ids))
        db.link_search_results(search_id, company_ids)
        
        logger.info(f"Webhook saved {len(company_ids)} companies")
        
        return {
            "success": True,
            "search_id": search_id,
            "saved_count": len(company_ids),
            "latency_ms": latency_ms
        }
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== EXPORT ENDPOINTS ====================

@app.get("/api/export/csv")
async def export_csv(
    city: Optional[str] = None,
    ring: Optional[int] = None,
    priority: Optional[str] = None
):
    """Export companies to CSV"""
    import csv
    import io
    from fastapi.responses import StreamingResponse
    
    try:
        companies = db.get_companies(limit=10000, city=city, ring=ring, priority=priority)
        
        output = io.StringIO()
        if companies:
            writer = csv.DictWriter(output, fieldnames=companies[0].keys())
            writer.writeheader()
            writer.writerows(companies)
        
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
