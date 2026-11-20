#!/usr/bin/env python3
"""Sea Battle: a community battleship game that lives in the profile README.

Visitors click a water tile, which opens an issue titled ``seabattle|fire|B4``.
The workflow in .github/workflows/seabattle.yml then runs:

    python3 seabattle/game.py apply    # read every open move issue, update state.json and README.md
    (commit + push)
    python3 seabattle/game.py notify   # comment on and close the issues that were handled

The enemy fleet is never stored in the repo: its layout is derived from the
SEABATTLE_SECRET Actions secret and the game number, so reading state.json
or the git history cannot reveal where the ships are.

Local use:  python3 seabattle/game.py render              (re-render README from state.json)
            python3 seabattle/game.py apply --issues f.json --out out.json   (offline test)
Standard library only.
"""
import hashlib
import hmac
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "seabattle", "state.json")
README = os.path.join(ROOT, "README.md")
START, END = "<!-- SEABATTLE:START -->", "<!-- SEABATTLE:END -->"

COLS = "ABCDEFGH"
ROWS = range(1, 9)
CELLS = [f"{c}{r}" for r in ROWS for c in COLS]
# id, emoji, name, size  (the two bosses are from Sea Survival)
SHIPS = [
    ("kraken", "🐙", "Kraken Titan", 4),
    ("dragon", "🐉", "Elder Sea Dragon", 3),
    ("ghost", "👻", "Ghost Galleon", 3),
    ("sloop", "🏴‍☠️", "Pirate Sloop", 2),
    ("gunboat", "🚤", "Iron Gunboat", 2),
]
SHIP = {s[0]: s for s in SHIPS}
MOVE = re.compile(r"^\s*seabattle\s*\|\s*fire\s*\|\s*([A-Ha-h])\s*([1-8])\s*$")
LOGIN = re.compile(r"^[A-Za-z0-9-]{1,39}(\[bot\])?$")
TILE_W = 44


# ---------------------------------------------------------------- fleet

def fleet(secret: str, game: int) -> dict:
    """ship id -> list of cells, deterministic for (secret, game). Ships never touch, not even diagonally."""
    seed = hmac.new(secret.encode(), f"seabattle-game-{game}".encode(), hashlib.sha256).digest()
    rng = random.Random(int.from_bytes(seed, "big"))
    for strict in (True, False):
        for _ in range(500):
            taken, layout, ok = set(), {}, True
            for sid, _, _, size in SHIPS:
                spots = []
                for horiz in (True, False):
                    for r in range(8 - (0 if horiz else size - 1)):
                        for c in range(8 - (size - 1 if horiz else 0)):
                            cells = [(r, c + i) if horiz else (r + i, c) for i in range(size)]
                            zone = {(y + dy, x + dx) for y, x in cells for dy in (-1, 0, 1) for dx in (-1, 0, 1)} if strict else set(cells)
                            if not zone & taken:
                                spots.append(cells)
                if not spots:
                    ok = False
                    break
                cells = rng.choice(spots)
                taken |= set(cells)
                layout[sid] = [f"{COLS[c]}{r + 1}" for r, c in cells]
            if ok:
                return layout
    raise RuntimeError("could not place the fleet")


# ---------------------------------------------------------------- state

def board_url() -> str:
    owner = (os.environ.get("REPO") or "NguyenHuyHoangBeng/NguyenHuyHoangBeng").split("/")[0]
    return f"https://github.com/{owner}#-sea-battle-sink-the-kraken-fleet"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def new_state() -> dict:
    return {"game": 1, "started": now()[:10], "shots": {}, "sunk": {}, "log": [],
            "captains": {}, "hall_of_fame": [], "processed": []}


def load() -> dict:
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return new_state()


def save(state: dict) -> None:
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
        f.write("\n")


def captain(state, login):
    return state["captains"].setdefault(login, {"shots": 0, "hits": 0, "sinks": 0, "wins": 0})


def fire(state: dict, layout: dict, cell: str, login: str) -> str:
    """Apply one shot, return the reply for the issue (markdown)."""
    game = state["game"]
    if cell in state["shots"]:
        prev = state["shots"][cell]
        return (f"🌊 **{cell}** was already hit by **{prev['by']}** in game #{game}, so no shot was fired.\n\n"
                f"Pick a fresh water tile on the [board]({board_url()}) and try again!")
    me = captain(state, login)
    me["shots"] += 1
    owner = next((sid for sid, cells in layout.items() if cell in cells), None)
    entry = {"game": game, "cell": cell, "by": login, "at": now()}
    if owner is None:
        state["shots"][cell] = {"result": "miss", "by": login}
        entry["result"] = "miss"
        state["log"].append(entry)
        reply = f"🌊 **Splash!** Your cannonball hit only water at **{cell}**. The enemy fleet is still out there..."
    else:
        me["hits"] += 1
        state["shots"][cell] = {"result": "hit", "by": login}
        entry["result"] = "hit"
        cells = layout[owner]
        if all(c in state["shots"] for c in cells):
            _, emoji, name, _ = SHIP[owner]
            me["sinks"] += 1
            state["sunk"][owner] = cells
            entry["result"] = "sunk"
            entry["ship"] = owner
            reply = f"💥 **DIRECT HIT at {cell}... and it's going down!** You sank the {emoji} **{name}**!"
        else:
            reply = f"💥 **HIT!** Your cannonball struck an enemy ship at **{cell}**. It's burning, finish it off!"
        state["log"].append(entry)
    state["log"] = state["log"][-30:]
    if len(state["sunk"]) == len(SHIPS):
        me["wins"] += 1
        shots = len(state["shots"])
        state["hall_of_fame"].append({"game": game, "winner": login, "shots": shots, "date": now()[:10]})
        reply += (f"\n\n🏆 **That was the last ship: you won game #{game}!** The whole fleet went down in {shots} shots. "
                  f"A new enemy fleet has already appeared for game #{game + 1}.")
        state.update(game=game + 1, started=now()[:10], shots={}, sunk={})
    return reply


# ---------------------------------------------------------------- README

def issue_url(repo: str, cell: str) -> str:
    title = f"seabattle|fire|{cell}"
    body = (f"⚓ Ready to fire at **{cell}**!\n\n"
            "Just press **Create** below, you don't need to type anything. "
            "The Sea Battle bot fires your cannon, updates the board on the profile and replies here in about a minute.")
    return f"https://github.com/{repo}/issues/new?" + urllib.parse.urlencode({"title": title, "body": body}, quote_via=urllib.parse.quote)


def who(login: str) -> str:
    return f"[{login}](https://github.com/{login})" if LOGIN.match(login) else login


def render(state: dict, repo: str) -> str:
    sunk_cells = {c for cells in state["sunk"].values() for c in cells}
    rows = []
    for r in ROWS:
        tiles = []
        for c in COLS:
            cell = f"{c}{r}"
            shot = state["shots"].get(cell)
            if cell in sunk_cells:
                tiles.append(f'<img src="seabattle/tiles/sunk.png" width="{TILE_W}" alt="{cell} sunk" title="{cell}: sunk" />')
            elif shot and shot["result"] == "hit":
                tiles.append(f'<img src="seabattle/tiles/hit.png" width="{TILE_W}" alt="{cell} hit" title="{cell}: hit by {shot["by"]}" />')
            elif shot:
                tiles.append(f'<img src="seabattle/tiles/miss.png" width="{TILE_W}" alt="{cell} miss" title="{cell}: miss by {shot["by"]}" />')
            else:
                tiles.append(f'<a href="{issue_url(repo, cell)}"><img src="seabattle/tiles/water_{cell}.png" width="{TILE_W}" alt="Fire at {cell}" title="Fire at {cell}!" /></a>')
        rows.append("".join(tiles))
    board = "<br />\n".join(rows)

    shots = len(state["shots"])
    hits = sum(1 for s in state["shots"].values() if s["result"] == "hit")
    afloat = len(SHIPS) - len(state["sunk"])
    fleet_rows = []
    for sid, emoji, name, size in SHIPS:
        status = "☠️ **sunk**" if sid in state["sunk"] else "🔥 afloat"
        fleet_rows.append(f"| {emoji} {name} | {'▰' * size} | {status} |")

    recent = [e for e in reversed(state["log"])][:6]
    recent_rows = [f"| {who(e['by'])} | {e['cell']} | "
                   + {"miss": "🌊 miss", "hit": "💥 hit"}.get(e["result"], f"☠️ sank the {SHIP[e.get('ship', 'kraken')][2]}")
                   + f" | game #{e['game']} |" for e in recent]

    caps = sorted(state["captains"].items(), key=lambda kv: (-kv[1]["hits"], -kv[1]["sinks"], -kv[1]["wins"], kv[1]["shots"], kv[0]))[:5]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    cap_rows = [f"| {medals[i]} | {who(k)} | {v['shots']} | {v['hits']} | {v['sinks']} | {v['wins']} |" for i, (k, v) in enumerate(caps)]
    hof = [f"{who(h['winner'])} (game #{h['game']}, {h['shots']} shots)" for h in reversed(state["hall_of_fame"][-3:])]

    out = [
        START,
        "## ⚓ Sea Battle: sink the Kraken fleet!",
        "",
        '<p align="center">',
        '  <img src="seabattle/header.jpg" width="100%" alt="A small pirate ship fires its cannons at a kraken, a sea dragon and a ghost galleon" />',
        "</p>",
        "",
        "**A mini game you play right here, with everyone who visits.** A hidden enemy fleet lurks under the waves. "
        "**Click any 🌊 water tile to fire a cannon:** GitHub opens an issue for you, just press **Create**. "
        "My bot fires the shot, updates this board and replies to you in about a minute. "
        "Sink the last ship to win the round and enter the Hall of Fame!",
        "",
        "> 🇻🇳 **Mini game chơi ngay trên profile, cùng mọi người ghé thăm.** Hạm đội địch đang trốn dưới biển: "
        "bấm vào một ô 🌊 để bắn đại bác, GitHub mở sẵn một issue, bạn chỉ cần bấm **Create**. "
        "Bot sẽ bắn, cập nhật bàn và trả lời bạn sau khoảng một phút. Ai bắn chìm con tàu cuối cùng thì thắng ván!",
        "",
        '<p align="center">',
        board,
        "</p>",
        "",
        f'<p align="center"><b>Game #{state["game"]}</b> · 🎯 {shots} shots · 💥 {hits} hits · 🚢 {afloat} of {len(SHIPS)} ships afloat</p>',
        "",
        "<table align=\"center\"><tr><td valign=\"top\">",
        "",
        "**Enemy fleet**",
        "",
        "| Ship | Size | Status |",
        "|---|---|---|",
        *fleet_rows,
        "",
        "</td><td valign=\"top\">",
        "",
        "**Last shots**",
        "",
        "| Captain | Tile | Result | |",
        "|---|---|---|---|",
        *(recent_rows or ["| _nobody yet_ | | be the first! | |"]),
        "",
        "</td></tr></table>",
        "",
        '<div align="center">',
        "",
        "**🏅 Top captains**",
        "",
        "| | Captain | Shots | Hits | Ships sunk | Wins |",
        "|---|---|---|---|---|---|",
        *(cap_rows or ["| | _your name here_ | | | | |"]),
        "",
        f"🏆 **Hall of Fame:** {' · '.join(hof) if hof else '_no fleet sunk yet, will you be the first?_'}",
        "",
        "</div>",
        "",
        "<sub>How it works: GitHub profiles can't run JavaScript, so the game runs on GitHub Issues + Actions. "
        "The fleet's layout comes from a secret key, so nobody can peek at it in the repo.</sub>",
        END,
    ]
    return "\n".join(out)


def write_readme(state: dict, repo: str) -> None:
    with open(README, encoding="utf-8") as f:
        text = f.read()
    block = render(state, repo)
    if START in text and END in text:
        text = text[: text.index(START)] + block + text[text.index(END) + len(END):]
    else:
        raise SystemExit(f"README.md has no {START} ... {END} markers")
    with open(README, "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------- GitHub I/O

def gh(*args, input_text=None) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, input=input_text).stdout


def open_move_issues(repo: str) -> list:
    raw = gh("api", f"repos/{repo}/issues?state=open&sort=created&direction=asc&per_page=100")
    items = [i for i in json.loads(raw) if "pull_request" not in i]
    return [{"number": i["number"], "title": i["title"], "login": i["user"]["login"]}
            for i in items if i["title"].strip().lower().startswith("seabattle")]


def cmd_apply(args) -> None:
    repo = os.environ.get("REPO") or "NguyenHuyHoangBeng/NguyenHuyHoangBeng"
    secret = os.environ.get("SEABATTLE_SECRET")
    if not secret:
        raise SystemExit("SEABATTLE_SECRET is not set")
    out_path = args.get("--out") or os.environ.get("SEABATTLE_OUT") or os.path.join(tempfile.gettempdir(), "seabattle_replies.json")
    if "--issues" in args:
        with open(args["--issues"], encoding="utf-8") as f:
            issues = json.load(f)
    else:
        issues = open_move_issues(repo)
    state = load()
    replies = []
    for issue in issues:
        n = issue["number"]
        if n in state["processed"]:
            replies.append({"number": n, "body": None})
            continue
        m = MOVE.match(issue["title"])
        if not m:
            body = ("🤔 I couldn't read that move. Click a 🌊 tile on the "
                    f"[board]({board_url()}) and press **Create** without changing the title.")
        else:
            cell = m.group(1).upper() + m.group(2)
            body = fire(state, fleet(secret, state["game"]), cell, issue["login"])
            body += f"\n\n[⚓ Back to the board]({board_url()})"
        state["processed"] = (state["processed"] + [n])[-300:]
        replies.append({"number": n, "body": body})
    save(state)
    write_readme(state, repo)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(replies, f, ensure_ascii=False, indent=1)
    print(f"handled {len(replies)} issue(s), game #{state['game']}, {len(state['shots'])} shots on the board")


def cmd_notify(args) -> None:
    repo = os.environ.get("REPO") or "NguyenHuyHoangBeng/NguyenHuyHoangBeng"
    out_path = args.get("--out") or os.environ.get("SEABATTLE_OUT") or os.path.join(tempfile.gettempdir(), "seabattle_replies.json")
    if not os.path.exists(out_path):
        return
    with open(out_path, encoding="utf-8") as f:
        replies = json.load(f)
    for r in replies:
        n = str(r["number"])
        try:
            if r["body"]:
                gh("issue", "comment", n, "--repo", repo, "--body-file", "-", input_text=r["body"])
            gh("issue", "close", n, "--repo", repo, "--reason", "completed")
        except subprocess.CalledProcessError as e:
            print(f"issue #{n}: {e.stderr.strip()}", file=sys.stderr)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd, rest = sys.argv[1], sys.argv[2:]
    args = {rest[i]: rest[i + 1] for i in range(0, len(rest) - 1, 2)}
    if cmd == "apply":
        cmd_apply(args)
    elif cmd == "notify":
        cmd_notify(args)
    elif cmd == "render":
        write_readme(load(), os.environ.get("REPO") or "NguyenHuyHoangBeng/NguyenHuyHoangBeng")
    elif cmd == "init":
        save(new_state())
        write_readme(load(), os.environ.get("REPO") or "NguyenHuyHoangBeng/NguyenHuyHoangBeng")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
