"""
Test recurring shift creation + availability endpoints.
Reads BACKEND_URL from frontend env.
"""
import os
import sys
import requests
from datetime import datetime, timezone, timedelta

BACKEND_URL = "https://b863035e-804d-4d41-9158-321900c27687.preview.emergentagent.com"
API = f"{BACKEND_URL}/api"

ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

results = []
created_shift_ids = []


def log(name, ok, detail=""):
    results.append((name, ok, detail))
    marker = "PASS" if ok else "FAIL"
    print(f"[{marker}] {name} :: {detail}")


def login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j["access_token"], j["user"]


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def parse_date_only(iso):
    # Strip TZ for date comparison
    return datetime.fromisoformat(iso).date()


def main():
    # Login
    admin_tok, admin_user = login(ADMIN)
    staff_tok, staff_user = login(STAFF)
    log("login admin", admin_user["role"] == "admin", admin_user["email"])
    log("login staff", staff_user["role"] == "staff", staff_user["email"])
    staff_id = staff_user["id"]

    # ------ TEST 1: daily recurring, repeat_count=4 ------
    base_start = datetime(2030, 4, 1, 9, 0, 0, tzinfo=timezone.utc)
    base_end = datetime(2030, 4, 1, 17, 0, 0, tzinfo=timezone.utc)
    body = {
        "user_id": staff_id,
        "title": "Daily Patrol — Test",
        "start": base_start.isoformat(),
        "end": base_end.isoformat(),
        "recurring": "daily",
        "repeat_count": 4,
    }
    r = requests.post(f"{API}/shifts", json=body, headers=hdr(admin_tok), timeout=30)
    log("POST /shifts daily x4 status", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code != 200:
        return
    j = r.json()
    log(
        "daily response shape",
        j.get("created") == 4 and j.get("series_id") and isinstance(j.get("first"), dict),
        f"created={j.get('created')} series_id={j.get('series_id')}",
    )
    daily_series_id = j["series_id"]

    # GET /api/shifts?all=true and confirm 4 shifts exist with same series_id
    r = requests.get(f"{API}/shifts?all=true", headers=hdr(admin_tok), timeout=30)
    log("GET /shifts?all=true status", r.status_code == 200, str(r.status_code))
    all_shifts = r.json()
    series_shifts = [s for s in all_shifts if s.get("series_id") == daily_series_id]
    log("daily series count = 4", len(series_shifts) == 4, f"found={len(series_shifts)}")

    # Verify date offsets +0d/+1d/+2d/+3d
    series_shifts_sorted = sorted(series_shifts, key=lambda s: s["start"])
    expected_starts = [base_start + timedelta(days=i) for i in range(4)]
    offsets_ok = True
    detail_offsets = []
    for i, sh in enumerate(series_shifts_sorted):
        actual = datetime.fromisoformat(sh["start"])
        # normalize tz
        if actual.tzinfo is None:
            actual = actual.replace(tzinfo=timezone.utc)
        expected = expected_starts[i]
        match = actual == expected
        detail_offsets.append(f"i={i} expected={expected.isoformat()} actual={actual.isoformat()} match={match}")
        if not match:
            offsets_ok = False
        # Track for cleanup
        created_shift_ids.append(sh["id"])
    log("daily date offsets +0d/+1d/+2d/+3d", offsets_ok, "; ".join(detail_offsets))

    # Verify occurrence_index 0..3
    occ_indexes = sorted([s.get("occurrence_index") for s in series_shifts_sorted])
    log("occurrence_index 0..3", occ_indexes == [0, 1, 2, 3], f"got={occ_indexes}")

    # ------ TEST 2: weekly recurring, repeat_count=3 ------
    w_start = datetime(2030, 5, 6, 8, 0, 0, tzinfo=timezone.utc)
    w_end = datetime(2030, 5, 6, 16, 0, 0, tzinfo=timezone.utc)
    body = {
        "user_id": staff_id,
        "title": "Weekly Audit — Test",
        "start": w_start.isoformat(),
        "end": w_end.isoformat(),
        "recurring": "weekly",
        "repeat_count": 3,
    }
    r = requests.post(f"{API}/shifts", json=body, headers=hdr(admin_tok), timeout=30)
    log("POST /shifts weekly x3 status", r.status_code == 200, str(r.status_code))
    j = r.json()
    log(
        "weekly response shape",
        j.get("created") == 3 and j.get("series_id"),
        f"created={j.get('created')} series_id={j.get('series_id')}",
    )
    weekly_series_id = j["series_id"]

    r = requests.get(f"{API}/shifts?all=true", headers=hdr(admin_tok), timeout=30)
    all_shifts = r.json()
    weekly_shifts = sorted(
        [s for s in all_shifts if s.get("series_id") == weekly_series_id],
        key=lambda s: s["start"],
    )
    log("weekly series count = 3", len(weekly_shifts) == 3, f"found={len(weekly_shifts)}")
    expected_starts = [w_start + timedelta(days=7 * i) for i in range(3)]
    weekly_ok = True
    weekly_detail = []
    for i, sh in enumerate(weekly_shifts):
        actual = datetime.fromisoformat(sh["start"])
        if actual.tzinfo is None:
            actual = actual.replace(tzinfo=timezone.utc)
        match = actual == expected_starts[i]
        weekly_detail.append(f"i={i} exp={expected_starts[i].isoformat()} act={actual.isoformat()} ok={match}")
        if not match:
            weekly_ok = False
        created_shift_ids.append(sh["id"])
    log("weekly date offsets +0d/+7d/+14d", weekly_ok, "; ".join(weekly_detail))

    # ------ TEST 3: recurring=none → expect created=1, series_id null ------
    n_start = datetime(2030, 6, 10, 9, 0, 0, tzinfo=timezone.utc)
    n_end = datetime(2030, 6, 10, 17, 0, 0, tzinfo=timezone.utc)
    body = {
        "user_id": staff_id,
        "title": "Single One-off — Test",
        "start": n_start.isoformat(),
        "end": n_end.isoformat(),
        "recurring": "none",
        "repeat_count": 5,  # should be ignored when none
    }
    r = requests.post(f"{API}/shifts", json=body, headers=hdr(admin_tok), timeout=30)
    log("POST /shifts recurring=none status", r.status_code == 200, str(r.status_code))
    j = r.json()
    log(
        "none response: created=1 series_id null",
        j.get("created") == 1 and j.get("series_id") is None,
        f"created={j.get('created')} series_id={j.get('series_id')}",
    )
    if j.get("first"):
        created_shift_ids.append(j["first"]["id"])

    # Also test omitted recurring field
    body2 = {
        "user_id": staff_id,
        "title": "Single Omitted — Test",
        "start": (n_start + timedelta(days=1)).isoformat(),
        "end": (n_end + timedelta(days=1)).isoformat(),
    }
    r = requests.post(f"{API}/shifts", json=body2, headers=hdr(admin_tok), timeout=30)
    log("POST /shifts recurring omitted status", r.status_code == 200, str(r.status_code))
    j = r.json()
    log(
        "omitted recurring: created=1 series_id null",
        j.get("created") == 1 and j.get("series_id") is None,
        f"created={j.get('created')} series_id={j.get('series_id')}",
    )
    if j.get("first"):
        created_shift_ids.append(j["first"]["id"])

    # ------ TEST 4: POST /shifts as staff → expect 403 ------
    r = requests.post(
        f"{API}/shifts",
        json={
            "user_id": staff_id,
            "title": "Should Fail",
            "start": n_start.isoformat(),
            "end": n_end.isoformat(),
        },
        headers=hdr(staff_tok),
        timeout=30,
    )
    log("staff POST /shifts → 403", r.status_code == 403, f"status={r.status_code} body={r.text[:120]}")

    # ------ TEST 5: POST /availability as staff (upsert) ------
    test_date = "2030-07-15"
    body = {"date": test_date, "available": False, "note": "test unavailable"}
    r = requests.post(f"{API}/availability", json=body, headers=hdr(staff_tok), timeout=30)
    log("POST /availability (false) status", r.status_code == 200, str(r.status_code))
    j = r.json()
    log("availability false body", j.get("available") is False and j.get("note") == "test unavailable", str(j))

    # Overwrite with available=true
    body2 = {"date": test_date, "available": True, "note": "now available"}
    r = requests.post(f"{API}/availability", json=body2, headers=hdr(staff_tok), timeout=30)
    log("POST /availability overwrite (true) status", r.status_code == 200, str(r.status_code))

    # GET as staff and verify only one record for this date and it's available=true
    r = requests.get(f"{API}/availability", headers=hdr(staff_tok), timeout=30)
    log("GET /availability staff status", r.status_code == 200, str(r.status_code))
    avail_list = r.json()
    on_date = [a for a in avail_list if a.get("date") == test_date]
    log(
        "availability upsert (1 record on date, available=true)",
        len(on_date) == 1 and on_date[0].get("available") is True and on_date[0].get("note") == "now available",
        f"matches={on_date}",
    )

    # ------ TEST 6: GET /availability as staff returns own; admin all=true returns everyone ------
    # Verify staff doesn't get other users
    others = [a for a in avail_list if a.get("user_id") != staff_id]
    log("staff GET /availability scoped to own", len(others) == 0, f"others_count={len(others)}")

    # Have admin set their own availability so we can check that admin all=true sees both
    admin_avail_date = "2030-07-20"
    r = requests.post(
        f"{API}/availability",
        json={"date": admin_avail_date, "available": False, "note": "admin OOO"},
        headers=hdr(admin_tok),
        timeout=30,
    )
    log("admin sets own availability", r.status_code == 200, str(r.status_code))

    # Admin without all=true → should only see own
    r = requests.get(f"{API}/availability", headers=hdr(admin_tok), timeout=30)
    admin_own = r.json()
    only_admin = all(a.get("user_id") == admin_user["id"] for a in admin_own)
    log("admin GET /availability (no all) scoped to own", only_admin, f"count={len(admin_own)}")

    # Admin ?all=true → should see staff record + admin record
    r = requests.get(f"{API}/availability?all=true", headers=hdr(admin_tok), timeout=30)
    log("admin GET /availability?all=true status", r.status_code == 200, str(r.status_code))
    all_avail = r.json()
    user_ids = {a.get("user_id") for a in all_avail}
    log(
        "admin all=true sees admin + staff",
        admin_user["id"] in user_ids and staff_id in user_ids,
        f"user_ids={user_ids}",
    )

    # Staff with all=true should still be scoped to own
    r = requests.get(f"{API}/availability?all=true", headers=hdr(staff_tok), timeout=30)
    staff_all = r.json()
    only_staff = all(a.get("user_id") == staff_id for a in staff_all)
    log("staff with all=true still scoped to own", only_staff, f"count={len(staff_all)}")

    # ------ Cleanup ------
    print("\n--- Cleanup ---")
    deleted = 0
    for sid in created_shift_ids:
        r = requests.delete(f"{API}/shifts/{sid}", headers=hdr(admin_tok), timeout=30)
        if r.status_code == 200:
            deleted += 1
    log("cleanup shifts deleted", deleted == len(created_shift_ids), f"{deleted}/{len(created_shift_ids)}")

    # Cleanup availability records (no DELETE endpoint exists, leave as-is — they're future-dated)
    print("\n--- Summary ---")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"{passed}/{total} passed")
    failed = [(n, d) for n, ok, d in results if not ok]
    if failed:
        print("\nFAILURES:")
        for n, d in failed:
            print(f"  - {n}: {d}")
        sys.exit(1)


if __name__ == "__main__":
    main()
