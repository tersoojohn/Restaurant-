/* Back office for owner and staff. Talks to the FastAPI backend on the same origin. No libraries. */
(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const naira = (n) => "\u20A6" + Math.round(Number(n || 0)).toLocaleString("en-NG");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const parse = (iso) => new Date(String(iso).split(".")[0]);
  const clock = (iso) => iso ? parse(iso).toLocaleTimeString("en-NG", { hour: "numeric", minute: "2-digit", hour12: true }) : "";
  const shortDate = (iso) => parse(iso).toLocaleDateString("en-NG", { day: "numeric", month: "short" });
  const minutesFromNow = (iso) => Math.round((parse(iso) - Date.now()) / 60000);

  const state = {
    token: localStorage.getItem("admin_token"),
    user: null,
    view: null,
    range: 7,
    filter: "live",
    live: [],
    seen: null,           // ids of live orders we have already shown (null until first load)
    fresh: new Set(),
    liveTimer: null,
    sound: localStorage.getItem("admin_sound") === "1",
    audio: null,
    customerQuery: "",
  };

  /* ============================================================ api */
  function errorText(data, status) {
    if (!data) return `Something went wrong (${status}).`;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d) => `${(d.loc || []).slice(-1)[0] ?? ""}: ${String(d.msg).replace(/^Value error, /, "")}`).join(". ");
    return "Something went wrong.";
  }

  async function api(path, { method = "GET", body, auth = true } = {}) {
    const headers = {};
    if (auth && state.token) headers.Authorization = `Bearer ${state.token}`;
    let payload;
    if (body instanceof FormData) payload = body;
    else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
    let res;
    try { res = await fetch(path, { method, headers, body: payload }); }
    catch { throw new Error("Cannot reach the server."); }
    let data = null;
    try { data = await res.json(); } catch { /* empty */ }
    if (!res.ok) {
      if (res.status === 401 && auth && state.token) signOut("Your session expired. Please sign in again.");
      throw new Error(errorText(data, res.status));
    }
    return data;
  }

  let toastTimer;
  function toast(msg, kind = "") {
    const t = $("#toast");
    t.textContent = msg; t.className = "toast " + kind; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 3800);
  }

  function tween(el, to, duration = 900) {
    const money = el.dataset.money === "1";
    const fmt = (n) => (money ? naira(n) : Math.round(n).toLocaleString("en-NG"));
    if (reduced) { el.textContent = fmt(to); return; }
    const start = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - start) / duration), e = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(to * e);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  const runCounters = () => $$("[data-count]").forEach((el) => tween(el, Number(el.dataset.count)));
  const settle = (fn) => requestAnimationFrame(() => requestAnimationFrame(fn));

  /* ============================================================ sign in / out */
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    const err = $("#login-error"), btn = $("#login-btn");
    err.textContent = ""; btn.disabled = true;
    try {
      const r = await api("/auth/login", { method: "POST", body: { email: f.email, password: f.password }, auth: false });
      if (!["owner", "staff"].includes(r.user.role)) throw new Error("This account does not have back-office access.");
      state.token = r.token; state.user = r.user;
      localStorage.setItem("admin_token", r.token);
      e.target.reset();
      startApp();
    } catch (ex) { err.textContent = ex.message; }
    finally { btn.disabled = false; }
  });

  function signOut(message) {
    clearInterval(state.liveTimer);
    state.token = null; state.user = null; state.seen = null; state.live = [];
    localStorage.removeItem("admin_token");
    $("#app").hidden = true;
    $("#login-screen").hidden = false;
    if (message) $("#login-error").textContent = message;
  }
  $("#logout").addEventListener("click", () => signOut());

  /* ============================================================ shell */
  const NAV = [
    ["overview", "Overview", ["owner"]],
    ["kitchen", "Kitchen", ["owner", "staff"]],
    ["dishes", "Dishes", ["owner"]],
    ["customers", "Customers", ["owner"]],
    ["team", "Team", ["owner"]],
  ];

  async function startApp() {
    $("#login-screen").hidden = true;
    $("#app").hidden = false;
    $("#me").innerHTML = `${esc(state.user.name)}<small>${esc(state.user.role)}</small>`;
    const items = NAV.filter(([, , roles]) => roles.includes(state.user.role));
    $("#nav").innerHTML = items.map(([id, label]) => `<button data-nav="${id}">${label}${id === "kitchen" ? '<span class="count" id="kcount" hidden>0</span>' : ""}</button>`).join("");
    renderSoundButton();
    state.seen = null;
    clearInterval(state.liveTimer);
    await pollLive();
    state.liveTimer = setInterval(pollLive, 15000);
    go(state.user.role === "owner" ? "overview" : "kitchen");
  }

  const TITLES = { overview: "Overview", kitchen: "Kitchen", dishes: "Dishes", customers: "Customers", team: "Team" };

  function go(view) {
    state.view = view;
    $$("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.nav === view));
    $("#title").textContent = TITLES[view];
    $("#side").classList.remove("open");
    const el = $("#view");
    el.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
    el.style.animation = "none"; void el.offsetWidth; el.style.animation = "";
    VIEWS[view]().catch((err) => { el.innerHTML = `<div class="card empty">${esc(err.message)}</div>`; });
  }

  document.addEventListener("click", (e) => {
    const nav = e.target.closest("[data-nav]");
    if (nav) return go(nav.dataset.nav);
    if (e.target.closest("#menu-btn")) return $("#side").classList.toggle("open");
    const el = e.target.closest("[data-act]");
    if (el) ACTIONS[el.dataset.act]?.(el);
  });

  /* ============================================================ new-order alerts */
  function beep() {
    if (!state.sound) return;
    try {
      state.audio = state.audio || new (window.AudioContext || window.webkitAudioContext)();
      const ctx = state.audio;
      if (ctx.state === "suspended") ctx.resume();
      [[880, 0], [1175, 0.18]].forEach(([freq, at]) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sine"; o.frequency.value = freq;
        g.gain.setValueAtTime(0.0001, ctx.currentTime + at);
        g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + at + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + at + 0.4);
        o.connect(g); g.connect(ctx.destination);
        o.start(ctx.currentTime + at); o.stop(ctx.currentTime + at + 0.45);
      });
    } catch { /* audio not available */ }
  }

  function renderSoundButton() {
    const b = $("#sound");
    b.textContent = `Order alert: ${state.sound ? "on" : "off"}`;
    b.classList.toggle("on", state.sound);
    b.setAttribute("aria-pressed", state.sound);
  }
  $("#sound").addEventListener("click", () => {
    state.sound = !state.sound;
    localStorage.setItem("admin_sound", state.sound ? "1" : "0");
    renderSoundButton();
    if (state.sound) beep();
  });

  async function pollLive() {
    let orders;
    try { orders = await api("/admin/orders"); } catch { return; }
    const ids = new Set(orders.map((o) => o.order_id));
    if (state.seen) {
      const added = orders.filter((o) => !state.seen.has(o.order_id) && o.status === "preparing");
      if (added.length) {
        added.forEach((o) => state.fresh.add(o.order_id));
        beep();
        toast(`New order${added.length > 1 ? "s" : ""}: #${added.map((o) => o.order_id).join(", #")}`);
      }
    }
    state.seen = ids;
    state.live = orders;
    const c = $("#kcount");
    if (c) { c.textContent = orders.length; c.hidden = orders.length === 0; }
    if (state.view === "kitchen" && state.filter === "live") renderLiveBoard();
  }

  /* ============================================================ overview */
  async function overview() {
    const d = await api(`/admin/dashboard?days=${state.range}`);
    const maxRev = Math.max(...d.revenue_by_day.map((x) => x.revenue), 1);
    const peak = d.revenue_by_day.reduce((a, b) => (b.revenue > a.revenue ? b : a), d.revenue_by_day[0]);
    const maxUnits = Math.max(...d.top_dishes.map((x) => x.units), 1);
    const total = d.range.delivery_orders + d.range.pickup_orders;
    const pct = total ? Math.round((d.range.delivery_orders / total) * 100) : 0;
    const every = d.revenue_by_day.length > 14 ? Math.ceil(d.revenue_by_day.length / 8) : 1;

    $("#view").innerHTML = `
      <div class="toolbar">
        ${[7, 14, 30].map((n) => `<button class="chip ${state.range === n ? "on" : ""}" data-act="range" data-n="${n}">Last ${n} days</button>`).join("")}
      </div>

      <div class="kpis">
        <div class="kpi hero" style="--i:0"><div class="label">Revenue today</div><div class="value" data-count="${d.today.revenue}" data-money="1">0</div><div class="sub">${d.today.orders} order${d.today.orders === 1 ? "" : "s"} today</div></div>
        <div class="kpi" style="--i:1"><div class="label">Revenue, last ${d.range_days} days</div><div class="value" data-count="${d.range.revenue}" data-money="1">0</div><div class="sub">${d.range.orders} paid order${d.range.orders === 1 ? "" : "s"}</div></div>
        <div class="kpi" style="--i:2"><div class="label">Average order</div><div class="value" data-count="${d.range.avg_order_value}" data-money="1">0</div><div class="sub">Food ${naira(d.range.food_sales)} + delivery ${naira(d.range.delivery_fees)}</div></div>
        <div class="kpi" style="--i:3"><div class="label">Customers</div><div class="value" data-count="${d.customers.total}">0</div><div class="sub">${d.customers.new_in_range} new in ${d.range_days} days</div></div>
      </div>

      <div class="grid-2">
        <div class="card">
          <h2>Daily revenue <span class="muted num" style="font-size:.85rem;font-weight:600">${d.range.revenue ? `Best day: ${shortDate(peak.date)} (${naira(peak.revenue)})` : "No paid orders yet"}</span></h2>
          <div class="bars">
            ${d.revenue_by_day.map((x, i) => `<div class="bar ${x.revenue === peak.revenue && x.revenue > 0 ? "peak" : ""}" style="--i:${i};--h:${(x.revenue / maxRev) * 100}%"><span class="tip">${shortDate(x.date)}: ${naira(x.revenue)} (${x.orders})</span><div class="fill" data-h="${(x.revenue / maxRev) * 100}"></div></div>`).join("")}
          </div>
          <div class="axis">${d.revenue_by_day.map((x, i) => `<span>${i % every === 0 ? shortDate(x.date) : ""}</span>`).join("")}</div>
        </div>

        <div class="card">
          <h2>In the kitchen now <button class="link" data-nav="kitchen" style="font-size:.85rem;color:var(--blue-700)">Open board</button></h2>
          <div class="now-grid">
            <div class="now"><strong>${d.kitchen_now.preparing}</strong><span>Preparing</span></div>
            <div class="now"><strong>${d.kitchen_now.ready}</strong><span>Ready</span></div>
            <div class="now"><strong>${d.kitchen_now.out_for_delivery}</strong><span>On the way</span></div>
          </div>
          <h2 style="margin-top:1.6rem">Delivery or pickup</h2>
          <div class="split">
            <div class="donut" style="--p:${pct}"></div>
            <div class="legend">
              <div><i></i>Delivery <b>${d.range.delivery_orders}</b></div>
              <div><i class="b"></i>Pickup <b>${d.range.pickup_orders}</b></div>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <h2>Best sellers, last ${d.range_days} days</h2>
        ${d.top_dishes.length ? d.top_dishes.map((x) => `
          <div class="rank-row"><span class="name">${esc(x.name)}</span><span class="meta">${x.units} sold &middot; ${naira(x.sales)}</span><div class="track"><i data-w="${(x.units / maxUnits) * 100}"></i></div></div>`).join("") : '<div class="empty">Sales will show up here after the first paid order.</div>'}
      </div>`;

    runCounters();
    settle(() => {
      $$(".fill").forEach((f) => (f.style.height = f.dataset.h + "%"));
      $$(".track i").forEach((t) => (t.style.width = t.dataset.w + "%"));
    });
  }

  /* ============================================================ kitchen */
  const FILTERS = [["live", "Live orders"], ["completed", "Completed"], ["cancelled", "Cancelled"], ["unpaid", "Awaiting payment"], ["problems", "Payment problems"]];
  const COLS = [["preparing", "Preparing"], ["ready", "Ready"], ["out_for_delivery", "On the way"]];

  async function kitchen() {
    $("#view").innerHTML = `
      <div class="toolbar">${FILTERS.map(([id, l]) => `<button class="chip ${state.filter === id ? "on" : ""}" data-act="filter" data-f="${id}">${l}</button>`).join("")}</div>
      <div id="kbody"><div class="skeleton"></div></div>`;
    if (state.filter === "live") { await pollLive(); renderLiveBoard(); return; }
    const f = state.filter;
    let orders;
    if (f === "problems") orders = [...await api("/admin/orders?status=payment_failed"), ...await api("/admin/orders?status=payment_mismatch")];
    else orders = await api(`/admin/orders?status=${f === "unpaid" ? "pending_payment" : f}`);
    renderHistory(orders);
  }

  function orderCard(o) {
    const due = o.ready_at ? minutesFromNow(o.ready_at) : null;
    const late = o.status === "preparing" && due !== null && due < 0;
    const cls = o.status === "ready" ? "ready" : o.status === "out_for_delivery" ? "go" : late ? "late" : "";
    const when = o.status === "preparing" && due !== null
      ? `<p class="when ${late ? "late" : ""}">${late ? `Overdue by ${-due} min` : `Due in ${due} min`} &middot; ready at ${clock(o.ready_at)}</p>`
      : o.status === "out_for_delivery" ? `<p class="when">Expected at ${clock(o.arrives_at)}</p>` : "";
    const delivery = o.order_type === "delivery";
    let acts = "";
    if (o.status === "preparing") acts = `<button class="btn btn-sm btn-ok" data-act="status" data-id="${o.order_id}" data-to="ready">Mark ready</button>`;
    if (o.status === "ready") acts = delivery
      ? `<button class="btn btn-sm" data-act="status" data-id="${o.order_id}" data-to="out_for_delivery">Send out</button>`
      : `<button class="btn btn-sm btn-ok" data-act="status" data-id="${o.order_id}" data-to="completed">Handed over</button>`;
    if (o.status === "out_for_delivery") acts = `<button class="btn btn-sm btn-ok" data-act="status" data-id="${o.order_id}" data-to="completed">Delivered</button>`;
    if (["preparing", "ready"].includes(o.status)) acts += `<button class="btn btn-sm btn-danger" data-act="status" data-id="${o.order_id}" data-to="cancelled">Cancel</button>`;
    return `
      <article class="ord ${cls} ${state.fresh.has(o.order_id) ? "fresh" : ""}">
        <div class="ord-top"><strong>#${o.order_id}</strong><span class="tag ${delivery ? "" : "amber"}">${delivery ? "Delivery" : "Pickup"}</span></div>
        <p class="who">${esc(o.customer.name)} &middot; <a href="tel:${esc(o.customer.phone)}">${esc(o.customer.phone)}</a></p>
        ${delivery ? `<p class="where">${esc(o.address)}</p>` : ""}
        <ul>${o.items.map((i) => `<li>${i.quantity} &times; ${esc(i.name)} <span>(${esc(i.unit)})</span></li>`).join("")}</ul>
        ${when}
        <p class="where num">${naira(o.total)} paid ${o.paid_at ? "at " + clock(o.paid_at) : ""}</p>
        <div class="acts">${acts}</div>
      </article>`;
  }

  function renderLiveBoard() {
    const body = $("#kbody");
    if (!body) return;
    body.innerHTML = `<div class="board">${COLS.map(([st, label]) => {
      const list = state.live.filter((o) => o.status === st);
      return `<div class="col"><h2>${label} <b>${list.length}</b></h2>${list.length ? list.map(orderCard).join("") : '<div class="none">Nothing here right now</div>'}</div>`;
    }).join("")}</div>`;
    state.fresh.clear();
  }

  const STATUS_TAG = { completed: ["Completed", "green"], cancelled: ["Cancelled", "red"], pending_payment: ["Awaiting payment", "amber"], payment_failed: ["Payment failed", "red"], payment_mismatch: ["Amount mismatch", "red"] };
  function renderHistory(orders) {
    $("#kbody").innerHTML = orders.length ? `<div class="card table-wrap"><table>
      <thead><tr><th>Order</th><th>Customer</th><th>Items</th><th>Total</th><th>Type</th><th>Status</th><th>Paid</th></tr></thead>
      <tbody>${orders.map((o) => { const [l, c] = STATUS_TAG[o.status] || [o.status, ""]; return `<tr>
        <td><strong>#${o.order_id}</strong></td><td>${esc(o.customer.name)}<br><span class="muted">${esc(o.customer.phone)}</span></td>
        <td>${o.items.map((i) => `${i.quantity} &times; ${esc(i.name)}`).join("<br>")}</td>
        <td class="num">${naira(o.total)}</td><td>${o.order_type === "delivery" ? "Delivery" : "Pickup"}</td>
        <td><span class="tag ${c}">${l}</span></td><td class="num">${o.paid_at ? shortDate(o.paid_at) + ", " + clock(o.paid_at) : "-"}</td></tr>`; }).join("")}</tbody></table></div>`
      : '<div class="card empty">Nothing to show here.</div>';
  }

  /* ============================================================ dishes */
  async function dishes() {
    const list = await api("/admin/dishes");
    $("#view").innerHTML = `
      <div class="card">
        <h2>Add a dish</h2>
        <form id="dish-form" class="form-grid">
          <label>Name<input name="name" required placeholder="Jollof Rice"></label>
          <label>Price (Naira)<input name="price" type="number" min="1" required placeholder="4500"></label>
          <label>Sold per<input name="unit" value="plate" required></label>
          <label>Minutes to prepare<input name="prep_minutes" type="number" min="1" required placeholder="15"></label>
          <label>Photo (optional)<input name="photo" type="file" accept="image/jpeg,image/png,image/webp"></label>
          <button class="btn" type="submit">Add dish</button>
        </form>
        <p class="form-error" id="dish-error"></p>
      </div>

      <div class="card table-wrap">
        <h2>Menu <span class="muted" style="font-size:.85rem;font-weight:600">${list.length} dishes &middot; photos are cropped to a circle on the website</span></h2>
        ${list.length ? `<table>
          <thead><tr><th>Photo</th><th>Name</th><th>Price</th><th>Unit</th><th>Prep (min)</th><th>Sold</th><th>On website</th><th></th></tr></thead>
          <tbody>${list.map((d) => `<tr data-row="${d.id}">
            <td><div class="stack">${d.image_url ? `<img class="thumb" src="${esc(d.image_url)}" alt="">` : '<div class="thumb"></div>'}
              <span class="file btn btn-sm btn-ghost">${d.image_url ? "Change" : "Add photo"}<input type="file" data-act-change="photo" data-id="${d.id}" accept="image/jpeg,image/png,image/webp"></span></div></td>
            <td><input class="w-name" data-f="name" value="${esc(d.name)}"></td>
            <td><input data-f="price" type="number" min="1" value="${d.price}"></td>
            <td><input data-f="unit" value="${esc(d.unit)}"></td>
            <td><input data-f="prep_minutes" type="number" min="1" value="${d.prep_minutes}"></td>
            <td class="num">${d.times_ordered}</td>
            <td><button class="chip ${d.available ? "on" : ""}" data-act="toggle-dish" data-id="${d.id}" data-on="${d.available ? 1 : 0}">${d.available ? "Visible" : "Hidden"}</button></td>
            <td><div class="stack"><button class="btn btn-sm" data-act="save-dish" data-id="${d.id}">Save</button>${d.image_url ? `<button class="link" style="font-size:.8rem;color:var(--muted)" data-act="remove-photo" data-id="${d.id}">Remove photo</button>` : ""}</div></td>
          </tr>`).join("")}</tbody></table>` : '<div class="empty">No dishes yet. Add your first one above.</div>'}
      </div>`;

    $("#dish-form").addEventListener("submit", addDish);
    $$("[data-act-change=photo]").forEach((inp) => inp.addEventListener("change", () => uploadPhoto(Number(inp.dataset.id), inp.files[0])));
  }

  function checkPhoto(file) {
    if (!file) return "";
    if (file.size > 5 * 1024 * 1024) return "That photo is over 5 MB. Please use a smaller one.";
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return "Use a JPG, PNG or WebP photo.";
    return "";
  }

  async function addDish(e) {
    e.preventDefault();
    const f = new FormData(e.target), err = $("#dish-error");
    err.textContent = "";
    const photo = f.get("photo");
    const bad = photo && photo.size ? checkPhoto(photo) : "";
    if (bad) { err.textContent = bad; return; }
    try {
      const dish = await api("/admin/dishes", { method: "POST", body: { name: f.get("name"), price: Number(f.get("price")), unit: f.get("unit"), prep_minutes: Number(f.get("prep_minutes")) } });
      if (photo && photo.size) await api(`/admin/dishes/${dish.id}/image`, (() => { const fd = new FormData(); fd.append("file", photo); return { method: "POST", body: fd }; })());
      toast(`${dish.name} added to the menu`);
      dishes();
    } catch (ex) { err.textContent = ex.message; }
  }

  async function uploadPhoto(id, file) {
    const bad = checkPhoto(file);
    if (bad) return toast(bad, "error");
    const fd = new FormData(); fd.append("file", file);
    try { await api(`/admin/dishes/${id}/image`, { method: "POST", body: fd }); toast("Photo updated"); dishes(); }
    catch (ex) { toast(ex.message, "error"); }
  }

  /* ============================================================ customers + team */
  async function customers() {
    const list = await api("/admin/customers");
    const draw = () => {
      const q = state.customerQuery.trim().toLowerCase();
      const rows = list.filter((c) => !q || c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q) || c.phone.includes(q));
      $("#cust-body").innerHTML = rows.length ? `<table>
        <thead><tr><th>Name</th><th>Contact</th><th>Orders</th><th>Total spent</th><th>Joined</th><th>Access</th></tr></thead>
        <tbody>${rows.map((c) => `<tr><td><strong>${esc(c.name)}</strong></td><td>${esc(c.email)}<br><span class="muted">${esc(c.phone)}</span></td>
          <td class="num">${c.orders}</td><td class="num">${naira(c.total_spent)}</td><td>${shortDate(c.joined)}</td>
          <td><button class="chip ${c.is_active ? "on" : ""}" data-act="user-active" data-id="${c.id}" data-on="${c.is_active ? 1 : 0}" data-after="customers">${c.is_active ? "Active" : "Blocked"}</button></td></tr>`).join("")}</tbody></table>` : '<div class="empty">No customers match.</div>';
    };
    $("#view").innerHTML = `<div class="toolbar"><input class="grow" id="cust-search" placeholder="Search name, email or phone" value="${esc(state.customerQuery)}"><span class="muted">${list.length} customers</span></div><div class="card table-wrap" id="cust-body"></div>`;
    $("#cust-search").addEventListener("input", (e) => { state.customerQuery = e.target.value; draw(); });
    draw();
  }

  async function team() {
    const staff = await api("/admin/staff");
    $("#view").innerHTML = `
      <div class="card">
        <h2>Add a kitchen staff account</h2>
        <p class="muted" style="margin:-.4rem 0 1rem">Staff can see the live order board and move orders along. They cannot see sales, customers or prices.</p>
        <form id="staff-form" class="form-grid">
          <label>Full name<input name="name" required></label>
          <label>Email<input name="email" type="email" required></label>
          <label>Phone<input name="phone" required></label>
          <label>Password (8+ characters)<input name="password" type="password" minlength="8" required autocomplete="new-password"></label>
          <button class="btn" type="submit">Create account</button>
        </form>
        <p class="form-error" id="staff-error"></p>
      </div>
      <div class="card table-wrap"><h2>Your staff</h2>
        ${staff.length ? `<table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Access</th></tr></thead><tbody>
          ${staff.map((s) => `<tr><td><strong>${esc(s.name)}</strong></td><td>${esc(s.email)}</td><td>${esc(s.phone)}</td>
          <td><button class="chip ${s.is_active ? "on" : ""}" data-act="user-active" data-id="${s.id}" data-on="${s.is_active ? 1 : 0}" data-after="team">${s.is_active ? "Active" : "Disabled"}</button></td></tr>`).join("")}</tbody></table>` : '<div class="empty">No staff yet.</div>'}
      </div>`;
    $("#staff-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target)), err = $("#staff-error");
      err.textContent = "";
      try { await api("/admin/staff", { method: "POST", body: f }); toast(`${f.name} can now sign in`); team(); }
      catch (ex) { err.textContent = ex.message; }
    });
  }

  /* ============================================================ actions */
  const ACTIONS = {
    range(el) { state.range = Number(el.dataset.n); go("overview"); },
    filter(el) { state.filter = el.dataset.f; kitchen(); },
    async status(el) {
      const to = el.dataset.to;
      if (to === "cancelled" && !confirm("Cancel this order?\n\nThe customer has already paid, so you must refund them from your Paystack dashboard.")) return;
      el.disabled = true;
      try {
        await api(`/admin/orders/${el.dataset.id}/status`, { method: "PATCH", body: { status: to } });
        toast(to === "cancelled" ? "Order cancelled. Remember to refund it in Paystack." : "Order updated");
        await pollLive();
        if (state.view === "kitchen" && state.filter !== "live") kitchen();
      } catch (ex) { toast(ex.message, "error"); el.disabled = false; }
    },
    async "save-dish"(el) {
      const row = $(`[data-row="${el.dataset.id}"]`);
      const body = {};
      $$("[data-f]", row).forEach((i) => { body[i.dataset.f] = i.type === "number" ? Number(i.value) : i.value; });
      try { await api(`/admin/dishes/${el.dataset.id}`, { method: "PATCH", body }); toast("Dish saved"); }
      catch (ex) { toast(ex.message, "error"); }
    },
    async "toggle-dish"(el) {
      try { await api(`/admin/dishes/${el.dataset.id}`, { method: "PATCH", body: { available: el.dataset.on !== "1" } }); dishes(); }
      catch (ex) { toast(ex.message, "error"); }
    },
    async "remove-photo"(el) {
      try { await api(`/admin/dishes/${el.dataset.id}`, { method: "PATCH", body: { image_url: "" } }); toast("Photo removed"); dishes(); }
      catch (ex) { toast(ex.message, "error"); }
    },
    async "user-active"(el) {
      const next = el.dataset.on !== "1";
      if (!next && !confirm("Block this account? They will be signed out immediately.")) return;
      try { await api(`/admin/users/${el.dataset.id}`, { method: "PATCH", body: { is_active: next } }); toast(next ? "Account enabled" : "Account blocked"); (el.dataset.after === "team" ? team : customers)(); }
      catch (ex) { toast(ex.message, "error"); }
    },
  };

  const VIEWS = { overview, kitchen, dishes, customers, team };

  /* ============================================================ start */
  (async function init() {
    if (!state.token) return;
    try {
      state.user = await api("/auth/me");
      if (!["owner", "staff"].includes(state.user.role)) throw new Error("no access");
      startApp();
    } catch { signOut(); }
  })();
})();
