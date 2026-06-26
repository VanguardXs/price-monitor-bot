import os
from datetime import date
from database.db import SessionLocal
from database.models import ApiUsage

DAILY_API_LIMIT = int(os.getenv("DAILY_API_LIMIT", "90"))  # safety margin under 100/month tier


def get_today_str() -> str:
    return date.today().isoformat()


def get_today_usage() -> int:
    db = SessionLocal()
    try:
        record = db.query(ApiUsage).filter(ApiUsage.date == get_today_str()).first()
        return record.request_count if record else 0
    finally:
        db.close()


def increment_usage(amount: int = 1) -> None:
    db = SessionLocal()
    try:
        today = get_today_str()
        record = db.query(ApiUsage).filter(ApiUsage.date == today).first()
        if not record:
            record = ApiUsage(date=today, request_count=0)
            db.add(record)
        record.request_count += amount
        db.commit()
    finally:
        db.close()


def has_quota(needed: int = 1) -> bool:
    """Check if there's enough daily quota left for `needed` more API calls"""
    return get_today_usage() + needed <= DAILY_API_LIMIT