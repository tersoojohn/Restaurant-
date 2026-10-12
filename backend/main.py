"""
Restaurant backend.

Roles:
  customer  browse menu, cart, checkout (Paystack), own order history
  staff     kitchen: see live order queue, move orders along
  owner     everything + dashboard, dishes, customers, staff accounts

Run:  uvicorn main:app --reload      (docs at /docs, click Authorize and paste a token)
"""
import hashlib
import hmac
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from auth import (create_token, current_user, hash_password, owner_only,
                  staff_or_owner, verify_password)
from models import (ACTIVE_STATUSES, PAID_STATUSES, Base, CartItem, Dish, Order,
                    OrderItem, SessionLocal, User, engine, get_db, now)

# the websites live in ../frontend (override with FRONTEND_DIR in .env if you move it)
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parent.parent / "frontend"))

DELIVERY_FEE = 1000
DELIVERY_MINUTES = 25
EXTRA_ITEM_BUFFER_MIN = 2

PAYSTACK_BASE = "https://api.paystack.co"
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_CALLBACK_URL = os.getenv("PAYSTACK_CALLBACK_URL", "")


# ================================================================ startup

def seed(db: Session):
    if not db.scalar(select(func.count()).select_from(Dish)):
        db.add_all([
            Dish(name="Rice and Stew", price=5000, unit="plate", prep_minutes=15, image_url="/img/dishes/rice.svg"),
            Dish(name="Chicken Wings", price=2500, unit="piece", prep_minutes=20, image_url="/img/dishes/wings.svg"),
            Dish(name="Jollof Rice", price=4500, unit="plate", prep_minutes=18, image_url="/img/dishes/jollof.svg"),
            Dish(name="Fried Plantain", price=1500, unit="plate", prep_minutes=8, image_url="/img/dishes/plantain.svg"),
        ])
    # the only way to get an owner account: set these env vars, nobody can self-register as owner
    email, password = os.getenv("OWNER_EMAIL"), os.getenv("OWNER_PASSWORD")
    if email and password and not db.scalar(select(User).where(User.email == email.lower())):
        db.add(User(name="Owner", email=email.lower(), phone=os.getenv("OWNER_PHONE", ""),
                    password_hash=hash_password(password), role="owner"))
    db.commit()
    if not db.scalar(select(User).where(User.role == "owner")):
        print("WARNING: no owner account. Set OWNER_EMAIL and OWNER_PASSWORD and restart.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Restaurant API", lifespan=lifespan)


# ================================================================ schemas

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _clean_photo_url(v: Optional[str]) -> Optional[str]:
    if v is None or not v.strip():
        return None
    v = v.strip()
    if not v.startswith(("https://", "http://", "/")):
        raise ValueError("Photo link must start with https://")
    return v


class DishIn(BaseModel):
    name: str
    price: int = Field(gt=0)
    unit: str = "plate"
    prep_minutes: int = Field(gt=0)
    available: bool = True
    image_url: Optional[str] = None

    _check_url = field_validator("image_url")(_clean_photo_url)


class DishUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = Field(None, gt=0)
    unit: Optional[str] = None
    prep_minutes: Optional[int] = Field(None, gt=0)
    available: Optional[bool] = None
    image_url: Optional[str] = None

    _check_url = field_validator("image_url")(_clean_photo_url)


class AddItem(BaseModel):
    dish_id: int
    quantity: int = Field(1, gt=0, le=100)


class CheckoutIn(BaseModel):
    order_type: Literal["delivery", "pickup"] = "delivery"
    address: Optional[str] = None


class StatusIn(BaseModel):
    status: Literal["ready", "out_for_delivery", "completed", "cancelled"]


class ActiveIn(BaseModel):
    is_active: bool


# ================================================================ auth

def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role}


@app.post("/auth/register", status_code=201, tags=["auth"])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(name=body.name, email=email, phone=body.phone,
                password_hash=hash_password(body.password), role="customer")
    db.add(user)
    db.commit()
    return {"token": create_token(user), "user": user_out(user)}


@app.post("/auth/login", tags=["auth"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")   # same message for both cases
    return {"token": create_token(user), "user": user_out(user)}


@app.get("/auth/me", tags=["auth"])
def me(user: User = Depends(current_user)):
    return user_out(user)


# ================================================================ menu (public)

@app.get("/config", tags=["menu"])
def public_config():
    """Numbers the website needs so it never hardcodes them."""
    return {"delivery_fee": DELIVERY_FEE, "delivery_minutes": DELIVERY_MINUTES}


@app.get("/dishes", tags=["menu"])
def list_dishes(sort: Literal["name", "popular", "price"] = "name", db: Session = Depends(get_db)):
    order = {"name": Dish.name, "popular": desc(Dish.times_ordered), "price": Dish.price}[sort]
    return db.scalars(select(Dish).where(Dish.available).order_by(order)).all()


@app.get("/dishes/most-ordered", tags=["menu"])
def most_ordered(limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    return db.scalars(
        select(Dish).where(Dish.available, Dish.times_ordered > 0)
        .order_by(desc(Dish.times_ordered)).limit(limit)
    ).all()


# ================================================================ cart (customer)

def cart_view(db: Session, user: User) -> dict:
    rows = db.execute(
        select(CartItem, Dish).join(Dish, CartItem.dish_id == Dish.id)
        .where(CartItem.user_id == user.id).order_by(CartItem.id)
    ).all()
    lines, subtotal = [], 0
    for item, dish in rows:
        line_total = dish.price * item.quantity
        subtotal += line_total
        lines.append({"dish_id": dish.id, "name": dish.name, "unit": dish.unit,
                      "unit_price": dish.price, "quantity": item.quantity,
                      "line_total": line_total, "available": dish.available})
    # kitchen cooks in parallel: slowest dish + small buffer per extra dish
    ready = (max(d.prep_minutes for _, d in rows) + EXTRA_ITEM_BUFFER_MIN * (len(rows) - 1)) if rows else 0
    return {"items": lines, "subtotal": subtotal, "ready_in_minutes": ready}


@app.get("/cart", tags=["cart"])
def view_cart(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return cart_view(db, user)


@app.post("/cart/items", tags=["cart"])
def add_item(body: AddItem, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dish = db.get(Dish, body.dish_id)
    if not dish:
        raise HTTPException(404, "Dish not found")
    if not dish.available:
        raise HTTPException(400, f"{dish.name} is not available right now")
    item = db.scalar(select(CartItem).where(CartItem.user_id == user.id, CartItem.dish_id == dish.id))
    if item:
        item.quantity += body.quantity
    else:
        db.add(CartItem(user_id=user.id, dish_id=dish.id, quantity=body.quantity))
    db.commit()
    return cart_view(db, user)


@app.delete("/cart/items/{dish_id}", tags=["cart"])
def remove_item(dish_id: int, quantity: int = 1, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    item = db.scalar(select(CartItem).where(CartItem.user_id == user.id, CartItem.dish_id == dish_id))
    if not item:
        raise HTTPException(404, "Item not in cart")
    item.quantity -= quantity
    if item.quantity <= 0:
        db.delete(item)
    db.commit()
    return cart_view(db, user)


# ================================================================ paystack

def paystack(method: str, path: str, **kwargs) -> dict:
    if not PAYSTACK_SECRET_KEY:
        raise HTTPException(500, "PAYSTACK_SECRET_KEY is not configured")
    try:
        r = httpx.request(method, f"{PAYSTACK_BASE}{path}", timeout=15,
                          headers={"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}, **kwargs)
        data = r.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Could not reach Paystack, try again")
    if r.status_code >= 400 or not data.get("status"):
        raise HTTPException(502, f"Paystack error: {data.get('message', 'unknown')}")
    return data["data"]


def mark_paid(db: Session, order: Order) -> Order:
    """Idempotent: webhook and verify can both fire for one payment."""
    if order.status != "pending_payment":
        return order
    travel = DELIVERY_MINUTES if order.order_type == "delivery" else 0
    t = now()
    order.status = "preparing"
    order.paid_at = t
    order.ready_at = t + timedelta(minutes=order.ready_in_minutes)
    order.arrives_at = t + timedelta(minutes=order.ready_in_minutes + travel)
    for line in order.items:
        dish = db.get(Dish, line.dish_id)
        if dish:
            dish.times_ordered += line.quantity
    db.query(CartItem).filter(CartItem.user_id == order.user_id).delete()
    db.commit()
    return order


def confirm_payment(db: Session, reference: str, tx: dict) -> Order:
    order = db.scalar(select(Order).where(Order.reference == reference))
    if not order:
        raise HTTPException(404, "Unknown reference")
    if tx.get("status") != "success":
        if order.status == "pending_payment" and tx.get("status") in ("failed", "abandoned"):
            order.status = "payment_failed"
            db.commit()
        return order
    # never trust status alone: amount and currency must match what we asked for
    if tx.get("amount") != order.total * 100 or tx.get("currency", "NGN") != "NGN":
        order.status = "payment_mismatch"
        db.commit()
        raise HTTPException(400, "Paid amount does not match order total")
    return mark_paid(db, order)


def order_out(o: Order, customer: Optional[User] = None) -> dict:
    out = {
        "order_id": o.id, "reference": o.reference, "status": o.status,
        "order_type": o.order_type, "address": o.address,
        "items": [{"dish_id": i.dish_id, "name": i.name, "unit": i.unit, "unit_price": i.unit_price,
                   "quantity": i.quantity, "line_total": i.line_total} for i in o.items],
        "subtotal": o.subtotal, "delivery_fee": o.delivery_fee, "total": o.total,
        "created_at": o.created_at, "paid_at": o.paid_at,
        "ready_at": o.ready_at, "arrives_at": o.arrives_at,
    }
    if customer:
        out["customer"] = {"name": customer.name, "phone": customer.phone, "email": customer.email}
    return out


# ================================================================ checkout & orders (customer)

@app.post("/checkout", status_code=201, tags=["orders"])
def checkout(body: CheckoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.order_type == "delivery" and not (body.address and body.address.strip()):
        raise HTTPException(400, "Address is required for delivery")
    view = cart_view(db, user)
    if not view["items"]:
        raise HTTPException(400, "Cart is empty")
    for line in view["items"]:
        if not line["available"]:
            raise HTTPException(400, f"{line['name']} just became unavailable, remove it to continue")

    fee = DELIVERY_FEE if body.order_type == "delivery" else 0
    total = view["subtotal"] + fee
    reference = f"ORD-{uuid.uuid4().hex[:14]}"
    order = Order(
        user_id=user.id, reference=reference, order_type=body.order_type,
        address=body.address, subtotal=view["subtotal"], delivery_fee=fee, total=total,
        ready_in_minutes=view["ready_in_minutes"],
        items=[OrderItem(dish_id=l["dish_id"], name=l["name"], unit=l["unit"],
                         unit_price=l["unit_price"], quantity=l["quantity"],
                         line_total=l["line_total"]) for l in view["items"]],
    )
    db.add(order)
    db.flush()   # get the id; if Paystack fails below, nothing is saved

    init = paystack("POST", "/transaction/initialize", json={
        "email": user.email, "amount": total * 100, "currency": "NGN",
        "reference": reference, "callback_url": PAYSTACK_CALLBACK_URL or None,
        "metadata": {"order_id": order.id, "user_id": user.id},
    })
    db.commit()
    return {**order_out(order), "payment_url": init["authorization_url"]}


@app.get("/payments/verify/{reference}", tags=["orders"])
def verify_payment(reference: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Call from your callback page after Paystack redirects the customer back."""
    order = db.scalar(select(Order).where(Order.reference == reference))
    if not order or (order.user_id != user.id and user.role == "customer"):
        raise HTTPException(404, "Order not found")
    tx = paystack("GET", f"/transaction/verify/{reference}")
    return order_out(confirm_payment(db, reference, tx))


@app.post("/payments/webhook", tags=["orders"])
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(PAYSTACK_SECRET_KEY.encode(), raw, hashlib.sha512).hexdigest()
    if not PAYSTACK_SECRET_KEY or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid signature")
    event = json.loads(raw)
    if event.get("event") == "charge.success":
        try:
            confirm_payment(db, event["data"].get("reference", ""), event["data"])
        except HTTPException:
            pass   # unknown reference or mismatch: logged in order status; still 200 so Paystack stops retrying
    return {"received": True}


@app.get("/orders", tags=["orders"])
def my_orders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    orders = db.scalars(select(Order).where(Order.user_id == user.id, Order.status != "pending_payment")
                        .order_by(desc(Order.id))).all()
    return [order_out(o) for o in orders]


@app.get("/orders/{order_id}", tags=["orders"])
def get_order(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    # customers only ever see their own orders; 404 (not 403) so ids can't be probed
    if not order or (user.role == "customer" and order.user_id != user.id):
        raise HTTPException(404, "Order not found")
    return order_out(order)


# ================================================================ kitchen (staff + owner)

NEXT_STATUS = {
    "preparing": {"ready", "cancelled"},
    "ready": {"out_for_delivery", "completed", "cancelled"},
    "out_for_delivery": {"completed"},
}


@app.get("/admin/orders", tags=["kitchen"])
def order_queue(status: Optional[str] = None, limit: int = Query(50, le=200),
                _: User = Depends(staff_or_owner), db: Session = Depends(get_db)):
    """Default: live queue (paid, not finished), oldest first."""
    statuses = (status,) if status else ACTIVE_STATUSES
    q = (select(Order, User).join(User, Order.user_id == User.id)
         .where(Order.status.in_(statuses)).order_by(Order.paid_at if not status else desc(Order.id))
         .limit(limit))
    return [order_out(o, u) for o, u in db.execute(q).all()]


@app.patch("/admin/orders/{order_id}/status", tags=["kitchen"])
def update_order_status(order_id: int, body: StatusIn, _: User = Depends(staff_or_owner),
                        db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if body.status not in NEXT_STATUS.get(order.status, set()):
        raise HTTPException(400, f"Cannot move an order from {order.status} to {body.status}")
    if body.status == "out_for_delivery" and order.order_type != "delivery":
        raise HTTPException(400, "Pickup orders cannot go out for delivery")
    if body.status == "completed" and order.order_type == "delivery" and order.status == "ready":
        raise HTTPException(400, "Delivery orders must go out for delivery first")
    order.status = body.status
    db.commit()
    out = order_out(order)
    if body.status == "cancelled":
        out["refund_required"] = True   # refunds are NOT automated yet: refund from the Paystack dashboard
    return out


# ================================================================ owner: dishes

@app.get("/admin/dishes", tags=["owner"])
def all_dishes(_: User = Depends(owner_only), db: Session = Depends(get_db)):
    return db.scalars(select(Dish).order_by(Dish.name)).all()


@app.post("/admin/dishes", status_code=201, tags=["owner"])
def create_dish(body: DishIn, _: User = Depends(owner_only), db: Session = Depends(get_db)):
    dish = Dish(**body.model_dump())
    db.add(dish)
    db.commit()
    return dish


@app.patch("/admin/dishes/{dish_id}", tags=["owner"])
def update_dish(dish_id: int, body: DishUpdate, _: User = Depends(owner_only),
                db: Session = Depends(get_db)):
    dish = db.get(Dish, dish_id)
    if not dish:
        raise HTTPException(404, "Dish not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(dish, field, value)
    db.commit()
    return dish


UPLOAD_DIR = FRONTEND_DIR / "uploads"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _image_extension(head: bytes) -> Optional[str]:
    """Identify the real file type from its first bytes (never trust the filename)."""
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


@app.post("/admin/dishes/{dish_id}/image", tags=["owner"])
async def upload_dish_image(dish_id: int, file: UploadFile = File(...),
                            _: User = Depends(owner_only), db: Session = Depends(get_db)):
    """Owner uploads a real photo for a dish (JPG, PNG or WebP, up to 5 MB)."""
    dish = db.get(Dish, dish_id)
    if not dish:
        raise HTTPException(404, "Dish not found")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo is too large, keep it under 5 MB")
    ext = _image_extension(data[:16])
    if not ext:
        raise HTTPException(400, "Upload a JPG, PNG or WebP photo")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    old = dish.image_url
    dish.image_url = f"/uploads/{name}"
    db.commit()
    if old and old.startswith("/uploads/"):               # tidy up the photo we replaced
        (UPLOAD_DIR / Path(old).name).unlink(missing_ok=True)
    return dish


# ================================================================ owner: people

@app.get("/admin/staff", tags=["owner"])
def list_staff(_: User = Depends(owner_only), db: Session = Depends(get_db)):
    users = db.scalars(select(User).where(User.role == "staff").order_by(User.id)).all()
    return [{**user_out(u), "is_active": u.is_active} for u in users]


@app.post("/admin/staff", status_code=201, tags=["owner"])
def create_staff(body: RegisterIn, _: User = Depends(owner_only), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(name=body.name, email=email, phone=body.phone,
                password_hash=hash_password(body.password), role="staff")
    db.add(user)
    db.commit()
    return user_out(user)


@app.patch("/admin/users/{user_id}", tags=["owner"])
def set_user_active(user_id: int, body: ActiveIn, owner: User = Depends(owner_only),
                    db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == owner.id:
        raise HTTPException(400, "You cannot disable your own account")
    user.is_active = body.is_active
    db.commit()
    return {**user_out(user), "is_active": user.is_active}


@app.get("/admin/customers", tags=["owner"])
def customers(_: User = Depends(owner_only), db: Session = Depends(get_db)):
    spend = {uid: (n, total) for uid, n, total in db.execute(
        select(Order.user_id, func.count(), func.sum(Order.total))
        .where(Order.status.in_(PAID_STATUSES)).group_by(Order.user_id))}
    users = db.scalars(select(User).where(User.role == "customer")).all()
    rows = [{**user_out(u), "is_active": u.is_active, "joined": u.created_at,
             "orders": spend.get(u.id, (0, 0))[0], "total_spent": spend.get(u.id, (0, 0))[1]}
            for u in users]
    return sorted(rows, key=lambda r: -r["total_spent"])


# ================================================================ owner: dashboard

@app.get("/admin/dashboard", tags=["owner"])
def dashboard(days: int = Query(7, ge=1, le=90), _: User = Depends(owner_only),
              db: Session = Depends(get_db)):
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    since = today - timedelta(days=days - 1)

    paid = db.scalars(select(Order).where(Order.status.in_(PAID_STATUSES), Order.paid_at >= since)).all()

    by_day = {(since + timedelta(days=i)).date().isoformat(): {"orders": 0, "revenue": 0}
              for i in range(days)}
    for o in paid:
        d = by_day[o.paid_at.date().isoformat()]
        d["orders"] += 1
        d["revenue"] += o.total

    today_orders = [o for o in paid if o.paid_at >= today]
    revenue = sum(o.total for o in paid)

    top = db.execute(
        select(OrderItem.name, func.sum(OrderItem.quantity).label("units"),
               func.sum(OrderItem.line_total).label("sales"))
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.status.in_(PAID_STATUSES), Order.paid_at >= since)
        .group_by(OrderItem.dish_id, OrderItem.name).order_by(desc("units")).limit(5)
    ).all()

    live = dict(db.execute(select(Order.status, func.count())
                           .where(Order.status.in_(ACTIVE_STATUSES)).group_by(Order.status)).all())

    return {
        "range_days": days,
        "today": {"orders": len(today_orders), "revenue": sum(o.total for o in today_orders)},
        "range": {
            "orders": len(paid),
            "revenue": revenue,                                  # includes delivery fees
            "food_sales": sum(o.subtotal for o in paid),
            "delivery_fees": sum(o.delivery_fee for o in paid),
            "avg_order_value": round(revenue / len(paid)) if paid else 0,
            "delivery_orders": sum(1 for o in paid if o.order_type == "delivery"),
            "pickup_orders": sum(1 for o in paid if o.order_type == "pickup"),
        },
        "revenue_by_day": [{"date": k, **v} for k, v in by_day.items()],
        "top_dishes": [{"name": n, "units": int(u), "sales": int(s)} for n, u, s in top],
        "kitchen_now": {s: live.get(s, 0) for s in ACTIVE_STATUSES},
        "customers": {
            "total": db.scalar(select(func.count()).select_from(User).where(User.role == "customer")),
            "new_in_range": db.scalar(select(func.count()).select_from(User)
                                      .where(User.role == "customer", User.created_at >= since)),
        },
    }


# ================================================================ websites (must stay LAST)
# "/" is the customer site, "/manage/" is the owner/staff dashboard (both in ../frontend).
# API routes above are matched first, this only catches what is left.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="site")
