"""Backend regression: Roster PDF import — parse + publish.

Hits the public proxy URL. Requires admin@company.com / Admin@123 and jane@company.com / Staff@123.
"""
import base64
import os
import sys
import time
import requests

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

PDF_URL = "https://customer-assets.emergentagent.com/job_employee-connect-9/artifacts/vkkc7dex_Week%2019.%202026%20-%20Google%20Sheets.pdf"

results = []  # (name, ok, info)

def rec(name, ok, info=""):
    results.append((name, ok, info))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}{(' — ' + info) if info else ''}")


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def section(title):
    print(f"\n=== {title} ===")


def get_users(admin_tok):
    r = requests.get(f"{BASE}/users", headers=H(admin_tok), timeout=20)
    r.raise_for_status()
    return r.json()


def cleanup_shifts(admin_tok, user_id):
    """Delete all shifts for a user_id flagged imported_from_roster."""
    r = requests.get(f"{BASE}/shifts?all=true", headers=H(admin_tok), timeout=20)
    if r.status_code != 200:
        return 0
    deleted = 0
    for s in r.json():
        if s.get("user_id") == user_id and s.get("imported_from_roster"):
            d = requests.delete(f"{BASE}/shifts/{s['id']}", headers=H(admin_tok), timeout=20)
            if d.status_code == 200:
                deleted += 1
    return deleted


def main():
    section("Login")
    admin_tok = login(ADMIN)
    rec("admin login", True)
    staff_tok = login(STAFF)
    rec("staff login", True)

    users = get_users(admin_tok)
    jane = next((u for u in users if u.get("email") == "jane@company.com"), None)
    admin_user = next((u for u in users if u.get("email") == "admin@company.com"), None)
    assert jane and admin_user, "Could not find Jane or admin"
    jane_id = jane["id"]
    rec("jane_id located", True, jane_id)

    # =========================
    # A. Parse a real roster PDF
    # =========================
    section("A. Parse a real roster PDF")
    # Download & encode
    pdf_path = "/tmp/roster.pdf"
    if not os.path.exists(pdf_path):
        r = requests.get(PDF_URL, timeout=60)
        with open(pdf_path, "wb") as f:
            f.write(r.content)
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    b64 = base64.b64encode(pdf_bytes).decode()
    rec("downloaded PDF", True, f"{len(pdf_bytes)} bytes")

    t0 = time.time()
    r = requests.post(f"{BASE}/roster/parse", json={"pdf_base64": b64}, headers=H(admin_tok), timeout=120)
    dt = time.time() - t0
    rec("A3 POST /roster/parse 200", r.status_code == 200, f"status={r.status_code} elapsed={dt:.1f}s body={r.text[:200] if r.status_code != 200 else ''}")
    if r.status_code == 200:
        data = r.json()
        rows = data.get("rows")
        count = data.get("count")
        rec("A4 rows is list", isinstance(rows, list))
        rec("A4 count > 0", isinstance(count, int) and count > 0, f"count={count}")
        # A5: every row has keys, strings
        bad = []
        for i, row in enumerate(rows or []):
            for k in ["name", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
                if k not in row or not isinstance(row[k], str):
                    bad.append((i, k, row.get(k)))
                    break
        rec("A5 all rows have 8 string keys", not bad, f"bad={bad[:3]}")
        # A6: name substring match
        needles = ["damien", "kieran", "caique", "mark", "nathan", "andrew", "paul", "eion", "matheus", "micheal", "michael", "noel", "brody", "dez", "emmet"]
        joined_names = " ".join((r.get("name", "") for r in rows)).lower()
        hits = [n for n in needles if n in joined_names]
        rec("A6 at least one expected name", bool(hits), f"matches={hits[:5]}")
    else:
        rec("A4/A5/A6 skipped", False, "parse failed")

    # A7 invalid base64
    r = requests.post(f"{BASE}/roster/parse", json={"pdf_base64": "@@@not-base64@@@"}, headers=H(admin_tok), timeout=20)
    info = f"status={r.status_code} detail={r.json().get('detail','') if r.status_code != 500 else ''}"
    detail = (r.json().get("detail", "") if r.headers.get("content-type", "").startswith("application/json") else "").lower()
    rec("A7 invalid base64 → 400 with 'invalid'", r.status_code == 400 and "invalid" in detail, info)

    # A8 non-PDF
    b64_hello = base64.b64encode(b"hello").decode()
    r = requests.post(f"{BASE}/roster/parse", json={"pdf_base64": b64_hello}, headers=H(admin_tok), timeout=20)
    detail = r.json().get("detail", "") if r.headers.get("content-type", "").startswith("application/json") else ""
    rec("A8 non-PDF → 400 'Not a valid PDF'", r.status_code == 400 and "not a valid pdf" in detail.lower(), f"status={r.status_code} detail={detail}")

    # A9 staff → 403
    r = requests.post(f"{BASE}/roster/parse", json={"pdf_base64": b64_hello}, headers=H(staff_tok), timeout=20)
    rec("A9 staff /roster/parse → 403", r.status_code == 403, f"status={r.status_code}")

    # =========================
    # B. Publish small synthetic roster
    # =========================
    section("B. Publish small synthetic roster")
    # Pre-cleanup just in case
    cleanup_shifts(admin_tok, jane_id)

    payload = {
        "week_start": "2027-06-07",  # Monday
        "default_start_time": "06:30",
        "notify": True,
        "rows": [
            {"user_id": jane_id, "days": {"mon": "Site A", "wed": "Site B", "fri": "Site C"}},
            {"user_id": None, "days": {"mon": "skipped"}},
        ],
    }
    r = requests.post(f"{BASE}/roster/publish", json=payload, headers=H(admin_tok), timeout=30)
    rec("B2 POST /roster/publish 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        body = r.json()
        rec("B3 created=3", body.get("created") == 3, f"created={body.get('created')}")
        rec("B3 deleted=0", body.get("deleted") == 0, f"deleted={body.get('deleted')}")
        rec("B3 week_start=2027-06-07", body.get("week_start") == "2027-06-07", f"week_start={body.get('week_start')}")
        rec("B3 week_end=2027-06-13", body.get("week_end") == "2027-06-13", f"week_end={body.get('week_end')}")
        rec("B3 notified_user_ids=[jane_id]", body.get("notified_user_ids") == [jane_id], f"notified={body.get('notified_user_ids')}")

    # B4 verify shifts via GET /shifts?all=true
    r = requests.get(f"{BASE}/shifts?all=true", headers=H(admin_tok), timeout=20)
    shifts_all = r.json() if r.status_code == 200 else []
    week_shifts = [
        s for s in shifts_all
        if s.get("user_id") == jane_id and s.get("imported_from_roster")
        and (s.get("start_at") or "").startswith("2027-06")
    ]
    rec("B4 ≥3 imported shifts for Jane", len(week_shifts) >= 3, f"count={len(week_shifts)}")
    titles = {s.get("title") for s in week_shifts}
    rec("B4 titles ⊆ {Site A,B,C}", titles == {"Site A", "Site B", "Site C"}, f"titles={titles}")
    end_nulls = all(s.get("end_at") in (None, "") for s in week_shifts)
    rec("B4 end_at null for all", end_nulls)
    # start_at contains T06:30
    starts = [s.get("start_at", "") for s in week_shifts]
    has_time = all(("T06:30" in s) for s in starts)
    rec("B4 start_at contains T06:30", has_time, f"sample={starts[:3]}")

    # B5 specific dates
    expected = {"Site A": "2027-06-07T06:30", "Site B": "2027-06-09T06:30", "Site C": "2027-06-11T06:30"}
    by_title = {s["title"]: s["start_at"] for s in week_shifts}
    for title, prefix in expected.items():
        rec(f"B5 {title} starts {prefix}", by_title.get(title, "").startswith(prefix), f"got={by_title.get(title)}")

    # =========================
    # C. Re-publish (policy 3a)
    # =========================
    section("C. Re-publish — replace existing tagged shifts")
    payload2 = {
        "week_start": "2027-06-07",
        "default_start_time": "06:30",
        "notify": True,
        "rows": [
            {"user_id": jane_id, "days": {"mon": "NEW A", "tue": "NEW T"}},
        ],
    }
    r = requests.post(f"{BASE}/roster/publish", json=payload2, headers=H(admin_tok), timeout=30)
    rec("C1 re-publish 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        b = r.json()
        rec("C1 deleted=3", b.get("deleted") == 3, f"deleted={b.get('deleted')}")
        rec("C1 created=2", b.get("created") == 2, f"created={b.get('created')}")

    # C2: verify only 2 NEW shifts remain
    r = requests.get(f"{BASE}/shifts?all=true", headers=H(admin_tok), timeout=20)
    shifts_all = r.json() if r.status_code == 200 else []
    week_shifts = [
        s for s in shifts_all
        if s.get("user_id") == jane_id and s.get("imported_from_roster")
        and (s.get("start_at") or "").startswith("2027-06")
    ]
    titles = {s.get("title") for s in week_shifts}
    rec("C2 exactly 2 shifts remain", len(week_shifts) == 2, f"count={len(week_shifts)}")
    rec("C2 titles = {NEW A, NEW T}", titles == {"NEW A", "NEW T"}, f"titles={titles}")

    # C3 empty rows
    payload3 = {
        "week_start": "2027-06-07",
        "default_start_time": "06:30",
        "notify": True,
        "rows": [],
    }
    r = requests.post(f"{BASE}/roster/publish", json=payload3, headers=H(admin_tok), timeout=30)
    if r.status_code == 200:
        b = r.json()
        rec("C3 empty publish: deleted=2", b.get("deleted") == 2, f"deleted={b.get('deleted')}")
        rec("C3 empty publish: created=0", b.get("created") == 0, f"created={b.get('created')}")
    else:
        rec("C3 empty publish 200", False, f"status={r.status_code}")

    # =========================
    # D. Edge cases
    # =========================
    section("D. Edge cases")
    # D1 Tuesday → snap to Monday
    pd1 = {"week_start": "2027-06-08", "default_start_time": "07:00", "notify": False, "rows": []}
    r = requests.post(f"{BASE}/roster/publish", json=pd1, headers=H(admin_tok), timeout=20)
    snapped = r.json().get("week_start") if r.status_code == 200 else None
    rec("D1 Tue snaps to Monday 2027-06-07", r.status_code == 200 and snapped == "2027-06-07", f"got={snapped}")

    # D2 bad date
    r = requests.post(f"{BASE}/roster/publish",
                      json={"week_start": "bad-date", "default_start_time": "07:00", "notify": False, "rows": []},
                      headers=H(admin_tok), timeout=20)
    rec("D2 bad week_start → 400", r.status_code == 400, f"status={r.status_code}")

    # D3 default_start_time=25:00
    r = requests.post(f"{BASE}/roster/publish",
                      json={"week_start": "2027-06-07", "default_start_time": "25:00", "notify": False, "rows": []},
                      headers=H(admin_tok), timeout=20)
    rec("D3 hour=25 → 400", r.status_code == 400, f"status={r.status_code}")

    # D4 default_start_time=07:99
    r = requests.post(f"{BASE}/roster/publish",
                      json={"week_start": "2027-06-07", "default_start_time": "07:99", "notify": False, "rows": []},
                      headers=H(admin_tok), timeout=20)
    rec("D4 minute=99 → 400", r.status_code == 400, f"status={r.status_code}")

    # D5 non-existent user_id → silently skipped
    pd5 = {
        "week_start": "2027-06-14",  # different week to avoid noise
        "default_start_time": "06:30",
        "notify": True,
        "rows": [{"user_id": "bogus-user-xyz", "days": {"mon": "Whatever"}}],
    }
    r = requests.post(f"{BASE}/roster/publish", json=pd5, headers=H(admin_tok), timeout=20)
    if r.status_code == 200:
        b = r.json()
        rec("D5 bogus user_id → 0 created, no error", b.get("created") == 0, f"body={b}")
    else:
        rec("D5 bogus user_id 200", False, f"status={r.status_code} body={r.text[:200]}")

    # D6 empty string day → skipped, D7 unknown day key → skipped
    pd67 = {
        "week_start": "2027-06-14",
        "default_start_time": "06:30",
        "notify": True,
        "rows": [
            {"user_id": jane_id, "days": {"mon": "", "funday": "Trip", "tue": "Real Tue"}},
        ],
    }
    r = requests.post(f"{BASE}/roster/publish", json=pd67, headers=H(admin_tok), timeout=20)
    if r.status_code == 200:
        b = r.json()
        rec("D6+D7 empty/unknown skipped, created=1", b.get("created") == 1, f"body={b}")
    else:
        rec("D6+D7 200", False, f"status={r.status_code}")

    # =========================
    # E. Auth guards
    # =========================
    section("E. Auth guards")
    r = requests.post(f"{BASE}/roster/parse", json={"pdf_base64": b64_hello}, headers=H(staff_tok), timeout=20)
    rec("E staff /roster/parse → 403", r.status_code == 403, f"status={r.status_code}")
    r = requests.post(f"{BASE}/roster/publish", json={"week_start": "2027-06-07", "default_start_time": "06:30", "rows": []}, headers=H(staff_tok), timeout=20)
    rec("E staff /roster/publish → 403", r.status_code == 403, f"status={r.status_code}")
    r = requests.post(f"{BASE}/roster/parse", json={"pdf_base64": b64_hello}, timeout=20)
    rec("E unauth /roster/parse → 401/403", r.status_code in (401, 403), f"status={r.status_code}")
    r = requests.post(f"{BASE}/roster/publish", json={"week_start": "2027-06-07", "default_start_time": "06:30", "rows": []}, timeout=20)
    rec("E unauth /roster/publish → 401/403", r.status_code in (401, 403), f"status={r.status_code}")

    # =========================
    # F. Cleanup
    # =========================
    section("F. Cleanup")
    deleted = cleanup_shifts(admin_tok, jane_id)
    rec(f"F cleanup deleted {deleted} leftover roster shifts for Jane", True, f"deleted={deleted}")

    # Summary
    section("Summary")
    failed = [(n, info) for n, ok, info in results if not ok]
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"PASS {passed}/{total}")
    if failed:
        print(f"FAIL {len(failed)}:")
        for n, info in failed:
            print(f"  - {n}{(' :: ' + info) if info else ''}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
