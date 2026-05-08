"""
Backend regression for newly-added admin features:
1) Holiday entitlement editor (PATCH /api/users/{id}/entitlement)
2) Admin tap-to-edit shifts (PATCH /api/shifts/{id})
3) Push-token endpoint (POST /api/users/me/push-token)
4) Smoke: notify() must not break create_shift, decide_holiday, decide_swap when no expo_push_token.
"""
import sys
import requests
from datetime import datetime, timezone, timedelta

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

results = []


def log(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append((name, ok, detail))
    print(f"[{status}] {name}{(' - ' + detail) if detail else ''}")


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"], r.json()["user"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    # Login both roles
    admin_tok, admin_user = login(ADMIN)
    staff_tok, staff_user = login(STAFF)
    log("login admin+staff", True, f"admin={admin_user['id'][:8]} staff={staff_user['id'][:8]}")

    staff_id = staff_user["id"]
    admin_id = admin_user["id"]

    # ---------- 1. Holiday entitlement editor ----------
    print("\n=== 1. Holiday entitlement editor ===")
    # 1a PATCH value=30 as admin
    r = requests.patch(f"{BASE}/users/{staff_id}/entitlement", params={"value": 30}, headers=H(admin_tok))
    ok = r.status_code == 200 and r.json().get("ok") is True and r.json().get("holiday_entitlement") == 30
    log("1a PATCH entitlement=30 admin → 200 {ok:true,holiday_entitlement:30}", ok, f"{r.status_code} {r.text[:120]}")

    # 1b GET /holidays/balance as that staff → entitlement == 30
    r = requests.get(f"{BASE}/holidays/balance", headers=H(staff_tok))
    ok = r.status_code == 200 and r.json().get("entitlement") == 30
    log("1b GET balance staff entitlement==30", ok, f"{r.status_code} {r.text[:160]}")

    # 1c value=-5 → 400
    r = requests.patch(f"{BASE}/users/{staff_id}/entitlement", params={"value": -5}, headers=H(admin_tok))
    log("1c PATCH entitlement=-5 → 400", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

    # 1d value=400 → 400
    r = requests.patch(f"{BASE}/users/{staff_id}/entitlement", params={"value": 400}, headers=H(admin_tok))
    log("1d PATCH entitlement=400 → 400", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

    # 1e PATCH as STAFF → 403
    r = requests.patch(f"{BASE}/users/{staff_id}/entitlement", params={"value": 25}, headers=H(staff_tok))
    log("1e PATCH entitlement as staff → 403", r.status_code == 403, f"{r.status_code} {r.text[:120]}")

    # 1f PATCH non-existent user → 404
    r = requests.patch(f"{BASE}/users/nonexistent/entitlement", params={"value": 20}, headers=H(admin_tok))
    log("1f PATCH non-existent user → 404", r.status_code == 404, f"{r.status_code} {r.text[:120]}")

    # 1g restore to 25
    r = requests.patch(f"{BASE}/users/{staff_id}/entitlement", params={"value": 25}, headers=H(admin_tok))
    log("1g restore entitlement=25", r.status_code == 200 and r.json().get("holiday_entitlement") == 25, f"{r.status_code}")

    # ---------- 2. PATCH /api/shifts/{sid} ----------
    print("\n=== 2. PATCH /shifts/{sid} ===")
    base_start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
    base_end = base_start + timedelta(hours=8)
    payload = {
        "user_id": staff_id,
        "title": "Initial Shift Title",
        "location": "Depot A",
        "start": base_start.isoformat(),
        "end": base_end.isoformat(),
        "notes": "initial notes",
        "recurring": "none",
        "repeat_count": 1,
    }
    # 2a POST /shifts admin
    r = requests.post(f"{BASE}/shifts", json=payload, headers=H(admin_tok))
    ok = r.status_code == 200 and r.json().get("created") == 1
    sid = None
    if ok:
        sid = r.json()["first"]["id"]
    log("2a POST /shifts admin recurring=none → created:1", ok, f"{r.status_code} sid={sid}")
    if not sid:
        print("Cannot continue PATCH tests without shift id")
    else:
        # 2b PATCH new title/start/end/location → user_id/user_name unchanged
        new_start = (base_start + timedelta(days=1)).isoformat()
        new_end = (base_end + timedelta(days=1)).isoformat()
        body = {
            "user_id": staff_id,
            "title": "Updated Title RT",
            "location": "Depot B - Updated",
            "start": new_start,
            "end": new_end,
            "notes": "updated notes",
            "recurring": "none",
            "repeat_count": 1,
        }
        r = requests.patch(f"{BASE}/shifts/{sid}", json=body, headers=H(admin_tok))
        d = r.json() if r.ok else {}
        ok = (
            r.status_code == 200
            and d.get("title") == "Updated Title RT"
            and d.get("location") == "Depot B - Updated"
            and d.get("start") == new_start
            and d.get("end") == new_end
            and d.get("user_id") == staff_id
            and d.get("user_name") == staff_user["name"]
        )
        log("2b PATCH new title/start/end/location, user unchanged", ok, f"{r.status_code} title={d.get('title')} user_name={d.get('user_name')}")

        # 2c PATCH different user_id → user_name auto-resolved
        body["user_id"] = admin_id
        r = requests.patch(f"{BASE}/shifts/{sid}", json=body, headers=H(admin_tok))
        d = r.json() if r.ok else {}
        ok = r.status_code == 200 and d.get("user_id") == admin_id and d.get("user_name") == admin_user["name"]
        log("2c PATCH user_id changes user_name auto-resolved", ok, f"{r.status_code} user_name={d.get('user_name')}")

        # 2d PATCH with customer_id + site_id → customer_name + site_name auto-populated
        # need a customer with at least one site
        cust_id = None
        site_id = None
        rc = requests.get(f"{BASE}/customers", headers=H(admin_tok))
        existing = [c for c in (rc.json() if rc.ok else []) if c.get("sites")]
        if existing:
            cust_id = existing[0]["id"]
            site_id = existing[0]["sites"][0]["id"]
            cust_name_expected = existing[0]["name"]
            site_name_expected = existing[0]["sites"][0]["name"]
        else:
            # create customer + site for the test
            rc = requests.post(f"{BASE}/customers", json={"name": "RT Test Customer", "company": "RT Co"}, headers=H(admin_tok))
            assert rc.status_code == 200, rc.text
            cust_id = rc.json()["id"]
            cust_name_expected = "RT Test Customer"
            rs = requests.post(
                f"{BASE}/customers/{cust_id}/sites",
                json={"name": "RT Site North", "address": "1 RT Way"},
                headers=H(admin_tok),
            )
            assert rs.status_code == 200, rs.text
            site_id = rs.json()["id"]
            site_name_expected = "RT Site North"

        body2 = dict(body)
        body2["customer_id"] = cust_id
        body2["site_id"] = site_id
        r = requests.patch(f"{BASE}/shifts/{sid}", json=body2, headers=H(admin_tok))
        d = r.json() if r.ok else {}
        ok = (
            r.status_code == 200
            and d.get("customer_id") == cust_id
            and d.get("customer_name") == cust_name_expected
            and d.get("site_id") == site_id
            and d.get("site_name") == site_name_expected
        )
        log("2d PATCH customer_id+site_id → customer_name + site_name auto-populated", ok, f"{r.status_code} cn={d.get('customer_name')} sn={d.get('site_name')}")

        # 2e PATCH as staff → 403
        r = requests.patch(f"{BASE}/shifts/{sid}", json=body2, headers=H(staff_tok))
        log("2e PATCH as staff → 403", r.status_code == 403, f"{r.status_code} {r.text[:120]}")

        # 2f PATCH non-existent shift → 404
        r = requests.patch(f"{BASE}/shifts/not-a-real-id-xyz", json=body2, headers=H(admin_tok))
        log("2f PATCH non-existent shift → 404", r.status_code == 404, f"{r.status_code} {r.text[:120]}")

        # 2g cleanup DELETE
        r = requests.delete(f"{BASE}/shifts/{sid}", headers=H(admin_tok))
        log("2g DELETE shift cleanup", r.status_code == 200, f"{r.status_code}")

    # ---------- 3. POST /users/me/push-token ----------
    print("\n=== 3. /users/me/push-token ===")
    valid_token = "ExponentPushToken[abc123]"
    # 3a staff valid → 200, /auth/me reflects it
    r = requests.post(f"{BASE}/users/me/push-token", json={"token": valid_token}, headers=H(staff_tok))
    ok = r.status_code == 200 and r.json().get("ok") is True
    log("3a staff valid token → 200 ok:true", ok, f"{r.status_code} {r.text[:120]}")
    r = requests.get(f"{BASE}/auth/me", headers=H(staff_tok))
    ok = r.status_code == 200 and r.json().get("expo_push_token") == valid_token
    log("3a /auth/me expo_push_token equals stored value", ok, f"{r.status_code} got={r.json().get('expo_push_token') if r.ok else r.text[:120]}")

    # 3b garbage token → 400
    r = requests.post(f"{BASE}/users/me/push-token", json={"token": "garbage-token"}, headers=H(staff_tok))
    log("3b garbage token → 400", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

    # 3c empty token → 200, then /auth/me shows null/empty
    r = requests.post(f"{BASE}/users/me/push-token", json={"token": ""}, headers=H(staff_tok))
    ok = r.status_code == 200 and r.json().get("ok") is True
    log("3c empty token → 200", ok, f"{r.status_code} {r.text[:120]}")
    r = requests.get(f"{BASE}/auth/me", headers=H(staff_tok))
    val = r.json().get("expo_push_token") if r.ok else "<err>"
    log("3c /auth/me expo_push_token is null/empty after clear", val in (None, ""), f"got={val!r}")

    # 3d admin valid token flow
    r = requests.post(f"{BASE}/users/me/push-token", json={"token": valid_token}, headers=H(admin_tok))
    ok = r.status_code == 200 and r.json().get("ok") is True
    log("3d admin valid token → 200", ok, f"{r.status_code}")
    # cleanup admin token so smoke test below runs without an expo_push_token
    requests.post(f"{BASE}/users/me/push-token", json={"token": ""}, headers=H(admin_tok))

    # ---------- 4. Smoke: notify must not break flows when no expo_push_token ----------
    print("\n=== 4. Smoke: notify() must not break create_shift/decide_holiday/decide_swap ===")
    # ensure both users have no token (already cleared for staff at 3c; admin at 3d cleanup)
    requests.post(f"{BASE}/users/me/push-token", json={"token": ""}, headers=H(staff_tok))

    # 4a create_shift (no token on staff)
    s_start = (datetime.now(timezone.utc) + timedelta(days=10)).replace(microsecond=0)
    s_end = s_start + timedelta(hours=4)
    r = requests.post(
        f"{BASE}/shifts",
        json={
            "user_id": staff_id,
            "title": "Smoke Notify Shift",
            "start": s_start.isoformat(),
            "end": s_end.isoformat(),
            "recurring": "none",
            "repeat_count": 1,
        },
        headers=H(admin_tok),
    )
    ok = r.status_code == 200 and r.json().get("created") == 1
    smoke_sid = r.json()["first"]["id"] if ok else None
    log("4a create_shift succeeds with no expo_push_token", ok, f"{r.status_code} {r.text[:200]}")

    # 4b POST /holidays/requests + decide_holiday
    today = datetime.now(timezone.utc).date()
    h_start = (today + timedelta(days=60)).isoformat()
    h_end = (today + timedelta(days=60)).isoformat()
    r = requests.post(
        f"{BASE}/holidays/requests",
        json={"start_date": h_start, "end_date": h_end, "reason": "RT smoke", "type": "annual"},
        headers=H(staff_tok),
    )
    ok = r.status_code == 200 and r.json().get("status") == "pending"
    h_id = r.json().get("id") if ok else None
    log("4b create holiday request", ok, f"{r.status_code} {r.text[:120]}")
    if h_id:
        r = requests.post(
            f"{BASE}/holidays/requests/{h_id}/decision",
            params={"decision": "rejected"},
            headers=H(admin_tok),
        )
        ok = r.status_code == 200 and r.json().get("ok") is True
        log("4b decide_holiday (reject) succeeds with no token", ok, f"{r.status_code} {r.text[:120]}")

    # 4c swap request (staff) + decide_swap (admin)
    if smoke_sid:
        r = requests.post(
            f"{BASE}/shifts/{smoke_sid}/swap",
            json={"target_user_id": admin_id, "reason": "RT swap smoke"},
            headers=H(staff_tok),
        )
        ok = r.status_code == 200 and r.json().get("status") == "pending"
        swap_id = r.json().get("id") if ok else None
        log("4c create swap request", ok, f"{r.status_code} {r.text[:120]}")
        if swap_id:
            r = requests.post(
                f"{BASE}/shifts/swaps/{swap_id}/decision",
                params={"decision": "rejected"},
                headers=H(admin_tok),
            )
            ok = r.status_code == 200 and r.json().get("ok") is True
            log("4c decide_swap (reject) succeeds with no token", ok, f"{r.status_code} {r.text[:120]}")

        # cleanup smoke shift
        requests.delete(f"{BASE}/shifts/{smoke_sid}", headers=H(admin_tok))

    # ---------- summary ----------
    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"{passed}/{total} passed")
    for name, ok, detail in results:
        if not ok:
            print(f"  FAIL: {name} -- {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
