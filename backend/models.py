"""Database setup and tables (SQLite by default, set DATABASE_URL for Postgres)."""
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import ForeignKey, String, UniqueConstraint, create_engine
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker)

load_dotenv()   # reads .env if present (real environment variables win)
DEFAULT_DB = Path(__file__).resolve().parent / "restaurant.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB}")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

WAT = timezone(timedelta(hours=1))   # Nigeria time; dashboard "today" follows this


def now() -> datetime:
    """Naive datetime in Nigeria time, used for every timestamp."""
    return datetime.now(WAT).replace(tzinfo=None)


# orders that count as real money / real food
ACTIVE_STATUSES = ("preparing", "ready", "out_for_delivery")
PAID_STATUSES = ACTIVE_STATUSES + ("completed",)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(String(20), default="customer")   # customer | staff | owner
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=now)


class Dish(Base):
    __tablename__ = "dishes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[int]                       # Naira per unit
    unit: Mapped[str] = mapped_column(String(30), default="plate")
    prep_minutes: Mapped[int]
    available: Mapped[bool] = mapped_column(default=True)
    image_url: Mapped[Optional[str]]                       # optional photo link
    times_ordered: Mapped[int] = mapped_column(default=0)   # paid units only


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "dish_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"))
    quantity: Mapped[int]


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reference: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    order_type: Mapped[str] = mapped_column(String(20))        # delivery | pickup
    address: Mapped[Optional[str]]
    subtotal: Mapped[int]
    delivery_fee: Mapped[int]
    total: Mapped[int]
    ready_in_minutes: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default="pending_payment", index=True)
    created_at: Mapped[datetime] = mapped_column(default=now)
    paid_at: Mapped[Optional[datetime]]
    ready_at: Mapped[Optional[datetime]]
    arrives_at: Mapped[Optional[datetime]]
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan")


class OrderItem(Base):
    """Snapshot of what was bought, so later price changes never rewrite history."""
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    dish_id: Mapped[int]
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(30))
    unit_price: Mapped[int]
    quantity: Mapped[int]
    line_total: Mapped[int]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
