"""Phase 1 backend regression — Clock weekly summary, YTD accrual,
admin entry edit/delete, Bank Holidays. Public proxy URL only."""
import os
import sys
import json
import math
import uuid
import time
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@company.com"
ADMIN_PASS = "Admin@123"
STAFF_EMAIL = "jane@company.com"
STAFF_PASS = "Staff@123"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "staff_app")
mc = MongoClient(MONGO_URL)
db = mc[DB_NAME]

PASS = 0
FAIL = 0
FAILED = []


def _log(ok: bool, msg: str):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  ❌ {msg}")


def login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=15)
    r.raise_for_status()
    return r.json()


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    print("\n=== Phase 1 backend test ===")
    print(f"BASE={BASE}")
    a = login(ADMIN_EMAIL, ADMIN_PASS)
    s = login(STAFF_EMAIL, STAFF_PASS)
    admin_tok = a["access_token"]
    staff_tok = s["access_token"]
    admin_id = a["user"]["id"]
    jane_id = s["user"]["id"]
    print(f"  admin_id={admin_id} jane_id={jane_id}")

    # ---------------- A. Weekly summary ----------------
    print("\n[A] Weekly summary")
    # A1 — admin default
    r = requests.get(f"{BASE}/clock/weekly-summary", headers=H(admin_tok), timeout=15)
    _log(r.status_code == 200, f"A1 admin default 200 (got {r.status_code})")
    body = r.json() if r.status_code == 200 else {}
    _log(isinstance(body.get("days"), list) and len(body.get("days", [])) == 7,
         f"A1 days len=7 (got {len(body.get('days', []))})")
    try:
        d = datetime.strptime(body.get("week_start", ""), "%Y-%m-%d")
        _log(d.weekday() == 0, f"A1 week_start is a Monday (got {body.get('week_start')} weekday={d.weekday()})")
    except Exception as e:
        _log(False, f"A1 week_start parse failed: {e}")
    for k in ("total_hours", "break_hours", "net_hours", "accrued_holiday_hours"):
        _log(isinstance(body.get(k), (int, float)), f"A1 {k} is numeric (got {type(body.get(k)).__name__}={body.get(k)})")

    # A2 — staff default
    r = requests.get(f"{BASE}/clock/weekly-summary", headers=H(staff_tok), timeout=15)
    _log(r.status_code == 200, f"A2 staff default 200 (got {r.status_code})")
    b = r.json() if r.status_code == 200 else {}
    _log(b.get("user_id") == jane_id, f"A2 user_id == jane (got {b.get('user_id')})")

    # A3 — staff passing user_id of admin should be ignored, returns jane
    r = requests.get(f"{BASE}/clock/weekly-summary?user_id={admin_id}", headers=H(staff_tok), timeout=15)
    _log(r.status_code == 200, f"A3 staff ?user_id=admin 200 (got {r.status_code})")
    _log(r.json().get("user_id") == jane_id, f"A3 returns jane's user_id (got {r.json().get('user_id')})")

    # A4 — admin passing user_id=jane returns jane
    r = requests.get(f"{BASE}/clock/weekly-summary?user_id={jane_id}", headers=H(admin_tok), timeout=15)
    _log(r.status_code == 200, f"A4 admin ?user_id=jane 200 (got {r.status_code})")
    _log(r.json().get("user_id") == jane_id, f"A4 returns jane (got {r.json().get('user_id')})")

    # A5 — specific past week 2025-06-02
    r = requests.get(f"{BASE}/clock/weekly-summary?week_start=2025-06-02", headers=H(admin_tok), timeout=15)
    _log(r.status_code == 200, f"A5 specific week 200 (got {r.status_code})")
    bb = r.json()
    _log(bb.get("week_start") == "2025-06-02", f"A5 week_start=2025-06-02 (got {bb.get('week_start')})")
    _log(bb.get("week_end") == "2025-06-08", f"A5 week_end=2025-06-08 (got {bb.get('week_end')})")

    # A6 — garbage
    r = requests.get(f"{BASE}/clock/weekly-summary?week_start=garbage", headers=H(admin_tok), timeout=15)
    _log(r.status_code == 400, f"A6 garbage week_start → 400 (got {r.status_code})")

    # ---------------- B. Accrual math (seed via Mongo) ----------------
    print("\n[B] Accrual math (Mongo seed for Jane in current week)")
    # Find current week start (UTC Monday)
    ref = datetime.now(timezone.utc)
    monday = (ref - timedelta(days=ref.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    # Pre-clean any test markers
    db.clock_entries.delete_many({"user_id": jane_id, "test_marker": "phase1"})
    # Seed: 8h shift starting Mon 09:00 UTC and 2h shift starting Mon 18:00 UTC.
    # If current day is Monday, that's fine — both fit within the week.
    e1_in = monday + timedelta(hours=9)
    e1_out = e1_in + timedelta(hours=8)
    e2_in = monday + timedelta(hours=18)
    e2_out = e2_in + timedelta(hours=2)
    seeded_ids = []
    for cin, cout in [(e1_in, e1_out), (e2_in, e2_out)]:
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": jane_id,
            "user_name": "Jane Doe",
            "clock_in": cin,
            "clock_out": cout,
            "duration_seconds": int((cout - cin).total_seconds()),
            "test_marker": "phase1",
        }
        db.clock_entries.insert_one(doc)
        seeded_ids.append(doc["id"])
    try:
        r = requests.get(f"{BASE}/clock/weekly-summary?user_id={jane_id}", headers=H(admin_tok), timeout=15)
        _log(r.status_code == 200, f"B0 200 (got {r.status_code})")
        b = r.json()
        # NOTE: there might be other real entries this week — so we additionally compute the EXPECTED
        # math given only the seed by deleting any other current-week entries for Jane first? No —
        # safer: instead check the DAY's bucket. The day's hours should be at least 10h (sum of our seed).
        # Re-seed in an isolated way: delete any non-test entries this week for Jane first, then put back.
        pass
    except Exception:
        pass

    # Isolate: store and remove existing non-test current-week entries
    other_entries = list(db.clock_entries.find({
        "user_id": jane_id,
        "clock_in": {"$gte": monday, "$lt": monday + timedelta(days=7)},
        "test_marker": {"$ne": "phase1"},
    }))
    if other_entries:
        ids = [o["_id"] for o in other_entries]
        db.clock_entries.delete_many({"_id": {"$in": ids}})

    try:
        r = requests.get(f"{BASE}/clock/weekly-summary?user_id={jane_id}", headers=H(admin_tok), timeout=15)
        b = r.json()
        _log(b.get("total_hours") == 10.0,
             f"B1 total_hours=10.0 (got {b.get('total_hours')})")
        _log(b.get("break_hours") == 0.5,
             f"B2 break_hours=0.5 (got {b.get('break_hours')})")
        _log(b.get("net_hours") == 9.5,
             f"B3 net_hours=9.5 (got {b.get('net_hours')})")
        _log(b.get("accrued_holiday_hours") == round(9.5 / 3.0, 2),
             f"B4 accrued_holiday_hours=3.17 (got {b.get('accrued_holiday_hours')})")
        # Also the Monday bucket should be 10.0 (since both seeds are on Monday UTC)
        mon_str = monday.strftime("%Y-%m-%d")
        day_hours = next((d["hours"] for d in b.get("days", []) if d["date"] == mon_str), None)
        _log(day_hours == 10.0, f"B5 Monday bucket=10.0 (got {day_hours})")
        # YTD accrual (admin can pass user_id)
        ry = requests.get(f"{BASE}/clock/accrual?user_id={jane_id}&year={ref.year}",
                          headers=H(admin_tok), timeout=15)
        _log(ry.status_code == 200, f"B6 /accrual 200 (got {ry.status_code})")
        yb = ry.json()
        _log("worked_hours" in yb and "accrued_holiday_hours" in yb and "days" not in yb,
             f"B7 accrual shape OK (got keys={list(yb.keys())})")
        _log(yb.get("worked_hours", 0) >= 10.0,
             f"B8 YTD worked_hours>=10 (got {yb.get('worked_hours')})")
    finally:
        # Cleanup seeded entries
        db.clock_entries.delete_many({"user_id": jane_id, "test_marker": "phase1"})
        # Restore other entries
        if other_entries:
            for o in other_entries:
                o.pop("_id", None)
                db.clock_entries.insert_one(o)

    # ---------------- C. Admin clock entry edit/delete ----------------
    print("\n[C] Admin clock entry edit/delete")
    # Ensure admin not already clocked in — if so, clock out first
    rs = requests.get(f"{BASE}/clock/status", headers=H(admin_tok), timeout=15)
    if rs.json().get("clocked_in"):
        requests.post(f"{BASE}/clock/out", headers=H(admin_tok), json={}, timeout=15)
    # C1 — clock in/out as admin
    r = requests.post(f"{BASE}/clock/in", headers=H(admin_tok), json={}, timeout=15)
    _log(r.status_code == 200, f"C1a clock in 200 (got {r.status_code} {r.text[:120]})")
    r = requests.post(f"{BASE}/clock/out", headers=H(admin_tok), json={}, timeout=15)
    _log(r.status_code == 200, f"C1b clock out 200 (got {r.status_code})")
    eid = r.json().get("id")
    _log(bool(eid), f"C1c entry id captured ({eid})")

    # C2 — patch clock_in to 2h ago, clock_out=now
    now_iso = datetime.now(timezone.utc).isoformat()
    two_h_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    r = requests.patch(f"{BASE}/clock/entries/{eid}", headers=H(admin_tok),
                       json={"clock_in": two_h_ago, "clock_out": now_iso}, timeout=15)
    _log(r.status_code == 200, f"C2 admin PATCH 200 (got {r.status_code} {r.text[:120]})")
    pb = r.json() if r.status_code == 200 else {}
    dur = pb.get("duration_seconds", 0)
    _log(abs(dur - 7200) <= 60, f"C2 duration_seconds≈7200 (got {dur})")
    _log("edited_at" in pb, f"C2 edited_at present (keys={[k for k in pb.keys() if 'edit' in k]})")

    # C3 — staff tries to PATCH → 403
    r = requests.patch(f"{BASE}/clock/entries/{eid}", headers=H(staff_tok),
                       json={"note": "hi"}, timeout=15)
    _log(r.status_code == 403, f"C3 staff PATCH → 403 (got {r.status_code})")

    # C4 — admin PATCH invalid timestamp → 400
    r = requests.patch(f"{BASE}/clock/entries/{eid}", headers=H(admin_tok),
                       json={"clock_in": "not-a-date"}, timeout=15)
    _log(r.status_code == 400, f"C4 invalid timestamp → 400 (got {r.status_code})")

    # C5 — staff DELETE → 403
    r = requests.delete(f"{BASE}/clock/entries/{eid}", headers=H(staff_tok), timeout=15)
    _log(r.status_code == 403, f"C5 staff DELETE → 403 (got {r.status_code})")

    # C6 — admin DELETE → 200 {ok:true}
    r = requests.delete(f"{BASE}/clock/entries/{eid}", headers=H(admin_tok), timeout=15)
    _log(r.status_code == 200 and r.json().get("ok") is True,
         f"C6 admin DELETE → 200 {{ok:true}} (got {r.status_code} {r.text[:80]})")

    # C7 — admin DELETE again → 404
    r = requests.delete(f"{BASE}/clock/entries/{eid}", headers=H(admin_tok), timeout=15)
    _log(r.status_code == 404, f"C7 DELETE again → 404 (got {r.status_code})")

    # ---------------- D. Bank Holidays ----------------
    print("\n[D] Bank Holidays")
    # D1 — admin GET 2026
    r = requests.get(f"{BASE}/bank-holidays?year=2026", headers=H(admin_tok), timeout=15)
    _log(r.status_code == 200, f"D1 GET 2026 200 (got {r.status_code})")
    arr = r.json() if r.status_code == 200 else []
    _log(len(arr) >= 10, f"D1 ≥10 entries (got {len(arr)})")
    required = {"id", "date", "name", "hours", "country", "custom", "created_at"}
    ok_fields = all(required.issubset(set(h.keys())) for h in arr)
    _log(ok_fields, "D1 all entries have required fields")
    countries = {h.get("country") for h in arr}
    _log(countries == {"IE"}, f"D1 country='IE' (got {countries})")
    customs = {h.get("custom") for h in arr}
    _log(False in customs, f"D1 contains custom=false entries (got customs={customs})")

    # D2 — key dates 2026-03-17 + 2026-12-25
    by_date = {h["date"]: h for h in arr}
    _log(by_date.get("2026-03-17", {}).get("name") == "St Patrick's Day",
         f"D2a 2026-03-17 = St Patrick's Day (got {by_date.get('2026-03-17')})")
    _log(by_date.get("2026-12-25", {}).get("name") == "Christmas Day",
         f"D2b 2026-12-25 = Christmas Day (got {by_date.get('2026-12-25')})")

    # D3 — admin POST custom holiday
    # First clean any preexisting custom 2026-11-30
    db.bank_holidays.delete_many({"date": "2026-11-30"})
    r = requests.post(f"{BASE}/bank-holidays", headers=H(admin_tok),
                      json={"date": "2026-11-30", "name": "Company Day", "hours": 6}, timeout=15)
    _log(r.status_code == 200, f"D3 admin POST custom → 200 (got {r.status_code} {r.text[:120]})")
    pb = r.json() if r.status_code == 200 else {}
    _log(pb.get("custom") is True, f"D3 custom=true (got {pb.get('custom')})")
    _log(pb.get("hours") == 6.0, f"D3 hours=6.0 (got {pb.get('hours')})")
    bid = pb.get("id")

    # D4 — duplicate → 400
    r = requests.post(f"{BASE}/bank-holidays", headers=H(admin_tok),
                      json={"date": "2026-11-30", "name": "Company Day Dupe", "hours": 8}, timeout=15)
    _log(r.status_code == 400, f"D4 duplicate POST → 400 (got {r.status_code})")

    # D5 — staff POST → 403
    r = requests.post(f"{BASE}/bank-holidays", headers=H(staff_tok),
                      json={"date": "2026-11-29", "name": "Should fail", "hours": 8}, timeout=15)
    _log(r.status_code == 403, f"D5 staff POST → 403 (got {r.status_code})")

    # D6 — admin DELETE
    if bid:
        r = requests.delete(f"{BASE}/bank-holidays/{bid}", headers=H(admin_tok), timeout=15)
        _log(r.status_code == 200, f"D6 admin DELETE → 200 (got {r.status_code})")

    # D7 — admin GET 2025
    r = requests.get(f"{BASE}/bank-holidays?year=2025", headers=H(admin_tok), timeout=15)
    _log(r.status_code == 200, f"D7 GET 2025 → 200 (got {r.status_code})")
    arr25 = r.json() if r.status_code == 200 else []
    _log(len(arr25) >= 10, f"D7 ≥10 entries 2025 (got {len(arr25)})")
    by25 = {h["date"]: h for h in arr25}
    _log(by25.get("2025-03-17", {}).get("name") == "St Patrick's Day",
         f"D7 2025-03-17 = St Patrick's Day (got {by25.get('2025-03-17')})")

    # ---------------- E. Auth guards ----------------
    print("\n[E] Auth guards")
    # Unauthenticated GET
    r = requests.get(f"{BASE}/clock/weekly-summary", timeout=15)
    _log(r.status_code in (401, 403), f"E1 unauth weekly-summary → 401/403 (got {r.status_code})")
    r = requests.get(f"{BASE}/bank-holidays", timeout=15)
    _log(r.status_code in (401, 403), f"E2 unauth bank-holidays → 401/403 (got {r.status_code})")
    r = requests.get(f"{BASE}/clock/accrual", timeout=15)
    _log(r.status_code in (401, 403), f"E3 unauth accrual → 401/403 (got {r.status_code})")
    # Staff PATCH/DELETE clock entries already exercised (C3 & C5)
    # Staff DELETE bank-holiday → 403
    # Seed a dummy custom holiday as admin, then staff delete should 403, then admin cleanup
    db.bank_holidays.delete_many({"date": "2027-07-04"})
    r = requests.post(f"{BASE}/bank-holidays", headers=H(admin_tok),
                      json={"date": "2027-07-04", "name": "Independence-test", "hours": 8}, timeout=15)
    bid = r.json().get("id") if r.status_code == 200 else None
    if bid:
        r = requests.delete(f"{BASE}/bank-holidays/{bid}", headers=H(staff_tok), timeout=15)
        _log(r.status_code == 403, f"E4 staff DELETE bank-holiday → 403 (got {r.status_code})")
        requests.delete(f"{BASE}/bank-holidays/{bid}", headers=H(admin_tok), timeout=15)

    print(f"\n=== RESULT === {PASS} passed, {FAIL} failed")
    if FAILED:
        print("\nFailures:")
        for f in FAILED:
            print(f"  - {f}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
