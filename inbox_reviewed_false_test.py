"""Phase A2 retest — inbox ?reviewed=false filter (legacy + explicit-false coverage).

Validates that GET /api/admin/submissions-inbox?reviewed=false now returns
all submissions where `reviewed` is NOT True (i.e., missing field OR False).
"""
import os
import sys
import time
import base64
import io
import requests

BASE = os.environ.get("BACKEND_URL", "https://employee-connect-9.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN = ("admin@company.com", "Admin@123")
STAFF = ("jane@company.com", "Staff@123")


def login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    fails = []
    passes = []

    def check(cond, msg):
        if cond:
            passes.append(msg)
            print(f"PASS: {msg}")
        else:
            fails.append(msg)
            print(f"FAIL: {msg}")

    print("=" * 60)
    print("Phase A2 retest: GET /admin/submissions-inbox?reviewed=false")
    print("=" * 60)

    admin_tok = login(*ADMIN)
    staff_tok = login(*STAFF)
    print("Auth: admin + staff tokens obtained.")

    # --- Scenario 1, 2, 3, 4: list counts ---
    r_all = requests.get(f"{BASE}/admin/submissions-inbox", headers=h(admin_tok), params={"limit": 1000}, timeout=30)
    check(r_all.status_code == 200, f"GET inbox (no filter) → 200 (got {r_all.status_code})")
    rows_all = r_all.json() if r_all.status_code == 200 else []
    n_all = len(rows_all)
    print(f"  count(no filter) = {n_all}")

    r_false = requests.get(f"{BASE}/admin/submissions-inbox", headers=h(admin_tok), params={"reviewed": "false", "limit": 1000}, timeout=30)
    check(r_false.status_code == 200, f"GET inbox ?reviewed=false → 200 (got {r_false.status_code})")
    rows_false = r_false.json() if r_false.status_code == 200 else []
    n_false = len(rows_false)
    print(f"  count(reviewed=false) = {n_false}")

    r_true = requests.get(f"{BASE}/admin/submissions-inbox", headers=h(admin_tok), params={"reviewed": "true", "limit": 1000}, timeout=30)
    check(r_true.status_code == 200, f"GET inbox ?reviewed=true → 200 (got {r_true.status_code})")
    rows_true = r_true.json() if r_true.status_code == 200 else []
    n_true = len(rows_true)
    print(f"  count(reviewed=true) = {n_true}")

    # Scenario 2: reviewed=false count should be significantly more than 2
    check(n_false > 2, f"reviewed=false count ({n_false}) > 2 (previous failure showed 2)")

    # Scenario 4: math should add up
    check(
        n_all == n_true + n_false,
        f"Math: count(no filter)={n_all} == count(reviewed=true)={n_true} + count(reviewed=false)={n_false}",
    )

    # Each row in ?reviewed=false should NOT have reviewed=True
    bad_false = [r for r in rows_false if r.get("reviewed") is True]
    check(len(bad_false) == 0, f"All rows in reviewed=false have reviewed != True (bad rows={len(bad_false)})")

    # Each row in ?reviewed=true must have reviewed=True
    bad_true = [r for r in rows_true if r.get("reviewed") is not True]
    check(len(bad_true) == 0, f"All rows in reviewed=true have reviewed == True (bad rows={len(bad_true)})")

    # Sample inspection — count legacy (field missing/None) vs explicit False in rows_false
    legacy_count = sum(1 for r in rows_false if r.get("reviewed") in (None, False))
    print(f"  legacy/false rows in reviewed=false = {legacy_count}/{n_false}")

    # --- Scenario 5: Create fresh form submission as staff, verify it appears in ?reviewed=false ---
    print("\n--- Scenario 5: fresh staff form submission ---")
    # Create a tiny form template as admin
    tpl_payload = {
        "title": "Retest Inbox A2 Reviewed=false",
        "kind": "form",
        "fields": [{"key": "comment", "type": "text", "label": "Comment"}],
    }
    r_tpl = requests.post(f"{BASE}/forms/templates", headers=h(admin_tok), json=tpl_payload, timeout=20)
    check(r_tpl.status_code == 200, f"Create form template → 200 (got {r_tpl.status_code} {r_tpl.text[:200]})")
    tid = r_tpl.json().get("id") if r_tpl.status_code == 200 else None

    sid = None
    if tid:
        r_sub = requests.post(
            f"{BASE}/forms/submissions",
            headers=h(staff_tok),
            json={"template_id": tid, "values": {"comment": "retest A2 reviewed=false fix"}},
            timeout=20,
        )
        check(r_sub.status_code == 200, f"Staff POST /forms/submissions → 200 (got {r_sub.status_code} {r_sub.text[:200]})")
        if r_sub.status_code == 200:
            sid = r_sub.json().get("id")
            print(f"  new submission id={sid}")

    if sid:
        # GET ?reviewed=false should include this submission
        r_false2 = requests.get(
            f"{BASE}/admin/submissions-inbox",
            headers=h(admin_tok),
            params={"reviewed": "false", "limit": 1000},
            timeout=30,
        )
        check(r_false2.status_code == 200, "GET inbox ?reviewed=false (after new submission) → 200")
        rows_false2 = r_false2.json() if r_false2.status_code == 200 else []
        ids_false2 = {r.get("id") for r in rows_false2}
        check(sid in ids_false2, f"New submission id={sid} appears in ?reviewed=false (size={len(rows_false2)})")

        # And NOT in ?reviewed=true
        r_true2 = requests.get(
            f"{BASE}/admin/submissions-inbox",
            headers=h(admin_tok),
            params={"reviewed": "true", "limit": 1000},
            timeout=30,
        )
        rows_true2 = r_true2.json() if r_true2.status_code == 200 else []
        ids_true2 = {r.get("id") for r in rows_true2}
        check(sid not in ids_true2, f"New submission id={sid} does NOT appear in ?reviewed=true")

        # Toggle reviewed=true on it, then it should disappear from ?reviewed=false and appear in ?reviewed=true
        r_toggle = requests.patch(
            f"{BASE}/forms/submissions/{sid}/review",
            headers=h(admin_tok),
            json={"reviewed": True},
            timeout=20,
        )
        check(r_toggle.status_code == 200, f"PATCH review reviewed=true → 200 (got {r_toggle.status_code})")

        r_false3 = requests.get(
            f"{BASE}/admin/submissions-inbox",
            headers=h(admin_tok),
            params={"reviewed": "false", "limit": 1000},
            timeout=30,
        )
        ids_false3 = {r.get("id") for r in (r_false3.json() if r_false3.status_code == 200 else [])}
        check(sid not in ids_false3, "After toggle reviewed=true, sid not in ?reviewed=false")

        r_true3 = requests.get(
            f"{BASE}/admin/submissions-inbox",
            headers=h(admin_tok),
            params={"reviewed": "true", "limit": 1000},
            timeout=30,
        )
        ids_true3 = {r.get("id") for r in (r_true3.json() if r_true3.status_code == 200 else [])}
        check(sid in ids_true3, "After toggle reviewed=true, sid appears in ?reviewed=true")

        # Toggle back to false and verify it returns to ?reviewed=false
        requests.patch(
            f"{BASE}/forms/submissions/{sid}/review",
            headers=h(admin_tok),
            json={"reviewed": False},
            timeout=20,
        )
        r_false4 = requests.get(
            f"{BASE}/admin/submissions-inbox",
            headers=h(admin_tok),
            params={"reviewed": "false", "limit": 1000},
            timeout=30,
        )
        ids_false4 = {r.get("id") for r in (r_false4.json() if r_false4.status_code == 200 else [])}
        check(sid in ids_false4, "After toggle back reviewed=false, sid back in ?reviewed=false")

    # --- Cleanup ---
    if tid:
        r_del = requests.delete(f"{BASE}/forms/templates/{tid}", headers=h(admin_tok), timeout=20)
        print(f"Cleanup DELETE template → {r_del.status_code}")

    # --- Final math re-check after cleanup, to ensure invariant holds ---
    r_all_f = requests.get(f"{BASE}/admin/submissions-inbox", headers=h(admin_tok), params={"limit": 1000}, timeout=30)
    r_t_f = requests.get(f"{BASE}/admin/submissions-inbox", headers=h(admin_tok), params={"reviewed": "true", "limit": 1000}, timeout=30)
    r_f_f = requests.get(f"{BASE}/admin/submissions-inbox", headers=h(admin_tok), params={"reviewed": "false", "limit": 1000}, timeout=30)
    a, t, f = len(r_all_f.json()), len(r_t_f.json()), len(r_f_f.json())
    print(f"Final counts (post-cleanup): all={a}, true={t}, false={f}")
    check(a == t + f, f"Final invariant: {a} == {t} + {f}")

    print("\n" + "=" * 60)
    print(f"RESULTS: {len(passes)} PASS, {len(fails)} FAIL")
    print("=" * 60)
    if fails:
        for m in fails:
            print(f"  FAIL: {m}")
        sys.exit(1)


if __name__ == "__main__":
    main()
