from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class TrackedProduct(Base):
    __tablename__ = "tracked_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, nullable=False)
    query = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tracked_product_id = Column(Integer, nullable=False)
    source = Column(String)
    title = Column(String)
    price = Column(Float)
    rating = Column(Float)
    reviews = Column(Integer)
    url = Column(String)
    fetched_at = Column(DateTime, default=datetime.utcnow)

class ApiUsage(Base):
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, unique=True, nullable=False)  # "2026-06-25"
    request_count = Column(Integer, default=0)