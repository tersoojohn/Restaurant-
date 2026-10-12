/* Customer site. Talks to the FastAPI backend on the same origin. No libraries. */
(() => {
  "use strict";

  /* ============================================================ edit these for your restaurant */
  const CONFIG = {
    name: ["Pot", "Plate"],                      // shown as  Pot & Plate
    words: ["home", "Sunday", "celebration", "mama's love"],   // the rotating word in the headline
    intro: "Rice, wings, plantain and more, cooked fresh when you order. Choose each dish the way you like it, pay securely, and we bring it to your door or keep it warm for pickup.",
    phone: "+234 000 000 0000",
    address: "Add your restaurant address in static/js/site.js",
    // 0 = Sunday ... 6 = Saturday. [opens, closes] in 24-hour time, or null when closed.
    hours: { 0: [12, 20], 1: [8, 21], 2: [8, 21], 3: [8, 21], 4: [8, 21], 5: [8, 22], 6: [10, 22] },
  };
  const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  /* ============================================================ helpers */
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const naira = (n) => "\u20A6" + Math.round(Number(n)).toLocaleString("en-NG");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const readJSON = (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } };
  const clock = (iso) => iso ? new Date(String(iso).split(".")[0]).toLocaleTimeString("en-NG", { hour: "numeric", minute: "2-digit", hour12: true }) : "";
  const dayTime = (iso) => iso ? new Date(String(iso).split(".")[0]).toLocaleDateString("en-NG", { day: "numeric", month: "short" }) + ", " + clock(iso) : "";
  const hash = (s) => [...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
  const hourLabel = (h) => `${((h + 11) % 12) + 1} ${h < 12 || h === 24 ? "AM" : "PM"}`;

  const state = {
    token: localStorage.getItem("token"),
    user: readJSON("user"),
    dishes: [],
    favIds: new Set(),
    cart: { items: [], subtotal: 0, ready_in_minutes: 0 },
    server: { delivery_fee: 1000, delivery_minutes: 25 },
    sort: "name",
    query: "",
    qty: {},
    orderType: "delivery",
    address: "",
    pendingAdd: null,
    busy: false,
    authTab: "login",
    ordersTimer: null,
  };

  /* ============================================================ api */
  function errorText(data, status) {
    if (!data) return `Something went wrong (${status}). Please try again.`;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => `${(d.loc || []).slice(-1)[0] ?? ""}: ${String(d.msg).replace(/^Value error, /, "")}`).join(". ");
    }
    return "Something went wrong. Please try again.";
  }

  async function api(path, { method = "GET", body } = {}) {
    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let res;
    try {
      res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    } catch {
      throw new Error("Cannot reach the server. Check your connection.");
    }
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      if (res.status === 401 && state.token) logout(true);
      throw new Error(errorText(data, res.status));
    }
    return data;
  }

  /* ============================================================ small UI pieces */
  let toastTimer;
  function toast(msg, kind = "") {
    const t = $("#toast");
    t.textContent = msg;
    t.className = "toast " + kind;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      t.classList.add("out");
      setTimeout(() => { t.hidden = true; }, 300);
    }, 3200);
  }

  function showBanner(msg, good = false, withOrders = false) {
    const b = $("#banner");
    b.className = "banner" + (good ? " good" : "");
    b.innerHTML = `<span>${esc(msg)}</span><span>${withOrders ? '<button data-act="orders">View my orders</button> ' : ""}<button data-act="dismiss-banner">Dismiss</button></span>`;
    b.hidden = false;
  }

  function tween(el, to, { prefix = "", suffix = "", format = (n) => Math.round(n).toLocaleString("en-NG"), duration = 900 } = {}) {
    const from = Number(el.dataset.v || 0);
    el.dataset.v = to;
    if (reduced || from === to) { el.textContent = prefix + format(to) + suffix; return; }
    const start = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = prefix + format(from + (to - from) * eased) + suffix;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  /* ============================================================ dish art */
  function fallbackPlate(name) {
    const hue = hash(name) % 42;
    const initial = esc(String(name).trim().charAt(0).toUpperCase() || "?");
    return `<svg class="plate" viewBox="0 0 300 300" role="img" aria-label="${esc(name)}"><circle cx="150" cy="150" r="142" fill="#fff9ee"/><circle cx="150" cy="150" r="124" fill="none" stroke="#eadcc4" stroke-width="3"/><circle cx="150" cy="150" r="108" fill="hsl(${hue} 88% 52%)"/><circle cx="150" cy="150" r="108" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="3"/><text x="150" y="190" text-anchor="middle" font-family="Fraunces Variable, Georgia, serif" font-size="120" font-weight="700" fill="#fff">${initial}</text></svg>`;
  }

  function artHTML(d) {
    const url = d.image_url;
    if (!url) return fallbackPlate(d.name);
    const cls = /\.svg(\?|$)/i.test(url) ? "plate" : "photo";
    return `<img class="${cls}" src="${esc(url)}" alt="${esc(d.name)}" loading="lazy" width="300" height="300" data-fallback="${esc(d.name)}">`;
  }

  // if an image fails to load, swap in the generated plate instead of a broken picture
  document.addEventListener("error", (e) => {
    const img = e.target;
    if (img && img.tagName === "IMG" && img.dataset.fallback) {
      img.insertAdjacentHTML("afterend", fallbackPlate(img.dataset.fallback));
      img.remove();
    }
  }, true);

  const BACKDROPS = ["bd-sun", "bd-tomato", "bd-leaf", "bd-berry"];

  /* ============================================================ static page bits */
  function renderStatic() {
    document.title = `${CONFIG.name.join(" & ")}`;
    $$("[data-brand-a]").forEach((e) => (e.textContent = CONFIG.name[0]));
    $$("[data-brand-b]").forEach((e) => (e.textContent = CONFIG.name[1]));
    $("#hero-intro").textContent = CONFIG.intro;
    $("#visit-address").textContent = CONFIG.address;
    $("#visit-phone").textContent = CONFIG.phone;
    const today = new Date().getDay();
    $("#visit-hours").innerHTML = [1, 2, 3, 4, 5, 6, 0].map((d) => {
      const h = CONFIG.hours[d];
      const cls = d === today ? ' class="today"' : "";
      return `<dt${cls}>${DAY_NAMES[d]}</dt><dd${cls}>${h ? `${hourLabel(h[0])} to ${hourLabel(h[1])}` : "Closed"}</dd>`;
    }).join("");
    renderOpenStatus();
  }

  function renderOpenStatus() {
    const now = new Date();
    const h = CONFIG.hours[now.getDay()];
    const hr = now.getHours() + now.getMinutes() / 60;
    const pill = $("#open-pill");
    let text;
    if (h && hr >= h[0] && hr < h[1]) { text = `Open now, until ${hourLabel(h[1])}`; pill.classList.remove("closed"); }
    else {
      pill.classList.add("closed");
      let next = null;
      for (let i = 0; i < 7 && !next; i++) {
        const day = (now.getDay() + i) % 7, dh = CONFIG.hours[day];
        if (dh && (i > 0 || hr < dh[0])) next = { i, open: dh[0], day };
      }
      text = next ? `Closed, opens ${next.i === 0 ? "today" : next.i === 1 ? "tomorrow" : DAY_NAMES[next.day]} at ${hourLabel(next.open)}` : "Closed";
    }
    $("#open-text").textContent = text;
  }

  function startRotator() {
    const wrap = $("#rotator");
    const words = CONFIG.words;
    wrap.querySelector(".rot-word").textContent = words[0] + ".";
    if (reduced || words.length < 2) return;
    let i = 0;
    setInterval(() => {
      i = (i + 1) % words.length;
      const old = wrap.querySelector(".rot-word:last-child");
      const next = document.createElement("span");
      next.className = "rot-word in";
      next.textContent = words[i] + ".";
      wrap.appendChild(next);                  // both words overlap in one grid cell, so the line is never empty
      old.classList.add("out");
      setTimeout(() => old.remove(), 600);
    }, 3000);
  }

  /* ============================================================ menu data */
  async function loadMenu() {
    const [dishes, favs, server] = await Promise.all([
      api("/dishes"),
      api("/dishes/most-ordered?limit=4"),
      api("/config").catch(() => state.server),
    ]);
    state.dishes = dishes;
    state.favIds = new Set(favs.map((d) => d.id));
    state.favs = favs;
    state.server = server;
    renderHero();
    renderTicker();
    renderFacts();
    renderFavs();
    renderMenu();
  }

  function renderHero() {
    const d = state.favs?.[0] || [...state.dishes].sort((a, b) => a.prep_minutes - b.prep_minutes)[0];
    const card = $("#hero-card");
    if (!d) { card.hidden = true; return; }
    const isFav = state.favs?.[0] === d;
    card.hidden = false;
    card.innerHTML = `
      <p class="label">${isFav ? "Most ordered right now" : "Quickest to your table"}</p>
      <h2>${esc(d.name)}</h2>
      <p class="price-line">${naira(d.price)} <small>/ ${esc(d.unit)}</small></p>
      <p class="meta">Ready in about ${d.prep_minutes} min</p>
      <button class="btn btn-sm btn-block" data-act="add" data-id="${d.id}">Add to my order</button>`;
  }

  function renderTicker() {
    const bits = [...state.dishes.map((d) => d.name), "Cooked fresh to order", "Delivery or pickup", "Pay with Paystack"];
    const one = bits.map((b) => `<span>${esc(b)}</span><i></i>`).join("");
    $("#ticker").innerHTML = one + one;
  }

  function renderFacts() {
    const fastest = state.dishes.length ? Math.min(...state.dishes.map((d) => d.prep_minutes)) : 0;
    const facts = [
      [state.dishes.length, "", "dishes on the menu today"],
      [fastest, " min", "for our quickest dish"],
      [state.server.delivery_fee, "", "flat delivery fee", true],
      [state.server.delivery_minutes, " min", "average ride to your door"],
    ];
    $("#facts").innerHTML = facts.map(([n, suf, label, money], i) =>
      `<div class="fact reveal" style="--i:${i}"><strong data-count="${n}" data-money="${money ? 1 : 0}" data-suffix="${suf}">0</strong><span>${label}</span></div>`).join("");
    observe();
  }

  function renderFavs() {
    const sec = $("#favs-section");
    if (!state.favs.length) { sec.hidden = true; return; }
    sec.hidden = false;
    $("#favs").innerHTML = state.favs.map((d, i) => `
      <article class="fav reveal" style="--i:${i}">
        <span class="rank" aria-hidden="true">${i + 1}</span>
        <div class="art" data-art>${artHTML(d)}</div>
        <h3>${esc(d.name)}</h3>
        <p class="price-line">${naira(d.price)} <small>/ ${esc(d.unit)}</small></p>
        <p class="meta">Ordered ${d.times_ordered} time${d.times_ordered === 1 ? "" : "s"} &middot; ready in ${d.prep_minutes} min</p>
        <button class="btn btn-sm btn-sun" data-act="add" data-id="${d.id}">Add to my order</button>
      </article>`).join("");
    observe();
  }

  function visibleDishes() {
    const q = state.query.trim().toLowerCase();
    let list = state.dishes.filter((d) => !q || d.name.toLowerCase().includes(q));
    const by = {
      name: (a, b) => a.name.localeCompare(b.name),
      popular: (a, b) => b.times_ordered - a.times_ordered || a.name.localeCompare(b.name),
      price: (a, b) => a.price - b.price,
      fast: (a, b) => a.prep_minutes - b.prep_minutes,
    }[state.sort];
    return list.sort(by);
  }

  function renderMenu() {
    const list = visibleDishes();
    const box = $("#menu-list");
    if (!list.length) {
      box.innerHTML = `<div class="empty-state"><strong>${state.dishes.length ? "Nothing matches that" : "The menu is being prepared"}</strong>${state.dishes.length ? "Try a different word, or clear the search." : "Please check back in a moment."}</div>`;
      return;
    }
    box.innerHTML = list.map((d, n) => {
      const q = state.qty[d.id] || 1;
      return `
      <article class="card" style="--n:${Math.min(n, 12)}" data-id="${d.id}">
        <div class="stage-art ${BACKDROPS[d.id % BACKDROPS.length]}">
          <div class="tagrow">${state.favIds.has(d.id) ? '<span class="tag">Most ordered</span>' : ""}</div>
          <div class="art" data-art>${artHTML(d)}</div>
        </div>
        <div class="body">
          <div class="row"><h3>${esc(d.name)}</h3><span class="price">${naira(d.price)}<small> / ${esc(d.unit)}</small></span></div>
          <p class="meta"><span class="pill">Ready in about ${d.prep_minutes} min</span></p>
          <div class="buy">
            <div class="stepper"><button data-act="menu-dec" data-id="${d.id}" aria-label="One less">&minus;</button><span aria-live="polite">${q}</span><button data-act="menu-inc" data-id="${d.id}" aria-label="One more">+</button></div>
            <button class="btn btn-sm" data-act="add" data-id="${d.id}">Add</button>
          </div>
        </div>
      </article>`;
    }).join("");
  }

  /* ============================================================ cart */
  const cartCount = () => state.cart.items.reduce((n, l) => n + l.quantity, 0);

  function renderCartBadge(bump = false) {
    const n = cartCount();
    const b = $("#cart-count");
    b.hidden = n === 0;
    b.textContent = n;
    if (bump) { b.classList.remove("bump"); void b.offsetWidth; b.classList.add("bump"); }
  }

  async function loadCart() {
    if (!state.token) { state.cart = { items: [], subtotal: 0, ready_in_minutes: 0 }; renderCartBadge(); renderCart(); return; }
    try { state.cart = await api("/cart"); } catch { /* handled in api() */ }
    renderCartBadge();
    renderCart();
  }

  function renderCart() {
    const body = $("#cart-body");
    if (!state.token) {
      body.innerHTML = `<div class="empty"><strong>Log in to start your order</strong>It only takes a minute.<p style="margin-top:1.2rem"><button class="btn" data-act="login">Log in or sign up</button></p></div>`;
      return;
    }
    const c = state.cart;
    if (!c.items.length) {
      body.innerHTML = `<div class="empty"><strong>Your order is empty</strong>Pick something delicious from the menu.<p style="margin-top:1.2rem"><button class="btn" data-act="close-go-menu">Browse the menu</button></p></div>`;
      return;
    }
    const delivery = state.orderType === "delivery";
    const fee = delivery ? state.server.delivery_fee : 0;
    const total = c.subtotal + fee;
    const blocked = c.items.some((l) => !l.available);
    const dishById = Object.fromEntries(state.dishes.map((d) => [d.id, d]));
    const eta = c.ready_in_minutes + (delivery ? state.server.delivery_minutes : 0);

    body.innerHTML = `
      ${c.items.map((l) => `
        <div class="line">
          <div class="thumb">${artHTML(dishById[l.dish_id] || { name: l.name })}</div>
          <div><h4>${esc(l.name)}</h4><div class="unit">${naira(l.unit_price)} / ${esc(l.unit)}</div></div>
          <div class="total">${naira(l.line_total)}</div>
          <div class="controls">
            <div class="stepper"><button data-act="cart-dec" data-id="${l.dish_id}" aria-label="One less">&minus;</button><span>${l.quantity}</span><button data-act="cart-inc" data-id="${l.dish_id}" aria-label="One more">+</button></div>
            <button class="link" data-act="cart-remove" data-id="${l.dish_id}" data-qty="${l.quantity}">Remove</button>
          </div>
          ${l.available ? "" : '<div class="warn">No longer available. Remove it to continue.</div>'}
        </div>`).join("")}

      <div class="seg" data-on="${state.orderType}" role="group" aria-label="Delivery or pickup">
        <button data-act="type" data-type="delivery" class="${delivery ? "is-on" : ""}">Delivery</button>
        <button data-act="type" data-type="pickup" class="${delivery ? "" : "is-on"}">Pickup</button>
      </div>
      ${delivery ? `<label class="field">Delivery address<textarea id="address" rows="2" placeholder="House number, street, area">${esc(state.address)}</textarea></label>` : ""}

      <div class="eta">${delivery ? "Arrives in about" : "Ready for pickup in about"} ${eta} minutes after payment</div>

      <div class="sum">
        <div><span>Subtotal</span><span>${naira(c.subtotal)}</span></div>
        <div><span>${delivery ? "Delivery fee" : "Pickup"}</span><span>${delivery ? naira(fee) : "Free"}</span></div>
        <div class="grand"><span>Total</span><span id="grand" data-v="${total}">${naira(total)}</span></div>
      </div>
      <button class="btn btn-block" data-act="checkout" ${blocked || state.busy ? "disabled" : ""}>${state.busy ? "Taking you to Paystack..." : `Pay ${naira(total)} with Paystack`}</button>
      <p class="secure">Payments are handled by Paystack. We never see your card details.</p>`;
  }

  async function addToCart(id, qty, sourceEl) {
    if (!state.token) {
      state.pendingAdd = { id, qty };
      showAuth("login", "Log in or create an account to start your order.");
      return;
    }
    const dish = state.dishes.find((d) => d.id === id);
    try {
      state.cart = await api("/cart/items", { method: "POST", body: { dish_id: id, quantity: qty } });
      if (sourceEl) fly(sourceEl);
      renderCartBadge(true);
      renderCart();
      state.qty[id] = 1;
      const stepper = $(`.card[data-id="${id}"] .stepper span`);
      if (stepper) stepper.textContent = "1";
      toast(`${qty} \u00D7 ${dish ? dish.name : "dish"} added to your order`);
    } catch (err) { toast(err.message, "error"); }
  }

  async function changeCart(id, delta, removeAll) {
    try {
      if (delta > 0) state.cart = await api("/cart/items", { method: "POST", body: { dish_id: id, quantity: 1 } });
      else state.cart = await api(`/cart/items/${id}?quantity=${removeAll || 1}`, { method: "DELETE" });
      renderCartBadge(true);
      renderCart();
    } catch (err) { toast(err.message, "error"); }
  }

  // the dish picture flies into the cart button
  function fly(fromEl) {
    if (reduced) return;
    const holder = fromEl.closest(".card, .fav, .hero-card");
    const art = holder && (holder.querySelector("[data-art] img, [data-art] svg") || holder.querySelector(".hero-plate"));
    const target = $("#cart-btn");
    if (!art || !target) return;
    const a = art.getBoundingClientRect(), b = target.getBoundingClientRect();
    const size = Math.min(a.width, 120);
    const clone = art.cloneNode(true);
    Object.assign(clone.style, { position: "fixed", left: `${a.left + a.width / 2 - size / 2}px`, top: `${a.top + a.height / 2 - size / 2}px`, width: `${size}px`, height: `${size}px`, margin: 0, zIndex: 130, pointerEvents: "none", borderRadius: "50%" });
    document.body.appendChild(clone);
    const dx = b.left + b.width / 2 - (a.left + a.width / 2), dy = b.top + b.height / 2 - (a.top + a.height / 2);
    const anim = clone.animate([
      { transform: "translate(0,0) scale(1) rotate(0)", opacity: 1 },
      { transform: `translate(${dx * 0.55}px, ${dy * 0.35 - 80}px) scale(.7) rotate(120deg)`, opacity: 1, offset: 0.5 },
      { transform: `translate(${dx}px, ${dy}px) scale(.1) rotate(300deg)`, opacity: 0.3 },
    ], { duration: 800, easing: "cubic-bezier(.5,0,.25,1)" });
    anim.onfinish = () => clone.remove();
  }

  async function checkout() {
    if (state.busy) return;
    const address = state.address.trim();
    if (state.orderType === "delivery" && !address) {
      toast("Please add your delivery address", "error");
      $("#address")?.focus();
      return;
    }
    state.busy = true;
    renderCart();
    try {
      const order = await api("/checkout", { method: "POST", body: { order_type: state.orderType, address: state.orderType === "delivery" ? address : null } });
      toast("Taking you to Paystack...");
      window.location.href = order.payment_url;       // stay "busy" while the browser leaves
    } catch (err) {
      state.busy = false;
      renderCart();
      toast(err.message, "error");
    }
  }

  /* ============================================================ payment return */
  async function verifyReference(ref) {
    try {
      const order = await api(`/payments/verify/${encodeURIComponent(ref)}`);
      if (["preparing", "ready", "out_for_delivery", "completed"].includes(order.status)) {
        const when = order.order_type === "delivery" ? `arriving around ${clock(order.arrives_at)}` : `ready for pickup around ${clock(order.ready_at)}`;
        showBanner(`Payment received. Order #${order.order_id} is being prepared, ${when}.`, true, true);
      } else if (order.status === "payment_failed") {
        showBanner("That payment did not go through. You have not been charged. Your order is still saved, you can try again.");
      } else {
        showBanner("We are still waiting for confirmation from Paystack. If you were charged, your order will update shortly.", false, true);
      }
    } catch (err) {
      showBanner(`We could not confirm the payment yet (${err.message}). If you were charged it will update shortly, check My orders.`, false, true);
    }
    await loadCart();
  }

  async function handlePaymentReturn() {
    const p = new URLSearchParams(location.search);
    const ref = p.get("reference") || p.get("trxref");
    if (ref) { sessionStorage.setItem("pay_ref", ref); history.replaceState({}, "", location.pathname); }
    const pending = sessionStorage.getItem("pay_ref");
    if (!pending) return;
    if (!state.token) { showAuth("login", "Log in to confirm your payment."); return; }
    sessionStorage.removeItem("pay_ref");
    await verifyReference(pending);
  }

  /* ============================================================ auth */
  function renderAccount() {
    const a = $("#acct");
    if (state.user) {
      const first = esc(String(state.user.name).split(" ")[0]);
      const staff = ["owner", "staff"].includes(state.user.role) ? '<a class="link" href="/manage/">Dashboard</a>' : "";
      a.innerHTML = `<span class="hide-sm">Hi, ${first}</span>${staff}<button class="link" data-act="orders">My orders</button><button class="link" data-act="logout">Log out</button>`;
    } else {
      a.innerHTML = `<button class="link" data-act="login">Log in</button>`;
    }
  }

  function showAuth(tab = "login", note = "") {
    setAuthTab(tab);
    $("#auth-note").textContent = note || "Log in to order, or create an account in under a minute.";
    $("#auth-error").textContent = "";
    $("#auth-modal").hidden = false;
    setTimeout(() => $("#auth-form input:not([hidden])")?.focus(), 50);
  }
  const hideAuth = () => { $("#auth-modal").hidden = true; };

  function setAuthTab(tab) {
    state.authTab = tab;
    $$(".tab").forEach((t) => t.classList.toggle("is-on", t.dataset.tab === tab));
    $$("#auth-form [data-only]").forEach((l) => { l.hidden = l.dataset.only !== tab; });
    $("#auth-submit").textContent = tab === "login" ? "Log in" : "Create my account";
    $("#auth-form [name=password]").autocomplete = tab === "login" ? "current-password" : "new-password";
  }

  async function submitAuth(e) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    const err = $("#auth-error");
    err.textContent = "";
    const btn = $("#auth-submit");
    btn.disabled = true;
    try {
      const reg = state.authTab === "register";
      const r = await api(reg ? "/auth/register" : "/auth/login", { method: "POST", body: reg ? { name: f.name, phone: f.phone, email: f.email, password: f.password } : { email: f.email, password: f.password } });
      state.token = r.token; state.user = r.user;
      localStorage.setItem("token", r.token);
      localStorage.setItem("user", JSON.stringify(r.user));
      hideAuth();
      e.target.reset();
      renderAccount();
      await loadCart();
      toast(reg ? "Welcome! Your account is ready." : `Welcome back, ${r.user.name.split(" ")[0]}`);
      if (state.pendingAdd) { const p = state.pendingAdd; state.pendingAdd = null; await addToCart(p.id, p.qty); }
      await handlePaymentReturn();
    } catch (ex) { err.textContent = ex.message; }
    finally { btn.disabled = false; }
  }

  function logout(expired = false) {
    state.token = null; state.user = null;
    localStorage.removeItem("token"); localStorage.removeItem("user");
    state.cart = { items: [], subtotal: 0, ready_in_minutes: 0 };
    closeDrawers();
    renderAccount(); renderCartBadge(); renderCart();
    toast(expired ? "Your session expired, please log in again." : "You are logged out.");
  }

  /* ============================================================ orders */
  const STATUS = {
    pending_payment: ["Awaiting payment", ""], payment_failed: ["Payment failed", "s-bad"], payment_mismatch: ["Payment issue", "s-bad"],
    preparing: ["Being prepared", ""], ready: ["Ready", "s-good"], out_for_delivery: ["On the way", "s-good"], completed: ["Done", "s-good"], cancelled: ["Cancelled", "s-bad"],
  };

  function trackHTML(o) {
    if (["cancelled", "payment_failed", "payment_mismatch", "pending_payment"].includes(o.status)) return "";
    const steps = o.order_type === "delivery" ? [["preparing", "Preparing"], ["ready", "Ready"], ["out_for_delivery", "On the way"], ["completed", "Delivered"]] : [["preparing", "Preparing"], ["ready", "Ready"], ["completed", "Collected"]];
    const idx = steps.findIndex(([s]) => s === o.status);
    const bars = steps.map((_, i) => `<i class="${o.status === "completed" || i < idx ? "done" : i === idx ? "now" : ""}"></i>`).join("");
    const labels = steps.map(([, l], i) => `<span class="${i <= idx ? "on" : ""}">${l}</span>`).join("");
    return `<div class="track" style="grid-template-columns:repeat(${steps.length},1fr)">${bars}</div><div class="track-labels" style="grid-template-columns:repeat(${steps.length},1fr)">${labels}</div>`;
  }

  async function loadOrders() {
    const body = $("#orders-body");
    try {
      const orders = await api("/orders");
      if (!orders.length) { body.innerHTML = '<div class="empty"><strong>No orders yet</strong>Your orders will show up here.</div>'; return; }
      body.innerHTML = orders.map((o) => {
        const [label, cls] = STATUS[o.status] || [o.status, ""];
        let when = "";
        if (o.status === "preparing" || o.status === "ready") when = o.order_type === "delivery" ? `Arriving around ${clock(o.arrives_at)}` : `Ready for pickup around ${clock(o.ready_at)}`;
        if (o.status === "out_for_delivery") when = `Should arrive around ${clock(o.arrives_at)}`;
        return `<article class="order">
          <div class="order-top"><strong>Order #${o.order_id}</strong><span class="status ${cls}">${label}</span></div>
          <ul>${o.items.map((i) => `<li>${i.quantity} &times; ${esc(i.name)} <span>(${naira(i.line_total)})</span></li>`).join("")}</ul>
          ${trackHTML(o)}
          ${when ? `<p class="when">${when}</p>` : ""}
          <p class="small">${o.order_type === "delivery" ? "Delivery" : "Pickup"} &middot; ${naira(o.total)} &middot; ${dayTime(o.created_at)}</p>
          ${o.status === "payment_failed" ? '<p class="small">You were not charged for this order.</p>' : ""}
          ${o.status === "cancelled" ? '<p class="small">If you paid, your refund is being processed. Contact us if you need help.</p>' : ""}
        </article>`;
      }).join("");
    } catch (err) { body.innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
  }

  function openOrders() {
    if (!state.token) return showAuth("login", "Log in to see your orders.");
    openDrawer("orders-drawer");
    $("#orders-body").innerHTML = '<div class="empty">Loading...</div>';
    loadOrders();
    clearInterval(state.ordersTimer);
    state.ordersTimer = setInterval(loadOrders, 20000);       // live status while the drawer is open
  }

  /* ============================================================ drawers */
  function openDrawer(id) {
    closeDrawers(true);
    $("#overlay").hidden = false;
    const d = $("#" + id);
    d.classList.add("open");
    d.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }
  function closeDrawers(keepOverlay) {
    clearInterval(state.ordersTimer);
    $$(".drawer").forEach((d) => { d.classList.remove("open"); d.setAttribute("aria-hidden", "true"); });
    if (!keepOverlay) { $("#overlay").hidden = true; document.body.style.overflow = ""; }
  }

  /* ============================================================ scroll + pointer effects */
  const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      const el = en.target;
      el.classList.add("in");
      el.querySelectorAll?.("[data-count]").forEach(runCounter);
      if (el.matches("[data-count]")) runCounter(el);
      io.unobserve(el);
    });
  }, { threshold: 0.15 }) : null;

  function runCounter(el) {
    if (el.dataset.done) return;
    el.dataset.done = 1;
    tween(el, Number(el.dataset.count), { suffix: el.dataset.suffix || "", prefix: el.dataset.money === "1" ? "\u20A6" : "", duration: 1100 });
  }

  function observe() {
    $$(".reveal:not(.in)").forEach((el) => (io ? io.observe(el) : (el.classList.add("in"), el.querySelectorAll("[data-count]").forEach(runCounter))));
  }

  function setupEffects() {
    const bar = $("#progress"), top = $("#topbar");
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const max = document.documentElement.scrollHeight - innerHeight;
        bar.style.transform = `scaleX(${max > 0 ? scrollY / max : 0})`;
        top.classList.toggle("scrolled", scrollY > 40);
        ticking = false;
      });
    };
    addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    if (reduced) return;
    const stage = $("#stage");
    $("#hero").addEventListener("pointermove", (e) => {
      const r = stage.getBoundingClientRect();
      stage.style.setProperty("--mx", ((e.clientX - r.left) / r.width - 0.5).toFixed(3));
      stage.style.setProperty("--my", ((e.clientY - r.top) / r.height - 0.5).toFixed(3));
    });

    // 3D tilt on dish cards (mouse only)
    const grid = $("#menu-list");
    grid.addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse") return;
      const card = e.target.closest(".card");
      if (!card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty("--ry", `${(((e.clientX - r.left) / r.width) - 0.5) * 9}deg`);
      card.style.setProperty("--rx", `${-(((e.clientY - r.top) / r.height) - 0.5) * 9}deg`);
    });
    grid.addEventListener("pointerout", (e) => {
      const card = e.target.closest(".card");
      if (card && !card.contains(e.relatedTarget)) { card.style.setProperty("--rx", "0deg"); card.style.setProperty("--ry", "0deg"); }
    });

    // ripple on buttons
    document.addEventListener("pointerdown", (e) => {
      const b = e.target.closest(".btn");
      if (!b || b.disabled) return;
      const r = b.getBoundingClientRect(), size = Math.max(r.width, r.height);
      const s = document.createElement("span");
      s.className = "ripple";
      Object.assign(s.style, { width: `${size}px`, height: `${size}px`, left: `${e.clientX - r.left - size / 2}px`, top: `${e.clientY - r.top - size / 2}px` });
      b.appendChild(s);
      setTimeout(() => s.remove(), 600);
    });
  }

  /* ============================================================ events */
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-act]");
    if (!el) return;
    const id = Number(el.dataset.id);
    switch (el.dataset.act) {
      case "open-cart": openDrawer("cart-drawer"); renderCart(); break;
      case "orders": openOrders(); break;
      case "close": closeDrawers(); break;
      case "close-go-menu": closeDrawers(); location.hash = "#menu"; break;
      case "login": closeDrawers(); showAuth("login"); break;
      case "logout": logout(); break;
      case "close-auth": hideAuth(); state.pendingAdd = null; break;
      case "auth-tab": setAuthTab(el.dataset.tab); $("#auth-error").textContent = ""; break;
      case "dismiss-banner": $("#banner").hidden = true; break;
      case "sort":
        state.sort = el.dataset.sort;
        $$("[data-act=sort]").forEach((c) => c.classList.toggle("is-on", c === el));
        renderMenu();
        break;
      case "menu-inc": case "menu-dec": {
        const next = Math.max(1, Math.min(50, (state.qty[id] || 1) + (el.dataset.act === "menu-inc" ? 1 : -1)));
        state.qty[id] = next;
        el.parentElement.querySelector("span").textContent = next;
        break;
      }
      case "add": addToCart(id, state.qty[id] || 1, el); break;
      case "cart-inc": changeCart(id, 1); break;
      case "cart-dec": changeCart(id, -1); break;
      case "cart-remove": changeCart(id, -1, Number(el.dataset.qty)); break;
      case "type": state.orderType = el.dataset.type; renderCart(); break;
      case "checkout": checkout(); break;
    }
  });

  document.addEventListener("input", (e) => {
    if (e.target.id === "address") state.address = e.target.value;
    if (e.target.id === "search") {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => { state.query = e.target.value; renderMenu(); }, 120);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#auth-modal").hidden) hideAuth(); else closeDrawers();
  });
  $("#auth-form").addEventListener("submit", submitAuth);
  $("#auth-modal").addEventListener("click", (e) => { if (e.target.id === "auth-modal") hideAuth(); });

  /* ============================================================ start */
  async function init() {
    renderStatic();
    renderAccount();
    setupEffects();
    startRotator();
    observe();
    setInterval(renderOpenStatus, 60000);
    try { await loadMenu(); }
    catch (err) { $("#menu-list").innerHTML = `<div class="empty-state"><strong>We could not load the menu</strong>${esc(err.message)}</div>`; }
    if (state.token) {
      try { state.user = await api("/auth/me"); localStorage.setItem("user", JSON.stringify(state.user)); renderAccount(); } catch { /* logged out by api() */ }
      await loadCart();
    } else { renderCart(); }
    await handlePaymentReturn();
  }
  init();
})();
