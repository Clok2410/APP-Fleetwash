"""Phase 6 backend regression — push-token diagnostics + shift drag-and-drop reassign."""
import requests
import sys
import time

BASE = "https://employee-connect-9.preview.emergentagent.com/api"

ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

results = []

def log(name, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    results.append((ok, name, detail))


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return r.json()["access_token"], r.json()["user"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    admin_tok, admin_user = login(ADMIN)
    staff_tok, staff_user = login(STAFF)
    admin_id = admin_user["id"]
    jane_id = staff_user["id"]
    print(f"\n>>> admin_id={admin_id}\n>>> jane_id={jane_id}\n")

    # ------------------- A. Push token + status -------------------
    print("\n=== A. Push token + status ===")

    # A1 Staff GET push-status — shape check
    r = requests.get(f"{BASE}/users/me/push-status", headers=H(staff_tok))
    log("A1 staff GET /push-status → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        j = r.json()
        keys_ok = all(k in j for k in ("registered", "token_preview", "updated_at"))
        log("A1 shape contains keys registered/token_preview/updated_at", keys_ok, f"{list(j.keys())}")

    # A2 Staff POST push-token "" → 200 (clears)
    r = requests.post(f"{BASE}/users/me/push-token", json={"token": ""}, headers=H(staff_tok))
    log("A2 staff POST /push-token {token:''} → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

    # A3 Staff GET status → registered=false, token_preview=null
    r = requests.get(f"{BASE}/users/me/push-status", headers=H(staff_tok))
    j = r.json() if r.status_code == 200 else {}
    log("A3 after clear, registered=false", r.status_code == 200 and j.get("registered") is False, f"{j}")
    log("A3 after clear, token_preview=null", r.status_code == 200 and j.get("token_preview") in (None,), f"{j.get('token_preview')}")

    # A4 Staff POST valid token
    valid_tok = "ExponentPushToken[AAAA-BBBB-CCCC-DDDD]"
    r = requests.post(f"{BASE}/users/me/push-token", json={"token": valid_tok}, headers=H(staff_tok))
    log("A4 staff POST valid ExponentPushToken → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")

    # A5 Staff GET status → registered=true, preview pattern, updated_at not null
    r = requests.get(f"{BASE}/users/me/push-status", headers=H(staff_tok))
    j = r.json() if r.status_code == 200 else {}
    log("A5 registered=true", j.get("registered") is True, f"{j}")
    preview = j.get("token_preview")
    # expected: first 14 + last 6 chars joined by ellipsis
    expected_preview = f"{valid_tok[:14]}\u2026{valid_tok[-6:]}"
    log("A5 token_preview matches first 14 + ellipsis + last 6", preview == expected_preview, f"expected={expected_preview!r} got={preview!r}")
    log("A5 updated_at not null", j.get("updated_at") not in (None, ""), f"{j.get('updated_at')}")

    # A6 Staff POST junk → 400
    r = requests.post(f"{BASE}/users/me/push-token", json={"token": "junk"}, headers=H(staff_tok))
    detail = ""
    try:
        detail = r.json().get("detail", "")
    except Exception:
        detail = r.text
    log("A6 staff POST junk → 400", r.status_code == 400, f"{r.status_code} {detail}")
    log("A6 detail == 'Invalid Expo push token'", "Invalid Expo push token" in str(detail), f"{detail}")

    # Note: After A6 the token should still be the valid one from A4 (junk was rejected before write)

    # ------------------- B. Push test -------------------
    print("\n=== B. Push test ===")

    # B1 Staff POST /push-test {} → target_id=jane
    r = requests.post(f"{BASE}/users/push-test", json={}, headers=H(staff_tok))
    log("B1 staff POST /push-test {} → 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    if r.status_code == 200:
        j = r.json()
        log("B1 target_id == jane_id", j.get("target_id") == jane_id, f"target_id={j.get('target_id')}")
        # Jane has a token from A4 — sent should be True OR (if expo rejects) we'd see send_error
        # We accept either sent=True (most likely) or sent=False with reason send_error
        if j.get("sent") is True:
            log("B1 sent=true (Jane has token)", True, f"{j}")
        else:
            # Should not be no_token since we registered one in A4
            ok = j.get("reason") in ("send_error",)
            log("B1 sent=false with reason send_error (Expo gateway behavior)", ok, f"{j}")

    # B2 Staff POST /push-test {user_id:admin_id} → backend IGNORES, targets self
    r = requests.post(f"{BASE}/users/push-test", json={"user_id": admin_id}, headers=H(staff_tok))
    log("B2 staff /push-test {user_id:admin_id} → 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    if r.status_code == 200:
        j = r.json()
        log("B2 target_id == jane_id (staff cannot target admin)", j.get("target_id") == jane_id, f"target_id={j.get('target_id')}")
        log("B2 target_id != admin_id", j.get("target_id") != admin_id, "")

    # B3 Admin POST /push-test {user_id:jane_id, title, body} → 200; sent=true if jane has token
    r = requests.post(
        f"{BASE}/users/push-test",
        json={"user_id": jane_id, "title": "Hi", "body": "Test"},
        headers=H(admin_tok),
    )
    log("B3 admin /push-test {user_id:jane} → 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    if r.status_code == 200:
        j = r.json()
        log("B3 target_id == jane_id", j.get("target_id") == jane_id, f"{j}")
        if j.get("sent") is True:
            log("B3 sent=true (jane has token)", True, "")
        else:
            ok = j.get("reason") in ("send_error",)
            log("B3 sent=false with reason send_error acceptable", ok, f"{j}")

    # B4 Admin POST nonexistent → 404
    r = requests.post(
        f"{BASE}/users/push-test", json={"user_id": "nonexistent_user_xyz"}, headers=H(admin_tok)
    )
    detail = ""
    try:
        detail = r.json().get("detail", "")
    except Exception:
        detail = r.text
    log("B4 admin /push-test nonexistent → 404", r.status_code == 404, f"{r.status_code} {detail}")
    log("B4 detail == 'User not found'", detail == "User not found", f"{detail!r}")

    # ------------------- C. Shift reassign -------------------
    print("\n=== C. Shift reassign ===")

    # C0 Find or create a shift assigned to Jane
    r = requests.get(f"{BASE}/shifts?all=true", headers=H(admin_tok))
    log("C0 admin GET /shifts?all=true → 200", r.status_code == 200, f"{r.status_code}")
    shifts = r.json() if r.status_code == 200 else []
    s1 = next((s for s in shifts if s.get("user_id") == jane_id), None)
    cleanup_created = None
    if not s1:
        # Create one
        from datetime import datetime, timedelta, timezone
        st = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        en = (datetime.now(timezone.utc) + timedelta(days=10, hours=4)).isoformat()
        payload = {"user_id": jane_id, "title": "Reassign test shift", "start": st, "end": en}
        r = requests.post(f"{BASE}/shifts", json=payload, headers=H(admin_tok))
        log("C0 created test shift for Jane", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        if r.status_code == 200:
            s1 = r.json().get("first")
            cleanup_created = s1.get("id") if s1 else None
    s1_id = s1["id"]
    original_user_id = s1["user_id"]
    print(f">>> using shift {s1_id} originally assigned to {original_user_id}")

    # C1 Admin PATCH reassign → admin
    r = requests.patch(
        f"{BASE}/shifts/{s1_id}/reassign",
        json={"user_id": admin_id},
        headers=H(admin_tok),
    )
    log("C1 admin PATCH /reassign user_id=admin → 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    if r.status_code == 200:
        j = r.json()
        log("C1 response user_id == admin_id", j.get("user_id") == admin_id, f"{j.get('user_id')}")
        # admin's name — fetch /auth/me to get exact name
        admin_name = admin_user.get("name")
        log("C1 response user_name == admin name", j.get("user_name") == admin_name, f"got={j.get('user_name')} expected={admin_name}")
        log("C1 reassigned_at is set", j.get("reassigned_at") not in (None, ""), f"{j.get('reassigned_at')}")

    # C2 Idempotent re-PATCH same user_id
    r = requests.patch(
        f"{BASE}/shifts/{s1_id}/reassign",
        json={"user_id": admin_id},
        headers=H(admin_tok),
    )
    log("C2 idempotent PATCH same user → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        j = r.json()
        log("C2 user_id still admin_id", j.get("user_id") == admin_id, f"{j.get('user_id')}")

    # C3 nonexistent shift
    r = requests.patch(
        f"{BASE}/shifts/nonexistent_shift_xyz/reassign",
        json={"user_id": admin_id},
        headers=H(admin_tok),
    )
    detail = ""
    try:
        detail = r.json().get("detail", "")
    except Exception:
        detail = r.text
    log("C3 nonexistent shift → 404", r.status_code == 404, f"{r.status_code} {detail}")
    log("C3 detail == 'Shift not found'", detail == "Shift not found", f"{detail!r}")

    # C4 bogus user_id → 404
    r = requests.patch(
        f"{BASE}/shifts/{s1_id}/reassign",
        json={"user_id": "bogus_user_id"},
        headers=H(admin_tok),
    )
    detail = ""
    try:
        detail = r.json().get("detail", "")
    except Exception:
        detail = r.text
    log("C4 bogus user_id → 404", r.status_code == 404, f"{r.status_code} {detail}")
    log("C4 detail == 'Target user not found'", detail == "Target user not found", f"{detail!r}")

    # C5 Staff PATCH → 403
    r = requests.patch(
        f"{BASE}/shifts/{s1_id}/reassign",
        json={"user_id": jane_id},
        headers=H(staff_tok),
    )
    log("C5 staff PATCH → 403", r.status_code == 403, f"{r.status_code} {r.text[:200]}")

    # C6 Cleanup: reassign back to original user (Jane)
    r = requests.patch(
        f"{BASE}/shifts/{s1_id}/reassign",
        json={"user_id": original_user_id},
        headers=H(admin_tok),
    )
    log("C6 cleanup PATCH back to original → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        log("C6 user_id restored", r.json().get("user_id") == original_user_id, "")

    # If we created a shift, delete it
    if cleanup_created:
        r = requests.delete(f"{BASE}/shifts/{cleanup_created}", headers=H(admin_tok))
        log("C6b cleanup created shift deleted", r.status_code == 200, f"{r.status_code}")

    # ------------------- D. Auth guards -------------------
    print("\n=== D. Auth ===")
    r = requests.get(f"{BASE}/users/me/push-status")
    log("D1 unauth GET /push-status → 401/403", r.status_code in (401, 403), f"{r.status_code}")
    r = requests.post(f"{BASE}/users/push-test", json={})
    log("D2 unauth POST /push-test → 401/403", r.status_code in (401, 403), f"{r.status_code}")
    r = requests.patch(f"{BASE}/shifts/{s1_id}/reassign", json={"user_id": admin_id})
    log("D3 unauth PATCH /reassign → 401/403", r.status_code in (401, 403), f"{r.status_code}")

    # ------------------- Summary -------------------
    print("\n========== SUMMARY ==========")
    passed = sum(1 for ok, _, _ in results if ok)
    failed = sum(1 for ok, _, _ in results if not ok)
    print(f"PASS: {passed}/{len(results)}, FAIL: {failed}")
    if failed:
        print("\nFailures:")
        for ok, name, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
