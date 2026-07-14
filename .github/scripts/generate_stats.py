#!/usr/bin/env python3
"""Generate GitHub profile stat cards as static SVGs.

Replaces third-party card services (e.g. github-readme-stats.vercel.app,
which can be rate-limited or paused) with SVGs generated in CI and served
from this repo's `output` branch — same pattern as the contribution snake.

Usage:
    GITHUB_TOKEN=... python3 generate_stats.py --user David031 --out dist

Writes:
    stats.svg / stats-dark.svg          overview card
    top-langs.svg / top-langs-dark.svg  compact language breakdown card

Stdlib only — no pip installs needed in CI.
"""

import argparse
import json
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

THEMES = {
    # matches github-readme-stats "default"
    "light": {
        "suffix": "",
        "bg": "#fffefe",
        "title": "#2f80ed",
        "text": "#434d58",
        "icon": "#4c71f2",
        "muted": "#858e99",
    },
    # matches github-readme-stats "tokyonight"
    "dark": {
        "suffix": "-dark",
        "bg": "#1a1b27",
        "title": "#70a5fd",
        "text": "#38bdae",
        "icon": "#bf91f3",
        "muted": "#7d8590",
    },
}

# Octicons (MIT) — 16x16 path data
ICONS = {
    "star": "M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 11.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z",
    "commit": "M10.5 7.75a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zm1.43.75a4.002 4.002 0 01-7.86 0H.75a.75.75 0 010-1.5h3.32a4.001 4.001 0 017.86 0h3.32a.75.75 0 010 1.5h-3.32z",
    "pr": "M11.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122V6A2.5 2.5 0 0110 8.5H6a1 1 0 00-1 1v1.128a2.251 2.251 0 11-1.5 0V5.372a2.25 2.25 0 111.5 0v1.836A2.492 2.492 0 016 7h4a1 1 0 001-1v-.628A2.25 2.25 0 019.5 3.25zM4.25 12a.75.75 0 100 1.5.75.75 0 000-1.5zM3.5 3.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0z",
    "issue": "M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8zm9 3a1 1 0 11-2 0 1 1 0 012 0zm-.25-6.25a.75.75 0 00-1.5 0v3.5a.75.75 0 001.5 0v-3.5z",
    "repo": "M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 010-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8z",
    "people": "M2 5.5a3.5 3.5 0 115.898 2.549 5.508 5.508 0 013.034 4.084.75.75 0 11-1.482.235 4.001 4.001 0 00-7.9 0 .75.75 0 01-1.482-.236A5.507 5.507 0 013.102 8.05 3.493 3.493 0 012 5.5zM11 4a3.001 3.001 0 012.22 5.018 5.01 5.01 0 012.56 3.012.749.749 0 01-.885.954.752.752 0 01-.549-.514 3.507 3.507 0 00-2.522-2.372.75.75 0 01-.574-.73v-.352a.75.75 0 01.416-.672A1.5 1.5 0 0011 5.5.75.75 0 0111 4zm-5.5-.5a2 2 0 100 4 2 2 0 000-4z",
}

FONT = "font-family=\"'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif\""


def fetch_data(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": login,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    user = payload["data"]["user"]
    if user is None:
        raise RuntimeError(f"user {login!r} not found")
    return user


def collect_stats(user: dict) -> dict:
    repos = user["repositories"]["nodes"]
    contrib = user["contributionsCollection"]
    return {
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": contrib["totalCommitContributions"] + contrib["restrictedContributionsCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
    }


def collect_languages(user: dict, top_n: int = 8) -> list:
    sizes, colors = {}, {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] = sizes.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or "#8b949e"
    total = sum(sizes.values())
    if not total:
        return []
    top = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [(name, size / total * 100, colors[name]) for name, size in top]


def stats_svg(login: str, stats: dict, theme: dict) -> str:
    rows = [
        ("star", "Total Stars", stats["stars"]),
        ("commit", "Commits (last year)", stats["commits"]),
        ("pr", "Pull Requests", stats["prs"]),
        ("issue", "Issues", stats["issues"]),
        ("repo", "Repositories", stats["repos"]),
        ("people", "Followers", stats["followers"]),
    ]
    width, row_h, top = 450, 21, 59
    height = top + row_h * len(rows) + 15  # 200
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="GitHub stats for {escape(login)}">',
        f'<rect width="{width}" height="{height}" rx="4.5" fill="{theme["bg"]}"/>',
        f'<text x="25" y="33" {FONT} font-size="18" font-weight="600" fill="{theme["title"]}">{escape(login)}&#8217;s GitHub Stats</text>',
    ]
    for i, (icon, label, value) in enumerate(rows):
        y = top + i * row_h
        parts.append(
            f'<g transform="translate(25,{y})">'
            f'<path transform="translate(0,-12)" fill="{theme["icon"]}" fill-rule="evenodd" d="{ICONS[icon]}"/>'
            f'<text x="25" y="1" {FONT} font-size="14" font-weight="600" fill="{theme["text"]}">{escape(label)}:</text>'
            f'<text x="220" y="1" {FONT} font-size="14" font-weight="700" fill="{theme["text"]}">{value:,}</text>'
            f"</g>"
        )
    parts.append("</svg>")
    return "".join(parts)


def langs_svg(langs: list, theme: dict) -> str:
    width, bar_w, pad = 320, 270, 25
    col_w, row_h, legend_top = 135, 22, 90
    n_rows = (len(langs) + 1) // 2
    height = legend_top + n_rows * row_h + 8
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Most used languages">',
        f'<rect width="{width}" height="{height}" rx="4.5" fill="{theme["bg"]}"/>',
        f'<text x="{pad}" y="33" {FONT} font-size="18" font-weight="600" fill="{theme["title"]}">Most Used Languages</text>',
        # stacked percentage bar (clipped to rounded rect)
        f'<defs><clipPath id="bar"><rect x="{pad}" y="52" width="{bar_w}" height="10" rx="5"/></clipPath></defs>',
        f'<g clip-path="url(#bar)">',
    ]
    x = float(pad)
    for name, pct, color in langs:
        seg = bar_w * pct / 100
        parts.append(f'<rect x="{x:.2f}" y="52" width="{seg + 1:.2f}" height="10" fill="{color}"/>')
        x += seg
    parts.append("</g>")
    for i, (name, pct, color) in enumerate(langs):
        cx = pad + (i % 2) * col_w
        cy = legend_top + (i // 2) * row_h
        parts.append(
            f'<g transform="translate({cx},{cy})">'
            f'<circle cx="5" cy="-4" r="5" fill="{color}"/>'
            f'<text x="16" y="0" {FONT} font-size="12" fill="{theme["text"]}">{escape(name)} {pct:.1f}%</text>'
            f"</g>"
        )
    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", required=True, help="GitHub login to render cards for")
    ap.add_argument("--out", default="dist", help="output directory (default: dist)")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("error: GITHUB_TOKEN env var is required", file=sys.stderr)
        return 1

    user = fetch_data(args.user, token)
    stats = collect_stats(user)
    langs = collect_languages(user)
    print(f"stats: {stats}")
    print(f"languages: {[(n, round(p, 1)) for n, p, _ in langs]}")

    os.makedirs(args.out, exist_ok=True)
    for theme in THEMES.values():
        with open(os.path.join(args.out, f"stats{theme['suffix']}.svg"), "w") as f:
            f.write(stats_svg(args.user, stats, theme))
        if langs:
            with open(os.path.join(args.out, f"top-langs{theme['suffix']}.svg"), "w") as f:
                f.write(langs_svg(langs, theme))
    print(f"wrote SVGs to {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
