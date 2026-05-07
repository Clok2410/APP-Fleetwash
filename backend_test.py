"""Backend regression tests for StaffHub API.

Targets the public proxy URL from frontend/.env (EXPO_PUBLIC_BACKEND_URL).
All routes prefixed with /api.
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------- Resolve base URL from frontend/.env ----------
FRONT_ENV = Path("/app/frontend/.env")
BASE_URL = None
for line in FRONT_ENV.read_text().splitlines():
    if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
        BASE_URL = line.split("=", 1)[1].strip().strip('"')
        break
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"
API = f"{BASE_URL.rstrip('/')}/api"
print(f"[INFO] Using API base: {API}")

ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

results = []  # (name, ok, msg)


def record(name, ok, msg=""):
    results.append((name, ok, msg))
    icon = "PASS" if ok else "FAIL"
    print(f"[{icon}] {name} :: {msg}")


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data["user"]


# ---------- Smoke ----------
def test_smoke():
    try:
        admin_token, admin_user = login(ADMIN)
        record("smoke.auth.login.admin", True, f"role={admin_user.get('role')}")
    except Exception as e:
        record("smoke.auth.login.admin", False, str(e))
        raise

    try:
        staff_token, staff_user = login(STAFF)
        record("smoke.auth.login.staff", True, f"role={staff_user.get('role')}")
    except Exception as e:
        record("smoke.auth.login.staff", False, str(e))
        raise

    r = requests.get(f"{API}/auth/me", headers=auth_headers(admin_token), timeout=15)
    record("smoke.auth.me.admin", r.ok and r.json().get("role") == "admin", f"status={r.status_code}")

    r = requests.get(f"{API}/auth/me", headers=auth_headers(staff_token), timeout=15)
    record("smoke.auth.me.staff", r.ok and r.json().get("role") == "staff", f"status={r.status_code}")

    r = requests.get(f"{API}/clock/status", headers=auth_headers(staff_token), timeout=15)
    record("smoke.clock.status", r.ok and "clocked_in" in r.json(), f"status={r.status_code}")

    r = requests.get(f"{API}/notifications", headers=auth_headers(admin_token), timeout=15)
    record("smoke.notifications.admin", r.ok and isinstance(r.json(), list), f"status={r.status_code}")

    return admin_token, staff_token, admin_user, staff_user


# ---------- Holidays ----------
def test_holidays(admin_token, staff_token):
    # 1. balance baseline
    r = requests.get(f"{API}/holidays/balance", headers=auth_headers(staff_token), timeout=15)
    if not r.ok:
        record("holidays.balance.staff", False, f"status={r.status_code} body={r.text[:120]}")
        return
    balance0 = r.json()
    required_keys = {"entitlement", "used", "pending", "remaining"}
    ok = required_keys.issubset(balance0.keys()) and all(isinstance(balance0[k], (int, float)) for k in required_keys)
    record("holidays.balance.staff", ok, f"baseline={balance0}")

    # 2. create pending
    today = datetime.now(timezone.utc).date()
    sd = (today + timedelta(days=30)).isoformat()
    ed = (today + timedelta(days=32)).isoformat()  # 3 days inclusive
    r = requests.post(
        f"{API}/holidays/requests",
        headers=auth_headers(staff_token),
        json={"start_date": sd, "end_date": ed, "reason": "Family trip", "type": "annual"},
        timeout=15,
    )
    if not r.ok:
        record("holidays.create.pending", False, f"status={r.status_code} body={r.text[:200]}")
        return
    pending_req = r.json()
    record(
        "holidays.create.pending",
        pending_req.get("status") == "pending" and pending_req.get("id"),
        f"id={pending_req.get('id')}",
    )

    # Second request to be approved (3 days)
    sd2 = (today + timedelta(days=60)).isoformat()
    ed2 = (today + timedelta(days=62)).isoformat()
    r = requests.post(
        f"{API}/holidays/requests",
        headers=auth_headers(staff_token),
        json={"start_date": sd2, "end_date": ed2, "reason": "Vacation", "type": "annual"},
        timeout=15,
    )
    approve_req = r.json() if r.ok else None
    record(
        "holidays.create.toApprove",
        bool(approve_req and approve_req.get("id")),
        f"id={(approve_req or {}).get('id')}",
    )

    # 3. balance reflects pending
    r = requests.get(f"{API}/holidays/balance", headers=auth_headers(staff_token), timeout=15)
    bal_after_create = r.json()
    pending_delta = bal_after_create["pending"] - balance0["pending"]
    record(
        "holidays.balance.pendingDelta",
        pending_delta == 6,
        f"delta={pending_delta} new={bal_after_create}",
    )

    # 4. list staff own
    r = requests.get(f"{API}/holidays/requests", headers=auth_headers(staff_token), timeout=15)
    own = r.json() if r.ok else []
    own_ids = {x["id"] for x in own}
    record(
        "holidays.list.staffOwn",
        pending_req["id"] in own_ids and approve_req["id"] in own_ids,
        f"count={len(own)}",
    )

    # Verify staff cannot get all=true beyond own
    r = requests.get(f"{API}/holidays/requests?all=true", headers=auth_headers(staff_token), timeout=15)
    staff_all = r.json() if r.ok else []
    record(
        "holidays.list.staffAllScoped",
        all(x["user_id"] == own[0]["user_id"] for x in staff_all) if staff_all else True,
        f"count={len(staff_all)}",
    )

    # 5. admin lists all
    r = requests.get(f"{API}/holidays/requests?all=true", headers=auth_headers(admin_token), timeout=15)
    admin_all = r.json() if r.ok else []
    record(
        "holidays.list.adminAll",
        pending_req["id"] in {x["id"] for x in admin_all},
        f"count={len(admin_all)}",
    )

    # 6. approve + reject
    r = requests.post(
        f"{API}/holidays/requests/{approve_req['id']}/decision?decision=approved",
        headers=auth_headers(admin_token),
        timeout=15,
    )
    record("holidays.decision.approve", r.ok and r.json().get("ok"), f"status={r.status_code}")

    r = requests.post(
        f"{API}/holidays/requests/{pending_req['id']}/decision?decision=rejected",
        headers=auth_headers(admin_token),
        timeout=15,
    )
    record("holidays.decision.reject", r.ok and r.json().get("ok"), f"status={r.status_code}")

    # Staff cannot decide
    r = requests.post(
        f"{API}/holidays/requests/{approve_req['id']}/decision?decision=approved",
        headers=auth_headers(staff_token),
        timeout=15,
    )
    record("holidays.decision.staffForbidden", r.status_code == 403, f"status={r.status_code}")

    # 7. balance after decisions
    r = requests.get(f"{API}/holidays/balance", headers=auth_headers(staff_token), timeout=15)
    bal_final = r.json()
    used_delta = bal_final["used"] - balance0["used"]
    pending_back = bal_final["pending"] - balance0["pending"]
    remaining_diff = balance0["remaining"] - bal_final["remaining"]
    ok = used_delta == 3 and pending_back == 0 and remaining_diff == 3
    record(
        "holidays.balance.finalMath",
        ok,
        f"used+={used_delta} pending+={pending_back} remaining-={remaining_diff} bal={bal_final}",
    )


# ---------- Shifts with customer/site linking ----------
def test_shifts_linking(admin_token, staff_token, staff_user):
    # 1. Create customer
    r = requests.post(
        f"{API}/customers",
        headers=auth_headers(admin_token),
        json={"name": "Riverside Council", "company": "Riverside Council Ltd", "email": "ops@riverside.example", "phone": "+44 20 7946 0010"},
        timeout=15,
    )
    if not r.ok:
        record("shifts.customer.create", False, f"status={r.status_code}")
        return None
    cust = r.json()
    record("shifts.customer.create", True, f"id={cust['id']}")

    # 2. Add site to customer
    r = requests.post(
        f"{API}/customers/{cust['id']}/sites",
        headers=auth_headers(admin_token),
        json={
            "name": "Riverside Depot - East",
            "address": "12 East Wharf, London E14",
            "lat": 51.5008,
            "lng": -0.0249,
            "radius_m": 200,
            "description": "Main east depot",
        },
        timeout=15,
    )
    if not r.ok:
        record("shifts.customer.site.create", False, f"status={r.status_code}")
        return cust
    site = r.json()
    record("shifts.customer.site.create", True, f"id={site['id']}")

    # 3. Create shift linked to customer + site
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=1, hours=8)).replace(microsecond=0).isoformat()
    r = requests.post(
        f"{API}/shifts",
        headers=auth_headers(admin_token),
        json={
            "user_id": staff_user["id"],
            "title": "Morning Patrol",
            "start": start,
            "end": end,
            "customer_id": cust["id"],
            "site_id": site["id"],
            "notes": "Standard patrol",
        },
        timeout=15,
    )
    if not r.ok:
        record("shifts.create.linked", False, f"status={r.status_code} body={r.text[:200]}")
        return cust
    shift = r.json()
    ok = (
        shift.get("customer_id") == cust["id"]
        and shift.get("customer_name") == cust["name"]
        and shift.get("site_id") == site["id"]
        and shift.get("site_name") == site["name"]
    )
    record(
        "shifts.create.linked.autoNames",
        ok,
        f"customer_name={shift.get('customer_name')} site_name={shift.get('site_name')}",
    )

    # 4. Staff GET /shifts persists names
    r = requests.get(f"{API}/shifts", headers=auth_headers(staff_token), timeout=15)
    shifts = r.json() if r.ok else []
    found = next((s for s in shifts if s["id"] == shift["id"]), None)
    ok = bool(found and found.get("customer_name") == cust["name"] and found.get("site_name") == site["name"])
    record("shifts.list.staff.persistedNames", ok, f"found={'yes' if found else 'no'} names=({(found or {}).get('customer_name')},{(found or {}).get('site_name')})")

    # Cleanup shift to avoid clutter (admin only)
    requests.delete(f"{API}/shifts/{shift['id']}", headers=auth_headers(admin_token), timeout=15)
    return cust


# ---------- Customer notes ----------
def test_customer_notes(admin_token, staff_token, customer):
    if not customer:
        record("customer.notes.skip", False, "no customer available")
        return
    cid = customer["id"]

    # 1. non-pinned note (added first)
    r = requests.post(
        f"{API}/customers/{cid}/notes",
        headers=auth_headers(admin_token),
        json={"body": "Routine site maintenance done.", "category": "general", "pinned": False},
        timeout=15,
    )
    note_unpinned = r.json() if r.ok else None
    record("customer.notes.create.nonPinned", bool(note_unpinned and note_unpinned.get("id")), f"status={r.status_code}")

    time.sleep(0.5)

    # 2. pinned note (added later but should sort first)
    r = requests.post(
        f"{API}/customers/{cid}/notes",
        headers=auth_headers(admin_token),
        json={"body": "Gate code: 4421 - DO NOT SHARE", "category": "access", "pinned": True},
        timeout=15,
    )
    note_pinned = r.json() if r.ok else None
    record("customer.notes.create.pinned", bool(note_pinned and note_pinned.get("pinned") is True), f"status={r.status_code}")

    # 3. list → pinned-first ordering
    r = requests.get(f"{API}/customers/{cid}/notes", headers=auth_headers(staff_token), timeout=15)
    notes = r.json() if r.ok else []
    ok = (
        len(notes) >= 2
        and notes[0].get("pinned") is True
        and any(n["id"] == (note_unpinned or {}).get("id") for n in notes)
    )
    record(
        "customer.notes.list.pinnedFirst",
        ok,
        f"count={len(notes)} firstPinned={notes[0].get('pinned') if notes else None}",
    )

    # 4. staff can read but cannot create note? endpoint allows current_user, only admin gated for create_customer; notes endpoint allows any auth.
    r = requests.post(
        f"{API}/customers/{cid}/notes",
        headers=auth_headers(staff_token),
        json={"body": "Met new contact at site.", "category": "general", "pinned": False},
        timeout=15,
    )
    record("customer.notes.create.staffAllowed", r.ok, f"status={r.status_code}")


def main():
    admin_token, staff_token, admin_user, staff_user = test_smoke()
    test_holidays(admin_token, staff_token)
    customer = test_shifts_linking(admin_token, staff_token, staff_user)
    test_customer_notes(admin_token, staff_token, customer)

    print("\n========== SUMMARY ==========")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [r for r in results if not r[1]]
    for name, ok, msg in results:
        print(f"{'PASS' if ok else 'FAIL'} {name} :: {msg}")
    print(f"\nTotal: {len(results)} | Passed: {passed} | Failed: {len(failed)}")
    if failed:
        print("\nFailures:")
        for name, _, msg in failed:
            print(f"  - {name}: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
