"""
Utility functions for phone validation, data cleaning, etc.
"""
import re
from typing import List, Optional


def validate_russian_phone(phone: str) -> Optional[str]:
    """
    Validate and normalize Russian phone number

    Accepts formats:
    - +7 (XXX) XXX-XX-XX
    - 8 (XXX) XXX-XX-XX
    - +7XXXXXXXXXX
    - 8XXXXXXXXXX

    Returns normalized format: +7XXXXXXXXXX or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digits
    digits = re.sub(r'\D', '', phone)

    # Check length (should be 11 digits for Russian numbers)
    if len(digits) != 11:
        return None

    # Check if starts with 7 or 8
    if digits[0] == '8':
        digits = '7' + digits[1:]
    elif digits[0] != '7':
        return None

    # Check if second digit is valid (3-9 for Russian mobile/city codes)
    if digits[1] not in '3456789':
        return None

    return '+' + digits


def extract_phones_from_text(text: str) -> List[str]:
    """
    Extract and validate all phone numbers from text
    Returns list of normalized phone numbers
    """
    # Pattern for Russian phone numbers
    patterns = [
        r'\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
        r'\+?[78]\d{10}',
    ]

    phones = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        phones.extend(matches)

    # Validate and normalize
    validated = []
    for phone in phones:
        normalized = validate_russian_phone(phone)
        if normalized and normalized not in validated:
            validated.append(normalized)

    return validated


def extract_emails_from_text(text: str) -> List[str]:
    """
    Extract and validate email addresses from text
    """
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)

    # Remove duplicates and common false positives
    validated = []
    for email in emails:
        email = email.lower()
        if email not in validated and not email.endswith(('.png', '.jpg', '.gif')):
            validated.append(email)

    return validated


def validate_inn(inn: str) -> bool:
    """
    Validate Russian INN (ИНН) number
    INN can be 10 digits (legal entity) or 12 digits (individual entrepreneur)
    """
    if not inn:
        return False

    # Remove non-digits
    inn = re.sub(r'\D', '', inn)

    # Check length
    if len(inn) not in (10, 12):
        return False

    # All digits
    if not inn.isdigit():
        return False

    return True


def clean_company_name(name: str) -> str:
    """
    Clean and normalize company name
    Remove extra spaces, quotes, etc.
    """
    if not name:
        return ""

    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    # Remove quotes
    name = name.replace('"', '').replace("'", '')

    return name
