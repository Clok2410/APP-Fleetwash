"""
Phase 4 — Employee-specific form assignment regression test.

Covers:
  A. PDF form template assignment
  B. Regular form/checklist template assignment
  C. Back-compat (no assigned_user_ids field)

Backend base: https://employee-connect-9.preview.emergentagent.com/api
Credentials per /app/memory/test_credentials.md.
"""
import base64
import io
import sys
import requests

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN = ("admin@company.com", "Admin@123")
STAFF = ("jane@company.com", "Staff@123")

# ---------- helpers ----------

PASS = []
FAIL = []


def assert_eq(label, expected, actual):
    if expected == actual:
        PASS.append(label)
        print(f"  PASS  {label}")
    else:
        FAIL.append(f"{label} → expected {expected!r} got {actual!r}")
        print(f"  FAIL  {label} → expected {expected!r} got {actual!r}")


def assert_true(label, cond, detail=""):
    if cond:
        PASS.append(label)
        print(f"  PASS  {label}")
    else:
        FAIL.append(f"{label} {detail}")
        print(f"  FAIL  {label} {detail}")


def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"], r.json()["user"]


def headers(tok):
    return {"Authorization": f"Bearer {tok}"}


def build_acroform_pdf() -> bytes:
    """Build a small reportlab AcroForm PDF with 3 fields: text full_name, checkbox accept, choice dept."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "Onboarding Form (assignment regression)")

    form = c.acroForm
    c.drawString(72, 680, "Full name:")
    form.textfield(name="full_name", tooltip="Full name", x=160, y=672, width=300, height=20,
                   borderColor=None, fillColor=None, textColor=None, forceBorder=False)
    c.drawString(72, 640, "I accept:")
    form.checkbox(name="accept", tooltip="I accept", x=160, y=634, size=18, checked=False)
    c.drawString(72, 600, "Department:")
    form.choice(name="dept", tooltip="Department",
                value="Engineering",
                options=["Engineering", "Operations", "HR", "Finance"],
                x=160, y=590, width=200, height=22)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------- main ----------

def main():
    print("=" * 78)
    print("Phase 4 — Employee-specific form assignment regression")
    print("=" * 78)

    print("\n[setup] login admin + staff")
    admin_tok, admin_user = login(*ADMIN)
    staff_tok, staff_user = login(*STAFF)
    admin_id = admin_user["id"]
    staff_id = staff_user["id"]
    print(f"  admin id={admin_id}")
    print(f"  jane  id={staff_id}")

    # Lookup jane via /users to mirror the spec
    r = requests.get(f"{BASE}/users", headers=headers(admin_tok), timeout=20)
    r.raise_for_status()
    users = r.json()
    jane = next((u for u in users if u.get("role") == "staff" and "jane" in (u.get("email") or "").lower()), None)
    assert_true("setup.find_jane_via_users", jane is not None and jane["id"] == staff_id)
    jane_id = jane["id"]

    # ---------- A. PDF form template assignment ----------
    print("\n[A] PDF form template assignment")
    pdf_bytes = build_acroform_pdf()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    # A.2 TPL_ALL — empty assigned list
    r = requests.post(
        f"{BASE}/pdf-forms/templates",
        json={"title": "Assignment ALL", "description": "all-staff", "pdf_base64": pdf_b64, "assigned_user_ids": []},
        headers=headers(admin_tok), timeout=30,
    )
    assert_eq("A.2 admin POST TPL_ALL status", 200, r.status_code)
    tpl_all = r.json()
    TPL_ALL = tpl_all["id"]
    assert_eq("A.2 TPL_ALL.assigned_user_ids", [], tpl_all.get("assigned_user_ids"))
    assert_eq("A.2 TPL_ALL.has_acroform", True, tpl_all.get("has_acroform"))
    assert_eq("A.2 TPL_ALL.field_count", 3, tpl_all.get("field_count"))

    # A.3 TPL_JANE
    r = requests.post(
        f"{BASE}/pdf-forms/templates",
        json={"title": "Assignment JANE", "pdf_base64": pdf_b64, "assigned_user_ids": [jane_id]},
        headers=headers(admin_tok), timeout=30,
    )
    assert_eq("A.3 admin POST TPL_JANE status", 200, r.status_code)
    TPL_JANE = r.json()["id"]
    assert_eq("A.3 TPL_JANE.assigned_user_ids", [jane_id], r.json().get("assigned_user_ids"))

    # A.4 TPL_ADMIN_ONLY
    r = requests.post(
        f"{BASE}/pdf-forms/templates",
        json={"title": "Assignment ADMIN-ONLY", "pdf_base64": pdf_b64, "assigned_user_ids": [admin_id]},
        headers=headers(admin_tok), timeout=30,
    )
    assert_eq("A.4 admin POST TPL_ADMIN_ONLY status", 200, r.status_code)
    TPL_ADMIN_ONLY = r.json()["id"]
    assert_eq("A.4 TPL_ADMIN_ONLY.assigned_user_ids", [admin_id], r.json().get("assigned_user_ids"))

    # A.5 admin GET sees all three with assigned_user_ids field
    r = requests.get(f"{BASE}/pdf-forms/templates", headers=headers(admin_tok), timeout=20)
    assert_eq("A.5 admin GET templates status", 200, r.status_code)
    docs = r.json()
    by_id = {d["id"]: d for d in docs}
    assert_true("A.5 admin sees TPL_ALL", TPL_ALL in by_id)
    assert_true("A.5 admin sees TPL_JANE", TPL_JANE in by_id)
    assert_true("A.5 admin sees TPL_ADMIN_ONLY", TPL_ADMIN_ONLY in by_id)
    if TPL_ALL in by_id:
        assert_eq("A.5 TPL_ALL field present", [], by_id[TPL_ALL].get("assigned_user_ids"))
    if TPL_JANE in by_id:
        assert_eq("A.5 TPL_JANE field present", [jane_id], by_id[TPL_JANE].get("assigned_user_ids"))
    if TPL_ADMIN_ONLY in by_id:
        assert_eq("A.5 TPL_ADMIN_ONLY field present", [admin_id], by_id[TPL_ADMIN_ONLY].get("assigned_user_ids"))

    # A.6 staff sees only TPL_ALL + TPL_JANE
    r = requests.get(f"{BASE}/pdf-forms/templates", headers=headers(staff_tok), timeout=20)
    assert_eq("A.6 staff GET templates status", 200, r.status_code)
    staff_ids = {d["id"] for d in r.json()}
    assert_true("A.6 staff sees TPL_ALL", TPL_ALL in staff_ids)
    assert_true("A.6 staff sees TPL_JANE", TPL_JANE in staff_ids)
    assert_true("A.6 staff NOT sees TPL_ADMIN_ONLY", TPL_ADMIN_ONLY not in staff_ids)

    # A.7 staff GET TPL_ADMIN_ONLY → 403
    r = requests.get(f"{BASE}/pdf-forms/templates/{TPL_ADMIN_ONLY}", headers=headers(staff_tok), timeout=20)
    assert_eq("A.7 staff GET TPL_ADMIN_ONLY status", 403, r.status_code)
    assert_true("A.7 detail contains 'Not assigned'", "not assigned" in (r.json().get("detail") or "").lower(),
                detail=f"detail={r.json().get('detail')}")

    # A.8 staff POST fill on TPL_ADMIN_ONLY → 403
    r = requests.post(
        f"{BASE}/pdf-forms/templates/{TPL_ADMIN_ONLY}/fill",
        json={"values": {}, "flatten": False},
        headers=headers(staff_tok), timeout=20,
    )
    assert_eq("A.8 staff POST fill TPL_ADMIN_ONLY status", 403, r.status_code)
    assert_true("A.8 detail contains 'Not assigned'", "not assigned" in (r.json().get("detail") or "").lower())

    # A.9 staff POST sessions on TPL_ADMIN_ONLY → 403
    r = requests.post(
        f"{BASE}/pdf-forms/templates/{TPL_ADMIN_ONLY}/sessions",
        json={},
        headers=headers(staff_tok), timeout=20,
    )
    assert_eq("A.9 staff POST sessions TPL_ADMIN_ONLY status", 403, r.status_code)
    assert_true("A.9 detail contains 'Not assigned'", "not assigned" in (r.json().get("detail") or "").lower())

    # A.10 staff POST sessions on TPL_JANE → 200
    r = requests.post(
        f"{BASE}/pdf-forms/templates/{TPL_JANE}/sessions",
        json={},
        headers=headers(staff_tok), timeout=20,
    )
    assert_eq("A.10 staff POST sessions TPL_JANE status", 200, r.status_code)
    jane_session_id = r.json().get("id")
    # cleanup the auto-created session as admin
    if jane_session_id:
        requests.delete(f"{BASE}/pdf-forms/sessions/{jane_session_id}", headers=headers(admin_tok), timeout=20)

    # A.11 admin PATCH /pdf-forms/templates/{TPL_JANE}/assign with [admin_id]
    r = requests.patch(
        f"{BASE}/pdf-forms/templates/{TPL_JANE}/assign",
        json={"assigned_user_ids": [admin_id]},
        headers=headers(admin_tok), timeout=20,
    )
    assert_eq("A.11 admin PATCH TPL_JANE assign status", 200, r.status_code)
    assert_eq("A.11 response assigned_user_ids", [admin_id], r.json().get("assigned_user_ids"))

    # A.12 staff no longer sees TPL_JANE
    r = requests.get(f"{BASE}/pdf-forms/templates", headers=headers(staff_tok), timeout=20)
    staff_ids2 = {d["id"] for d in r.json()}
    assert_true("A.12 staff no longer sees TPL_JANE", TPL_JANE not in staff_ids2)
    assert_true("A.12 staff still sees TPL_ALL", TPL_ALL in staff_ids2)

    # A.13 staff PATCH /TPL_ALL/assign → 403
    r = requests.patch(
        f"{BASE}/pdf-forms/templates/{TPL_ALL}/assign",
        json={"assigned_user_ids": []},
        headers=headers(staff_tok), timeout=20,
    )
    assert_eq("A.13 staff PATCH assign status", 403, r.status_code)

    # A.14 admin PATCH /TPL_ALL/assign with [] → 200
    r = requests.patch(
        f"{BASE}/pdf-forms/templates/{TPL_ALL}/assign",
        json={"assigned_user_ids": []},
        headers=headers(admin_tok), timeout=20,
    )
    assert_eq("A.14 admin PATCH TPL_ALL reset status", 200, r.status_code)
    assert_eq("A.14 reset assigned_user_ids", [], r.json().get("assigned_user_ids"))

    # A.15 cleanup
    for tid, label in [(TPL_ALL, "TPL_ALL"), (TPL_JANE, "TPL_JANE"), (TPL_ADMIN_ONLY, "TPL_ADMIN_ONLY")]:
        r = requests.delete(f"{BASE}/pdf-forms/templates/{tid}", headers=headers(admin_tok), timeout=20)
        assert_eq(f"A.15 cleanup DELETE {label}", 200, r.status_code)

    # ---------- B. Regular form/checklist template assignment ----------
    print("\n[B] Regular form/checklist template assignment")
    # B.1 admin create form template assigned to Jane
    r = requests.post(
        f"{BASE}/forms/templates",
        json={
            "title": "Onboarding Q&A (jane-only)",
            "description": "assignment test",
            "kind": "form",
            "fields": [{"key": "comments", "label": "Comments", "type": "text", "required": False}],
            "assigned_user_ids": [jane_id],
        },
        headers=headers(admin_tok), timeout=20,
    )
    assert_eq("B.1 admin POST form template status", 200, r.status_code)
    F_TID = r.json()["id"]
    assert_eq("B.1 assigned_user_ids", [jane_id], r.json().get("assigned_user_ids"))

    # B.2 staff GET /forms/templates includes this template
    r = requests.get(f"{BASE}/forms/templates", headers=headers(staff_tok), timeout=20)
    assert_eq("B.2 staff GET forms templates status", 200, r.status_code)
    staff_form_ids = {d["id"] for d in r.json()}
    assert_true("B.2 staff sees jane-assigned form template", F_TID in staff_form_ids)

    # B.3 staff POST submission → 200
    r = requests.post(
        f"{BASE}/forms/submissions",
        json={"template_id": F_TID, "values": {"comments": "Looks good — Jane"}},
        headers=headers(staff_tok), timeout=20,
    )
    assert_eq("B.3 staff POST submission status", 200, r.status_code)

    # B.4 admin PATCH /forms/templates/{tid}/assign → [admin_id]
    r = requests.patch(
        f"{BASE}/forms/templates/{F_TID}/assign",
        json={"assigned_user_ids": [admin_id]},
        headers=headers(admin_tok), timeout=20,
    )
    assert_eq("B.4 admin PATCH form assign status", 200, r.status_code)
    assert_eq("B.4 admin assigned only", [admin_id], r.json().get("assigned_user_ids"))

    # B.5 staff POST submission now → 403
    r = requests.post(
        f"{BASE}/forms/submissions",
        json={"template_id": F_TID, "values": {"comments": "should be blocked"}},
        headers=headers(staff_tok), timeout=20,
    )
    assert_eq("B.5 staff POST submission after reassign status", 403, r.status_code)
    assert_true("B.5 detail contains 'Not assigned'", "not assigned" in (r.json().get("detail") or "").lower())

    # B.5b staff list templates should no longer include it
    r = requests.get(f"{BASE}/forms/templates", headers=headers(staff_tok), timeout=20)
    staff_form_ids2 = {d["id"] for d in r.json()}
    assert_true("B.5b staff no longer lists admin-only form template", F_TID not in staff_form_ids2)

    # B.6 staff PATCH assign → 403
    r = requests.patch(
        f"{BASE}/forms/templates/{F_TID}/assign",
        json={"assigned_user_ids": []},
        headers=headers(staff_tok), timeout=20,
    )
    assert_eq("B.6 staff PATCH form assign status", 403, r.status_code)

    # B.7 cleanup
    r = requests.delete(f"{BASE}/forms/templates/{F_TID}", headers=headers(admin_tok), timeout=20)
    assert_eq("B.7 admin DELETE form template", 200, r.status_code)

    # ---------- C. Back-compat (no assigned_user_ids field) ----------
    print("\n[C] Back-compat — missing assigned_user_ids defaults to ALL")
    # PDF template without passing assigned_user_ids at all
    r = requests.post(
        f"{BASE}/pdf-forms/templates",
        json={"title": "Legacy back-compat (no assign field)", "pdf_base64": pdf_b64},
        headers=headers(admin_tok), timeout=30,
    )
    assert_eq("C admin POST legacy PDF tpl status", 200, r.status_code)
    LEGACY = r.json()["id"]
    assert_eq("C legacy.assigned_user_ids defaults []", [], r.json().get("assigned_user_ids"))

    # staff GET sees it
    r = requests.get(f"{BASE}/pdf-forms/templates", headers=headers(staff_tok), timeout=20)
    staff_ids3 = {d["id"] for d in r.json()}
    assert_true("C staff sees legacy PDF tpl (no assign)", LEGACY in staff_ids3)

    # staff can GET it
    r = requests.get(f"{BASE}/pdf-forms/templates/{LEGACY}", headers=headers(staff_tok), timeout=20)
    assert_eq("C staff GET legacy template status", 200, r.status_code)

    # admin can fill it (sanity)
    r = requests.post(
        f"{BASE}/pdf-forms/templates/{LEGACY}/fill",
        json={"values": {"full_name": "Legacy Smith", "accept": True, "dept": "HR"}, "flatten": False},
        headers=headers(admin_tok), timeout=30,
    )
    assert_eq("C admin POST fill legacy status", 200, r.status_code)

    # cleanup
    r = requests.delete(f"{BASE}/pdf-forms/templates/{LEGACY}", headers=headers(admin_tok), timeout=20)
    assert_eq("C cleanup DELETE legacy", 200, r.status_code)

    # ---------- summary ----------
    print("\n" + "=" * 78)
    print(f"RESULT: {len(PASS)} pass / {len(FAIL)} fail")
    print("=" * 78)
    if FAIL:
        print("\nFAILURES:")
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
