# Restaurant ordering platform

FastAPI backend + two websites it serves itself:

| URL | Who | Look |
|---|---|---|
| `/` | Customers | Red, saffron and green. Menu, cart, Paystack checkout, order tracking |
| `/manage/` | Owner and kitchen staff | Blue. Live kitchen board, sales dashboard, dishes, customers, team 

## 1. First run (5 minutes)

Folder layout:

```
restuarant/
  backend/    Python API (main.py, models.py, auth.py, manage.py, tests)
  frontend/   the two websites (index.html, css/, js/, manage/, fonts/, img/)
  env/        your virtual environment
```

Runs everything **from the backend folder**:


## 2. Users and access levels

There is no separate Django-style admin site. Access is controlled by **role**:

| Role | How it is created | Can do |
|---|---|---|
| **owner** (superuser) | `python manage.py createowner`, or `OWNER_EMAIL` and `OWNER_PASSWORD` in `.env` | Everything: dashboard, dishes, photos, customers, staff accounts |
| **staff** (kitchen) | Owner adds them in **Back office > Team**, or `python manage.py createstaff` | Live order board only. Cannot see sales, customers or prices |
| **customer** | Anyone, from the website sign-up form | Menu, own cart, own orders |

Nobody can make themselves an owner or staff from the website. Only the command line (`manage.py`) and an existing owner can.


## 3. How the website works, step by step

1. **Customer opens `/`.** The page loads the menu from `GET /dishes`, the most ordered dishes from `GET /dishes/most-ordered`, and the delivery fee from `GET /config`.
2. **Adds dishes.** Logged-out visitors are asked to log in first, then their pending dish is added automatically. Each dish is its own cart line with its own price (rice per plate, wings per piece).
3. **Checkout.** `POST /checkout` snapshots the prices into an order with status `pending_payment`, asks Paystack for a payment page (amount in kobo), and returns the Paystack link. The browser goes there.
4. **Payment.** The customer pays on Paystack. Two things then confirm it, and either alone is enough:
   - the browser returns to `/?reference=...` and the site calls `GET /payments/verify/{reference}`
   - Paystack calls `POST /payments/webhook` (signature checked with your secret key)
5. **Order becomes live.** Status turns `preparing`, the ready time and arrival time start counting, dish "times ordered" go up, the cart empties. This happens once even if both confirmations arrive.
6. **Kitchen.** The order appears on the back-office Kitchen board within 15 seconds (with an optional sound). Staff move it: `preparing`, `ready`, `out_for_delivery`, `completed`. The customer sees the same progress under **My orders**.
7. **Owner dashboard.** Revenue, best sellers, delivery vs pickup and customers are calculated from paid orders only.

## 5. Customising the look and text

- Restaurant name, headline words, opening hours, phone, address: top of `frontend/js/site.js` (`CONFIG`).
- Colours: the variables at the top of `frontend/css/site.css` (customer) and `frontend/manage/admin.css` (back office).
- Delivery fee and ride time: `DELIVERY_FEE` and `DELIVERY_MINUTES` in `main.py`.
- Refunds are manual: cancelling a paid order shows a reminder, you refund in the Paystack dashboard.
- Not built yet: password reset, login rate limiting, expiring unpaid orders, rider assignment, automated refunds.
