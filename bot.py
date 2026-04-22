"""
LeadRadar v9 — MONEY HUNTER (Railway Edition)
==============================================
Sources that ACTUALLY work on Railway cloud IPs:

1. Reddit OAuth2      — 60+ subreddits, 100 req/min FREE
2. HackerNews API     — Algolia API, no auth needed
3. Adzuna Jobs API    — FREE 50k calls/month, EU jobs
4. Jooble API         — FREE job/service listings EU
5. Google Alerts RSS  — paste your RSS URLs

SETUP:
- Reddit: railway vars REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
          REDDIT_USERNAME, REDDIT_PASSWORD
- Adzuna: free signup at developer.adzuna.com → get APP_ID + API_KEY
          railway vars ADZUNA_APP_ID, ADZUNA_API_KEY
- Jooble: free key at jooble.org/api → railway var JOOBLE_API_KEY
- HackerNews: zero setup needed
- Google Alerts: add RSS URLs in GOOGLE_ALERTS list below
"""

import re, time, os, hashlib, logging, requests, feedparser
from datetime import datetime, timezone

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8788839173:AAHhd8sQlMnzG4_c2cdOhqJjCjHqfrkdGbw")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID",   "8550794773")

REDDIT_CLIENT_ID     = os.environ.get("REDDIT_CLIENT_ID",     "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME      = os.environ.get("REDDIT_USERNAME",      "")
REDDIT_PASSWORD      = os.environ.get("REDDIT_PASSWORD",      "")

ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID",  "")
ADZUNA_API_KEY = os.environ.get("ADZUNA_API_KEY", "")
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY", "")

MIN_SCORE     = 30
MAX_AGE_H     = 6
SCAN_INTERVAL = 120
DAILY_LIMIT   = 200

def _get_proxies():
    p = (os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or
         os.environ.get("http_proxy")  or os.environ.get("HTTP_PROXY"))
    return {"http": p, "https": p} if p else None
PROXIES = _get_proxies()

# ══════════════════════════════════════════════
#  BUYING INTENT PATTERNS
# ══════════════════════════════════════════════
PATTERNS = {
    "wholesale": {
        "emoji": "📦", "value": 100,
        "rx": [
            r'\b(looking\s+for|need|seeking|sourcing|find)\s+(a\s+)?(supplier|manufacturer|vendor|distributor|wholesaler|factory|OEM)\b',
            r'\b(bulk\s+(order|buy|purchase)|wholesale\s+(price|supplier|order)|minimum\s+order|moq)\b',
            r'\b(private\s+label|white\s+label|contract\s+manufactur|rfq|request\s+for\s+quote)\b',
            r'\b(import\s+from|export\s+to|sourcing\s+from|trade\s+terms|incoterms)\b',
            r'\bprice\s+per\s+(unit|kg|ton|pallet|piece|liter|meter)\b',
            r'\b(caut|zoek|suche|cherche|szukam)\s+(furnizor|leverancier|lieferant|fournisseur|dostawcy)\b',
            r'\b(lieferant|leverancier|fournisseur)\s+(gesucht|gezocht)\b',
        ]
    },
    "legal": {
        "emoji": "⚖️", "value": 500,
        "rx": [
            r'\b(need|looking\s+for|want|hiring)\s+(a\s+)?(lawyer|solicitor|attorney|barrister|notary|legal\s+(counsel|rep|firm|help|advice))\b',
            r'\b(contract\s+(review|drafting|dispute)|employment\s+law|trademark|ip\s+lawyer)\b',
            r'\b(avocat|rechtsanwalt|advocaat|avvocato|abogado|prawnik|notaire)\b',
            r'\b(caut\s+avocat|suche\s+rechtsanwalt|zoek\s+advocaat|cherche\s+avocat|szukam\s+prawnika)\b',
            r'\b(business\s+lawyer|corporate\s+(lawyer|counsel)|legal\s+advice\s+for\s+(startup|business))\b',
        ]
    },
    "solar": {
        "emoji": "☀️", "value": 250,
        "rx": [
            r'\b(solar\s+(panel|install|system|quote|energy|array)|photovoltaic|pv\s+system)\b',
            r'\b(solar\s+(installer|company|contractor)|getting\s+solar|install\s+solar)\b',
            r'\b(heat\s+pump\s+(install|quote|system|replacement)|ground\s+source\s+heat\s+pump)\b',
            r'\b(solaranlage|zonnepanelen|panouri\s+solare)\b',
            r'\b(battery\s+storage|home\s+battery|powerwall|ev\s+charging\s+install)\b',
        ]
    },
    "construction": {
        "emoji": "🏗️", "value": 150,
        "rx": [
            r'\b(need|looking\s+for|hiring)\s+(a\s+)?(contractor|builder|electrician|plumber|roofer|tiler|plasterer|carpenter|surveyor)\b',
            r'\b(house|office|shop|property)\s+(renovation|refurb|extension|conversion|fit.?out)\b',
            r'\bget(ting)?\s+quotes?\s+for\s+(building|renovation|extension|refurb|construction)\b',
            r'\burgently?\s+need\s+(a\s+)?(plumber|electrician|builder|contractor|roofer)\b',
            r'\b(caut\s+constructor|suche\s+bauunternehmen|zoek\s+aannemer|cherche\s+entrepreneur)\b',
        ]
    },
    "property": {
        "emoji": "🏠", "value": 300,
        "rx": [
            r'\b(looking\s+to\s+(buy|purchase)|want\s+to\s+(buy|purchase))\s+.{0,20}(property|warehouse|office|flat|house|apartment|land)\b',
            r'\b(commercial\s+property|office\s+space|warehouse\s+space)\s+(needed|wanted|for\s+(rent|sale|lease))\b',
            r'\b(need|looking\s+for)\s+(a\s+)?(warehouse|office|factory|storage)\s+(space|premises)\b',
            r'\b(real\s+estate\s+(agent|broker|deal)|property\s+investment|buy.to.let)\b',
        ]
    },
    "finance": {
        "emoji": "💰", "value": 350,
        "rx": [
            r'\b(business\s+loan|commercial\s+mortgage|asset\s+finance|invoice\s+factoring|bridging\s+loan)\b',
            r'\b(looking\s+for|need)\s+(a\s+)?(financial\s+(advisor|broker|consultant)|accountant|bookkeeper)\b',
            r'\b(vat\s+(registration|advice)|tax\s+(advice|planning|consultant))\b',
            r'\b(raising\s+capital|seed\s+funding|looking\s+for\s+investors?|investment\s+round)\b',
            r'\b(need|seeking)\s+(a\s+)?(business\s+loan|working\s+capital|startup\s+funding)\b',
        ]
    },
    "tech": {
        "emoji": "💻", "value": 200,
        "rx": [
            r'\b(need|looking\s+for|hiring)\s+(a\s+)?(developer|programmer|dev\s+team|software\s+(agency|house)|tech\s+co.?founder)\b',
            r'\b(need|want)\s+(a\s+)?(website|web\s+app|mobile\s+app|saas|mvp|ecommerce\s+store)\s+(built|developed|created|made)\b',
            r'\b(need\s+(digital\s+marketing|seo|ppc|google\s+ads|social\s+media\s+management))\b',
            r'\b(looking\s+for\s+(web\s+design|frontend|backend|full.?stack|react|python|django)\s+(dev|developer|agency))\b',
        ]
    },
    "digital_products": {
        "emoji": "🗂️", "value": 40,
        "rx": [
            r'\b(looking\s+for|need|where\s+(can\s+i|to)\s+(find|get|buy))\s+(a\s+)?(template|spreadsheet|planner|tracker|worksheet|checklist|guide|ebook|printable)\b',
            r'\b(gdpr\s+(template|policy|compliance|document)|privacy\s+policy\s+template|dpa\s+template)\b',
            r'\b(budget\s+(template|spreadsheet|tracker)|expense\s+tracker|financial\s+planner\s+template)\b',
            r'\b(habit\s+tracker|daily\s+planner|weekly\s+planner|productivity\s+(template|planner))\b',
            r'\b(business\s+plan\s+template|sop\s+template|contract\s+template|invoice\s+template)\b',
            r'\b(compliance\s+(template|checklist|kit)|dora\s+compliance|gdpr\s+kit)\b',
            r'\b(canva\s+template|notion\s+template|excel\s+template|google\s+sheets\s+template)\b',
        ]
    },
    "recruitment": {
        "emoji": "👔", "value": 120,
        "rx": [
            r'\b(we.?re\s+hiring|now\s+hiring|actively\s+hiring|currently\s+hiring)\b',
            r'\b(looking\s+for\s+(staff|employees|workers|candidates|talent))\b',
            r'\b(recruitment\s+(agency|partner)|staffing\s+(agency|firm))\b',
        ]
    },
    "manufacturing": {
        "emoji": "🏭", "value": 130,
        "rx": [
            r'\b(need|looking\s+for)\s+(a\s+)?(cnc|injection\s+mould|casting|forging|welding|3d\s+print)\s+(company|service|supplier)\b',
            r'\b(manufacturing\s+(partner|outsourc)|production\s+(outsourc|line))\b',
            r'\b(custom\s+(parts|components|tooling|mould)|bespoke\s+manufactur)\b',
        ]
    },
    "logistics": {
        "emoji": "🚚", "value": 110,
        "rx": [
            r'\b(need|looking\s+for)\s+(a\s+)?(freight|logistics|courier|3pl|haulage|shipping|transport)\s+(company|partner|service|quote)\b',
            r'\b(customs\s+(clearance|broker|agent)|freight\s+forwarder)\b',
        ]
    },
}

BOOSTERS = {
    r'\b\d{2,}[\s,]*(unit|piece|pcs|kg|ton|pallet)s?\b': 20,
    r'[€$£]\d+|\d+\s*(eur|usd|gbp|ron)\b': 20,
    r'\b(urgent|asap|immediately|this\s+week|deadline)\b': 20,
    r'\b(monthly|recurring|long.?term|ongoing\s+contract)\b': 15,
    r'\b(b2b|wholesale|commercial|enterprise)\b': 10,
    r'\b(ltd|gmbh|bv|srl|llc|plc|inc|nv|sa)\b': 10,
    r'\b(europe|european|eu\s+market|benelux|dach)\b': 10,
}

NOISE = [
    r'\b(my|our)\s+(cat|dog|kitten|puppy|rabbit)\b',
    r'\b(tube|train|bus|metro)\s+strike\b',
    r'\b(netflix|disney|hbo|streaming|movie|series)\b',
    r'\b(recipe|baking|cooking|restaurant\s+review)\b',
    r'\b(venting|need\s+to\s+rant|feeling\s+(lost|hopeless|depressed|anxious))\b',
]

def is_noise(text):
    return any(re.search(p, text.lower(), re.I) for p in NOISE)

def score(text):
    if not text or len(text) < 20: return {}
    lo = text.lower()
    best, best_s, best_m = None, 0, []
    for name, cfg in PATTERNS.items():
        s, m = 0, []
        for rx in cfg["rx"]:
            if re.search(rx, lo, re.I):
                s += 40; m.append(rx)
        if s > best_s:
            best, best_s, best_m = name, s, m
    if best_s == 0 or is_noise(text): return {}
    for rx, bonus in BOOSTERS.items():
        if re.search(rx, lo, re.I): best_s += bonus
    if len(text) < 50: best_s = int(best_s * 0.75)
    cfg = PATTERNS[best]
    return {"score": min(best_s, 100), "niche": best,
            "value": cfg["value"], "emoji": cfg["emoji"], "matched": best_m[:2]}

def age_unix(ts):
    try:
        m = (datetime.now(timezone.utc).timestamp() - float(ts)) / 60
        return int(m) if 0 <= m <= MAX_AGE_H * 60 else None
    except: return None

def age_rss(entry):
    for f in ("published", "updated", "created"):
        raw = entry.get(f)
        if not raw: continue
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(raw)
            m  = (datetime.now(timezone.utc).timestamp() - dt.timestamp()) / 60
            return int(m) if 0 <= m <= MAX_AGE_H * 60 else None
        except: pass
    return None

def fmt(m):
    if m is None: return "recent"
    return f"{m}m ago" if m < 60 else f"{m//60}h{m%60:02d}m ago"

seen = set()
daily_count = 0
reset_day = None

def is_new(uid):
    global daily_count, reset_day
    today = datetime.now().date()
    if today != reset_day:
        daily_count = 0; reset_day = today; seen.clear()
    if daily_count >= DAILY_LIMIT or uid in seen: return False
    seen.add(uid); return True

def send(lead):
    global daily_count
    sc   = lead["score"]
    fire = "🔥" if sc >= 75 else "🎯" if sc >= 50 else "📌"
    kws  = " · ".join(re.sub(r'[\(\)\[\]\?\+\*\\\^\$\|]|\\b','',m)[:40] for m in lead["matched"][:2]) or "buying intent"
    txt  = lead["text"][:700]
    url  = lead.get("url","")
    lnk  = f'\n🔗 <a href="{url}">Open</a>' if url else ""
    msg  = (f"{fire} <b>LEAD {sc}%</b> {lead['emoji']}\n"
            f"🕐 {lead['age']}  ·  🌐 {lead['source']}\n\n"
            f"<b>{lead['niche'].upper()}</b> — Est. €{lead['value']:,}\n"
            f"👤 {lead['author']}\n\n"
            f"💬 <i>{txt}</i>\n\n"
            f"🔑 {kws}{lnk}\n"
            f"──────────────────\n/reply  /save  /ignore")
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT, "text": msg,
                                "parse_mode": "HTML", "disable_web_page_preview": False},
                          proxies=PROXIES, timeout=15)
        r.raise_for_status()
        daily_count += 1
        log.info(f"✅ [{sc}%|{lead['age']}|{lead['niche']}] {lead['source'][:25]} — {txt[:50]}...")
        return True
    except Exception as e:
        log.error(f"Telegram: {e}"); return False

def notify(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"},
                      proxies=PROXIES, timeout=15)
    except: pass

def process(text, source, author, url, uid, age_m):
    if not text or len(text) < 20: return False
    if not is_new(uid): return False
    r = score(text)
    if not r or r["score"] < MIN_SCORE: return False
    return send({**r, "source": source, "author": author,
                 "text": text.strip(), "url": url, "age": fmt(age_m)})

# ══════════════════════════════════════════════
#  SOURCE 1: REDDIT OAuth2
# ══════════════════════════════════════════════
_rt = ""; _rt_exp = 0.0
_rh = {"User-Agent": "LeadRadar/9.0 by u/LeadRadarBot"}

SUBREDDITS = [
    "forhire","slavelabour","hiring","WorkOnline","Upwork","freelance",
    "digitalnomad","entrepreneur","smallbusiness","ecommerce","startups",
    "business","manufacturing","b2b","wholesale","supplychain","ImportExport",
    "dropshipping","AmazonSeller","legaladviceeurope","LegalAdviceUK",
    "legaladvice","solar","heatpumps","solarenergy","GreenEnergy","HVAC",
    "RealEstate","realestateinvesting","HousingUK","CommercialRealEstate",
    "HomeImprovement","DIY","renovation","Plumbing","askanelectrician",
    "webdev","web_design","SaaS","AppDevelopment","indiehackers",
    "eupersonalfinance","UKPersonalFinance","MortgageUK",
    "germany","Romania","poland","belgium","Austria","Netherlands",
    "france","italy","spain","portugal","czech","hungary",
    "logistics","procurement","Etsy","etsysellers",
]

def _reddit_token():
    global _rt, _rt_exp
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        return False
    try:
        r = requests.post("https://www.reddit.com/api/v1/access_token",
                          auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
                          data={"grant_type":"password","username":REDDIT_USERNAME,"password":REDDIT_PASSWORD},
                          headers=_rh, timeout=15)
        r.raise_for_status()
        d = r.json()
        _rt = d["access_token"]
        _rt_exp = time.time() + d.get("expires_in", 3600) - 60
        log.info("Reddit OAuth ✅"); return True
    except Exception as e:
        log.error(f"Reddit OAuth: {e}"); return False

def _reddit_hdrs():
    global _rt, _rt_exp
    if time.time() >= _rt_exp:
        if not _reddit_token(): return None
    return {**_rh, "Authorization": f"bearer {_rt}"}

def scan_reddit():
    hdrs = _reddit_hdrs()
    if not hdrs:
        log.warning("Reddit skipped — add REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD to Railway vars")
        return 0
    found = 0
    for sub in SUBREDDITS:
        try:
            r = requests.get(f"https://oauth.reddit.com/r/{sub}/new?limit=25",
                             headers=hdrs, timeout=15)
            if r.status_code == 401: _reddit_token(); hdrs = _reddit_hdrs(); continue
            if r.status_code == 429: time.sleep(30); continue
            if r.status_code != 200: continue
            rem = int(r.headers.get("X-Ratelimit-Remaining", 100))
            if rem < 5: time.sleep(float(r.headers.get("X-Ratelimit-Reset", 60)))
            for p in r.json().get("data",{}).get("children",[]):
                d   = p.get("data",{})
                age = age_unix(d.get("created_utc",0))
                if age is None: continue
                uid = f"r_{d.get('id','')}"
                txt = f"{d.get('title','')} {d.get('selftext','')}".strip()
                url = f"https://reddit.com{d.get('permalink','')}"
                if process(txt, f"Reddit r/{sub}", f"u/{d.get('author','?')}", url, uid, age):
                    found += 1
        except Exception as e:
            log.debug(f"r/{sub}: {e}")
        time.sleep(1.0)
    log.info(f"Reddit: {found}"); return found

# ══════════════════════════════════════════════
#  SOURCE 2: HACKERNEWS (Algolia API — no auth)
# ══════════════════════════════════════════════
def scan_hackernews():
    found = 0
    try:
        r = requests.get("https://hn.algolia.com/api/v1/search?query=who+is+hiring&tags=story&hitsPerPage=3", timeout=15)
        if r.status_code != 200: return 0
        for hit in r.json().get("hits",[]):
            sid = hit.get("objectID")
            if not sid: continue
            if (datetime.now(timezone.utc).timestamp() - hit.get("created_at_i",0)) / 86400 > 35: continue
            cr = requests.get(f"https://hn.algolia.com/api/v1/items/{sid}", timeout=15)
            if cr.status_code != 200: continue
            for c in cr.json().get("children",[])[:100]:
                txt = re.sub(r'<[^>]+',' ', c.get("text","")).strip()
                if len(txt) < 40: continue
                uid = f"hn_{c.get('id','')}"
                a   = age_unix(c.get("created_at_i",0))
                url = f"https://news.ycombinator.com/item?id={c.get('id','')}"
                if process(txt, "HackerNews", "HN", url, uid, a): found += 1
            time.sleep(1.0)
    except Exception as e: log.debug(f"HN: {e}")
    log.info(f"HackerNews: {found}"); return found

# ══════════════════════════════════════════════
#  SOURCE 3: ADZUNA API (free, no IP blocking)
#  Signup: developer.adzuna.com → free 50k calls/month
#  Set: ADZUNA_APP_ID + ADZUNA_API_KEY in Railway vars
# ══════════════════════════════════════════════
ADZUNA_COUNTRIES = ["gb","de","nl","fr","pl","at","be","it","es"]
ADZUNA_KEYWORDS  = [
    "looking for supplier","need manufacturer","bulk order",
    "need developer","need contractor","need lawyer",
    "solar installation","heat pump","gdpr template",
    "caut furnizor","suche lieferant","zoek leverancier",
]

def scan_adzuna():
    if not ADZUNA_APP_ID or not ADZUNA_API_KEY:
        log.debug("Adzuna skipped — set ADZUNA_APP_ID and ADZUNA_API_KEY")
        return 0
    found = 0
    for country in ADZUNA_COUNTRIES:
        for kw in ADZUNA_KEYWORDS[:4]:
            try:
                r = requests.get(
                    f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                    params={"app_id": ADZUNA_APP_ID, "app_key": ADZUNA_API_KEY,
                            "what": kw, "results_per_page": 10,
                            "sort_by": "date", "max_days_old": 1},
                    timeout=15)
                if r.status_code != 200: continue
                for job in r.json().get("results",[]):
                    txt  = f"{job.get('title','')} {job.get('description','')[:500]}"
                    url  = job.get("redirect_url","")
                    uid  = f"az_{hashlib.md5(url.encode()).hexdigest()}"
                    created = job.get("created","")
                    a = None
                    if created:
                        try:
                            import dateutil.parser
                            dt = dateutil.parser.parse(created)
                            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                            a = int((datetime.now(timezone.utc).timestamp() - dt.timestamp()) / 60)
                            if a > MAX_AGE_H * 60: a = None
                        except: pass
                    company = job.get("company",{}).get("display_name","poster")
                    if process(txt, f"Adzuna {country.upper()}", company, url, uid, a):
                        found += 1
                time.sleep(0.5)
            except Exception as e: log.debug(f"Adzuna {country}/{kw}: {e}")
    log.info(f"Adzuna: {found}"); return found

# ══════════════════════════════════════════════
#  SOURCE 4: JOOBLE API (free, no IP blocking)
#  Get free key at: jooble.org/api
#  Set: JOOBLE_API_KEY in Railway vars
# ══════════════════════════════════════════════
JOOBLE_LOCATIONS = ["London","Berlin","Amsterdam","Paris","Warsaw",
                    "Vienna","Brussels","Bucharest","Rome","Madrid"]
JOOBLE_KEYWORDS  = [
    "need supplier","looking for contractor","need developer",
    "solar installer","need lawyer","bulk order","need manufacturer",
]

def scan_jooble():
    if not JOOBLE_API_KEY:
        log.debug("Jooble skipped — set JOOBLE_API_KEY")
        return 0
    found = 0
    for loc in JOOBLE_LOCATIONS[:5]:
        for kw in JOOBLE_KEYWORDS[:3]:
            try:
                r = requests.post(
                    f"https://jooble.org/api/{JOOBLE_API_KEY}",
                    json={"keywords": kw, "location": loc, "page": 1},
                    timeout=15)
                if r.status_code != 200: continue
                for job in r.json().get("jobs",[])[:10]:
                    txt  = f"{job.get('title','')} {job.get('snippet','')}"
                    url  = job.get("link","")
                    uid  = f"jb_{hashlib.md5(url.encode()).hexdigest()}"
                    updated = job.get("updated","")
                    a = None
                    if updated:
                        try:
                            import dateutil.parser
                            dt = dateutil.parser.parse(updated)
                            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                            a = int((datetime.now(timezone.utc).timestamp() - dt.timestamp()) / 60)
                            if a > MAX_AGE_H * 60: a = None
                        except: pass
                    if process(txt, f"Jooble {loc}", "poster", url, uid, a): found += 1
                time.sleep(0.5)
            except Exception as e: log.debug(f"Jooble {loc}/{kw}: {e}")
    log.info(f"Jooble: {found}"); return found

# ══════════════════════════════════════════════
#  SOURCE 5: GOOGLE ALERTS RSS
#  Setup: google.com/alerts → create alert →
#  Deliver to: RSS feed → copy URL → paste below
# ══════════════════════════════════════════════
GOOGLE_ALERTS = [
    ("looking for supplier",  "https://www.google.com/alerts/feeds/11153208817654572433/8448339046648067788"),
    ("need a manufacturer",   "https://www.google.com/alerts/feeds/11153208817654572433/3906776238236591017"),
    ("bulk order",            "https://www.google.com/alerts/feeds/11153208817654572433/18220794623728720681"),
    ("caut furnizor",         "https://www.google.com/alerts/feeds/11153208817654572433/7856377135374911869"),
    ("suche lieferant",       "https://www.google.com/alerts/feeds/11153208817654572433/18220794623728721387"),
    ("zoek leverancier",      "https://www.google.com/alerts/feeds/11153208817654572433/8512881618146256200"),
    ("need a lawyer",         "https://www.google.com/alerts/feeds/11153208817654572433/6254872757984268765"),
    ("solar installation",    "https://www.google.com/alerts/feeds/11153208817654572433/5694287621501170967"),
    ("gdpr template",         "https://www.google.com/alerts/feeds/11153208817654572433/1384381268658598876"),
    ("budget template",       "https://www.google.com/alerts/feeds/11153208817654572433/16326372038950064024"),
]

def scan_google_alerts():
    if not GOOGLE_ALERTS: return 0
    found = 0
    for name, url in GOOGLE_ALERTS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:20]:
                a   = age_rss(e)
                if a is None: continue
                uid = f"ga_{hashlib.md5(e.get('link','').encode()).hexdigest()}"
                txt = re.sub(r'<[^>]+',' ', f"{e.get('title','')} {e.get('summary','')}").strip()
                if process(txt, f"Google Alert: {name}", "web", e.get("link",""), uid, a):
                    found += 1
            time.sleep(0.8)
        except Exception as e: log.debug(f"Alert {name}: {e}")
    if found: log.info(f"Google Alerts: {found}")
    return found

# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

def full_scan():
    total  = scan_reddit()
    total += scan_hackernews()
    total += scan_adzuna()
    total += scan_jooble()
    total += scan_google_alerts()
    log.info(f"── Scan complete: {total} leads ──")
    return total

def main():
    log.info("LeadRadar v9 — MONEY HUNTER starting")

    reddit_ok  = all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD])
    adzuna_ok  = bool(ADZUNA_APP_ID and ADZUNA_API_KEY)
    jooble_ok  = bool(JOOBLE_API_KEY)
    alerts_ok  = bool(GOOGLE_ALERTS)

    if reddit_ok: _reddit_token()

    notify(
        "💰 <b>LeadRadar v9 — MONEY HUNTER</b>\n\n"
        "<b>Sources:</b>\n"
        f"{'✅' if reddit_ok else '⚠️'} Reddit OAuth {'(active)' if reddit_ok else '— add 4 Railway vars'}\n"
        f"✅ HackerNews (always on)\n"
        f"{'✅' if adzuna_ok else '⚙️'} Adzuna API {'(active)' if adzuna_ok else '— free signup: developer.adzuna.com'}\n"
        f"{'✅' if jooble_ok else '⚙️'} Jooble API {'(active)' if jooble_ok else '— free key: jooble.org/api'}\n"
        f"{'✅' if alerts_ok else '⚙️'} Google Alerts {'(active)' if alerts_ok else '— add RSS URLs in code'}\n\n"
        "<b>To activate Reddit (biggest source):</b>\n"
        "On Railway → Variables → Add:\n"
        "<code>REDDIT_CLIENT_ID</code>\n"
        "<code>REDDIT_CLIENT_SECRET</code>\n"
        "<code>REDDIT_USERNAME</code>\n"
        "<code>REDDIT_PASSWORD</code>\n\n"
        "<b>To get Reddit credentials:</b>\n"
        "Try on mobile browser or different computer:\n"
        "reddit.com/prefs/apps → create app → script\n\n"
        "<b>To activate Adzuna (EU jobs/services):</b>\n"
        "developer.adzuna.com → free signup → API key\n"
        "Add: <code>ADZUNA_APP_ID</code> + <code>ADZUNA_API_KEY</code>\n\n"
        "<b>To activate Jooble:</b>\n"
        "jooble.org/api → free key → Add: <code>JOOBLE_API_KEY</code>"
    )

    last = 0.0
    while True:
        if time.time() - last >= SCAN_INTERVAL:
            full_scan()
            last = time.time()
        time.sleep(15)

if __name__ == "__main__":
    main()
