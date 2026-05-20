"""
Phase A4 Test: Customer eircode/address fields + Site eircode field
Tests against the public proxy URL.
"""
import os
import sys
import json
import requests

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN_CREDS = {"email": "admin@company.com", "password": "Admin@123"}
STAFF_CREDS = {"email": "jane@company.com", "password": "Staff@123"}

passes = []
fails = []
created_cids = []


def check(label, cond, detail=""):
    if cond:
        passes.append(label)
        print(f"  PASS  {label}")
    else:
        fails.append((label, detail))
        print(f"  FAIL  {label} :: {detail}")


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j["access_token"], j["user"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    print("[Phase A4] Customer eircode/address & Site eircode")

    print("\n-- LOGIN --")
    admin_tok, admin_user = login(ADMIN_CREDS)
    staff_tok, staff_user = login(STAFF_CREDS)
    print(f"  admin_id={admin_user['id']}  staff_id={staff_user['id']}  staff_name={staff_user['name']}")
    admin_id = admin_user["id"]
    staff_id = staff_user["id"]
    staff_name = staff_user["name"]

    # =========================================================================
    # (A) Create customer with new fields
    # =========================================================================
    print("\n-- (A) Create customer with new fields --")

    # A1: Admin create with address+eircode
    payload = {
        "name": "Acme Co",
        "company": "Acme Ltd",
        "email": "contact@acme.ie",
        "phone": "+353-1-555-0100",
        "address": "12 Main St, Dublin",
        "eircode": "D02 X285",
    }
    r = requests.post(f"{BASE}/customers", headers=H(admin_tok), json=payload, timeout=30)
    check("A1 admin POST /customers (with address+eircode) status 200",
          r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    cid = None
    if r.status_code == 200:
        body = r.json()
        cid = body.get("id")
        created_cids.append(cid)
        check("A1 response has id", bool(cid), f"body={body}")
        check("A1 address persisted", body.get("address") == "12 Main St, Dublin",
              f"got={body.get('address')}")
        check("A1 eircode persisted", body.get("eircode") == "D02 X285",
              f"got={body.get('eircode')}")
        check("A1 name persisted", body.get("name") == "Acme Co", f"got={body.get('name')}")

    # A2: GET as admin
    r = requests.get(f"{BASE}/customers/{cid}", headers=H(admin_tok), timeout=30)
    check("A2 admin GET /customers/{cid} status 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        b = r.json()
        check("A2 address visible", b.get("address") == "12 Main St, Dublin")
        check("A2 eircode visible", b.get("eircode") == "D02 X285")

    # A3: GET as staff (Jane)
    r = requests.get(f"{BASE}/customers/{cid}", headers=H(staff_tok), timeout=30)
    check("A3 staff GET /customers/{cid} status 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        b = r.json()
        check("A3 staff sees address", b.get("address") == "12 Main St, Dublin")
        check("A3 staff sees eircode", b.get("eircode") == "D02 X285")

    # A4: GET /customers list as staff
    r = requests.get(f"{BASE}/customers", headers=H(staff_tok), timeout=30)
    check("A4 staff GET /customers status 200", r.status_code == 200)
    if r.status_code == 200:
        lst = r.json()
        match = [c for c in lst if c.get("id") == cid]
        check("A4 list contains new customer", len(match) == 1, f"matches={len(match)}")
        if match:
            check("A4 list item has address", match[0].get("address") == "12 Main St, Dublin")
            check("A4 list item has eircode", match[0].get("eircode") == "D02 X285")

    # A5: Staff POST /customers → 403
    r = requests.post(f"{BASE}/customers", headers=H(staff_tok),
                      json={"name": "Should Fail"}, timeout=30)
    check("A5 staff POST /customers 403", r.status_code == 403,
          f"status={r.status_code} body={r.text[:200]}")

    # =========================================================================
    # (B) Backward compat
    # =========================================================================
    print("\n-- (B) Backward compat (no address/eircode) --")

    r = requests.post(f"{BASE}/customers", headers=H(admin_tok),
                      json={"name": "Legacy Customer Ltd", "company": "Legacy Holdings"},
                      timeout=30)
    check("B1 admin POST /customers WITHOUT address/eircode 200",
          r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    legacy_cid = None
    if r.status_code == 200:
        b = r.json()
        legacy_cid = b.get("id")
        created_cids.append(legacy_cid)
        # null or missing both acceptable
        addr = b.get("address", None)
        eir = b.get("eircode", None)
        check("B1 address null/missing", addr is None,
              f"got address={addr}")
        check("B1 eircode null/missing", eir is None,
              f"got eircode={eir}")

    r = requests.get(f"{BASE}/customers/{legacy_cid}", headers=H(admin_tok), timeout=30)
    check("B2 GET legacy customer 200 (no crash)", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        b = r.json()
        check("B2 legacy address null/missing", b.get("address") is None)
        check("B2 legacy eircode null/missing", b.get("eircode") is None)

    # =========================================================================
    # (C) PATCH update fields
    # =========================================================================
    print("\n-- (C) PATCH updates --")

    # C1: rename + new address + new eircode
    r = requests.patch(f"{BASE}/customers/{cid}", headers=H(admin_tok),
                       json={"name": "Acme Co Renamed",
                             "address": "NEW addr",
                             "eircode": "A65 F4E2"}, timeout=30)
    check("C1 admin PATCH (rename+addr+eir) 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        b = r.json()
        check("C1 name=Acme Co Renamed", b.get("name") == "Acme Co Renamed")
        check("C1 address=NEW addr", b.get("address") == "NEW addr")
        check("C1 eircode=A65 F4E2", b.get("eircode") == "A65 F4E2")

    # C2: clear eircode (set to empty string)
    r = requests.patch(f"{BASE}/customers/{cid}", headers=H(admin_tok),
                       json={"name": "Acme Co Renamed", "eircode": ""}, timeout=30)
    check("C2 admin PATCH clear eircode 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        b = r.json()
        eir = b.get("eircode")
        check("C2 eircode cleared (empty or null)", eir in ("", None),
              f"got eircode={eir!r}")

    # C3: Staff PATCH → 403
    r = requests.patch(f"{BASE}/customers/{cid}", headers=H(staff_tok),
                       json={"name": "Hack"}, timeout=30)
    check("C3 staff PATCH /customers/{cid} 403", r.status_code == 403,
          f"status={r.status_code}")

    # =========================================================================
    # (D) Sites with eircode
    # =========================================================================
    print("\n-- (D) Sites with eircode --")

    # D1: Admin add site with eircode
    site_payload = {
        "name": "Main Yard",
        "address": "Yard Rd",
        "eircode": "D04 W7N6",
        "description": "rear gate",
    }
    r = requests.post(f"{BASE}/customers/{cid}/sites", headers=H(admin_tok),
                      json=site_payload, timeout=30)
    check("D1 admin POST /customers/{cid}/sites 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:300]}")
    site_id = None
    if r.status_code == 200:
        b = r.json()
        site_id = b.get("id")
        check("D1 site has eircode=D04 W7N6", b.get("eircode") == "D04 W7N6",
              f"got={b.get('eircode')}")
        check("D1 site name=Main Yard", b.get("name") == "Main Yard")
        check("D1 site address=Yard Rd", b.get("address") == "Yard Rd")
        check("D1 site description=rear gate", b.get("description") == "rear gate")

    # D2: GET customer shows site has eircode
    r = requests.get(f"{BASE}/customers/{cid}", headers=H(admin_tok), timeout=30)
    if r.status_code == 200:
        cust = r.json()
        sites = cust.get("sites", [])
        site = next((s for s in sites if s.get("id") == site_id), None)
        check("D2 customer doc contains site", site is not None,
              f"sites count={len(sites)}")
        if site:
            check("D2 site.eircode=D04 W7N6", site.get("eircode") == "D04 W7N6")

    # D3: Admin add site WITHOUT eircode
    r = requests.post(f"{BASE}/customers/{cid}/sites", headers=H(admin_tok),
                      json={"name": "Old Site"}, timeout=30)
    check("D3 admin POST site no eircode 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        b = r.json()
        check("D3 site eircode null/missing", b.get("eircode") is None,
              f"got eircode={b.get('eircode')!r}")
        check("D3 site name=Old Site", b.get("name") == "Old Site")

    # D4: Staff POST /sites → 403
    r = requests.post(f"{BASE}/customers/{cid}/sites", headers=H(staff_tok),
                      json={"name": "StaffSite"}, timeout=30)
    check("D4 staff POST sites 403", r.status_code == 403, f"status={r.status_code}")

    # =========================================================================
    # (E) Notes — staff can add notes
    # =========================================================================
    print("\n-- (E) Notes (staff CAN add) --")

    # E1: Staff post note
    r = requests.post(f"{BASE}/customers/{cid}/notes", headers=H(staff_tok),
                      json={"body": "gate code 1234", "category": "access", "pinned": False},
                      timeout=30)
    check("E1 staff POST /customers/{cid}/notes 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:300]}")
    staff_note_id = None
    if r.status_code == 200:
        b = r.json()
        staff_note_id = b.get("id")
        check(f"E1 note.author_name='{staff_name}'", b.get("author_name") == staff_name,
              f"got author_name={b.get('author_name')!r}")
        check("E1 note.author_id=staff_id", b.get("author_id") == staff_id,
              f"got author_id={b.get('author_id')!r}")
        check("E1 note.body=gate code 1234", b.get("body") == "gate code 1234")
        check("E1 note.category=access", b.get("category") == "access")
        check("E1 note.pinned=False", b.get("pinned") is False)

    # E2: GET notes as staff
    r = requests.get(f"{BASE}/customers/{cid}/notes", headers=H(staff_tok), timeout=30)
    check("E2 staff GET notes 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        lst = r.json()
        check("E2 staff note in list",
              any(n.get("id") == staff_note_id for n in lst),
              f"count={len(lst)}")

    # E3: Admin posts pinned note
    r = requests.post(f"{BASE}/customers/{cid}/notes", headers=H(admin_tok),
                      json={"body": "pinned admin note", "category": "general", "pinned": True},
                      timeout=30)
    check("E3 admin POST pinned note 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:200]}")
    admin_note_id = None
    if r.status_code == 200:
        b = r.json()
        admin_note_id = b.get("id")
        check("E3 note.pinned=True", b.get("pinned") is True)

    # Verify pinned-first ordering
    r = requests.get(f"{BASE}/customers/{cid}/notes", headers=H(admin_tok), timeout=30)
    if r.status_code == 200:
        lst = r.json()
        check("E3 GET notes returns list", isinstance(lst, list) and len(lst) >= 2)
        if lst:
            check("E3 pinned-first ordering (first note is pinned)",
                  lst[0].get("pinned") is True,
                  f"first.pinned={lst[0].get('pinned')} first.id={lst[0].get('id')}")
            check("E3 first note is the admin pinned one",
                  lst[0].get("id") == admin_note_id,
                  f"first.id={lst[0].get('id')} expected={admin_note_id}")

    # =========================================================================
    # (F) Cleanup
    # =========================================================================
    print("\n-- (F) Cleanup --")
    for c in created_cids:
        r = requests.delete(f"{BASE}/customers/{c}", headers=H(admin_tok), timeout=30)
        check(f"F DELETE /customers/{c[:8]}... 200", r.status_code == 200,
              f"status={r.status_code}")

    # =========================================================================
    print("\n" + "=" * 60)
    print(f"TOTAL: {len(passes)} pass / {len(fails)} fail")
    if fails:
        print("\nFAILURES:")
        for label, detail in fails:
            print(f"  - {label}\n      {detail}")
    print("=" * 60)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
