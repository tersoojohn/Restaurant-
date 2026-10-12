"""Run: pytest -q   (Paystack is mocked, no network needed)"""
import hashlib
import hmac
import json
import os
import tempfile

_db = tempfile.mkstemp(suffix=".db")[1]
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_db}",
    "JWT_SECRET": "test-secret",
    "PAYSTACK_SECRET_KEY": "sk_test_demo",
    "OWNER_EMAIL": "owner@test.com",
    "OWNER_PASSWORD": "owner-pass-123",
})

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

import main


def fake_paystack(method, path, **kw):
    if path.endswith("initialize"):
        return {"authorization_url": "https://checkout.paystack.com/abc"}
    ref = path.split("/")[-1]
    order_total = fake_paystack.amounts[ref]
    return {"status": "success", "amount": order_total, "currency": "NGN", "reference": ref}


fake_paystack.amounts = {}


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client, patch.object(main, "paystack", fake_paystack):
        yield client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def login(c, email, password):
    r = c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def register(c, email, name="Ada"):
    r = c.post("/auth/register", json={"name": name, "email": email, "phone": "08012345678",
                                       "password": "password123"})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def pay(c, order):
    """Simulate Paystack calling our webhook with a valid signature."""
    body = json.dumps({"event": "charge.success", "data": {
        "reference": order["reference"], "status": "success",
        "amount": order["total"] * 100, "currency": "NGN"}}).encode()
    sig = hmac.new(b"sk_test_demo", body, hashlib.sha512).hexdigest()
    return c.post("/payments/webhook", content=body, headers={"x-paystack-signature": sig})


def test_full_flow(c):
    owner = login(c, "owner@test.com", "owner-pass-123")
    cust = register(c, "ada@test.com")

    # --- order: 2 plates rice + 4 wings, delivery
    c.post("/cart/items", json={"dish_id": 1, "quantity": 2}, headers=auth(cust))
    cart = c.post("/cart/items", json={"dish_id": 2, "quantity": 4}, headers=auth(cust)).json()
    assert cart["subtotal"] == 20000 and cart["ready_in_minutes"] == 22

    order = c.post("/checkout", json={"order_type": "delivery", "address": "Rayfield, Jos"},
                   headers=auth(cust)).json()
    assert order["status"] == "pending_payment" and order["total"] == 21000
    fake_paystack.amounts[order["reference"]] = 2100000

    # nothing counted before payment
    assert c.get("/dishes/most-ordered").json() == []
    assert c.get("/admin/dashboard", headers=auth(owner)).json()["today"]["revenue"] == 0

    # --- webhook: bad signature rejected, good one accepted, replay is harmless
    assert c.post("/payments/webhook", content=b"{}", headers={"x-paystack-signature": "x"}).status_code == 401
    assert pay(c, order).status_code == 200
    assert pay(c, order).status_code == 200
    o = c.get(f"/orders/{order['order_id']}", headers=auth(cust)).json()
    assert o["status"] == "preparing"
    assert [d["times_ordered"] for d in c.get("/dishes/most-ordered").json()] == [4, 2]  # counted once
    assert c.get("/cart", headers=auth(cust)).json()["items"] == []

    # --- owner dashboard
    d = c.get("/admin/dashboard", headers=auth(owner)).json()
    assert d["today"] == {"orders": 1, "revenue": 21000}
    assert d["range"]["food_sales"] == 20000 and d["range"]["delivery_fees"] == 1000
    assert d["top_dishes"][0] == {"name": "Chicken Wings", "units": 4, "sales": 10000}
    assert d["kitchen_now"]["preparing"] == 1
    assert d["customers"]["total"] == 1
    cs = c.get("/admin/customers", headers=auth(owner)).json()
    assert cs[0]["email"] == "ada@test.com" and cs[0]["total_spent"] == 21000

    # --- staff runs the kitchen but cannot see money
    r = c.post("/admin/staff", headers=auth(owner), json={
        "name": "Chef", "email": "chef@test.com", "phone": "0800000000", "password": "chefpass123"})
    assert r.status_code == 201
    staff = login(c, "chef@test.com", "chefpass123")
    queue = c.get("/admin/orders", headers=auth(staff)).json()
    assert queue[0]["customer"]["phone"] == "08012345678"
    assert c.get("/admin/dashboard", headers=auth(staff)).status_code == 403
    oid = order["order_id"]
    s = lambda st: c.patch(f"/admin/orders/{oid}/status", json={"status": st}, headers=auth(staff))
    assert s("completed").status_code == 400           # can't skip steps
    assert s("ready").status_code == 200
    assert s("completed").status_code == 400           # delivery must go out first
    assert s("out_for_delivery").status_code == 200
    assert s("completed").status_code == 200
    assert c.get("/admin/orders", headers=auth(staff)).json() == []


def test_access_control(c):
    owner = login(c, "owner@test.com", "owner-pass-123")
    a = register(c, "a@test.com", "Alice")
    b = register(c, "b@test.com", "Bola")

    assert c.get("/cart").status_code == 401                                   # no token
    assert c.get("/cart", headers=auth("garbage")).status_code == 401          # bad token
    assert c.get("/admin/dashboard", headers=auth(a)).status_code == 403       # customer
    assert c.get("/admin/orders", headers=auth(a)).status_code == 403
    assert c.post("/admin/dishes", headers=auth(a),
                  json={"name": "x", "price": 1, "prep_minutes": 1}).status_code == 403
    assert c.post("/admin/staff", headers=auth(a), json={
        "name": "Eve", "email": "e@test.com", "phone": "0800000000", "password": "password123"}).status_code == 403

    # A's order is invisible to B
    c.post("/cart/items", json={"dish_id": 1}, headers=auth(a))
    o = c.post("/checkout", json={"order_type": "pickup"}, headers=auth(a)).json()
    assert c.get(f"/orders/{o['order_id']}", headers=auth(b)).status_code == 404
    assert c.get(f"/orders/{o['order_id']}", headers=auth(owner)).status_code == 200

    # can't register as owner, duplicate email blocked, wrong password blocked
    assert c.post("/auth/register", json={"name": "Zainab", "email": "a@test.com", "phone": "0800000000",
                                          "password": "password123"}).status_code == 409
    assert c.post("/auth/login", json={"email": "a@test.com", "password": "nope"}).status_code == 401

    # delivery needs an address; empty cart blocked
    assert c.post("/checkout", json={"order_type": "delivery"}, headers=auth(b)).status_code == 400

    # unavailable dishes disappear and cannot be added
    c.patch("/admin/dishes/4", json={"available": False}, headers=auth(owner))
    assert 4 not in [d["id"] for d in c.get("/dishes").json()]
    assert c.post("/cart/items", json={"dish_id": 4}, headers=auth(b)).status_code == 400

    # disabling a user kills their existing token immediately
    uid = c.get("/auth/me", headers=auth(b)).json()["id"]
    assert c.patch(f"/admin/users/{uid}", json={"is_active": False}, headers=auth(owner)).status_code == 200
    assert c.get("/auth/me", headers=auth(b)).status_code == 401


def test_amount_mismatch_is_not_paid(c):
    cust = register(c, "m@test.com", "Musa")
    c.post("/cart/items", json={"dish_id": 1}, headers=auth(cust))
    o = c.post("/checkout", json={"order_type": "pickup"}, headers=auth(cust)).json()
    body = json.dumps({"event": "charge.success", "data": {
        "reference": o["reference"], "status": "success", "amount": 100, "currency": "NGN"}}).encode()
    sig = hmac.new(b"sk_test_demo", body, hashlib.sha512).hexdigest()
    c.post("/payments/webhook", content=body, headers={"x-paystack-signature": sig})
    assert c.get(f"/orders/{o['order_id']}", headers=auth(cust)).json()["status"] == "payment_mismatch"


# ---------------------------------------------------------------- websites, photos, user commands

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_websites_are_served_and_api_still_wins(c):
    assert "text/html" in c.get("/").headers["content-type"]
    assert c.get("/manage/").status_code == 200
    for path in ("/css/site.css", "/js/site.js", "/manage/admin.js", "/manage/admin.css",
                 "/img/dishes/hero-plate.svg", "/fonts/fraunces-latin-wght-normal.woff2"):
        assert c.get(path).status_code == 200, path
    assert c.get("/config").json() == {"delivery_fee": 1000, "delivery_minutes": 25}
    # the static mount must never swallow API routes
    assert c.get("/dishes").status_code == 200
    assert c.get("/admin/dashboard").status_code == 401


def test_photo_upload_rules(c):
    owner = login(c, "owner@test.com", "owner-pass-123")
    customer = register(c, "photo@test.com", "Photo Person")

    up = lambda data, name="x.png", tok=owner: c.post(
        "/admin/dishes/1/image", files={"file": (name, data, "image/png")}, headers=auth(tok))

    assert up(PNG, tok=customer).status_code == 403                       # customers cannot upload
    assert up(b"<script>alert(1)</script>", "evil.png").status_code == 400  # real type is checked, not the name
    assert up(PNG + b"0" * (5 * 1024 * 1024)).status_code == 413           # size limit

    first = up(PNG).json()["image_url"]
    assert first.startswith("/uploads/") and c.get(first).status_code == 200
    second = up(PNG).json()["image_url"]
    assert second != first and c.get(first).status_code == 404            # old photo is cleaned up

    # tidy: remove our test file and restore the seeded illustration
    (main.UPLOAD_DIR / second.split("/")[-1]).unlink(missing_ok=True)
    c.patch("/admin/dishes/1", json={"image_url": "/img/dishes/rice.svg"}, headers=auth(owner))


def test_photo_link_validation(c):
    owner = login(c, "owner@test.com", "owner-pass-123")
    dish = {"name": "Link Test", "price": 100, "prep_minutes": 5}
    assert c.post("/admin/dishes", json={**dish, "image_url": "javascript:alert(1)"}, headers=auth(owner)).status_code == 422
    assert c.post("/admin/dishes", json={**dish, "image_url": "https://example.com/a.jpg"}, headers=auth(owner)).status_code == 201
    r = c.post("/admin/dishes", json={**dish, "image_url": "  "}, headers=auth(owner))
    assert r.status_code == 201 and r.json()["image_url"] is None


def test_staff_list_is_owner_only(c):
    owner = login(c, "owner@test.com", "owner-pass-123")
    names = [s["name"] for s in c.get("/admin/staff", headers=auth(owner)).json()]
    assert "Chef" in names
    cust = register(c, "nostaff@test.com", "No Staff")
    assert c.get("/admin/staff", headers=auth(cust)).status_code == 403


def test_manage_commands(c):
    import manage
    from models import SessionLocal

    with SessionLocal() as db:
        manage.create_user(db, name="Second Owner", email="O2@test.com", phone="0800", password="longpassword1", role="owner")
        with pytest.raises(manage.CommandError):
            manage.create_user(db, name="Weak", email="weak@test.com", phone="0800", password="short", role="staff")
        with pytest.raises(manage.CommandError):
            manage.create_user(db, name="Dupe", email="o2@test.com", phone="0800", password="longpassword1", role="staff")
        with pytest.raises(manage.CommandError):
            manage.create_user(db, name="Bad", email="not-an-email", phone="0800", password="longpassword1", role="staff")
    login(c, "o2@test.com", "longpassword1")          # emails are case-insensitive

    with SessionLocal() as db:
        manage.set_active(db, "o2@test.com", False)
        with pytest.raises(manage.CommandError):       # the last active owner can never be locked out
            manage.set_active(db, "owner@test.com", False)
        with pytest.raises(manage.CommandError):
            manage.set_role(db, "owner@test.com", "customer")
        manage.set_active(db, "o2@test.com", True)
        manage.change_password(db, "o2@test.com", "brandnewpass1")
    login(c, "o2@test.com", "brandnewpass1")

    manage.main(["createstaff", "--name", "CLI Chef", "--email", "cli@test.com", "--phone", "0800", "--password", "clipassword1"])
    token = login(c, "cli@test.com", "clipassword1")
    assert c.get("/admin/orders", headers=auth(token)).status_code == 200      # staff can reach the kitchen
    assert c.get("/admin/dashboard", headers=auth(token)).status_code == 403   # but not the money
    manage.main(["listusers", "--role", "owner"])
    with pytest.raises(SystemExit):
        manage.main(["createowner", "--name", "X Y", "--email", "cli@test.com", "--phone", "1", "--password", "longpassword1"])
