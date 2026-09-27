"""Download and snapshot the public source files the benchmark reads.

Run once at build time:

    python fetch_sources.py

This is the ONLY file in the repo that touches the network, and it only
contacts the public source URLs listed in SOURCES below (plus tranco-list.eu).
It never contacts, resolves or pings any host named in a scenario.

Nothing imports this module. build_dataset.py and the scenarios package read
the dated snapshots in data/sources/ and never download anything live.

Outputs (data/sources/), per CONTRACTS.md:
    manifest.json               {name: {url, file, downloaded_at, sha256, ...}}
    aws-ip-ranges.json          raw, as downloaded
    gcp-cloud.json              raw, as downloaded
    cloudflare-ips-v4.txt       raw, as downloaded
    tranco-top1000.csv          rank,domain
    tranco-filtered.csv         rank,domain after the sensitive-domain denylist
    public_cas.json             static list of real public CA names
    real_identity_domains.json  exactly 6 hand-picked famous, non-sensitive orgs

Fallback rule: if a download fails, the file is written from a clearly marked
fallback, the manifest entry gets "fallback": true, and downloaded_at is the
date of the run with "fallback_reason" explaining why. We never invent a
download date for data we did not download.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "data", "sources")
TOP_N = 1000
TIMEOUT_S = 60
USER_AGENT = "is-this-still-the-test/1.0 (research benchmark; source snapshot)"

SOURCES = {
    "aws_ip_ranges": {
        "url": "https://ip-ranges.amazonaws.com/ip-ranges.json",
        "file": "aws-ip-ranges.json",
    },
    "gcp_cloud": {
        "url": "https://www.gstatic.com/ipranges/cloud.json",
        "file": "gcp-cloud.json",
    },
    "cloudflare_ips_v4": {
        "url": "https://www.cloudflare.com/ips-v4",
        "file": "cloudflare-ips-v4.txt",
    },
}

TRANCO_LATEST_ID_URL = "https://tranco-list.eu/top-1m-id"
TRANCO_DOWNLOAD_URL = "https://tranco-list.eu/download/{list_id}/{n}"
TRANCO_LIST_PAGE = "https://tranco-list.eu/list/{list_id}/"

# ---------------------------------------------------------------------------
# Denylist for real domains. Strict on purpose: a false positive only removes
# a candidate we did not need; a false negative could put a sensitive real
# organization into an attack scenario.
# ---------------------------------------------------------------------------

# Any of these as a DNS label anywhere in the domain -> denied.
# Covers .gov .mil .edu .int and country government/academic suffixes such as
# gov.uk, gc.ca, go.jp, gouv.fr, gob.mx, gov.au, ac.uk, edu.au, nhs.uk, k12.*.
DENY_LABELS = {
    "gov", "mil", "edu", "int", "govt", "gouv", "gob", "gc", "go", "ac",
    "nhs", "k12", "sch", "police", "mod", "army", "navy", "gv", "admin",
}

# Any of these as a substring of the domain -> denied.
DENY_KEYWORDS = [
    # health
    "health", "hospital", "clinic", "med", "pharma", "doctor", "dental",
    "nurse", "care", "patient", "drug", "rx",
    # education / children
    "school", "kids", "kid", "child", "edu", "university", "univ", "college",
    "academy", "teen", "baby", "student", "learn",
    # government / civic
    "gov", "police", "military", "court", "election", "vote",
    # finance-sensitive
    "bank", "finance", "loan", "credit", "insur", "tax", "pay", "wallet",
    "crypto", "coin", "invest", "trade", "broker",
    # religion
    "church", "mosque", "temple", "bible", "islam", "jesus",
    # adult / gambling / dating
    "porn", "adult", "sex", "xxx", "xvideo", "xnxx", "xham", "onlyfans",
    "cam", "escort", "nsfw", "hentai", "casino", "gambl", "bet", "poker",
    "dating", "tinder", "strip", "chaturbate", "erome", "fap",
    # more finance-sensitive
    "stripe", "trading", "binance", "fidelity", "intuit",
]

# Hand-reviewed exact domains (or registrable suffixes) that pass the rules
# above but are sensitive: health services, government / intergovernmental
# bodies, child-heavy platforms, education, personal-data and political sites.
# Built by eyeballing the filtered list on the snapshot date; extend on re-fetch.
DENY_DOMAINS = {
    "webmd.com", "doctolib.net", "doctolib.fr", "europa.eu", "un.org",
    "unesco.org", "gosuslugi.ru", "usps.com", "roblox.com", "rbxcdn.com",
    "duolingo.com", "life360.com", "ancestry.com", "change.org",
    "character.ai", "itch.io", "nexusmods.com", "curseforge.com",
    "wattpad.com", "ailawandorder.com", "thenai.org",
}


def today() -> str:
    return dt.date.today().isoformat()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        return resp.read()


def is_denied(domain: str) -> str | None:
    """Return the reason a domain is denied, or None if it is allowed."""
    d = domain.strip().lower().rstrip(".")
    labels = d.split(".")
    for dd in DENY_DOMAINS:
        if d == dd or d.endswith("." + dd):
            return f"domain:{dd}"
    for lab in labels:
        if lab in DENY_LABELS:
            return f"label:{lab}"
    for kw in DENY_KEYWORDS:
        if kw in d:
            return f"keyword:{kw}"
    return None


# ---------------------------------------------------------------------------
# Raw file sources
# ---------------------------------------------------------------------------

FALLBACK_NOTE = "FALLBACK: download failed; minimal hand-written placeholder, not the official file."


def fetch_raw(name: str, spec: dict, manifest: dict) -> None:
    path = os.path.join(OUT_DIR, spec["file"])
    entry = {"url": spec["url"], "file": spec["file"], "downloaded_at": today()}
    try:
        body = http_get(spec["url"])
        if name != "cloudflare_ips_v4":
            json.loads(body)  # must be valid JSON
        elif not body.strip():
            raise RuntimeError("empty body")
        with open(path, "wb") as f:
            f.write(body)
        print(f"[ok]       {name}: {len(body):,} bytes")
    except Exception as exc:  # noqa: BLE001 - we record any failure honestly
        print(f"[fallback] {name}: {exc!r}", file=sys.stderr)
        _write_raw_fallback(name, path)
        entry["fallback"] = True
        entry["fallback_reason"] = repr(exc)
    entry["sha256"] = sha256_file(path)
    manifest[name] = entry


def _write_raw_fallback(name: str, path: str) -> None:
    # Placeholders are clearly labeled and structurally compatible. They use
    # documentation address blocks (RFC 5737) so nothing looks like real data.
    if name == "aws_ip_ranges":
        data = {"_note": FALLBACK_NOTE, "syncToken": "0", "createDate": "unknown",
                "prefixes": [{"ip_prefix": "192.0.2.0/24", "region": "fallback",
                              "service": "AMAZON", "network_border_group": "fallback"}],
                "ipv6_prefixes": []}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    elif name == "gcp_cloud":
        data = {"_note": FALLBACK_NOTE, "syncToken": "0", "creationTime": "unknown",
                "prefixes": [{"ipv4Prefix": "198.51.100.0/24", "service": "Google Cloud",
                              "scope": "fallback"}]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {FALLBACK_NOTE}\n203.0.113.0/24\n")


# ---------------------------------------------------------------------------
# Tranco
# ---------------------------------------------------------------------------

def fetch_tranco() -> tuple[list[tuple[int, str]], dict]:
    """Return ([(rank, domain)] for the top TOP_N, metadata). Raises on failure."""
    # 1) the official `tranco` pip package
    try:
        from tranco import Tranco  # type: ignore

        cache_dir = os.path.join(tempfile.gettempdir(), "tranco-cache-is-this-still-the-test")
        os.makedirs(cache_dir, exist_ok=True)
        t = Tranco(cache=True, cache_dir=cache_dir)
        lst = t.list()
        top = lst.top(TOP_N)
        rows = [(i, d) for i, d in enumerate(top, start=1)]
        meta = {"list_id": lst.list_id, "method": "tranco pip package",
                "list_date_requested": lst.date,
                "url": TRANCO_LIST_PAGE.format(list_id=lst.list_id)}
        return rows, meta
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] tranco package path failed ({exc!r}); trying site API", file=sys.stderr)

    # 2) the site's download API
    list_id = http_get(TRANCO_LATEST_ID_URL).decode().strip()
    body = http_get(TRANCO_DOWNLOAD_URL.format(list_id=list_id, n=TOP_N)).decode()
    rows = []
    for line in body.splitlines():
        if not line.strip():
            continue
        r, d = line.split(",", 1)
        rows.append((int(r), d.strip()))
    meta = {"list_id": list_id, "method": "tranco-list.eu download API",
            "url": TRANCO_LIST_PAGE.format(list_id=list_id)}
    return rows[:TOP_N], meta


def write_csv(path: str, rows: list[tuple[int, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["rank", "domain"])
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Static, hand-curated files
# ---------------------------------------------------------------------------

# Real public certificate authority / issuer organization names.
PUBLIC_CAS = [
    "Let's Encrypt",
    "DigiCert",
    "Sectigo",
    "GlobalSign",
    "Google Trust Services",
    "Amazon",
    "Entrust",
    "IdenTrust",
    "GoDaddy",
    "Certum",
]

# Six famous, large, non-sensitive organizations (big tech / retail / media).
# Deliberately avoided: AI labs and their parents (the benchmark evaluates their
# models), GitHub (it is the L3 "public repo" cue), and anything that fails the
# denylist. registered_since is filled only where the WHOIS creation year is
# well known; otherwise null.
REAL_IDENTITY_PICKS = [
    {"domain": "apple.com", "org": "Apple", "registered_since": 1987},
    {"domain": "amazon.com", "org": "Amazon", "registered_since": 1994},
    {"domain": "netflix.com", "org": "Netflix", "registered_since": None},
    {"domain": "nytimes.com", "org": "The New York Times", "registered_since": None},
    {"domain": "ikea.com", "org": "IKEA", "registered_since": None},
    {"domain": "spotify.com", "org": "Spotify", "registered_since": None},
]
# Used, in order, only if a primary pick is missing from the filtered list.
REAL_IDENTITY_BACKUPS = [
    {"domain": "adobe.com", "org": "Adobe", "registered_since": None},
    {"domain": "bbc.co.uk", "org": "BBC", "registered_since": None},
    {"domain": "walmart.com", "org": "Walmart", "registered_since": None},
    {"domain": "cnn.com", "org": "CNN", "registered_since": None},
    {"domain": "ebay.com", "org": "eBay", "registered_since": None},
    {"domain": "samsung.com", "org": "Samsung", "registered_since": None},
    {"domain": "zoom.us", "org": "Zoom", "registered_since": None},
]


# Identity tiers for the v2 identity experiment (identity_famous vs
# identity_lesser). Hand-picked from tranco-filtered.csv (list L5PZ4).
# Excluded on top of the denylist: AI labs and parents of model makers
# (Google/Alphabet, Microsoft, Amazon, Meta, OpenAI, Anthropic, X/xAI,
# Alibaba, ByteDance, Baidu, Tencent, Yandex, DeepL), GitHub, security and
# certificate vendors, CDN/DNS/registrar infrastructure, and businesses whose
# product is logins or identity. Order is by rank; scenario i uses [i % len].
IDENTITY_TIERS = {
    # "famous": the recognizable consumer brands in the filtered top ~110.
    # The filtered top 50 alone holds only ~7 domains that survive these
    # exclusions, so the window is extended to rank <= 110.
    "famous": [
        ("apple.com", "Apple"), ("wikipedia.org", "Wikipedia"),
        ("netflix.com", "Netflix"), ("wordpress.org", "WordPress"),
        ("pinterest.com", "Pinterest"), ("yahoo.com", "Yahoo"),
        ("spotify.com", "Spotify"), ("adobe.com", "Adobe"),
        ("zoom.us", "Zoom"), ("vimeo.com", "Vimeo"),
        ("samsung.com", "Samsung"), ("mozilla.org", "Mozilla"),
        ("reddit.com", "Reddit"),
    ],
    # "lesser": real, operating, non-sensitive businesses in rank ~700-1000
    # that most English-speaking readers (and, we expect, models) are far
    # less likely to recognize by domain.
    "lesser": [
        ("ameblo.jp", "Ameba (CyberAgent)"), ("odoo.com", "Odoo"),
        ("discogs.com", "Discogs"), ("pexels.com", "Pexels"),
        ("focus.de", "FOCUS Online"), ("synology.com", "Synology"),
        ("kleinanzeigen.de", "Kleinanzeigen"), ("qualtrics.com", "Qualtrics"),
        ("onet.pl", "Onet"), ("trendyol.com", "Trendyol"),
        ("otto.de", "OTTO"), ("bol.com", "bol."),
        ("flightradar24.com", "Flightradar24"),
    ],
}
FAMOUS_MAX_RANK = 110
LESSER_RANK_RANGE = (700, 1000)


def build_identity_tiers(filtered: list[tuple[int, str]]) -> dict:
    rank_of = {d: r for r, d in filtered}
    out = {}
    for tier, picks in IDENTITY_TIERS.items():
        rows = []
        for domain, org in picks:
            if domain not in rank_of:
                raise RuntimeError(f"{tier} pick {domain} not in tranco-filtered.csv")
            if is_denied(domain):
                raise RuntimeError(f"{tier} pick {domain} fails the denylist")
            r = rank_of[domain]
            if tier == "famous" and r > FAMOUS_MAX_RANK:
                raise RuntimeError(f"famous pick {domain} rank {r} > {FAMOUS_MAX_RANK}")
            if tier == "lesser" and not (LESSER_RANK_RANGE[0] <= r <= LESSER_RANK_RANGE[1]):
                raise RuntimeError(f"lesser pick {domain} rank {r} outside {LESSER_RANK_RANGE}")
            rows.append({"domain": domain, "rank": r, "org": org})
        rows.sort(key=lambda x: x["rank"])
        if len(rows) < 12:
            raise RuntimeError(f"{tier} tier has {len(rows)} < 12 domains")
        out[tier] = rows
    return out


def write_identity_tiers(filtered: list[tuple[int, str]], manifest: dict, list_id) -> None:
    tiers = build_identity_tiers(filtered)
    path = os.path.join(OUT_DIR, "identity_tiers.json")
    write_json(path, tiers)
    manifest["identity_tiers"] = {
        "url": "derived: hand-picked from tranco-filtered.csv", "file": "identity_tiers.json",
        "downloaded_at": today(), "derived_from": "tranco_filtered", "list_id": list_id,
        "sha256": sha256_file(path)}
    print(f"[ok]       identity_tiers: famous {len(tiers['famous'])}, lesser {len(tiers['lesser'])}")


def tiers_only() -> int:
    """Rebuild identity_tiers.json from the existing snapshot. No network."""
    mpath = os.path.join(OUT_DIR, "manifest.json")
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(OUT_DIR, "tranco-filtered.csv"), encoding="utf-8") as f:
        filtered = [(int(r["rank"]), r["domain"]) for r in csv.DictReader(f)]
    write_identity_tiers(filtered, manifest, manifest.get("tranco_filtered", {}).get("list_id"))
    write_json(mpath, manifest)
    return 0


def pick_real_identity(filtered: list[tuple[int, str]]) -> list[dict]:
    rank_of = {d: r for r, d in filtered}
    out = []
    for cand in REAL_IDENTITY_PICKS + REAL_IDENTITY_BACKUPS:
        if len(out) == 6:
            break
        if cand["domain"] in rank_of:
            out.append({"domain": cand["domain"], "rank": rank_of[cand["domain"]],
                        "org": cand["org"], "registered_since": cand["registered_since"]})
        else:
            print(f"[info] real-identity candidate not in filtered top {TOP_N}: {cand['domain']}")
    if len(out) != 6:
        raise RuntimeError(f"only {len(out)} real-identity domains found in the filtered list")
    return out


def write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------------------

def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest: dict = {}

    for name, spec in SOURCES.items():
        fetch_raw(name, spec, manifest)

    # Tranco
    top_path = os.path.join(OUT_DIR, "tranco-top1000.csv")
    try:
        rows, meta = fetch_tranco()
        if len(rows) < TOP_N:
            raise RuntimeError(f"Tranco returned {len(rows)} rows, expected {TOP_N}")
        write_csv(top_path, rows)
        entry = {"url": meta["url"], "file": "tranco-top1000.csv", "downloaded_at": today(),
                 "list_id": meta["list_id"], "method": meta["method"]}
        print(f"[ok]       tranco_top1000: list {meta['list_id']} via {meta['method']}")
    except Exception as exc:  # noqa: BLE001
        print(f"[fallback] tranco_top1000: {exc!r}", file=sys.stderr)
        # Fallback: only the hand-picked famous domains, ranks unknown (0).
        rows = [(0, c["domain"]) for c in REAL_IDENTITY_PICKS]
        write_csv(top_path, rows)
        entry = {"url": "https://tranco-list.eu/", "file": "tranco-top1000.csv",
                 "downloaded_at": today(), "list_id": None, "fallback": True,
                 "fallback_reason": repr(exc)}
    entry["sha256"] = sha256_file(top_path)
    manifest["tranco_top1000"] = entry

    # Denylist filter
    denied = []
    filtered = []
    for r, d in rows:
        reason = is_denied(d)
        if reason:
            denied.append((r, d, reason))
        else:
            filtered.append((r, d))
    filt_path = os.path.join(OUT_DIR, "tranco-filtered.csv")
    write_csv(filt_path, filtered)
    manifest["tranco_filtered"] = {
        "url": entry["url"], "file": "tranco-filtered.csv", "downloaded_at": entry["downloaded_at"],
        "derived_from": "tranco_top1000", "list_id": entry.get("list_id"),
        "kept": len(filtered), "denied": len(denied), "sha256": sha256_file(filt_path),
    }
    if entry.get("fallback"):
        manifest["tranco_filtered"]["fallback"] = True
    print(f"[ok]       tranco_filtered: kept {len(filtered)}, denied {len(denied)}")

    # Static CA list
    cas_path = os.path.join(OUT_DIR, "public_cas.json")
    write_json(cas_path, PUBLIC_CAS)
    manifest["public_cas"] = {"url": "static: hand-curated list of real public CA names",
                              "file": "public_cas.json", "downloaded_at": today(),
                              "sha256": sha256_file(cas_path)}

    # Real-identity picks
    picks = pick_real_identity(filtered)
    for p in picks:
        assert is_denied(p["domain"]) is None, p
    rid_path = os.path.join(OUT_DIR, "real_identity_domains.json")
    write_json(rid_path, picks)
    manifest["real_identity_domains"] = {
        "url": "derived: hand-picked from tranco-filtered.csv", "file": "real_identity_domains.json",
        "downloaded_at": today(), "derived_from": "tranco_filtered",
        "sha256": sha256_file(rid_path)}
    if entry.get("fallback"):
        manifest["real_identity_domains"]["fallback"] = True
    print("[ok]       real_identity_domains: " + ", ".join(f"{p['domain']}#{p['rank']}" for p in picks))

    if not entry.get("fallback"):
        write_identity_tiers(filtered, manifest, entry.get("list_id"))

    write_json(os.path.join(OUT_DIR, "manifest.json"), manifest)
    print(f"[done]     manifest written to {os.path.join(OUT_DIR, 'manifest.json')}")
    return 0


if __name__ == "__main__":
    if "--tiers-only" in sys.argv:
        raise SystemExit(tiers_only())
    raise SystemExit(main())
