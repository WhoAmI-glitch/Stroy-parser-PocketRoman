"""
Company scraper with Bright Data MCP + Rusprofile enrichment
Searches 2gis.ru, yandex.ru/maps, rusprofile.ru for company data
"""
import asyncio
import json
import os
import pickle
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

import utils
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

RUSPROFILE_EMAIL = os.getenv("RUSPROFILE_EMAIL", "")
RUSPROFILE_PASSWORD = os.getenv("RUSPROFILE_PASSWORD", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
API_TOKEN = os.getenv("API_TOKEN", "")
BROWSER_AUTH = os.getenv("BROWSER_AUTH", "")
WEB_UNLOCKER_ZONE = os.getenv("WEB_UNLOCKER_ZONE", "")

SESSION_DIR = Path("/tmp")
SESSION_FILE = SESSION_DIR / ".rusprofile_session.pkl"
SESSION_MAX_AGE_HOURS = 128
BASE_URL = "https://www.rusprofile.ru"
SEARCH_URL = "https://www.rusprofile.ru/search?query={query}"


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CompanyData:
    """Full company data from web scraping + rusprofile"""
    inn: str = ""
    ogrn: str = ""
    kpp: str = ""
    short_name: str = ""
    full_name: str = ""
    status: str = ""
    legal_address: str = ""
    region: str = ""
    director_name: str = ""
    director_position: str = ""
    registration_date: str = ""
    okved_main: str = ""
    okved_main_name: str = ""
    authorized_capital: str = ""
    revenue: str = ""
    profit: str = ""
    employees_count: str = ""
    phones: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    website: str = ""
    okpo: str = ""
    oktmo: str = ""
    tax_system: str = ""
    msp_category: str = ""
    government_contracts_count: int = 0
    government_contracts_sum: str = ""
    court_cases_plaintiff: int = 0
    court_cases_defendant: int = 0
    founders: List[Dict] = field(default_factory=list)
    source_url: str = ""
    parsed_at: str = ""
    data_source: str = ""  # "agent", "rusprofile", "merged"

    def to_dict(self):
        return asdict(self)

    def merge_with(self, other: 'CompanyData') -> 'CompanyData':
        """Merge with another CompanyData, filling in blanks"""
        for fld in self.__dataclass_fields__:
            self_val = getattr(self, fld)
            other_val = getattr(other, fld)

            # If self is empty and other has value, use other
            if not self_val and other_val:
                setattr(self, fld, other_val)
            # For lists, merge unique values
            elif isinstance(self_val, list) and isinstance(other_val, list):
                merged = list(set(self_val + other_val))
                setattr(self, fld, merged)

        self.data_source = "merged"
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# RUSPROFILE PARSER (Premium Data)
# ═══════════════════════════════════════════════════════════════════════════════

class RusprofileParser:
    """Rusprofile parser for premium data (revenue, employees, etc.)"""

    def __init__(self):
        self.email = RUSPROFILE_EMAIL
        self.password = RUSPROFILE_PASSWORD

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        self.is_logged_in = False
        self._load_session()

    def _save_session(self):
        try:
            data = {
                "cookies": self.session.cookies.get_dict(),
                "timestamp": datetime.now().isoformat(),
                "email": self.email
            }
            with open(SESSION_FILE, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save rusprofile session: {e}")

    def _load_session(self):
        try:
            if not SESSION_FILE.exists():
                return False
            with open(SESSION_FILE, 'rb') as f:
                data = pickle.load(f)
            if datetime.now() - datetime.fromisoformat(data["timestamp"]) > timedelta(hours=SESSION_MAX_AGE_HOURS):
                return False
            if data.get("email") != self.email:
                return False
            for name, value in data["cookies"].items():
                self.session.cookies.set(name, value)
            self.is_logged_in = True
            return True
        except:
            return False

    def _fetch(self, url):
        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error(f"Rusprofile fetch failed: {e}")
            return None

    def login(self, force=False):
        if self.is_logged_in and not force:
            return True
        if not self.email or not self.password:
            logger.info("Rusprofile credentials not set - skipping premium data")
            return False

        logger.info(f"Logging into Rusprofile as {self.email}...")

        html = self._fetch(BASE_URL)
        if not html:
            return False

        soup = BeautifulSoup(html, 'lxml')
        csrf = ""
        csrf_input = soup.find('input', {'name': '_token'}) or soup.find('input', {'name': 'csrf_token'})
        if csrf_input:
            csrf = csrf_input.get('value', '')

        login_data = {'email': self.email, 'password': self.password, 'remember': '1'}
        if csrf:
            login_data['_token'] = csrf

        self.session.headers['Referer'] = BASE_URL

        try:
            resp = self.session.post(BASE_URL, data=login_data, timeout=30, allow_redirects=True)
            if 'logout' in resp.text.lower() or 'выход' in resp.text.lower():
                self.is_logged_in = True
                self._save_session()
                logger.info("Rusprofile login successful!")
                return True
            return False
        except Exception as e:
            logger.error(f"Rusprofile login failed: {e}")
            return False

    def get_premium_data(self, inn: str) -> Optional[CompanyData]:
        """Get premium data (revenue, employees, etc.) from Rusprofile"""
        if not inn or not utils.validate_inn(inn):
            logger.warning(f"Invalid INN: {inn}")
            return None

        self.login()

        url = SEARCH_URL.format(query=quote(inn))
        html = self._fetch(url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'lxml')

        # Check if we landed on company page directly
        canonical = soup.find('link', rel='canonical')
        if canonical and '/id/' in canonical.get('href', ''):
            return self._parse_premium_fields(html, canonical.get('href'))

        # Find link to company page
        link = soup.find('a', href=re.compile(r'/id/\d+'))
        if not link:
            logger.warning(f"Company not found on Rusprofile for INN: {inn}")
            return None

        company_url = BASE_URL + link.get('href') if not link.get('href').startswith('http') else link.get('href')
        html = self._fetch(company_url)
        if not html:
            return None

        return self._parse_premium_fields(html, company_url)

    def _parse_premium_fields(self, html: str, source_url: str) -> CompanyData:
        """Parse premium fields from Rusprofile company page"""
        soup = BeautifulSoup(html, 'lxml')
        data = CompanyData(source_url=source_url, data_source="rusprofile")
        text = soup.get_text(" ", strip=True)

        # Basic identifiers
        m = re.search(r'ИНН[:\s]*(\d{10,12})', html)
        if m:
            data.inn = m.group(1)
        m = re.search(r'ОГРН[:\s]*(\d{13,15})', html)
        if m:
            data.ogrn = m.group(1)
        m = re.search(r'КПП[:\s]*(\d{9})', html)
        if m:
            data.kpp = m.group(1)

        # Name
        h1 = soup.find('h1')
        if h1:
            data.short_name = utils.clean_company_name(h1.get_text(strip=True))

        # Status
        if re.search(r'Действующ', text, re.I):
            data.status = "Действующая"
        elif re.search(r'Ликвидир', text, re.I):
            data.status = "Ликвидирована"

        # Address
        addr = soup.find('address') or soup.find('span', {'itemprop': 'address'})
        if addr:
            data.legal_address = addr.get_text(strip=True)
        else:
            m = re.search(r'(?:Юридический адрес|Адрес)[:\s]*([^\n<]+)', text)
            if m:
                data.legal_address = m.group(1).strip()[:200]

        # Director
        m = re.search(r'(Генеральный директор|Директор)[:\s]*([А-ЯЁа-яё\s\-]{5,50})', text)
        if m:
            data.director_position = m.group(1)
            data.director_name = re.sub(r'\s+', ' ', m.group(2)).strip()

        # Registration date
        m = re.search(r'Дата регистрации[:\s]*(\d{2}\.\d{2}\.\d{4})', text)
        if m:
            data.registration_date = m.group(1)

        # OKVED
        m = re.search(r'ОКВЭД[:\s]*(\d{2}\.\d{2}(?:\.\d{1,2})?)', text)
        if m:
            data.okved_main = m.group(1)

        # ═══════════════════════════════════════════════════════════════════
        # PREMIUM FIELDS - Main reason to use Rusprofile
        # ═══════════════════════════════════════════════════════════════════

        # Revenue (Выручка)
        revenue_patterns = [
            r'Выручка за \d{4}[:\s]*([\d\s,\.]+\s*(?:млн|тыс|млрд)?\.?\s*(?:руб|₽)?)',
            r'Выручка[:\s]*([\d\s,\.]+\s*(?:млн|тыс|млрд)?\.?\s*(?:руб|₽)?)',
        ]
        for pattern in revenue_patterns:
            m = re.search(pattern, text, re.I)
            if m and m.group(1).strip():
                data.revenue = m.group(1).strip()
                break

        # Profit (Прибыль)
        profit_patterns = [
            r'(?:Чистая\s+)?прибыль за \d{4}[:\s]*([\-\d\s,\.]+\s*(?:млн|тыс|млрд)?\.?\s*(?:руб|₽)?)',
            r'(?:Чистая\s+)?прибыль[:\s]*([\-\d\s,\.]+\s*(?:млн|тыс|млрд)?\.?\s*(?:руб|₽)?)',
        ]
        for pattern in profit_patterns:
            m = re.search(pattern, text, re.I)
            if m and m.group(1).strip():
                data.profit = m.group(1).strip()
                break

        # Capital
        m = re.search(r'Уставный капитал[:\s]*([\d\s,\.]+)\s*(?:руб|₽)?', text, re.I)
        if m:
            data.authorized_capital = m.group(1).strip() + " руб."

        # Employees
        emp_patterns = [
            r'(?:Численность|Сотрудников|Среднесписочная численность)[:\s]*(\d+)',
            r'(\d+)\s*(?:сотрудник|человек|работник)',
        ]
        for pattern in emp_patterns:
            m = re.search(pattern, text, re.I)
            if m:
                data.employees_count = m.group(1)
                break

        # Tax system
        m = re.search(r'(?:Налоговый режим|Система налогообложения)[:\s]*(ОСН|УСН|ЕНВД|ЕСХН|ПСН|НПД)', text, re.I)
        if m:
            data.tax_system = m.group(1).upper()

        # MSP category
        m = re.search(r'(Микро|Малое|Среднее)\s*предприятие', text, re.I)
        if m:
            data.msp_category = m.group(1).capitalize()

        # Codes
        for code, fld in [('ОКПО', 'okpo'), ('ОКТМО', 'oktmo')]:
            m = re.search(rf'{code}[:\s]*(\d+)', text)
            if m:
                setattr(data, fld, m.group(1))

        # Government contracts
        m = re.search(r'(?:Госконтракт|Контракт)[ыов]*[:\s]*(\d+)', text, re.I)
        if m:
            data.government_contracts_count = int(m.group(1))

        # Court cases
        m = re.search(r'(?:Истец|как истец)[:\s]*(\d+)', text, re.I)
        if m:
            data.court_cases_plaintiff = int(m.group(1))
        m = re.search(r'(?:Ответчик|как ответчик)[:\s]*(\d+)', text, re.I)
        if m:
            data.court_cases_defendant = int(m.group(1))

        # Contacts - extract and validate phone numbers
        data.phones = utils.extract_phones_from_text(html)
        data.emails = utils.extract_emails_from_text(html)

        # Website
        website_el = soup.find('a', {'class': re.compile(r'website|site', re.I)})
        if website_el:
            data.website = website_el.get('href', '') or website_el.get_text(strip=True)

        # Extract region from address
        if data.legal_address:
            parts = data.legal_address.split(',')
            for part in parts:
                if 'область' in part.lower() or 'край' in part.lower() or 'республика' in part.lower():
                    data.region = part.strip()
                    break

        data.parsed_at = datetime.now().isoformat()
        return data


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT FOR AGENT
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a Russian company finder agent. Your task is to search for companies and extract ALL available information.

When the user asks to find companies, search these sources:
- 2gis.ru (maps, has phones, addresses, websites)
- yandex.ru/maps (similar to 2gis, often has phone numbers)
- rusprofile.ru (official registry, has INN, OGRN)
- list-org.com (business directory)
- cataloxy.ru (company catalog)

For EACH company found, extract as much as possible:
- Company name (short and full)
- INN (ИНН) - 10 or 12 digits - REQUIRED
- OGRN (ОГРН) - 13 or 15 digits
- Legal address
- Phone numbers - IMPORTANT: Extract ALL phone numbers you find
- Email addresses
- Website
- Director name
- Main activity (ОКВЭД)
- Status (active/liquidated)

PHONE NUMBERS ARE CRITICAL:
- Look for them on 2GIS and Yandex Maps pages
- Extract all variants: +7, 8, with/without spaces and dashes
- Return all found phones, not just one

Return ALL found data in this JSON format:
```json
{
    "companies": [
        {
            "short_name": "ООО Компания",
            "full_name": "Общество с ограниченной ответственностью Компания",
            "inn": "1234567890",
            "ogrn": "1234567890123",
            "legal_address": "г. Самара, ул. Примерная, д. 1",
            "region": "Самарская область",
            "phones": ["+7 846 123-45-67", "+7 846 987-65-43"],
            "emails": ["info@company.ru"],
            "website": "www.company.ru",
            "director_name": "Иванов Иван Иванович",
            "okved_main": "41.20",
            "okved_main_name": "Строительство жилых и нежилых зданий",
            "status": "Действующая",
            "registration_date": "01.01.2020",
            "source_url": "https://..."
        }
    ]
}
```

IMPORTANT:
1. INN is REQUIRED for each company
2. Extract ALL phone numbers from 2gis/yandex maps
3. Extract websites and emails when visible
4. Include the source URL where you found the data
5. Search multiple sources to get complete information
6. Missing fields should be empty strings "" or empty arrays []"""


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY FINDER AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class CompanyFinderAgent:
    """Agent that finds companies via MCP and enriches with Rusprofile"""

    def __init__(self):
        self.parser = RusprofileParser()

    def extract_companies_from_response(self, response: str) -> List[CompanyData]:
        """Extract company data from agent response"""
        companies = []

        # Find JSON block
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if 'companies' in data:
                    for comp in data['companies']:
                        company = CompanyData(
                            inn=comp.get('inn', ''),
                            ogrn=comp.get('ogrn', ''),
                            short_name=utils.clean_company_name(comp.get('short_name', '')),
                            full_name=comp.get('full_name', ''),
                            legal_address=comp.get('legal_address', ''),
                            region=comp.get('region', ''),
                            phones=[utils.validate_russian_phone(p) for p in comp.get('phones', []) if utils.validate_russian_phone(p)],
                            emails=comp.get('emails', []),
                            website=comp.get('website', ''),
                            director_name=comp.get('director_name', ''),
                            okved_main=comp.get('okved_main', ''),
                            okved_main_name=comp.get('okved_main_name', ''),
                            status=comp.get('status', ''),
                            registration_date=comp.get('registration_date', ''),
                            source_url=comp.get('source_url', ''),
                            data_source="agent"
                        )
                        if company.inn and utils.validate_inn(company.inn):
                            companies.append(company)
                        else:
                            logger.warning(f"Skipping company without valid INN: {company.short_name}")
                    return companies
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from agent response: {e}")

        # Fallback: extract INNs from text
        inn_matches = re.findall(r'ИНН[:\s]*(\d{10,12})', response)
        for inn in inn_matches:
            if utils.validate_inn(inn) and not any(c.inn == inn for c in companies):
                companies.append(CompanyData(inn=inn, data_source="agent"))

        return companies

    def enrich_with_rusprofile(self, companies: List[CompanyData]) -> List[CompanyData]:
        """Enrich companies with premium data from Rusprofile"""
        enriched = []

        logger.info(f"Enriching {len(companies)} companies with Rusprofile data...")

        for i, company in enumerate(companies, 1):
            logger.info(f"[{i}/{len(companies)}] Enriching {company.short_name or company.inn}")
            logger.info(f"  Agent found: INN={company.inn}, phones={len(company.phones)}, website={bool(company.website)}")

            # Get premium data from Rusprofile
            premium = self.parser.get_premium_data(company.inn)

            if premium:
                # Merge: keep agent data, fill missing with Rusprofile
                company.merge_with(premium)
                logger.info(f"  Rusprofile: revenue={premium.revenue}, employees={premium.employees_count}, phones={len(premium.phones)}")
            else:
                logger.warning(f"  Rusprofile: no additional data found for {company.inn}")

            enriched.append(company)

            # Small delay to avoid rate limiting
            import time
            time.sleep(1)

        return enriched


async def scrape_companies(query: str, max_results: int = 10, enrich: bool = True) -> List[CompanyData]:
    """
    Main function to scrape companies using MCP + Claude agent

    Args:
        query: Search query (e.g., "Find construction companies in Samara")
        max_results: Maximum number of companies to return
        enrich: Whether to enrich with Rusprofile premium data

    Returns:
        List of CompanyData objects
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    if not API_TOKEN:
        raise ValueError("API_TOKEN environment variable not set (Bright Data)")

    agent_handler = CompanyFinderAgent()

    model = ChatAnthropic(
        model="claude-3-5-haiku-20241022",
        api_key=ANTHROPIC_API_KEY,
        max_retries=3,
    )

    server_params = StdioServerParameters(
        command="npx",
        env={
            **os.environ,
            "API_TOKEN": API_TOKEN,
            "BROWSER_AUTH": BROWSER_AUTH or "",
            "WEB_UNLOCKER_ZONE": WEB_UNLOCKER_ZONE or "",
        },
        args=["@brightdata/mcp"],
    )

    logger.info(f"Starting search: {query}")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            agent = create_react_agent(model, tools)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query}
            ]

            logger.info("Agent is searching...")
            agent_response = await agent.ainvoke({"messages": messages})
            ai_message = agent_response["messages"][-1].content

            logger.info("Agent response received")

            # Extract companies from response
            companies = agent_handler.extract_companies_from_response(ai_message)

            if not companies:
                logger.warning("No companies with valid INNs found in agent response")
                return []

            # Limit results
            companies = companies[:max_results]
            logger.info(f"Agent found {len(companies)} companies with INNs")

            # Enrich with Rusprofile if requested
            if enrich:
                enriched = agent_handler.enrich_with_rusprofile(companies)
                return enriched
            else:
                return companies
