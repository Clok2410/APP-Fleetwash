"""Phase A3 HR DocuSign-replacement backend test suite.

Runs against the public proxy URL. Reports PASS/FAIL count.
"""
import base64
import io
import os
import sys
from datetime import datetime

import requests

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@company.com"
ADMIN_PASS = "Admin@123"
STAFF_EMAIL = "jane@company.com"
STAFF_PASS = "Staff@123"

# 1x1 transparent PNG
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

results = []  # (name, passed, detail)


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}{(' — ' + detail) if detail else ''}")


def login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data["user"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def main():
    print(f"=== Auth ===")
    admin_token, admin_user = login(ADMIN_EMAIL, ADMIN_PASS)
    staff_token, staff_user = login(STAFF_EMAIL, STAFF_PASS)
    admin_id = admin_user["id"]
    jane_id = staff_user["id"]
    check("auth.login admin", admin_user.get("role") == "admin", admin_user.get("role"))
    check("auth.login staff", staff_user.get("role") == "staff", staff_user.get("role"))

    # =============== (A) Issue & List ===============
    print("\n=== (A) Issue & list ===")
    # A1 — pick an existing PDF template
    r = requests.get(f"{BASE}/pdf-forms/templates", headers=auth(admin_token), timeout=30)
    check("A1.list templates 200", r.status_code == 200, str(r.status_code))
    tpls = r.json()
    check("A1.has >=1 template", len(tpls) >= 1, f"count={len(tpls)}")
    tid = tpls[0]["id"] if tpls else None
    if not tid:
        # As fallback: upload a minimal template using reportlab
        try:
            from reportlab.pdfgen import canvas
            buf = io.BytesIO()
            c = canvas.Canvas(buf)
            c.drawString(72, 720, "Test HR Doc")
            c.save()
            up = requests.post(
                f"{BASE}/pdf-forms/templates",
                headers=auth(admin_token),
                json={"title": "HR Test Doc", "pdf_base64": base64.b64encode(buf.getvalue()).decode()},
                timeout=30,
            )
            tid = up.json()["id"]
        except Exception as e:
            print(f"FATAL: cannot create template: {e}")
            sys.exit(1)

    # A2 — Admin issues to jane
    body = {"template_id": tid, "user_id": jane_id, "expires_at": "2027-12-31", "message": "Test handbook"}
    r = requests.post(f"{BASE}/hr/issue", headers=auth(admin_token), json=body, timeout=30)
    check("A2.issue 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    issuance = r.json() if r.status_code == 200 else {}
    iid = issuance.get("id")
    check("A2.status pending", issuance.get("status") == "pending", issuance.get("status"))
    check("A2.audit[0] issued", (issuance.get("audit") or [{}])[0].get("kind") == "issued")
    check("A2.issued_by admin", issuance.get("issued_by") == admin_id)
    check("A2.issued_by_name 'Admin'", issuance.get("issued_by_name") == "Admin", issuance.get("issued_by_name"))
    check("A2.message", issuance.get("message") == "Test handbook")
    check("A2.expires_at", issuance.get("expires_at") == "2027-12-31")

    # A3 — admin list ?user_id=jane
    r = requests.get(f"{BASE}/hr/issuances", headers=auth(admin_token), params={"user_id": jane_id}, timeout=30)
    check("A3.admin list 200", r.status_code == 200)
    ids = [d["id"] for d in r.json()]
    check("A3.contains iid", iid in ids)

    # A4 — staff list
    r = requests.get(f"{BASE}/hr/issuances", headers=auth(staff_token), timeout=30)
    check("A4.staff list 200", r.status_code == 200)
    staff_list = r.json()
    check("A4.contains iid", any(d["id"] == iid for d in staff_list))
    # Verify only own
    own_check = all(d.get("user_id") == jane_id for d in staff_list)
    check("A4.only own (user_id=jane)", own_check)

    # A5 — admin filter status=pending
    r = requests.get(f"{BASE}/hr/issuances", headers=auth(admin_token), params={"status": "pending"}, timeout=30)
    check("A5.filter pending 200", r.status_code == 200)
    check("A5.contains iid", any(d["id"] == iid for d in r.json()))

    # A6 — unauth
    r = requests.get(f"{BASE}/hr/issuances", timeout=30)
    check("A6.unauth GET 401", r.status_code == 401, str(r.status_code))

    # A7 — issue with non-existent template
    r = requests.post(f"{BASE}/hr/issue", headers=auth(admin_token), json={"template_id": "nonexistent-xxx", "user_id": jane_id}, timeout=30)
    check("A7.bad template 404", r.status_code == 404, str(r.status_code))

    # A8 — non-existent user
    r = requests.post(f"{BASE}/hr/issue", headers=auth(admin_token), json={"template_id": tid, "user_id": "nonexistent-uid"}, timeout=30)
    check("A8.bad user 404", r.status_code == 404, str(r.status_code))

    # A9 — bad expires_at
    r = requests.post(f"{BASE}/hr/issue", headers=auth(admin_token), json={"template_id": tid, "user_id": jane_id, "expires_at": "bad"}, timeout=30)
    check("A9.bad date 400", r.status_code == 400, str(r.status_code))

    # A10 — staff issue
    r = requests.post(f"{BASE}/hr/issue", headers=auth(staff_token), json={"template_id": tid, "user_id": jane_id}, timeout=30)
    check("A10.staff issue 403", r.status_code == 403, str(r.status_code))

    # =============== (B) Read flow ===============
    print("\n=== (B) Read flow ===")
    r = requests.post(f"{BASE}/hr/issuances/{iid}/read", headers=auth(staff_token), timeout=30)
    check("B1.staff read 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    rd1 = r.json() if r.status_code == 200 else {}
    check("B1.status read", rd1.get("status") == "read", rd1.get("status"))
    check("B1.read_at populated", bool(rd1.get("read_at")))
    audit = rd1.get("audit") or []
    audit_len_b1 = len(audit)
    read_evt = next((e for e in audit if e.get("kind") == "read"), None)
    check("B1.audit has 'read'", read_evt is not None)
    check("B1.read actor_name Jane Doe", (read_evt or {}).get("actor_name") == "Jane Doe", (read_evt or {}).get("actor_name"))

    # B2 — re-call (idempotent)
    r = requests.post(f"{BASE}/hr/issuances/{iid}/read", headers=auth(staff_token), timeout=30)
    check("B2.idempotent 200", r.status_code == 200)
    rd2 = r.json()
    check("B2.status still read", rd2.get("status") == "read")
    audit_len_b2 = len(rd2.get("audit") or [])
    check("B2.audit length unchanged", audit_len_b2 == audit_len_b1, f"before={audit_len_b1} after={audit_len_b2}")

    # B3 — admin can also call /read (spec says admin allowed)
    r = requests.post(f"{BASE}/hr/issuances/{iid}/read", headers=auth(admin_token), timeout=30)
    check("B3.admin /read allowed 200", r.status_code == 200, str(r.status_code))

    # B4 — unauth
    r = requests.post(f"{BASE}/hr/issuances/{iid}/read", timeout=30)
    check("B4.unauth /read 401", r.status_code == 401, str(r.status_code))

    # B5 — non-existent
    r = requests.post(f"{BASE}/hr/issuances/nope-not-real/read", headers=auth(staff_token), timeout=30)
    check("B5./read 404", r.status_code == 404, str(r.status_code))

    # =============== (C) Sign flow ===============
    print("\n=== (C) Sign flow ===")
    # C1 — admin sign
    r = requests.post(f"{BASE}/hr/issuances/{iid}/sign", headers=auth(admin_token), json={"signature_base64": TINY_PNG_B64}, timeout=30)
    check("C1.admin sign 403", r.status_code == 403, str(r.status_code))

    # C2 — empty body
    r = requests.post(f"{BASE}/hr/issuances/{iid}/sign", headers=auth(staff_token), json={}, timeout=30)
    check("C2.empty body 422/400", r.status_code in (400, 422), str(r.status_code))

    # C3 — invalid base64
    r = requests.post(f"{BASE}/hr/issuances/{iid}/sign", headers=auth(staff_token), json={"signature_base64": "@@@not-base64@@@"}, timeout=60)
    check("C3.invalid b64 400", r.status_code == 400, f"{r.status_code} {r.text[:200]}")

    # C4 — valid sign
    r = requests.post(
        f"{BASE}/hr/issuances/{iid}/sign",
        headers={**auth(staff_token), "User-Agent": "HR-A3-Test/1.0"},
        json={"signature_base64": TINY_PNG_B64, "printed_name": "Jane Doe"},
        timeout=60,
    )
    check("C4.sign 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    signed_doc = r.json() if r.status_code == 200 else {}
    check("C4.status signed", signed_doc.get("status") == "signed")
    check("C4.signed_at present", bool(signed_doc.get("signed_at")))
    check("C4.signature_ip field exists", "signature_ip" in signed_doc)
    check("C4.signature_user_agent captured", "HR-A3-Test" in (signed_doc.get("signature_user_agent") or ""), signed_doc.get("signature_user_agent"))
    check("C4.printed_name", signed_doc.get("printed_name") == "Jane Doe")
    check("C4.has_signed_pdf true", signed_doc.get("has_signed_pdf") is True)
    audit_signed = signed_doc.get("audit") or []
    check("C4.audit has 'signed'", any(e.get("kind") == "signed" for e in audit_signed))

    # C5 — sign again
    r = requests.post(f"{BASE}/hr/issuances/{iid}/sign", headers=auth(staff_token), json={"signature_base64": TINY_PNG_B64}, timeout=30)
    check("C5.already signed 400", r.status_code == 400, str(r.status_code))

    # C6 — non-existent
    r = requests.post(f"{BASE}/hr/issuances/nope-not-real/sign", headers=auth(staff_token), json={"signature_base64": TINY_PNG_B64}, timeout=30)
    check("C6.sign nonexistent 404", r.status_code == 404, str(r.status_code))

    # C7 — unauth
    r = requests.post(f"{BASE}/hr/issuances/{iid}/sign", json={"signature_base64": TINY_PNG_B64}, timeout=30)
    check("C7.unauth sign 401", r.status_code == 401, str(r.status_code))

    # =============== (D) Signed PDF download ===============
    print("\n=== (D) Signed PDF download ===")
    # D1 — staff download
    r = requests.get(f"{BASE}/hr/issuances/{iid}/pdf", headers=auth(staff_token), timeout=60)
    check("D1.staff pdf 200", r.status_code == 200, str(r.status_code))
    check("D1.content-type application/pdf", "application/pdf" in r.headers.get("content-type", ""), r.headers.get("content-type"))
    check("D1.body starts with %PDF", r.content[:5] == b"%PDF-", str(r.content[:10]))
    check("D1.body length > 1000", len(r.content) > 1000, f"len={len(r.content)}")

    # D2 — admin download
    r = requests.get(f"{BASE}/hr/issuances/{iid}/pdf", headers=auth(admin_token), timeout=60)
    check("D2.admin pdf 200", r.status_code == 200, str(r.status_code))
    check("D2.body starts with %PDF", r.content[:5] == b"%PDF-")

    # D3 — create a second staff user via admin /auth/register, then try to access Jane's PDF
    other_email = f"hr_other_staff_{int(datetime.utcnow().timestamp())}@company.com"
    other_password = "Other@123"
    r = requests.post(
        f"{BASE}/auth/register",
        headers=auth(admin_token),
        json={"email": other_email, "password": other_password, "name": "Other Staff", "role": "staff"},
        timeout=30,
    )
    other_created = r.status_code == 200
    other_token = None
    if other_created:
        try:
            other_token, _ = login(other_email, other_password)
        except Exception:
            other_token = None
    if other_token:
        r = requests.get(f"{BASE}/hr/issuances/{iid}/pdf", headers=auth(other_token), timeout=60)
        check("D3.other staff pdf 403", r.status_code == 403, str(r.status_code))
    else:
        print("[SKIP] D3 — could not create or log in second staff user (auth/register may not allow). Will attempt direct sweep with no token.")

    # D4 — unauth
    r = requests.get(f"{BASE}/hr/issuances/{iid}/pdf", timeout=30)
    check("D4.unauth pdf 401", r.status_code == 401, str(r.status_code))

    # D5 — non-existent
    r = requests.get(f"{BASE}/hr/issuances/nope-not-real/pdf", headers=auth(admin_token), timeout=30)
    check("D5.pdf nonexistent 404", r.status_code == 404, str(r.status_code))

    # =============== (E) Cancel ===============
    print("\n=== (E) Cancel ===")
    # E1 — issue fresh doc
    r = requests.post(f"{BASE}/hr/issue", headers=auth(admin_token), json={"template_id": tid, "user_id": jane_id, "message": "Fresh"}, timeout=30)
    check("E1.fresh issue 200", r.status_code == 200)
    iid2 = r.json().get("id") if r.status_code == 200 else None

    # E2 — admin cancel fresh
    if iid2:
        r = requests.post(f"{BASE}/hr/issuances/{iid2}/cancel", headers=auth(admin_token), timeout=30)
        check("E2.cancel 200", r.status_code == 200, str(r.status_code))
        cd = r.json() if r.status_code == 200 else {}
        check("E2.status cancelled", cd.get("status") == "cancelled", cd.get("status"))
        check("E2.audit has 'cancelled'", any(e.get("kind") == "cancelled" for e in (cd.get("audit") or [])))

    # E3 — cancel signed
    r = requests.post(f"{BASE}/hr/issuances/{iid}/cancel", headers=auth(admin_token), timeout=30)
    check("E3.cancel signed 400", r.status_code == 400, str(r.status_code))
    if r.status_code == 400:
        check("E3.detail mentions signed", "signed" in (r.json().get("detail", "").lower()))

    # E4 — staff cancel
    if iid2:
        r = requests.post(f"{BASE}/hr/issuances/{iid2}/cancel", headers=auth(staff_token), timeout=30)
        check("E4.staff cancel 403", r.status_code == 403, str(r.status_code))

    # =============== (F) Staff directory ===============
    print("\n=== (F) Staff directory ===")
    r = requests.get(f"{BASE}/hr/staff", headers=auth(admin_token), timeout=30)
    check("F1./hr/staff 200", r.status_code == 200)
    staff_list = r.json() if r.status_code == 200 else []
    check("F1.list non-empty", len(staff_list) >= 1)
    if staff_list:
        names = [s.get("name", "") for s in staff_list]
        check("F1.alphabetical", names == sorted(names, key=lambda x: (x or "").lower()), str(names[:6]))
        # No admin
        roles = [s.get("role") for s in staff_list]
        check("F1.no admin in list", "admin" not in roles)
        s0 = staff_list[0]
        check("F1.has id", "id" in s0)
        check("F1.has email", "email" in s0)
        check("F1.has name", "name" in s0)
        check("F1.has hr_counts", isinstance(s0.get("hr_counts"), dict))
        if isinstance(s0.get("hr_counts"), dict):
            req_keys = {"pending", "read", "signed", "expired", "cancelled"}
            check("F1.hr_counts keys", req_keys.issubset(set(s0["hr_counts"].keys())))
        check("F1.has hr_total", "hr_total" in s0)
        check("F1.has hr_pending_signature", "hr_pending_signature" in s0)
        check("F1.no password_hash", "password_hash" not in s0)

    # F2
    r = requests.get(f"{BASE}/hr/staff", headers=auth(staff_token), timeout=30)
    check("F2.staff GET 403", r.status_code == 403, str(r.status_code))

    # =============== (G) Staff profile detail ===============
    print("\n=== (G) Staff profile detail ===")
    r = requests.get(f"{BASE}/hr/staff/{jane_id}/profile", headers=auth(admin_token), timeout=30)
    check("G1.profile 200", r.status_code == 200, str(r.status_code))
    prof = r.json() if r.status_code == 200 else {}
    check("G1.has user", isinstance(prof.get("user"), dict))
    if isinstance(prof.get("user"), dict):
        check("G1.user.id matches", prof["user"].get("id") == jane_id)
    check("G1.has holiday", isinstance(prof.get("holiday"), dict))
    if isinstance(prof.get("holiday"), dict):
        h = prof["holiday"]
        for k in ("entitlement", "used_days", "pending_days", "remaining"):
            check(f"G1.holiday.{k} present", k in h)
    check("G1.has issuances list", isinstance(prof.get("issuances"), list))
    if isinstance(prof.get("issuances"), list):
        signed_in_list = next((d for d in prof["issuances"] if d.get("id") == iid), None)
        check("G1.signed iid present", signed_in_list is not None)
        if signed_in_list:
            check("G1.signed status='signed'", signed_in_list.get("status") == "signed")
            check("G1.has_signed_pdf=true", signed_in_list.get("has_signed_pdf") is True)
            check("G1.signed_pdf_base64 stripped", "signed_pdf_base64" not in signed_in_list)

    # G2
    r = requests.get(f"{BASE}/hr/staff/{jane_id}/profile", headers=auth(staff_token), timeout=30)
    check("G2.staff profile 403", r.status_code == 403, str(r.status_code))

    # =============== (H) Expiry sweep ===============
    print("\n=== (H) Expiry sweep ===")
    # H1 — issue with past expires_at
    r = requests.post(f"{BASE}/hr/issue", headers=auth(admin_token), json={"template_id": tid, "user_id": jane_id, "expires_at": "2020-01-01", "message": "Past doc"}, timeout=30)
    check("H1.fresh past-expiry issue 200", r.status_code == 200, str(r.status_code))
    iid3 = r.json().get("id") if r.status_code == 200 else None

    # H2 — sweep
    r = requests.post(f"{BASE}/hr/sweep-expiry", headers=auth(admin_token), timeout=30)
    check("H2.sweep 200", r.status_code == 200, str(r.status_code))
    sw = r.json() if r.status_code == 200 else {}
    check("H2.expired count >=1", sw.get("expired", 0) >= 1, f"expired={sw.get('expired')}")

    # H3 — verify iid3 expired
    if iid3:
        r = requests.get(f"{BASE}/hr/issuances/{iid3}", headers=auth(admin_token), timeout=30)
        check("H3.get iid3 200", r.status_code == 200)
        d3 = r.json() if r.status_code == 200 else {}
        check("H3.status expired", d3.get("status") == "expired", d3.get("status"))
        check("H3.audit has 'expired'", any(e.get("kind") == "expired" for e in (d3.get("audit") or [])))

    # H4 — staff sweep
    r = requests.post(f"{BASE}/hr/sweep-expiry", headers=auth(staff_token), timeout=30)
    check("H4.staff sweep 403", r.status_code == 403, str(r.status_code))

    # =============== (I) Regression: customers/depots refactor ===============
    print("\n=== (I) Customers/depots refactor regression ===")
    # I1
    r = requests.post(f"{BASE}/customers", headers=auth(admin_token), json={"name": "Refactor Test", "eircode": "D02 X285"}, timeout=30)
    check("I1.create customer 200", r.status_code == 200, str(r.status_code))
    cust = r.json() if r.status_code == 200 else {}
    cid = cust.get("id")
    check("I1.eircode echoed", cust.get("eircode") == "D02 X285")

    # I2
    r = requests.get(f"{BASE}/customers", headers=auth(admin_token), timeout=30)
    check("I2.list customers 200", r.status_code == 200)
    found = next((c for c in r.json() if c.get("id") == cid), None)
    check("I2.contains cid", found is not None)
    check("I2.eircode persists", (found or {}).get("eircode") == "D02 X285")

    # I3
    r = requests.patch(f"{BASE}/customers/{cid}", headers=auth(admin_token), json={"name": "Refactor Renamed", "eircode": "A65 F4E2"}, timeout=30)
    check("I3.patch 200", r.status_code == 200, str(r.status_code))
    upd = r.json() if r.status_code == 200 else {}
    check("I3.name updated", upd.get("name") == "Refactor Renamed")
    check("I3.eircode updated", upd.get("eircode") == "A65 F4E2")

    # I4
    r = requests.post(f"{BASE}/customers/{cid}/contacts", headers=auth(admin_token), json={"name": "Bob", "phone": "+353-1"}, timeout=30)
    check("I4.add contact 200", r.status_code == 200, str(r.status_code))
    r = requests.get(f"{BASE}/customers/{cid}", headers=auth(admin_token), timeout=30)
    cobj = r.json() if r.status_code == 200 else {}
    check("I4.contact in customer.contacts", any(c.get("name") == "Bob" for c in (cobj.get("contacts") or [])))

    # I5
    r = requests.post(f"{BASE}/customers/{cid}/sites", headers=auth(admin_token), json={"name": "Yard", "eircode": "D04 W7N6"}, timeout=30)
    check("I5.add site 200", r.status_code == 200, str(r.status_code))
    r = requests.get(f"{BASE}/customers/{cid}", headers=auth(admin_token), timeout=30)
    cobj = r.json() if r.status_code == 200 else {}
    yard = next((s for s in (cobj.get("sites") or []) if s.get("name") == "Yard"), None)
    check("I5.site present", yard is not None)
    check("I5.site eircode", (yard or {}).get("eircode") == "D04 W7N6")

    # I6 — staff posts note
    r = requests.post(f"{BASE}/customers/{cid}/notes", headers=auth(staff_token), json={"body": "gate code 1234", "category": "access"}, timeout=30)
    check("I6.staff add note 200", r.status_code == 200, str(r.status_code))
    r = requests.get(f"{BASE}/customers/{cid}/notes", headers=auth(staff_token), timeout=30)
    notes = r.json() if r.status_code == 200 else []
    check("I6.note present", any(n.get("body") == "gate code 1234" for n in notes))

    # I7 — depot
    r = requests.post(f"{BASE}/depots", headers=auth(admin_token), json={"name": "Test Depot", "lat": 53.3498, "lng": -6.2603, "radius_m": 300}, timeout=30)
    check("I7.create depot 200", r.status_code == 200, str(r.status_code))
    depot = r.json() if r.status_code == 200 else {}
    did = depot.get("id")

    # I8 — staff list depots
    r = requests.get(f"{BASE}/depots", headers=auth(staff_token), timeout=30)
    check("I8.staff list depots 200", r.status_code == 200, str(r.status_code))
    check("I8.contains did", any(d.get("id") == did for d in r.json()))

    # I9 — admin delete depot
    r = requests.delete(f"{BASE}/depots/{did}", headers=auth(admin_token), timeout=30)
    check("I9.delete depot 200", r.status_code == 200, str(r.status_code))

    # I10 — admin delete customer cascades notes
    r = requests.delete(f"{BASE}/customers/{cid}", headers=auth(admin_token), timeout=30)
    check("I10.delete customer 200", r.status_code == 200, str(r.status_code))
    # Verify cascade
    r = requests.get(f"{BASE}/customers/{cid}", headers=auth(admin_token), timeout=30)
    check("I10.customer gone 404", r.status_code == 404, str(r.status_code))
    r = requests.get(f"{BASE}/customers/{cid}/notes", headers=auth(admin_token), timeout=30)
    notes_after = r.json() if r.status_code == 200 else []
    check("I10.notes cascade deleted", len(notes_after) == 0, f"remaining={len(notes_after)}")

    # =============== (J) Cleanup ===============
    print("\n=== (J) Cleanup ===")
    # Cancel iid3 (expired — admin cancel allowed since not signed)
    if iid3:
        r = requests.post(f"{BASE}/hr/issuances/{iid3}/cancel", headers=auth(admin_token), timeout=30)
        check("J.cancel iid3", r.status_code == 200, str(r.status_code))
    # Try to deactivate the second staff user (cleanup optional)
    # Signed iid stays per spec.

    # ----- Report -----
    print("\n=== Summary ===")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    total = len(results)
    print(f"PASSED: {passed}/{total}")
    print(f"FAILED: {len(failed)}")
    for n, d in failed:
        print(f"  - {n} :: {d}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
