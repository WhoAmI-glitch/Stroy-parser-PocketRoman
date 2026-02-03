"""
Database layer for СтройПарсер
Handles PostgreSQL connection and all DB operations
"""
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

logger = logging.getLogger(__name__)

# Connection pool
db_pool: Optional[pool.ThreadedConnectionPool] = None


def get_database_url() -> str:
    """Get DATABASE_URL from environment"""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable not set")
    # Railway uses postgres:// but psycopg2 needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def init_db():
    """Initialize database connection pool and create tables"""
    global db_pool
    try:
        database_url = get_database_url()
        db_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url,
            cursor_factory=RealDictCursor
        )
        logger.info("Database connection pool created")
        create_tables()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def close_db():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        db_pool.closeall()
        logger.info("Database connection pool closed")


@contextmanager
def get_connection():
    """Get a connection from the pool"""
    conn = db_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db_pool.putconn(conn)


def create_tables():
    """Create all required tables if they don't exist"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Companies table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id SERIAL PRIMARY KEY,
                    название_компании TEXT,
                    телефон TEXT,
                    email TEXT,
                    адрес TEXT,
                    город TEXT,
                    расстояние_км INTEGER,
                    кольцо INTEGER,
                    категория TEXT,
                    сайт TEXT,
                    источник TEXT,
                    дата_парсинга TIMESTAMPTZ DEFAULT NOW(),
                    инн TEXT UNIQUE,
                    огрн TEXT,
                    оборот BIGINT,
                    приоритет TEXT,
                    оквэд TEXT,
                    контакт_выбран BOOLEAN DEFAULT FALSE,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            
            # Searches table for tracking search history
            cur.execute("""
                CREATE TABLE IF NOT EXISTS searches (
                    id SERIAL PRIMARY KEY,
                    query TEXT NOT NULL,
                    city TEXT,
                    ring INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    status TEXT DEFAULT 'pending',
                    latency_ms INTEGER,
                    result_count INTEGER DEFAULT 0,
                    session_id TEXT
                )
            """)
            
            # Search results linking table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS search_results (
                    search_id INTEGER REFERENCES searches(id) ON DELETE CASCADE,
                    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                    rank INTEGER,
                    PRIMARY KEY (search_id, company_id)
                )
            """)
            
            # Cities table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cities (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    ring INTEGER,
                    distance_km INTEGER
                )
            """)
            
            # Scraping progress table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scraping_progress (
                    id SERIAL PRIMARY KEY,
                    city TEXT,
                    status TEXT,
                    companies_found INTEGER DEFAULT 0,
                    started_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                )
            """)
            
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            
            # Create indexes for performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_companies_city ON companies(город)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_companies_inn ON companies(инн)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_companies_ring ON companies(кольцо)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_searches_created ON searches(created_at DESC)")
            
            logger.info("Database tables created/verified")


# ==================== COMPANY OPERATIONS ====================

def upsert_company(company: Dict[str, Any]) -> int:
    """Insert or update a company by INN, return company ID"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO companies (
                    название_компании, телефон, email, адрес, город,
                    расстояние_км, кольцо, категория, сайт, источник,
                    инн, огрн, оборот, приоритет, оквэд, updated_at
                ) VALUES (
                    %(название_компании)s, %(телефон)s, %(email)s, %(адрес)s, %(город)s,
                    %(расстояние_км)s, %(кольцо)s, %(категория)s, %(сайт)s, %(источник)s,
                    %(инн)s, %(огрн)s, %(оборот)s, %(приоритет)s, %(оквэд)s, NOW()
                )
                ON CONFLICT (инн) DO UPDATE SET
                    название_компании = EXCLUDED.название_компании,
                    телефон = COALESCE(EXCLUDED.телефон, companies.телефон),
                    email = COALESCE(EXCLUDED.email, companies.email),
                    адрес = COALESCE(EXCLUDED.адрес, companies.адрес),
                    город = COALESCE(EXCLUDED.город, companies.город),
                    сайт = COALESCE(EXCLUDED.сайт, companies.сайт),
                    оборот = COALESCE(EXCLUDED.оборот, companies.оборот),
                    updated_at = NOW()
                RETURNING id
            """, {
                'название_компании': company.get('название_компании') or company.get('name'),
                'телефон': company.get('телефон') or company.get('phone'),
                'email': company.get('email'),
                'адрес': company.get('адрес') or company.get('address'),
                'город': company.get('город') or company.get('city'),
                'расстояние_км': company.get('расстояние_км'),
                'кольцо': company.get('кольцо') or company.get('ring'),
                'категория': company.get('категория') or company.get('category'),
                'сайт': company.get('сайт') or company.get('website'),
                'источник': company.get('источник') or company.get('source', 'rusprofile.ru'),
                'инн': company.get('инн') or company.get('inn'),
                'огрн': company.get('огрн') or company.get('ogrn'),
                'оборот': company.get('оборот') or company.get('revenue'),
                'приоритет': company.get('приоритет') or company.get('priority'),
                'оквэд': company.get('оквэд') or company.get('okved'),
            })
            result = cur.fetchone()
            return result['id'] if result else None


def get_companies(
    limit: int = 100,
    offset: int = 0,
    city: Optional[str] = None,
    ring: Optional[int] = None,
    priority: Optional[str] = None,
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None
) -> List[Dict]:
    """Get companies with optional filters"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            conditions = []
            params = {'limit': limit, 'offset': offset}
            
            if city:
                conditions.append("город = %(city)s")
                params['city'] = city
            if ring:
                conditions.append("кольцо = %(ring)s")
                params['ring'] = ring
            if priority:
                conditions.append("приоритет = %(priority)s")
                params['priority'] = priority
            if has_email:
                conditions.append("email IS NOT NULL AND email != ''")
            if has_phone:
                conditions.append("телефон IS NOT NULL AND телефон != ''")
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            cur.execute(f"""
                SELECT * FROM companies
                {where_clause}
                ORDER BY дата_парсинга DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)
            return cur.fetchall()


def get_company_count(
    city: Optional[str] = None,
    ring: Optional[int] = None,
    priority: Optional[str] = None
) -> Dict[str, int]:
    """Get company statistics"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE приоритет = 'A') as priority_a,
                    COUNT(*) FILTER (WHERE приоритет = 'B') as priority_b,
                    COUNT(*) FILTER (WHERE приоритет = 'C') as priority_c,
                    COUNT(*) FILTER (WHERE контакт_выбран = TRUE) as with_contact,
                    COUNT(*) FILTER (WHERE email IS NOT NULL AND email != '') as with_email,
                    COUNT(*) FILTER (WHERE телефон IS NOT NULL AND телефон != '') as with_phone
                FROM companies
            """)
            return cur.fetchone()


def delete_company(company_id: int) -> bool:
    """Delete a company by ID"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM companies WHERE id = %s", (company_id,))
            return cur.rowcount > 0


# ==================== SEARCH OPERATIONS ====================

def create_search(query: str, city: Optional[str] = None, ring: Optional[int] = None, session_id: Optional[str] = None) -> int:
    """Create a new search record"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO searches (query, city, ring, session_id, status)
                VALUES (%s, %s, %s, %s, 'running')
                RETURNING id
            """, (query, city, ring, session_id))
            return cur.fetchone()['id']


def update_search(search_id: int, status: str, latency_ms: int, result_count: int):
    """Update search with results"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE searches 
                SET status = %s, latency_ms = %s, result_count = %s
                WHERE id = %s
            """, (status, latency_ms, result_count, search_id))


def link_search_results(search_id: int, company_ids: List[int]):
    """Link companies to a search"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            for rank, company_id in enumerate(company_ids, 1):
                cur.execute("""
                    INSERT INTO search_results (search_id, company_id, rank)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (search_id, company_id, rank))


def get_recent_searches(limit: int = 20) -> List[Dict]:
    """Get recent search history"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.*, 
                       COUNT(sr.company_id) as actual_results
                FROM searches s
                LEFT JOIN search_results sr ON s.id = sr.search_id
                GROUP BY s.id
                ORDER BY s.created_at DESC
                LIMIT %s
            """, (limit,))
            return cur.fetchall()


# ==================== CITY OPERATIONS ====================

def get_cities() -> List[Dict]:
    """Get all cities"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM cities ORDER BY ring, name")
            return cur.fetchall()


def upsert_city(name: str, ring: int, distance_km: int) -> int:
    """Insert or update city"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cities (name, ring, distance_km)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    ring = EXCLUDED.ring,
                    distance_km = EXCLUDED.distance_km
                RETURNING id
            """, (name, ring, distance_km))
            return cur.fetchone()['id']
