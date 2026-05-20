"""
Phase A1: Test PATCH /api/holidays/requests/{rid}
"""
import requests
import sys

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN = ("admin@company.com", "Admin@123")
STAFF = ("jane@company.com", "Staff@123")

results = []
created_rids = []  # to clean up


def log(name, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}{' - ' + detail if detail else ''}")
    results.append((name, ok, detail))


def login(email, pwd):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data["user"]


def H(token):
    return {"Authorization": f"Bearer {token}"}


def main():
    print(f"Backend: {BASE}\n")
    # Login both
    try:
        admin_token, admin_user = login(*ADMIN)
        log("login admin", True, f"id={admin_user['id']}")
    except Exception as e:
        log("login admin", False, str(e)); return
    try:
        staff_token, staff_user = login(*STAFF)
        log("login staff", True, f"id={staff_user['id']} name={staff_user.get('name')}")
    except Exception as e:
        log("login staff", False, str(e)); return

    admin_id = admin_user["id"]
    staff_id = staff_user["id"]
    staff_name = staff_user.get("name") or "Jane Doe"
    admin_name = admin_user.get("name") or "Admin"

    # --- Capture initial balance for cleanup verification ---
    r = requests.get(f"{BASE}/holidays/balance", headers=H(staff_token))
    bal_initial = r.json()
    print(f"Initial balance: {bal_initial}\n")

    # ============ (A) Staff editing own PENDING request ============
    print("=== (A) Staff edits own pending ===")

    # A1: create pending request
    r = requests.post(
        f"{BASE}/holidays/requests",
        headers=H(staff_token),
        json={"start_date": "2027-08-02", "end_date": "2027-08-06", "reason": "family", "type": "annual"},
    )
    if r.status_code != 200:
        log("A1 create pending", False, f"status={r.status_code} body={r.text[:200]}")
        return
    doc = r.json()
    rid_a = doc["id"]
    created_rids.append(rid_a)
    log("A1 create pending", doc.get("status") == "pending" and doc.get("days") == 5,
        f"rid={rid_a} days={doc.get('days')}")

    # A2: PATCH dates + reason
    r = requests.patch(
        f"{BASE}/holidays/requests/{rid_a}",
        headers=H(staff_token),
        json={"start_date": "2027-08-03", "end_date": "2027-08-07", "reason": "family trip updated"},
    )
    ok = r.status_code == 200
    log("A2 staff PATCH dates+reason (200)", ok, f"status={r.status_code}")
    if ok:
        d = r.json()
        log("A2 doc start_date='2027-08-03'", d.get("start_date") == "2027-08-03", str(d.get("start_date")))
        log("A2 doc end_date='2027-08-07'", d.get("end_date") == "2027-08-07", str(d.get("end_date")))
        log("A2 doc reason='family trip updated'", d.get("reason") == "family trip updated", str(d.get("reason")))
        log("A2 doc days=5 recomputed", d.get("days") == 5, f"days={d.get('days')}")
        log("A2 doc edited_at present", bool(d.get("edited_at")), str(d.get("edited_at")))
        log("A2 doc edited_by='self'", d.get("edited_by") == "self", str(d.get("edited_by")))
        log("A2 doc edited_by_name matches staff", d.get("edited_by_name") == staff_name,
            f"got={d.get('edited_by_name')} expected={staff_name}")

    # A3: PATCH type='sick'
    r = requests.patch(f"{BASE}/holidays/requests/{rid_a}", headers=H(staff_token), json={"type": "sick"})
    ok = r.status_code == 200 and r.json().get("type") == "sick"
    log("A3 staff PATCH type=sick (200, type=sick)", ok, f"status={r.status_code} body={r.text[:120]}")

    # A4: PATCH type='vacation' invalid
    r = requests.patch(f"{BASE}/holidays/requests/{rid_a}", headers=H(staff_token), json={"type": "vacation"})
    log("A4 staff PATCH type='vacation' → 400", r.status_code == 400, f"status={r.status_code} body={r.text[:120]}")

    # A5: end before start
    r = requests.patch(
        f"{BASE}/holidays/requests/{rid_a}", headers=H(staff_token),
        json={"start_date": "2027-08-10", "end_date": "2027-08-05"},
    )
    log("A5 staff PATCH end<start → 400", r.status_code == 400, f"status={r.status_code} body={r.text[:120]}")

    # A6: bad-date
    r = requests.patch(f"{BASE}/holidays/requests/{rid_a}", headers=H(staff_token),
                       json={"start_date": "bad-date"})
    log("A6 staff PATCH start_date='bad-date' → 400", r.status_code == 400,
        f"status={r.status_code} body={r.text[:120]}")

    # A7: empty body → 200 no-op
    r = requests.patch(f"{BASE}/holidays/requests/{rid_a}", headers=H(staff_token), json={})
    log("A7 staff PATCH {} → 200 no-op", r.status_code == 200, f"status={r.status_code}")

    # A8: nonexistent rid → 404
    r = requests.patch(f"{BASE}/holidays/requests/nonexistent-xyz", headers=H(staff_token),
                       json={"reason": "x"})
    log("A8 staff PATCH /nonexistent-xyz → 404", r.status_code == 404,
        f"status={r.status_code} body={r.text[:120]}")

    # ============ (B) Staff cannot edit non-pending ============
    print("\n=== (B) Staff cannot edit non-pending ===")
    # First, ensure rid_a status is still 'pending' (we last set type='sick' but status untouched)
    r = requests.get(f"{BASE}/holidays/requests", headers=H(staff_token))
    cur = next((x for x in r.json() if x["id"] == rid_a), None)
    log("B (pre) rid_a is pending", cur and cur.get("status") == "pending",
        f"status={cur.get('status') if cur else 'missing'}")

    # B1: Admin approves
    r = requests.post(f"{BASE}/holidays/requests/{rid_a}/decision?decision=approved",
                      headers=H(admin_token))
    log("B1 admin approve", r.status_code == 200, f"status={r.status_code}")

    # B2: Staff PATCH approved → 400
    r = requests.patch(f"{BASE}/holidays/requests/{rid_a}", headers=H(staff_token),
                       json={"reason": "trying-after-approve"})
    ok = r.status_code == 400 and "pending" in (r.text or "").lower()
    log("B2 staff PATCH approved → 400 with 'pending' in detail", ok,
        f"status={r.status_code} body={r.text[:200]}")

    # ============ (C) Admin edits any state ============
    print("\n=== (C) Admin edits any state ===")

    # C1: Admin PATCH the approved request
    r = requests.patch(
        f"{BASE}/holidays/requests/{rid_a}", headers=H(admin_token),
        json={"start_date": "2027-08-15", "end_date": "2027-08-20", "reason": "admin-changed"},
    )
    ok = r.status_code == 200
    log("C1 admin PATCH approved (200)", ok, f"status={r.status_code}")
    if ok:
        d = r.json()
        log("C1 doc days=6 (Aug 15→20)", d.get("days") == 6, f"days={d.get('days')}")
        log("C1 doc edited_by='admin'", d.get("edited_by") == "admin", str(d.get("edited_by")))
        log("C1 doc edited_by_name matches admin", d.get("edited_by_name") == admin_name,
            f"got={d.get('edited_by_name')}")
        log("C1 doc reason='admin-changed'", d.get("reason") == "admin-changed", str(d.get("reason")))
        log("C1 doc status still 'approved'", d.get("status") == "approved", str(d.get("status")))

    # C2: Admin PATCH a fresh pending from Jane
    r = requests.post(f"{BASE}/holidays/requests", headers=H(staff_token),
                      json={"start_date": "2027-09-01", "end_date": "2027-09-03",
                            "reason": "fresh", "type": "annual"})
    rid_c = r.json().get("id"); created_rids.append(rid_c)
    log("C2 (pre) created fresh pending", r.status_code == 200 and bool(rid_c), f"rid={rid_c}")

    r = requests.patch(f"{BASE}/holidays/requests/{rid_c}", headers=H(admin_token),
                       json={"reason": "admin-edited-pending"})
    ok = r.status_code == 200
    log("C2 admin PATCH fresh pending (200)", ok, f"status={r.status_code}")
    if ok:
        d = r.json()
        log("C2 doc edited_by='admin'", d.get("edited_by") == "admin", str(d.get("edited_by")))

    # C3: Admin PATCH non-existent → 404
    r = requests.patch(f"{BASE}/holidays/requests/zzz-not-real", headers=H(admin_token),
                       json={"reason": "x"})
    log("C3 admin PATCH /nonexistent → 404", r.status_code == 404,
        f"status={r.status_code} body={r.text[:120]}")

    # ============ (D) Auth ============
    print("\n=== (D) Auth ===")
    r = requests.patch(f"{BASE}/holidays/requests/{rid_a}", json={"reason": "no-auth"})
    log("D1 unauth PATCH → 401", r.status_code == 401, f"status={r.status_code}")

    # ============ (E) Cleanup ============
    print("\n=== (E) Cleanup ===")
    # Cancel all created requests
    for rid in created_rids:
        # Try staff cancel; if fails (e.g., approved), try admin
        r = requests.post(f"{BASE}/holidays/requests/{rid}/cancel", headers=H(staff_token))
        if r.status_code != 200:
            r = requests.post(f"{BASE}/holidays/requests/{rid}/cancel", headers=H(admin_token))
        log(f"E cancel {rid[:8]}", r.status_code == 200,
            f"status={r.status_code} body={r.text[:120]}")

    # Verify balance restored
    r = requests.get(f"{BASE}/holidays/balance", headers=H(staff_token))
    bal_final = r.json()
    print(f"Final balance: {bal_final}")
    log("E balance.used returns to initial",
        bal_final.get("used") == bal_initial.get("used"),
        f"initial.used={bal_initial.get('used')} final.used={bal_final.get('used')}")
    log("E balance.pending returns to initial",
        bal_final.get("pending") == bal_initial.get("pending"),
        f"initial.pending={bal_initial.get('pending')} final.pending={bal_final.get('pending')}")
    log("E balance.remaining returns to initial",
        bal_final.get("remaining") == bal_initial.get("remaining"),
        f"initial.remaining={bal_initial.get('remaining')} final.remaining={bal_final.get('remaining')}")

    # Summary
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n========== {passed}/{passed + failed} PASS, {failed} FAIL ==========")
    if failed:
        for name, ok, detail in results:
            if not ok:
                print(f"  FAIL: {name} — {detail}")
        sys.exit(1)


if __name__ == "__main__":
    main()
