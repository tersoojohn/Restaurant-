"""
Generates the dish illustrations in ../frontend/img/dishes/*.svg.
Run (from the backend folder):  python make_art.py
These are stand-ins so the site looks finished on day one.
Real photos uploaded from the owner dashboard replace them automatically.
"""
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "img" / "dishes"
OUT.mkdir(parents=True, exist_ok=True)

C = 300  # centre of the 600x600 canvas


# ------------------------------------------------------------------ helpers
def f(x):
    return f"{x:.1f}"


def scatter(rng, cx, cy, radius, n, make):
    """n items spread inside a circle, nearer the middle more often."""
    parts = []
    for _ in range(n):
        a = rng.random() * math.tau
        r = radius * math.sqrt(rng.random())
        parts.append(make(cx + r * math.cos(a), cy + r * math.sin(a), rng))
    return "".join(parts)


def defs_common():
    return """
<defs>
  <filter id="drop" x="-30%" y="-30%" width="160%" height="170%">
    <feDropShadow dx="0" dy="14" stdDeviation="14" flood-color="#2a0a05" flood-opacity=".35"/>
  </filter>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="170%">
    <feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#2a0a05" flood-opacity=".32"/>
  </filter>
  <filter id="tiny" x="-30%" y="-30%" width="160%" height="170%">
    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#2a0a05" flood-opacity=".35"/>
  </filter>
  <radialGradient id="plateFace" cx="40%" cy="35%" r="75%">
    <stop offset="0" stop-color="#ffffff"/><stop offset=".7" stop-color="#f6efe3"/><stop offset="1" stop-color="#e8dcc7"/>
  </radialGradient>
  <radialGradient id="plateWell" cx="42%" cy="38%" r="70%">
    <stop offset="0" stop-color="#fffdf8"/><stop offset="1" stop-color="#eadfca"/>
  </radialGradient>
  <radialGradient id="jollofG" cx="38%" cy="32%" r="80%">
    <stop offset="0" stop-color="#f26a2a"/><stop offset=".55" stop-color="#d9401a"/><stop offset="1" stop-color="#a22410"/>
  </radialGradient>
  <radialGradient id="riceG" cx="38%" cy="32%" r="80%">
    <stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#f7f1e4"/><stop offset="1" stop-color="#ddd0b8"/>
  </radialGradient>
  <radialGradient id="stewG" cx="40%" cy="35%" r="75%">
    <stop offset="0" stop-color="#e2381f"/><stop offset="1" stop-color="#8f1608"/>
  </radialGradient>
  <linearGradient id="wingG" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#f0a53a"/><stop offset=".5" stop-color="#cf7421"/><stop offset="1" stop-color="#8f4012"/>
  </linearGradient>
  <radialGradient id="plantG" cx="45%" cy="42%" r="62%">
    <stop offset="0" stop-color="#ffe68e"/><stop offset=".55" stop-color="#f6bf3a"/><stop offset=".86" stop-color="#cf8420"/><stop offset="1" stop-color="#6f3510"/>
  </radialGradient>
  <radialGradient id="tomG" cx="40%" cy="35%" r="70%">
    <stop offset="0" stop-color="#ff6a52"/><stop offset="1" stop-color="#c91f17"/>
  </radialGradient>
  <radialGradient id="gloss" cx="35%" cy="28%" r="45%">
    <stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="shade" cx="62%" cy="68%" r="65%">
    <stop offset=".45" stop-color="#2a0a05" stop-opacity="0"/><stop offset="1" stop-color="#2a0a05" stop-opacity=".38"/>
  </radialGradient>
</defs>"""


def plate(cx=C, cy=C, r=262):
    return f"""
<g filter="url(#drop)">
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#plateFace)"/>
</g>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#d9c9ae" stroke-width="2"/>
<circle cx="{cx}" cy="{cy}" r="{r - 20}" fill="none" stroke="#fff" stroke-width="3" opacity=".9"/>
<circle cx="{cx}" cy="{cy}" r="{r * 0.78:.0f}" fill="url(#plateWell)" stroke="#e0d2b8" stroke-width="2"/>
<circle cx="{cx}" cy="{cy}" r="{r * 0.78 - 5:.0f}" fill="none" stroke="#fff" stroke-width="2" opacity=".8"/>
"""


# ------------------------------------------------------------------ food pieces
def grain(x, y, rng, palette, big=False):
    rx = rng.uniform(5.5, 8) if big else rng.uniform(4, 6)
    ry = rng.uniform(2.1, 3.1) if big else rng.uniform(1.6, 2.4)
    return (f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(rx)}" ry="{f(ry)}" '
            f'transform="rotate({rng.randint(0, 179)} {f(x)} {f(y)})" fill="{rng.choice(palette)}"/>')


def mound(rng, cx, cy, r, base, palette, n, shine=True):
    g = f'<g filter="url(#soft)"><circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{base})"/></g>'
    g += f'<clipPath id="mc{cx}{cy}{r}"><circle cx="{cx}" cy="{cy}" r="{r - 1}"/></clipPath>'
    g += f'<g clip-path="url(#mc{cx}{cy}{r})">'
    g += scatter(rng, cx, cy, r, n, lambda x, y, rg: grain(x, y, rg, palette))
    g += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#shade)"/>'
    if shine:
        g += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#gloss)"/>'
    g += "</g>"
    return g


def jollof(rng, cx, cy, r):
    palette = ["#f58a3a", "#e8541f", "#d1401a", "#f9b25a", "#b9300f", "#ee6a2a", "#fcd27f"]
    out = mound(rng, cx, cy, r, "jollofG", palette, int(r * 9))
    # little pieces of pepper and onion in the rice
    for _ in range(int(r / 6)):
        a = rng.random() * math.tau
        d = r * math.sqrt(rng.random()) * .85
        x, y = cx + d * math.cos(a), cy + d * math.sin(a)
        col = rng.choice(["#2f7d32", "#c3281a", "#f4e0b0", "#3d8c40"])
        out += f'<rect x="{f(x)}" y="{f(y)}" width="{f(rng.uniform(5, 9))}" height="{f(rng.uniform(3, 5))}" rx="1.5" transform="rotate({rng.randint(0, 179)} {f(x)} {f(y)})" fill="{col}" opacity=".9"/>'
    return out


def white_rice(rng, cx, cy, r):
    palette = ["#ffffff", "#fbf7ee", "#f1e8d6", "#ffffff", "#e9dcc2"]
    return mound(rng, cx, cy, r, "riceG", palette, int(r * 11))


def stew_pool(rng, cx, cy, r):
    out = f'<g filter="url(#soft)"><ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * .8:.0f}" fill="url(#stewG)"/></g>'
    out += f'<ellipse cx="{f(cx - r * .25)}" cy="{f(cy - r * .3)}" rx="{f(r * .45)}" ry="{f(r * .2)}" fill="#fff" opacity=".22"/>'
    out += scatter(rng, cx, cy, r * .7, 14, lambda x, y, rg: f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(rg.uniform(2, 5))}" fill="{rg.choice(["#f3a33a", "#6a0d05", "#fbd37b"])}" opacity=".65"/>')
    return out


def wing(rng, x, y, rot, scale=1.0, glaze="#b6260f"):
    """One chicken wing, drawn at origin pointing right, then moved/rotated."""
    body = ("M -46 0 C -48 -32 -12 -38 20 -24 C 40 -15 56 -7 70 -6 L 70 6 "
            "C 56 7 40 15 20 24 C -12 38 -48 32 -46 0 Z")
    parts = [f'<g transform="translate({f(x)} {f(y)}) rotate({rot}) scale({scale})">']
    parts.append('<g filter="url(#soft)">')
    parts.append(f'<path d="{body}" fill="url(#wingG)"/>')
    parts.append("</g>")
    parts.append(f'<path d="{body}" fill="{glaze}" opacity=".26"/>')
    # crisp skin texture
    parts.append(scatter(rng, -8, 0, 34, 26, lambda px, py, rg: f'<ellipse cx="{f(px)}" cy="{f(py)}" rx="{f(rg.uniform(2, 5))}" ry="{f(rg.uniform(1.2, 2.5))}" transform="rotate({rg.randint(0, 179)} {f(px)} {f(py)})" fill="{rg.choice(["#5e2a0d", "#f6c36a", "#7a3612", "#ffd88a"])}" opacity=".55"/>'))
    # shine
    parts.append('<ellipse cx="-14" cy="-13" rx="26" ry="8" fill="#fff" opacity=".28" transform="rotate(-12 -14 -13)"/>')
    # bone end
    parts.append('<g filter="url(#tiny)"><circle cx="77" cy="-7" r="7.5" fill="#fbf3e2"/><circle cx="77" cy="7" r="7.5" fill="#f4e8cf"/></g>')
    parts.append("</g>")
    return "".join(parts)


def plantain_slice(rng, x, y, rot, rx=34, ry=21):
    out = f'<g transform="translate({f(x)} {f(y)}) rotate({rot})">'
    out += f'<g filter="url(#soft)"><ellipse rx="{rx}" ry="{ry}" fill="url(#plantG)"/></g>'
    out += scatter(rng, 0, 0, rx * .6, 7, lambda px, py, rg: f'<circle cx="{f(px)}" cy="{f(py * .6)}" r="{f(rg.uniform(1, 2.4))}" fill="#7a3d10" opacity=".55"/>')
    out += f'<ellipse cx="{f(-rx * .3)}" cy="{f(-ry * .3)}" rx="{f(rx * .42)}" ry="{f(ry * .22)}" fill="#fff" opacity=".35"/>'
    out += "</g>"
    return out


def tomato_slice(rng, x, y, r=26):
    out = f'<g transform="translate({f(x)} {f(y)}) rotate({rng.randint(0, 359)})">'
    out += f'<g filter="url(#soft)"><circle r="{r}" fill="url(#tomG)"/></g>'
    out += f'<circle r="{r - 5}" fill="none" stroke="#ff9d86" stroke-width="2" opacity=".7"/>'
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        px, py = (r * .5) * math.cos(a), (r * .5) * math.sin(a)
        out += f'<ellipse cx="{f(px)}" cy="{f(py)}" rx="{f(r * .22)}" ry="{f(r * .14)}" transform="rotate({int(math.degrees(a))} {f(px)} {f(py)})" fill="#ffd1c4" opacity=".85"/>'
        out += f'<circle cx="{f(px)}" cy="{f(py)}" r="1.8" fill="#f6e08a"/>'
    out += f'<circle r="{r * .15:.1f}" fill="#ffe3da" opacity=".8"/>'
    out += "</g>"
    return out


def cucumber_slice(rng, x, y, r=22):
    out = f'<g transform="translate({f(x)} {f(y)})"><g filter="url(#soft)"><circle r="{r}" fill="#2f7a3a"/></g>'
    out += f'<circle r="{r - 3.5}" fill="#cfe8a8"/><circle r="{r - 8}" fill="#e6f3c8"/>'
    for i in range(6):
        a = i * math.tau / 6
        out += f'<ellipse cx="{f((r - 11) * math.cos(a))}" cy="{f((r - 11) * math.sin(a))}" rx="2.6" ry="1.4" transform="rotate({int(math.degrees(a))} {f((r - 11) * math.cos(a))} {f((r - 11) * math.sin(a))})" fill="#a9cf78"/>'
    out += "</g>"
    return out


def onion_ring(x, y, r=24, rot=0):
    return (f'<g transform="translate({f(x)} {f(y)}) rotate({rot})" filter="url(#tiny)">'
            f'<circle r="{r}" fill="none" stroke="#e9c7e0" stroke-width="5"/>'
            f'<circle r="{r - 8}" fill="none" stroke="#f6e4f1" stroke-width="3"/>'
            f'<circle r="{r + 3}" fill="none" stroke="#c78fb5" stroke-width="1.5" opacity=".7"/></g>')


def leaf(x, y, rot, s=1.0, col="#2e8b4a"):
    return (f'<g transform="translate({f(x)} {f(y)}) rotate({rot}) scale({s})" filter="url(#tiny)">'
            f'<path d="M0 0 C 12 -16 30 -16 42 0 C 30 16 12 16 0 0 Z" fill="{col}"/>'
            f'<path d="M2 0 L 38 0" stroke="#bfe5b2" stroke-width="1.6" opacity=".8"/></g>')


def chili(x, y, rot, s=1.0):
    return (f'<g transform="translate({f(x)} {f(y)}) rotate({rot}) scale({s})" filter="url(#soft)">'
            '<path d="M0 0 C 30 -14 70 -10 92 8 C 70 4 36 8 6 14 C -4 12 -6 4 0 0 Z" fill="#d6221a"/>'
            '<path d="M6 -2 C 30 -10 60 -9 80 3" stroke="#ff7a62" stroke-width="3" fill="none" opacity=".7"/>'
            '<path d="M0 0 C -8 -6 -14 -8 -20 -4 C -14 -2 -8 2 0 6 Z" fill="#2f7d32"/></g>')


def dip_bowl(x, y, r=46, col="#8a1c10"):
    return (f'<g filter="url(#soft)"><circle cx="{x}" cy="{y}" r="{r}" fill="#fffaf0" stroke="#e3d3b8" stroke-width="2"/></g>'
            f'<circle cx="{x}" cy="{y}" r="{r - 9}" fill="{col}"/>'
            f'<ellipse cx="{x - 10}" cy="{y - 12}" rx="{r * .4:.0f}" ry="{r * .16:.0f}" fill="#fff" opacity=".28"/>')


def sesame(rng, cx, cy, r, n):
    return scatter(rng, cx, cy, r, n, lambda x, y, rg: f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="2.2" ry="1.2" transform="rotate({rg.randint(0, 179)} {f(x)} {f(y)})" fill="#fff4d6"/>')


def zoom(body, s):
    """Scale the food (not the plate) about the plate centre so dishes fill the plate."""
    return f'<g transform="translate({C} {C}) scale({s}) translate({-C} {-C})">{body}</g>'


def wrap(body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" role="img" aria-label="{title}">'
            f'{defs_common()}{body}</svg>')


# ------------------------------------------------------------------ dishes
def make_rice():
    rng = random.Random(11)
    b = plate()
    food = ""
    food += stew_pool(rng, 372, 352, 92)
    food += white_rice(rng, 262, 288, 118)
    food += tomato_slice(rng, 426, 214, 24) + tomato_slice(rng, 440, 270, 20)
    food += leaf(190, 400, 140) + leaf(210, 420, 110, .8)
    return wrap(b + zoom(food, 1.16), "Rice and stew")


def make_jollof():
    rng = random.Random(7)
    b = plate()
    food = ""
    food += jollof(rng, 285, 290, 128)
    for i, (x, y, rot) in enumerate([(430, 392, -25), (468, 340, 10), (440, 440, -50)]):
        food += plantain_slice(rng, x, y, rot, 36, 22)
    food += tomato_slice(rng, 170, 208, 25) + onion_ring(158, 262, 22, 20) + onion_ring(188, 250, 18, -10)
    food += cucumber_slice(rng, 205, 175, 22)
    food += leaf(380, 160, -30) + leaf(350, 140, -60, .8)
    return wrap(b + zoom(food, 1.12), "Jollof rice")


def make_wings():
    rng = random.Random(23)
    b = plate()
    food = ""
    spots = [(230, 250, -35), (320, 232, 15), (200, 340, 190), (300, 330, 205), (390, 300, 50), (268, 410, 160)]
    for x, y, rot in spots:
        food += wing(rng, x, y, rot, 1.05)
    food += sesame(rng, 290, 310, 150, 70)
    food += dip_bowl(420, 418, 44)
    food += chili(165, 430, -25, .8) + leaf(410, 175, -20) + leaf(388, 158, -50, .8)
    return wrap(b + zoom(food, 1.1), "Chicken wings")


def make_plantain():
    rng = random.Random(5)
    b = plate()
    food = ""
    pos = []
    for row in range(3):
        for i in range(4):
            pos.append((190 + i * 62 + row * 12, 220 + row * 68, rng.randint(-30, 30)))
    for x, y, rot in pos:
        food += plantain_slice(rng, x, y, rot, 38, 24)
    food += dip_bowl(412, 420, 38, "#c0270f")
    food += leaf(170, 410, 150) + leaf(190, 432, 120, .8)
    return wrap(b + zoom(food, 1.12), "Fried plantain")


def make_hero():
    """Big composite used in the hero: a loaded plate."""
    rng = random.Random(41)
    b = plate(C, C, 270)
    food = ""
    food += jollof(rng, 255, 300, 120)
    for x, y, rot in [(402, 214, -30), (452, 292, 20), (404, 372, 160)]:
        food += wing(rng, x, y, rot, 1.0)
    food += sesame(rng, 430, 292, 70, 30)
    for i, (x, y, rot) in enumerate([(210, 440, -20), (275, 462, 15), (340, 450, -10)]):
        food += plantain_slice(rng, x, y, rot, 36, 22)
    food += tomato_slice(rng, 160, 190, 26) + onion_ring(150, 246, 22, 20) + cucumber_slice(rng, 200, 160, 20)
    food += leaf(340, 130, -30) + leaf(318, 112, -60, .8)
    return wrap(b + zoom(food, 1.04), "A plate of jollof rice, chicken wings and fried plantain")


def make_garnishes():
    """Pieces that float around the hero plate."""
    rng = random.Random(2)
    pieces = {
        "chili": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-30 -30 150 80">{defs_common()}{chili(0, 0, 0, 1)}</svg>',
        "tomato": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80">{defs_common()}{tomato_slice(rng, 40, 40, 30)}</svg>',
        "leaf": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-5 -25 60 50">{defs_common()}{leaf(0, 0, 0, 1.1)}</svg>',
        "plantain": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 70">{defs_common()}{plantain_slice(rng, 50, 35, -15, 38, 24)}</svg>',
    }
    return pieces


if __name__ == "__main__":
    files = {
        "rice.svg": make_rice(), "jollof.svg": make_jollof(), "wings.svg": make_wings(),
        "plantain.svg": make_plantain(), "hero-plate.svg": make_hero(),
    }
    for name, svg in make_garnishes().items():
        files[f"bit-{name}.svg"] = svg
    for name, svg in files.items():
        (OUT / name).write_text(svg)
        print("wrote", name, len(svg) // 1024, "KB")
