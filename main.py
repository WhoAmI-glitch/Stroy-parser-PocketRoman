"""
СтройПарсер v2.0 - БАЗА TD
FastAPI backend with PostgreSQL persistence
"""
import os
import time
import json
import re
import logging
import base64
import hmac
import hashlib
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File, Header, Body
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


# ==================== AUTH UTILITIES ====================

AUTH_SECRET = os.getenv("AUTH_SECRET", "change-me-in-prod")
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "604800"))  # 7 days


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    digest = base64.b64encode(dk).decode("utf-8")
    return f"pbkdf2_sha256$100000${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
        expected = base64.b64encode(dk).decode("utf-8")
        return hmac.compare_digest(expected, digest)
    except Exception:
        return False


def create_token(user_id: int) -> str:
    exp = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{user_id}.{exp}"
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}.{sig}".encode("utf-8")).decode("utf-8")
    return token


def verify_token(token: str) -> Optional[int]:
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id_str, exp_str, sig = raw.split(".", 2)
        payload = f"{user_id_str}.{exp_str}"
        expected = hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        if int(exp_str) < int(time.time()):
            return None
        return int(user_id_str)
    except Exception:
        return None


def sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user.get("id"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "email": user.get("email") or user.get("username"),
        "role": user.get("role", "user")
    }


def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


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


class TelegramSendRequest(BaseModel):
    companies: List[Dict[str, Any]]


class AuthRegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


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


# ==================== ENRICHMENT ====================

@app.post("/enrich")
async def enrich_companies(inn_list: List[str] = Body(...)):
    """
    Enrich companies by INN list.
    Returns companies already stored in DB for the provided INNs.
    """
    try:
        companies = db.get_companies_by_inn_list(inn_list)
        return {
            "success": True,
            "companies": companies,
            "count": len(companies)
        }
    except Exception as e:
        logger.error(f"Enrich error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== FILE UPLOAD ====================

@app.post("/upload-pricelist")
async def upload_pricelist(file: UploadFile = File(...)):
    """
    Accepts a price list file and stores it on disk.
    """
    try:
        uploads_dir = Path(os.getenv("UPLOADS_DIR", "uploads"))
        uploads_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{int(time.time())}_{file.filename}"
        save_path = uploads_dir / safe_name
        contents = await file.read()
        with open(save_path, "wb") as f:
            f.write(contents)
        return {
            "success": True,
            "filename": safe_name,
            "size": len(contents)
        }
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AUTH ENDPOINTS ====================

@app.post("/auth/register")
async def auth_register(request: AuthRegisterRequest):
    try:
        existing = db.get_user_by_email(request.email)
        if existing:
            raise HTTPException(status_code=400, detail="User already exists")
        password_hash = hash_password(request.password)
        user_id = db.create_user(
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            password_hash=password_hash
        )
        user = db.get_user_by_id(user_id)
        return {"success": True, "user": sanitize_user(user)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/login")
async def auth_login(request: AuthLoginRequest):
    try:
        user = db.get_user_by_email(request.email)
        if not user or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = create_token(user["id"])
        return {"success": True, "token": token, "user": sanitize_user(user)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/me")
async def auth_me(authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    return sanitize_user(user)


@app.post("/auth/change-password")
async def auth_change_password(request: AuthChangePasswordRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    if not verify_password(request.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    new_hash = hash_password(request.new_password)
    db.update_user_password(user["id"], new_hash)
    return {"success": True}


@app.post("/auth/logout")
async def auth_logout():
    # Stateless tokens: nothing to invalidate server-side
    return {"success": True}


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


# ==================== TELEGRAM ENDPOINTS ====================

@app.post("/api/telegram/send")
async def send_to_telegram(request: TelegramSendRequest):
    """Send selected companies to all authenticated Telegram users"""
    import httpx

    try:
        # Get bot token from environment or config
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '8248564352:AAERNBeg07cM03Gtiif3k49tRw6verjCYZ8')

        # Get all telegram users from database
        all_users = db.get_all_telegram_users()

        if not all_users:
            return {
                "success": False,
                "error": "No authenticated Telegram users found. Users must login to bot first with /login command."
            }

        # Get all user IDs
        all_user_ids = [user['telegram_id'] for user in all_users]

        # Format message
        companies_text = "*Новые компании из СтройПарсер*\n\n"

        for i, company in enumerate(request.companies, 1):
            companies_text += f"*{i}. {company.get('название_компании', 'N/A')}*\n"

            if company.get('инн'):
                companies_text += f"ИНН: `{company['инн']}`\n"
            if company.get('город'):
                companies_text += f"Город: {company['город']}\n"
            if company.get('оборот'):
                companies_text += f"Оборот: {formatNumber(company['оборот'])}\n"
            if company.get('приоритет'):
                companies_text += f"Приоритет: {company['приоритет']}\n"
            if company.get('телефон'):
                companies_text += f"Телефон: `{company['телефон']}`\n"
            if company.get('email'):
                companies_text += f"Email: `{company['email']}`\n"
            if company.get('сайт'):
                companies_text += f"Сайт: {company['сайт']}\n"

            companies_text += "\n"

        companies_text += f"_Отправлено: {datetime.now().strftime('%Y-%m-%d %H:%M')}_"

        # Send to all users
        success_count = 0
        fail_count = 0

        async with httpx.AsyncClient() as client:
            for user_id in all_user_ids:
                try:
                    response = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": user_id,
                            "text": companies_text,
                            "parse_mode": "Markdown"
                        },
                        timeout=10.0
                    )

                    if response.status_code == 200:
                        success_count += 1
                        logger.info(f"Sent companies to Telegram user {user_id}")
                    else:
                        fail_count += 1
                        logger.warning(f"Failed to send to {user_id}: {response.text}")

                except Exception as e:
                    fail_count += 1
                    logger.error(f"Error sending to {user_id}: {e}")

        return {
            "success": True,
            "message": f"Отправлено {success_count} пользователям",
            "sent_to": success_count,
            "failed": fail_count,
            "total_companies": len(request.companies)
        }

    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def formatNumber(num):
    """Helper to format numbers"""
    if num is None:
        return '-'
    if num >= 1000000000:
        return f"{num / 1000000000:.1f}B"
    if num >= 1000000:
        return f"{num / 1000000:.1f}M"
    if num >= 1000:
        return f"{num / 1000:.1f}K"
    return str(num)


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
