#!/usr/bin/env python3
"""Animate the items of the existing banner (assets/banner.jpg) with code only -> assets/anim/hero.svg.

The banner is one flat picture, so each item (ship, island, jars, coins, stars, heart, controller)
is a soft-edged masked copy of that same picture, moved a few pixels with CSS keyframes. Every move
keeps the copy at scale >= 1 and inside a mask with a margin, so the static item underneath never peeks
out. On top: twinkling sparkles, bubbles in the jars, a waterfall shimmer, sea glints and a light sweep.
The picture is embedded once (base64) because GitHub shows README SVGs in an <img> sandbox.

    python3 tools/hero_anim.py                 # write assets/anim/hero.svg
    python3 tools/hero_anim.py --frame 1.25    # paused at t=1.25 s (for preview GIFs)
"""
import base64
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1800, 600

# id: (mask shape, css animation, duration s, delay s, transform-origin x y)
ITEMS = {
    "ship": ("poly:155,92 278,76 310,138 366,184 406,262 410,292 502,288 528,412 466,462 300,476 128,472 22,444 18,392 86,326 98,306 106,222 138,196 146,150",
             "rock", 4.6, 0.0, (290, 440)),
    "island": ("poly:606,236 660,186 722,146 800,132 900,112 996,64 1036,28 1096,52 1104,146 1164,196 1180,282 1156,372 1104,424 1072,506 958,512 876,506 846,524 756,494 696,444 636,404 610,330",
               "float", 6.0, -1.0, (890, 300)),
    "coin1": ("circle:430,162,44", "coin", 2.6, 0.0, (430, 162)),
    "coin2": ("circle:560,322,42", "coin", 2.6, -0.9, (560, 322)),
    "coin3": ("circle:1475,188,43", "coin", 2.6, -1.7, (1475, 188)),
    "star1": ("circle:620,178,46", "twinkle", 2.2, 0.0, (620, 178)),
    "star2": ("circle:1607,175,45", "twinkle", 2.2, -1.1, (1607, 175)),
    "heart": ("circle:513,222,46", "beat", 1.5, 0.0, (513, 224)),
    "pad": ("ellipse:1287,140,94,62", "tilt", 4.4, -0.6, (1287, 140)),
    "jar1": ("rect:1200,236,130,212", "squash", 2.4, 0.0, (1265, 440)),
    "jar2": ("rect:1322,236,102,212", "squash", 2.4, -0.45, (1373, 440)),
    "jar3": ("rect:1414,236,92,212", "squash", 2.4, -0.9, (1460, 440)),
    "jar4": ("rect:1494,236,82,212", "squash", 2.4, -1.35, (1535, 440)),
}

KEYFRAMES = """
@keyframes rock{0%,100%{transform:translateY(0) rotate(-1.3deg) scale(1.035)}50%{transform:translateY(6px) rotate(1.3deg) scale(1.035)}}
@keyframes float{0%,100%{transform:translateY(0) scale(1.02)}50%{transform:translateY(-7px) scale(1.02)}}
@keyframes coin{0%,100%{transform:translateY(0) scale(1.06)}50%{transform:translateY(-7px) scale(1.16)}}
@keyframes twinkle{0%,100%{transform:scale(1.02) rotate(-6deg)}50%{transform:scale(1.22) rotate(8deg)}}
@keyframes beat{0%,60%,100%{transform:scale(1.02)}12%{transform:scale(1.2)}26%{transform:scale(1.06)}40%{transform:scale(1.16)}}
@keyframes tilt{0%,100%{transform:translateY(0) rotate(-4deg) scale(1.07)}50%{transform:translateY(-6px) rotate(4deg) scale(1.07)}}
@keyframes squash{0%,100%{transform:scale(1.01,1.01)}45%{transform:scale(1.0,1.045)}60%{transform:scale(1.03,1.0)}}
@keyframes spark{0%,100%{opacity:0;transform:scale(.2) rotate(0)}50%{opacity:1;transform:scale(1) rotate(90deg)}}
@keyframes rise{0%{opacity:0;transform:translateY(0)}20%{opacity:.9}100%{opacity:0;transform:translateY(-62px)}}
@keyframes fall{from{transform:translateY(-60px)}to{transform:translateY(60px)}}
@keyframes glint{0%,100%{opacity:0}50%{opacity:.75}}
@keyframes sweep{0%,60%{transform:translateX(-500px)}88%,100%{transform:translateX(2300px)}}
@keyframes tw{0%,100%{opacity:.08}50%{opacity:1}}
@keyframes glow{0%,100%{opacity:0;transform:scale(.4) rotate(0)}45%{opacity:1;transform:scale(1.05) rotate(40deg)}60%{opacity:.9;transform:scale(.9) rotate(55deg)}}
@keyframes shoot{0%{opacity:0;transform:translate(0,0)}2%{opacity:1}13%{opacity:0;transform:translate(560px,230px)}100%{opacity:0;transform:translate(560px,230px)}}
"""

# Areas the sky stars must not cover: the items and the sea.
AVOID = [(18, 70, 532, 500), (598, 24, 1184, 530), (1192, 226, 1784, 456), (1186, 72, 1390, 210),
         (380, 112, 476, 212), (510, 274, 610, 372), (1425, 140, 1525, 236), (568, 128, 672, 228),
         (1556, 124, 1660, 226), (462, 172, 566, 274), (0, 470, 1800, 600)]


def sky_points(n, seed, ymax=330):
    """Deterministic star positions in the open sky, away from every item."""
    import random
    rng, pts = random.Random(seed), []
    while len(pts) < n:
        x, y = rng.uniform(10, W - 10), rng.uniform(8, ymax)
        if any(x0 - 8 < x < x1 + 8 and y0 - 8 < y < y1 + 8 for x0, y0, x1, y1 in AVOID):
            continue
        if any((x - px) ** 2 + (y - py) ** 2 < 46 ** 2 for px, py in pts):
            continue
        pts.append((x, y))
    return pts, rng

SPARKS = [(735, 140, 14, 0.0), (876, 90, 12, -0.6), (1012, 118, 11, -1.2), (1172, 150, 13, -0.3),
          (1266, 242, 12, -0.9), (650, 120, 9, -1.5), (1700, 250, 11, -0.4), (360, 140, 10, -1.1), (980, 260, 9, -1.8)]
BUBBLES = [(1255, 410, 5, 1225, 1300), (1290, 400, 4, 1225, 1300), (1365, 405, 5, 1340, 1405), (1455, 410, 4, 1430, 1495),
           (1440, 400, 5, 1430, 1495), (1530, 405, 4, 1505, 1565), (1712, 380, 3, 1700, 1725), (1793, 380, 3, 1782, 1806)]
GLINTS = [(120, 532, 70), (420, 560, 90), (700, 545, 60), (1010, 575, 80), (1300, 540, 70), (1560, 565, 90), (1720, 530, 50)]


def mask_shape(spec: str) -> str:
    kind, args = spec.split(":", 1)
    if kind == "poly":
        return f'<polygon points="{args}"/>'
    v = [float(a) for a in args.split(",")]
    if kind == "circle":
        return f'<circle cx="{v[0]}" cy="{v[1]}" r="{v[2]}"/>'
    if kind == "ellipse":
        return f'<ellipse cx="{v[0]}" cy="{v[1]}" rx="{v[2]}" ry="{v[3]}"/>'
    return f'<rect x="{v[0]}" y="{v[1]}" width="{v[2]}" height="{v[3]}" rx="18"/>'


def anim(name, dur, delay, t, timing="ease-in-out"):
    """CSS animation shorthand; with t set, the animation is paused at time t (for preview frames)."""
    if t is None:
        return f"animation:{name} {dur}s {timing} {delay}s infinite"
    return f"animation:{name} {dur}s {timing} {delay - t}s infinite paused"


def build(t=None) -> str:
    with open(os.path.join(ROOT, "assets", "banner.jpg"), "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    defs = [f'<image id="b" href="data:image/jpeg;base64,{b64}" width="{W}" height="{H}"/>',
            '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="7"/></filter>',
            '<linearGradient id="sh" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
            '<stop offset=".5" stop-color="#fff" stop-opacity=".26"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>',
            '<radialGradient id="halo"><stop offset="0" stop-color="#FFF6D0" stop-opacity=".85"/><stop offset=".35" stop-color="#FFE9A8" stop-opacity=".35"/>'
            '<stop offset="1" stop-color="#FFE9A8" stop-opacity="0"/></radialGradient>',
            '<linearGradient id="tail" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".95"/></linearGradient>',
            '<clipPath id="fallclip"><polygon points="938,338 1052,330 1060,452 1000,476 944,456"/></clipPath>']
    body = ['<use href="#b"/>']
    for iid, (shape, name, dur, delay, (ox, oy)) in ITEMS.items():
        defs.append(f'<mask id="m_{iid}" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">'
                    f'<g fill="#fff" filter="url(#soft)">{mask_shape(shape)}</g></mask>')
        style = f"transform-box:view-box;transform-origin:{ox}px {oy}px;{anim(name, dur, delay, t)}"
        body.append(f'<g style="{style}"><use href="#b" mask="url(#m_{iid})"/></g>')

    # waterfall shimmer: light streaks sliding down inside the falling water
    streaks = "".join(f'<rect x="{x}" y="{y}" width="5" height="{h}" rx="2.5" fill="#fff" opacity=".45"/>'
                      for x, y, h in [(952, 330, 34), (975, 380, 26), (998, 345, 40), (1020, 395, 30), (1040, 350, 28), (965, 430, 24), (1012, 300, 30)])
    body.append(f'<g clip-path="url(#fallclip)"><g style="{anim("fall", 1.4, 0, t, "linear")}">{streaks}</g></g>')

    for x, y, r, *_ in BUBBLES:
        i = BUBBLES.index((x, y, r, *_))
        body.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#fff" style="opacity:0;{anim("rise", 2.6 + (i % 3) * 0.4, -i * 0.55, t, "ease-in")}"/>')

    for x, y, w in GLINTS:
        i = GLINTS.index((x, y, w))
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="3" rx="1.5" fill="#fff" style="opacity:0;{anim("glint", 3.0, -i * 0.7, t)}"/>')

    for x, y, s, delay in SPARKS:
        d = (f"M{x},{y - s} Q{x + s * .16},{y - s * .16} {x + s},{y} Q{x + s * .16},{y + s * .16} {x},{y + s} "
             f"Q{x - s * .16},{y + s * .16} {x - s},{y} Q{x - s * .16},{y - s * .16} {x},{y - s}Z")
        body.append(f'<path d="{d}" fill="#FFF7D1" style="opacity:0;transform-box:fill-box;transform-origin:50% 50%;{anim("spark", 2.4, delay, t)}"/>')

    # twinkling sky: tiny star dots, then bigger glowing four-point stars
    dots, rng = sky_points(64, 11)
    for i, (x, y) in enumerate(dots):
        r = rng.choice([1.6, 2.0, 2.6, 3.2])
        col = rng.choice(["#FFFFFF", "#FFF4C2", "#FFE7F3"])
        body.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{col}" style="opacity:.1;{anim("tw", round(rng.uniform(1.4, 3.4), 2), round(-rng.uniform(0, 3.4), 2), t)}"/>')
    bigs, rng = sky_points(20, 23, ymax=300)
    for x, y in bigs:
        s = rng.choice([10, 13, 16, 20])
        d = (f"M{x:.0f},{y - s:.0f} Q{x + s * .14:.1f},{y - s * .14:.1f} {x + s:.0f},{y:.0f} Q{x + s * .14:.1f},{y + s * .14:.1f} {x:.0f},{y + s:.0f} "
             f"Q{x - s * .14:.1f},{y + s * .14:.1f} {x - s:.0f},{y:.0f} Q{x - s * .14:.1f},{y - s * .14:.1f} {x:.0f},{y - s:.0f}Z")
        st = f"opacity:0;transform-box:fill-box;transform-origin:50% 50%;{anim('glow', round(rng.uniform(2.2, 4.2), 2), round(-rng.uniform(0, 4), 2), t)}"
        body.append(f'<g style="{st}"><circle cx="{x:.0f}" cy="{y:.0f}" r="{s * 2.0:.0f}" fill="url(#halo)"/><path d="{d}" fill="#FFFBE6"/></g>')

    # glints popping on the shiny items
    for x, y, s, delay in [(452, 140, 13, 0.0), (582, 300, 12, -0.8), (1497, 166, 13, -1.6), (640, 158, 12, -0.4),
                           (1627, 155, 12, -1.2), (530, 205, 10, -2.0), (905, 255, 14, -0.9), (1315, 120, 11, -1.4)]:
        d = (f"M{x},{y - s} Q{x + s * .12:.1f},{y - s * .12:.1f} {x + s},{y} Q{x + s * .12:.1f},{y + s * .12:.1f} {x},{y + s} "
             f"Q{x - s * .12:.1f},{y + s * .12:.1f} {x - s},{y} Q{x - s * .12:.1f},{y - s * .12:.1f} {x},{y - s}Z")
        body.append(f'<g style="opacity:0;transform-box:fill-box;transform-origin:50% 50%;{anim("glow", 2.0, delay, t)}">'
                    f'<circle cx="{x}" cy="{y}" r="{s * 1.8:.0f}" fill="url(#halo)"/><path d="{d}" fill="#fff"/></g>')

    # shooting stars: a bright head with a fading tail, now and then
    for x, y, dur, delay in [(140, 26, 7.0, -0.6), (820, 8, 9.0, -4.2), (1180, 30, 11.0, -8.0)]:
        tail = f'<rect x="{x - 150}" y="{y - 1.5}" width="150" height="3" rx="1.5" fill="url(#tail)" transform="rotate(22.3 {x} {y})"/>'
        head = f'<circle cx="{x}" cy="{y}" r="3.2" fill="#fff"/><circle cx="{x}" cy="{y}" r="9" fill="url(#halo)"/>'
        body.append(f'<g style="opacity:0;{anim("shoot", dur, delay, t, "linear")}">{tail}{head}</g>')

    body.append(f'<g style="{anim("sweep", 8.0, -2.0, t)}"><rect x="0" y="-120" width="240" height="{H + 240}" fill="url(#sh)" transform="skewX(-18)"/></g>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="A pirate ship rocking on the waves, a floating ring-puzzle island and juice jars, with spinning coins and twinkling stars">'
            f'<style>{KEYFRAMES}@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}</style>'
            f'<defs>{"".join(defs)}</defs>{"".join(body)}</svg>')


def main() -> None:
    t = float(sys.argv[sys.argv.index("--frame") + 1]) if "--frame" in sys.argv else None
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(ROOT, "assets", "anim", "hero.svg")
    svg = build(t)
    with open(out, "w") as f:
        f.write(svg)
    print(f"{out}: {len(svg) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
