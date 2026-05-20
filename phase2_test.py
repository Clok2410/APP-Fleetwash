"""Phase 2 backend regression — Profile editing + eligibility.

Hits the public proxy URL with the credentials in /app/memory/test_credentials.md.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "https://employee-connect-9.preview.emergentagent.com/api"

ADMIN = ("admin@company.com", "Admin@123")
STAFF = ("jane@company.com", "Staff@123")

PASS = 0
FAIL = 0
FAILURES: list = []


def _label(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
    if ok:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{name} — {detail}")


def login(email: str, password: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def H(tok: str):
    return {"Authorization": f"Bearer {tok}"}


def me(tok: str):
    return requests.get(f"{BASE}/auth/me", headers=H(tok), timeout=15).json()


def section(name: str):
    print(f"\n=== {name} ===")


# --- direct mongo seeding helpers for Sec D.3 ---
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "staff_app"


def _run_mongo(coro_factory):
    """Run a one-shot coroutine with a fresh AsyncIOMotorClient bound to a fresh loop.
    Avoids 'Event loop is closed' when calling multiple times across asyncio.run() calls.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        client = AsyncIOMotorClient(MONGO_URL, io_loop=loop)
        try:
            return loop.run_until_complete(coro_factory(client[DB_NAME]))
        finally:
            client.close()
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def seed_clock_entries(user_id: str, hours_list):
    """Insert clock_entries summing to provided hours within last 5 weeks. Returns inserted ids."""
    async def _do(mdb):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        ids = []
        offset_days = 7
        docs = []
        import uuid as _uuid
        for h in hours_list:
            cin = now - timedelta(days=offset_days)
            cout = cin + timedelta(hours=h)
            eid = str(_uuid.uuid4())
            ids.append(eid)
            docs.append({
                "id": eid,
                "user_id": user_id,
                "user_name": "Jane Doe",
                "clock_in": cin,
                "clock_out": cout,
                "duration_seconds": int(h * 3600),
                "note": "phase2-test-seed",
                "location": None,
            })
            offset_days += 2
        if docs:
            await mdb.clock_entries.insert_many(docs)
        return ids
    return _run_mongo(_do)


def remove_clock_entries(ids):
    async def _do(mdb):
        if ids:
            await mdb.clock_entries.delete_many({"id": {"$in": ids}})
    return _run_mongo(_do)


def main():
    section("Login + identity")
    admin_tok = login(*ADMIN)
    staff_tok = login(*STAFF)
    admin_me = me(admin_tok)
    staff_me = me(staff_tok)
    admin_id = admin_me["id"]
    staff_id = staff_me["id"]
    _label("Admin login + /auth/me", admin_me.get("role") == "admin", admin_id)
    _label("Staff login + /auth/me", staff_me.get("role") == "staff", staff_id)

    # ------------------------------------------------------------------
    section("A. Staff edits own profile")
    # A.1
    body = {"phone": "+353-87-555-9999", "dob": "1990-01-15", "pps_number": "1234567T"}
    r = requests.patch(f"{BASE}/users/me/profile", headers=H(staff_tok), json=body, timeout=15)
    _label("A.1 PATCH /users/me/profile → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        j = r.json()
        _label("A.1 phone updated", j.get("phone") == body["phone"], str(j.get("phone")))
        _label("A.1 dob updated", j.get("dob") == body["dob"], str(j.get("dob")))
        _label("A.1 pps_number updated", j.get("pps_number") == body["pps_number"], str(j.get("pps_number")))
        _label("A.1 no password_hash in response", "password_hash" not in j)

    # A.2 GET /auth/me reflects values
    j2 = me(staff_tok)
    _label("A.2 /auth/me phone match", j2.get("phone") == body["phone"], str(j2.get("phone")))
    _label("A.2 /auth/me dob match", j2.get("dob") == body["dob"], str(j2.get("dob")))
    _label("A.2 /auth/me pps_number match", j2.get("pps_number") == body["pps_number"], str(j2.get("pps_number")))

    # A.3 invalid dob → 400
    r = requests.patch(f"{BASE}/users/me/profile", headers=H(staff_tok), json={"dob": "not-a-date"}, timeout=15)
    _label("A.3 dob='not-a-date' → 400", r.status_code == 400, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 400:
        detail = (r.json().get("detail") or "").lower()
        _label("A.3 detail contains 'dob' and 'yyyy-mm-dd'", "dob" in detail and "yyyy-mm-dd" in detail, detail)

    # A.4 duplicate email → 400
    r = requests.patch(f"{BASE}/users/me/profile", headers=H(staff_tok), json={"email": "admin@company.com"}, timeout=15)
    _label("A.4 duplicate email → 400", r.status_code == 400, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 400:
        detail = (r.json().get("detail") or "").lower()
        _label("A.4 detail contains 'already in use'", "already in use" in detail, detail)

    # A.5 empty body → 200 no-op
    r = requests.patch(f"{BASE}/users/me/profile", headers=H(staff_tok), json={}, timeout=15)
    _label("A.5 empty body → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")

    # ------------------------------------------------------------------
    section("B. Admin edits a user")
    today = datetime.utcnow().replace(tzinfo=timezone.utc)
    twenty_w_ago = (today - timedelta(weeks=20)).strftime("%Y-%m-%d")

    # B.1
    body = {"start_date": twenty_w_ago, "employment_type": "full_time", "holiday_entitlement": 30, "phone": "+353-87-111-2222"}
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json=body, timeout=15)
    _label("B.1 admin PATCH /users/{jane_id} → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        j = r.json()
        _label("B.1 start_date updated", j.get("start_date") == twenty_w_ago, str(j.get("start_date")))
        _label("B.1 employment_type=full_time", j.get("employment_type") == "full_time", str(j.get("employment_type")))
        _label("B.1 holiday_entitlement=30", j.get("holiday_entitlement") == 30, str(j.get("holiday_entitlement")))
        _label("B.1 phone updated", j.get("phone") == "+353-87-111-2222", str(j.get("phone")))

    # B.2 employment_type=casual → 400
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"employment_type": "casual"}, timeout=15)
    _label("B.2 employment_type=casual → 400", r.status_code == 400, f"status={r.status_code}")
    if r.status_code == 400:
        detail = (r.json().get("detail") or "").lower()
        _label("B.2 detail mentions full_time/part_time", "full_time" in detail and "part_time" in detail, detail)

    # B.3 role=superadmin → 400
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"role": "superadmin"}, timeout=15)
    _label("B.3 role=superadmin → 400", r.status_code == 400, f"status={r.status_code}")

    # B.4 holiday_entitlement=400 → 400
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"holiday_entitlement": 400}, timeout=15)
    _label("B.4 holiday_entitlement=400 → 400", r.status_code == 400, f"status={r.status_code}")
    if r.status_code == 400:
        detail = (r.json().get("detail") or "")
        _label("B.4 detail mentions 0–365", "0" in detail and "365" in detail, detail)

    # B.5 start_date=bad → 400
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"start_date": "bad"}, timeout=15)
    _label("B.5 start_date='bad' → 400", r.status_code == 400, f"status={r.status_code} body={r.text[:200]}")

    # B.6 Staff PATCH another user → 403
    r = requests.patch(f"{BASE}/users/{admin_id}", headers=H(staff_tok), json={"name": "Hacker"}, timeout=15)
    _label("B.6 staff PATCH /users/{admin_id} → 403", r.status_code == 403, f"status={r.status_code} body={r.text[:200]}")

    # ------------------------------------------------------------------
    section("C. Eligibility (Sick Pay)")

    # C.1 reset Jane start_date=""
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"start_date": ""}, timeout=15)
    _label("C.1 admin reset start_date='' → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        _label("C.1 start_date cleared", r.json().get("start_date") in (None, ""), str(r.json().get("start_date")))

    r = requests.get(f"{BASE}/users/me/eligibility", headers=H(staff_tok), timeout=15)
    _label("C.1 staff GET /users/me/eligibility → 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        e = r.json()
        _label("C.1 sick_pay_eligible=false", e.get("sick_pay_eligible") is False, str(e.get("sick_pay_eligible")))
        _label("C.1 weeks_employed=null", e.get("weeks_employed") is None, str(e.get("weeks_employed")))
        _label("C.1 sick_pay_eligible_on=null", e.get("sick_pay_eligible_on") is None, str(e.get("sick_pay_eligible_on")))

    # C.2 start_date = 20w ago
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"start_date": twenty_w_ago}, timeout=15)
    assert r.status_code == 200
    e = requests.get(f"{BASE}/users/me/eligibility", headers=H(staff_tok), timeout=15).json()
    _label("C.2 sick_pay_eligible=true", e.get("sick_pay_eligible") is True, str(e.get("sick_pay_eligible")))
    _label("C.2 weeks_employed >= 20", (e.get("weeks_employed") or 0) >= 20, str(e.get("weeks_employed")))
    _label("C.2 sick_pay_eligible_on=null (already eligible)", e.get("sick_pay_eligible_on") is None, str(e.get("sick_pay_eligible_on")))

    # C.3 start_date = 5 weeks ago
    five_w_ago_dt = today - timedelta(weeks=5)
    five_w_ago = five_w_ago_dt.strftime("%Y-%m-%d")
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"start_date": five_w_ago}, timeout=15)
    assert r.status_code == 200
    e = requests.get(f"{BASE}/users/me/eligibility", headers=H(staff_tok), timeout=15).json()
    _label("C.3 sick_pay_eligible=false", e.get("sick_pay_eligible") is False, str(e.get("sick_pay_eligible")))
    wks = e.get("weeks_employed")
    _label("C.3 weeks_employed ≈ 5.0", wks is not None and abs(wks - 5.0) < 0.3, str(wks))
    expected_on = (datetime.fromisoformat(five_w_ago) + timedelta(days=91)).strftime("%Y-%m-%d")
    _label("C.3 sick_pay_eligible_on = start_date + 91d", e.get("sick_pay_eligible_on") == expected_on, f"got={e.get('sick_pay_eligible_on')} expected={expected_on}")

    # C.4 admin GET /users/{jane_id}/eligibility
    r = requests.get(f"{BASE}/users/{staff_id}/eligibility", headers=H(admin_tok), timeout=15)
    _label("C.4 admin GET /users/{jane}/eligibility → 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        e2 = r.json()
        for key in ("user_id", "employment_type", "start_date", "weeks_employed", "sick_pay_eligible",
                    "sick_pay_eligible_on", "bank_holiday_eligible", "hours_last_5_weeks",
                    "bank_holiday_threshold_hours"):
            _label(f"C.4 has key '{key}'", key in e2, "missing")

    # C.5 staff GET /users/{admin_id}/eligibility → 403
    r = requests.get(f"{BASE}/users/{admin_id}/eligibility", headers=H(staff_tok), timeout=15)
    _label("C.5 staff GET /users/{admin}/eligibility → 403", r.status_code == 403, f"status={r.status_code} body={r.text[:200]}")

    # ------------------------------------------------------------------
    section("D. Eligibility (Bank Holiday)")

    # D.1 full_time
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"employment_type": "full_time"}, timeout=15)
    assert r.status_code == 200
    e = requests.get(f"{BASE}/users/me/eligibility", headers=H(staff_tok), timeout=15).json()
    _label("D.1 full_time → bank_holiday_eligible=true", e.get("bank_holiday_eligible") is True, str(e.get("bank_holiday_eligible")))
    _label("D.1 full_time → threshold=0.0", e.get("bank_holiday_threshold_hours") == 0.0, str(e.get("bank_holiday_threshold_hours")))

    # D.2 part_time
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"employment_type": "part_time"}, timeout=15)
    assert r.status_code == 200
    e = requests.get(f"{BASE}/users/me/eligibility", headers=H(staff_tok), timeout=15).json()
    _label("D.2 part_time → threshold=40.0", e.get("bank_holiday_threshold_hours") == 40.0, str(e.get("bank_holiday_threshold_hours")))
    _label("D.2 part_time → hours_last_5_weeks is a number", isinstance(e.get("hours_last_5_weeks"), (int, float)), str(e.get("hours_last_5_weeks")))
    hrs_before = e.get("hours_last_5_weeks", 0)
    _label("D.2 part_time → bank_holiday_eligible matches threshold", e.get("bank_holiday_eligible") == (hrs_before >= 40.0), f"hours={hrs_before} eligible={e.get('bank_holiday_eligible')}")

    # D.3 seed 45h via mongo and re-check
    print("  [seed] inserting 2 clock_entries totaling 45h …")
    inserted = seed_clock_entries(staff_id, [20.0, 25.0])
    try:
        e = requests.get(f"{BASE}/users/me/eligibility", headers=H(staff_tok), timeout=15).json()
        _label("D.3 hours_last_5_weeks ≥ 40 (after seed)", (e.get("hours_last_5_weeks") or 0) >= 40.0, str(e.get("hours_last_5_weeks")))
        _label("D.3 bank_holiday_eligible=true (after seed)", e.get("bank_holiday_eligible") is True, str(e.get("bank_holiday_eligible")))
    finally:
        remove_clock_entries(inserted)
        print("  [seed] removed seeded entries")

    # D.3b verify post-cleanup hours dropped back to baseline
    e_after = requests.get(f"{BASE}/users/me/eligibility", headers=H(staff_tok), timeout=15).json()
    _label("D.3b after cleanup, hours back to baseline (~hrs_before)", abs((e_after.get("hours_last_5_weeks") or 0) - hrs_before) < 0.5, f"now={e_after.get('hours_last_5_weeks')} before={hrs_before}")

    # D.4 restore Jane
    r = requests.patch(f"{BASE}/users/{staff_id}", headers=H(admin_tok), json={"employment_type": "full_time", "start_date": ""}, timeout=15)
    _label("D.4 restore Jane full_time + cleared start_date", r.status_code == 200, f"status={r.status_code}")

    # ------------------------------------------------------------------
    section("E. Auth guards")

    # Unauth PATCH /users/me/profile
    r = requests.patch(f"{BASE}/users/me/profile", json={"phone": "x"}, timeout=15)
    _label("E.1 unauth PATCH /users/me/profile → 401", r.status_code == 401, f"status={r.status_code}")

    # Unauth GET /users/me/eligibility
    r = requests.get(f"{BASE}/users/me/eligibility", timeout=15)
    _label("E.2 unauth GET /users/me/eligibility → 401", r.status_code == 401, f"status={r.status_code}")

    # Staff PATCH /users/{other_id} → 403
    r = requests.patch(f"{BASE}/users/{admin_id}", headers=H(staff_tok), json={"name": "x"}, timeout=15)
    _label("E.3 staff PATCH /users/{admin_id} → 403", r.status_code == 403, f"status={r.status_code}")

    # Staff GET /users/{other_id}/eligibility → 403
    r = requests.get(f"{BASE}/users/{admin_id}/eligibility", headers=H(staff_tok), timeout=15)
    _label("E.4 staff GET /users/{admin_id}/eligibility → 403", r.status_code == 403, f"status={r.status_code}")

    # Restore staff phone field to a clean value (don't reset entitlement since other tests may rely on it)
    print("\n=== Cleanup: restoring Jane phone to None ===")
    requests.patch(f"{BASE}/users/me/profile", headers=H(staff_tok), json={"phone": ""}, timeout=15)

    # ------------------------------------------------------------------
    print(f"\n=== RESULT: {PASS} pass / {FAIL} fail ===")
    if FAILURES:
        print("Failures:")
        for f in FAILURES:
            print(f"  - {f}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
