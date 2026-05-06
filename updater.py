import os, hashlib, feedparser, requests
from datetime import datetime, timedelta
from dateutil import tz, parser as dparser
from google.oauth2 import service_account
from googleapiclient.discovery import build
import yaml

PARIS = tz.gettz("Europe/Paris")

def build_service():
creds = service_account.Credentials.from_service_account_file(
os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
scopes=["https://www.googleapis.com/auth/calendar&quot;]
)
return build("calendar", "v3", credentials=creds, cache_discovery=False)

def upsert(svc, cal_id, ev):
try:
return svc.events().update(calendarId=cal_id, eventId=ev["id"], body=ev).execute()
except:
return svc.events().insert(calendarId=cal_id, body=ev).execute()

def ensure_test_event(svc, cal_id):
nowp = datetime.now(PARIS)
tomorrow_9 = nowp.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
ev = {
"id": hashlib.sha1(("test-sync-"+tomorrow_9.strftime("%Y%m%d")).encode()).hexdigest()[:32],
"summary": "TEST sync – OK",
"start": {"dateTime": tomorrow_9.isoformat(), "timeZone": "Europe/Paris"},
"end": {"dateTime": (tomorrow_9 + timedelta(minutes=15)).isoformat(), "timeZone": "Europe/Paris"},
"description": "Événement de test pour valider la connexion."
}
upsert(svc, cal_id, ev)

def load_sources(path="sources.yml"):
if not os.path.exists(path): return []
with open(path, "r", encoding="utf-8") as f:
return yaml.safe_load(f) or []

def classify(title, desc):
t = f"{title} {desc}".lower()
if any(k in t for k in ["plf", "plfr", "plfss", "programme de stabilité", "pib", "ipc"]): return "BUDGET", 3
if any(k in t for k in ["budget", "déficit", "dette"]): return "BUDGET", 2
if any(k in t for k in ["pib", "inflation", "ipc", "chômage", "emploi", "salaires", "conjoncture"]): return "CONJONCTURE", 2
if any(k in t for k in ["retraites", "assurance chômage", "santé", "plfss"]): return "SOCIAL-BUDGET", 2
return "ECO", 1

def color_for(cat):
return {"BUDGET":"11","CONJONCTURE":"7","SOCIAL-BUDGET":"5","ECO":"9"}.get(cat,"9")

def parse_dt(s):
if not s: return None
dt = dparser.parse(s)
if not dt.tzinfo: dt = dt.replace(tzinfo=tz.UTC).astimezone(PARIS)
return dt

def uid(source, title, start_iso):
raw = f"{source}|{title}|{start_iso}"
return hashlib.sha1(raw.encode()).hexdigest()[:32]

def make_event(item):
dt_start = parse_dt(item.get("start",""))
dt_end = parse_dt(item.get("end","")) if item.get("end") else (dt_start + timedelta(hours=1) if dt_start else None)
cat, imp = classify(item.get("title",""), item.get("desc",""))
prefix = "[PRIOR] " if imp == 3 else ""
return {
"id": uid(item["source"], item["title"], dt_start.isoformat() if dt_start else ""),
"summary": f"{prefix}{item['title']}",
"description": f"{item.get('desc','')}\nSource: {item['source']}\nCatégorie: {cat} / Importance: {imp}\nLien: {item.get('link','')}",
"location": item.get("loc",""),
"colorId": color_for(cat),
"start": {"dateTime": dt_start.isoformat(), "timeZone": "Europe/Paris"} if dt_start else {"date": datetime.now(PARIS).date().isoformat()},
"end": {"dateTime": dt_end.isoformat(), "timeZone": "Europe/Paris"} if dt_end else None,
"reminders": {"useDefault": False, "overrides": [{"method":"email","minutes":10080},{"method":"popup","minutes":1440},{"method":"popup","minutes":0}]}
}

def fetch_items(src):
items = []
if src["type"] == "rss":
d = feedparser.parse(src["url"])
for e in d.entries:
items.append({
"source": src["name"],
"title": getattr(e, "title", ""),
"start": getattr(e, "published", getattr(e, "updated", "")),
"end": "",
"desc": getattr(e, "summary", ""),
"loc": "",
"link": getattr(e, "link", "")
})
return items

def main():
cal_id = os.environ["CALENDAR_ID"]
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "sa.json")
svc = build_service()
ensure_test_event(svc, cal_id)
for s in load_sources():
for it in fetch_items(s):
ev = make_event(it)
upsert(svc, cal_id, ev)

if name == "main":
main()
