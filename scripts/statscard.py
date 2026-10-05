#!/usr/bin/env python3
"""Genera assets/statscard.svg: una tarjeta estilo terminal (neofetch) con
tus stats de GitHub, retrato ASCII y barra de lenguajes.

Variables de entorno:
  GH_USER     tu usuario de GitHub                      (obligatorio)
  GH_TOKEN    token (GITHUB_TOKEN o un PAT)             (obligatorio salvo --demo)
  TAGLINE     texto bajo tu nombre, ej. "EEE @ Univ. of Dhaka"  (opcional)
  PROMPT_CMD  comando que "ejecuta" la terminal         (def: git fetch --stats)

Uso:
  python scripts/statscard.py            # datos reales
  python scripts/statscard.py --demo     # datos falsos, para probar el diseño
"""
import io
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

DEMO = "--demo" in sys.argv
OUT = os.environ.get("OUT", "assets/statscard.svg")

# --------------------------------------------------------------------------
# Paleta (ajústala a tu gusto)
# --------------------------------------------------------------------------
BG = "#0a0e17"
TITLEBAR = "#0f1523"
BORDER = "#1b2a3a"
ACCENT = "#2dd4bf"      # etiquetas y nombre
ORANGE = "#f5a623"      # usuario@host
TEXT = "#e6edf3"
MUTED = "#6b7a8d"
FONT = "'JetBrains Mono','Fira Code','SF Mono',Menlo,Consolas,'DejaVu Sans Mono',monospace"

# Colores de lenguajes si GitHub no devuelve uno
FALLBACK_COLORS = ["#3178c6", "#f34b7d", "#3572a5", "#41b01f", "#2dd4bf", "#2dd4bf"]


# --------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------
QUERY = """
query($login:String!){
  user(login:$login){
    name login createdAt avatarUrl
    followers{ totalCount }
    repositories(ownerAffiliations:[OWNER], isFork:false, first:100,
                 orderBy:{field:STARGAZERS, direction:DESC}){
      totalCount
      nodes{
        stargazerCount
        languages(first:6, orderBy:{field:SIZE, direction:DESC}){
          edges{ size node{ name color } }
        }
      }
    }
    contributionsCollection{
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar{
        totalContributions
        weeks{ contributionDays{ date contributionCount } }
      }
    }
  }
}
"""


def gh_query(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "statscard"},
    )
    data = json.load(urllib.request.urlopen(req, timeout=30))
    if "errors" in data:
        raise SystemExit(f"Error de la API: {data['errors']}")
    return data["data"]["user"]


def streaks(days):
    """days: lista [(date, count)] ordenada. Devuelve (actual, mayor, mejor_dia)."""
    longest = run = 0
    for _, n in days:
        run = run + 1 if n > 0 else 0
        longest = max(longest, run)
    # racha actual: si hoy aún no tiene commits, se cuenta desde ayer
    cur = 0
    seq = list(days)
    if seq and seq[-1][1] == 0:
        seq = seq[:-1]
    for _, n in reversed(seq):
        if n > 0:
            cur += 1
        else:
            break
    best = max((n for _, n in days), default=0)
    return cur, longest, best


def build_stats(u):
    cc = u["contributionsCollection"]
    cal = cc["contributionCalendar"]
    days = [
        (d["date"], d["contributionCount"])
        for w in cal["weeks"]
        for d in w["contributionDays"]
        if d["date"] <= date.today().isoformat()
    ]
    cur, longest, best = streaks(days)

    repos = u["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)

    # lenguajes por bytes
    sizes, colors = defaultdict(int), {}
    for r in repos:
        for e in r["languages"]["edges"]:
            sizes[e["node"]["name"]] += e["size"]
            if e["node"]["color"]:
                colors[e["node"]["name"]] = e["node"]["color"]
    total = sum(sizes.values()) or 1
    top = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]
    langs = [
        (n, round(s * 100 / total), colors.get(n, FALLBACK_COLORS[i % 6]))
        for i, (n, s) in enumerate(top)
    ]

    since = int(u["createdAt"][:4])
    return {
        "name": u["name"] or u["login"],
        "login": u["login"],
        "avatar": u["avatarUrl"],
        "since": f"{since} ~{date.today().year - since} yrs",
        "commits": f"{cc['totalCommitContributions']:,} / yr",
        "contribs": f"{cal['totalContributions']:,} / yr",
        "prs": f"{cc['totalPullRequestContributions']:,} / yr",
        "followers": f"{u['followers']['totalCount']:,}",
        "repos": f"{u['repositories']['totalCount']:,}",
        "stars": f"{stars:,}",
        "streak": f"{cur} days",
        "longest": f"{longest} days",
        "best": f"{best} commits",
        "langs": langs,
    }


def demo_stats():
    return {
        "name": "Tu Nombre", "login": "tu-usuario", "avatar": None,
        "since": "2018 ~8 yrs", "commits": "1,331 / yr", "contribs": "3,395 / yr",
        "prs": "7 / yr", "followers": "4", "repos": "40", "stars": "330",
        "streak": "17 days", "longest": "69 days", "best": "101 commits",
        "langs": [("TypeScript", 29, "#3178c6"), ("C++", 22, "#f34b7d"),
                  ("Python", 19, "#3572a5"), ("QML", 13, "#41b01f"),
                  ("Swift", 9, "#2dd4bf"), ("Kotlin", 8, "#2dd4bf")],
    }


# --------------------------------------------------------------------------
# Retrato ASCII
# --------------------------------------------------------------------------
ASCII_COLS, ASCII_ROWS = 56, 30
RAMP = " .:-=+*#%@"


def ascii_portrait(avatar_url):
    """Convierte el avatar en líneas de texto. Devuelve [] si no se puede."""
    try:
        from PIL import Image, ImageOps, ImageDraw
    except ImportError:
        return []
    try:
        if avatar_url:
            raw = urllib.request.urlopen(
                urllib.request.Request(avatar_url + ("&" if "?" in avatar_url else "?") + "s=200",
                                       headers={"User-Agent": "statscard"}), timeout=30).read()
            img = Image.open(io.BytesIO(raw)).convert("L")
        else:  # modo demo: silueta sintética
            img = Image.new("L", (200, 200), 0)
            d = ImageDraw.Draw(img)
            d.ellipse((60, 25, 140, 115), fill=200)
            d.ellipse((15, 120, 185, 300), fill=150)
    except Exception as e:  # sin red, avatar caído...
        print("aviso: sin retrato ASCII:", e, file=sys.stderr)
        return []

    img = ImageOps.autocontrast(img)
    img = img.resize((ASCII_COLS, ASCII_ROWS))
    px = img.load()
    lines = []
    for y in range(ASCII_ROWS):
        row = "".join(RAMP[px[x, y] * (len(RAMP) - 1) // 255] for x in range(ASCII_COLS))
        lines.append(row.rstrip())
    return lines


# --------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------
def render(s, tagline, cmd):
    W, H = 1020, 392
    e = escape
    out = []
    a = out.append

    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'role="img" aria-label="GitHub stats de {e(s["login"])}">')
    a(f'<style>text{{font-family:{FONT};white-space:pre}}'
      f'.k{{fill:{ACCENT};font-weight:700;font-size:17px}}'
      f'.v{{fill:{TEXT};font-size:17px}}'
      f'.m{{fill:{MUTED}}}'
      f'.art{{fill:{ACCENT};font-size:7px;opacity:.75}}'
      f'.cur{{animation:b 1.1s steps(1) infinite}}@keyframes b{{50%{{opacity:0}}}}</style>')
    a('<defs><clipPath id="win"><rect width="%d" height="%d" rx="14"/></clipPath></defs>' % (W, H))

    # ventana
    a(f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="14" fill="{BG}" stroke="{BORDER}"/>')
    a(f'<g clip-path="url(#win)"><rect width="{W}" height="38" fill="{TITLEBAR}"/></g>')
    for cx, col in ((28, "#ff5f57"), (53, "#febc2e"), (78, "#28c840")):
        a(f'<circle cx="{cx}" cy="19" r="6.5" fill="{col}"/>')
    a(f'<text x="120" y="24" class="m" font-size="15">{e(s["login"])}@github: ~/profile</text>')

    # prompt
    a(f'<text x="37" y="69" font-size="19">'
      f'<tspan fill="{ORANGE}" font-weight="700">{e(s["login"])}@github</tspan>'
      f'<tspan fill="{TEXT}">:~$ {e(cmd)}</tspan>'
      f'<tspan fill="{TEXT}" class="cur"> ▊</tspan></text>')

    # retrato ASCII
    art = ascii_portrait(s["avatar"])
    for i, line in enumerate(art):
        a(f'<text x="30" y="{92 + i * 8}" class="art" xml:space="preserve">{e(line)}</text>')

    # cabecera
    X = 340 if art else 40
    a(f'<text x="{X}" y="113" font-size="24" font-weight="700" fill="{ACCENT}">{e(s["name"])}</text>')
    sub = f'@{s["login"]}' + (f' · {tagline}' if tagline else '')
    a(f'<text x="{X}" y="137" font-size="15" class="m">{e(sub)}</text>')

    # stats en dos columnas
    left = [("since", s["since"]), ("commits", s["commits"]), ("contribs", s["contribs"]),
            ("PRs", s["prs"]), ("followers", s["followers"])]
    right = [("repos", s["repos"]), ("stars", s["stars"]), ("streak", s["streak"]),
             ("longest", s["longest"]), ("best day", s["best"])]
    for i, ((k1, v1), (k2, v2)) in enumerate(zip(left, right)):
        y = 182 + i * 30.5
        a(f'<text x="{X}" y="{y}" class="k">{e(k1)}</text>')
        a(f'<text x="{X + 122}" y="{y}" class="v">{e(v1)}</text>')
        a(f'<text x="{X + 351}" y="{y}" class="k">{e(k2)}</text>')
        a(f'<text x="{X + 455}" y="{y}" class="v">{e(v2)}</text>')

    # barra de lenguajes
    a(f'<line x1="28" y1="340" x2="{W-28}" y2="340" stroke="{BORDER}"/>')
    langs = s["langs"]
    if langs:
        total = sum(p for _, p, _ in langs) or 1
        usable, gap, x = (W - 56) - 2 * (len(langs) - 1), 2, 28.0
        for name, pct, col in langs:
            w = usable * pct / total
            a(f'<rect x="{x:.1f}" y="349" width="{w:.1f}" height="13" rx="2.5" fill="{col}"/>')
            x += w + gap
        lx = 28
        for name, pct, col in langs:
            label = f"{name} {pct}%"
            a(f'<circle cx="{lx + 4}" cy="378" r="4" fill="{col}"/>')
            a(f'<text x="{lx + 13}" y="383" font-size="13.5" class="m">{e(label)}</text>')
            lx += 13 + len(label) * 8.1 + 12

    a("</svg>")
    return "\n".join(out)


def main():
    user = os.environ.get("GH_USER", "tu-usuario")
    if DEMO:
        stats = demo_stats()
    else:
        token = os.environ.get("GH_TOKEN")
        if not (user and token):
            raise SystemExit("Faltan GH_USER y/o GH_TOKEN (o usa --demo)")
        stats = build_stats(gh_query(user, token))

    svg = render(stats, os.environ.get("TAGLINE", ""), os.environ.get("PROMPT_CMD", "git fetch --stats"))
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print("escrito", OUT)


if __name__ == "__main__":
    main()
