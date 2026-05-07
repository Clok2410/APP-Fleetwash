"""
Backend tests for PDF Fillable Forms endpoints.
Targets the public proxy URL (EXPO_PUBLIC_BACKEND_URL from /app/frontend/.env)
prefixed with /api as per ingress rules.
"""

import base64
import io
import sys
import json
from pathlib import Path
from typing import Optional

import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.colors import magenta, pink, blue, green
from pypdf import PdfReader


FRONT_ENV = Path("/app/frontend/.env")
BASE_URL = None
for line in FRONT_ENV.read_text().splitlines():
    if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
        BASE_URL = line.split("=", 1)[1].strip().strip('"')
        break
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"
API = f"{BASE_URL.rstrip('/')}/api"
print(f"[INFO] Using API base: {API}")

ADMIN_EMAIL = "admin@company.com"
ADMIN_PASSWORD = "Admin@123"
STAFF_EMAIL = "jane@company.com"
STAFF_PASSWORD = "Staff@123"


def _print(label: str, ok: bool, detail: str = ""):
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))


def login(email: str, password: str) -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def build_acroform_pdf() -> bytes:
    """Build small PDF with text + checkbox + choice AcroForm fields."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setFont("Helvetica", 14)
    c.drawString(72, 750, "StaffHub PDF Form Test")

    form = c.acroForm

    c.drawString(72, 700, "Full Name:")
    form.textfield(
        name="full_name",
        tooltip="Full Name",
        x=170, y=695,
        borderStyle="solid",
        borderColor=magenta, fillColor=pink,
        width=300, height=20,
        textColor=blue, forceBorder=True,
    )

    c.drawString(72, 660, "Accept terms:")
    form.checkbox(
        name="accept",
        tooltip="Accept terms",
        x=170, y=655,
        buttonStyle="check",
        borderColor=magenta, fillColor=pink,
        textColor=blue, forceBorder=True,
        size=20,
    )

    c.drawString(72, 620, "Department:")
    form.choice(
        name="dept",
        tooltip="Choose department",
        value="Engineering",
        x=170, y=615,
        width=200, height=20,
        borderColor=green, fillColor=pink,
        textColor=blue, forceBorder=True,
        options=["Engineering", "Operations", "HR", "Finance"],
    )

    c.showPage()
    c.save()
    return buf.getvalue()


def main():
    failures = []

    # ---- Login admin and staff ----
    try:
        admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
        staff_token = login(STAFF_EMAIL, STAFF_PASSWORD)
        _print("Login admin + staff", True)
    except Exception as e:
        _print("Login admin + staff", False, str(e))
        sys.exit(1)

    pdf_bytes = build_acroform_pdf()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    print(f"Generated PDF size: {len(pdf_bytes)} bytes")

    # ---- 1. POST /pdf-forms/templates as admin ----
    template_id: Optional[str] = None
    try:
        r = requests.post(
            f"{API}/pdf-forms/templates",
            json={
                "title": "Acceptance Form",
                "description": "AcroForm test template (text + checkbox + choice)",
                "pdf_base64": pdf_b64,
            },
            headers=hdr(admin_token),
            timeout=60,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        assert data.get("has_acroform") is True, f"has_acroform={data.get('has_acroform')}"
        assert data.get("field_count", 0) >= 3, f"field_count={data.get('field_count')}"
        assert "pdf_base64" not in data, "pdf_base64 should NOT be returned in create response"
        template_id = data["id"]
        _print(
            "1. POST /pdf-forms/templates (admin)",
            True,
            f"id={template_id} field_count={data['field_count']}",
        )
    except Exception as e:
        failures.append(("1. POST /pdf-forms/templates (admin)", str(e)))
        _print("1. POST /pdf-forms/templates (admin)", False, str(e))
        if not template_id:
            print("Cannot continue without template id")
            sys.exit(1)

    # ---- 2. GET /pdf-forms/templates list ----
    try:
        r = requests.get(f"{API}/pdf-forms/templates", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200, f"status={r.status_code}"
        items = r.json()
        match = [t for t in items if t.get("id") == template_id]
        assert match, "new template not in listing"
        for t in items:
            assert "pdf_base64" not in t, "list payload must NOT include pdf_base64"
        _print("2. GET /pdf-forms/templates (list)", True, f"count={len(items)}")
    except Exception as e:
        failures.append(("2. GET /pdf-forms/templates (list)", str(e)))
        _print("2. GET /pdf-forms/templates (list)", False, str(e))

    # ---- 3. GET /pdf-forms/templates/{id} ----
    try:
        r = requests.get(
            f"{API}/pdf-forms/templates/{template_id}",
            headers=hdr(admin_token),
            timeout=30,
        )
        assert r.status_code == 200, f"status={r.status_code}"
        d = r.json()
        assert d.get("pdf_base64"), "pdf_base64 must be present in detail"
        fields = d.get("fields") or []
        types = {f.get("type") for f in fields}
        assert "text" in types, f"missing 'text' field type, got {types}"
        assert "checkbox" in types, f"missing 'checkbox' field type, got {types}"
        assert "select" in types, f"missing 'select' field type, got {types}"
        select_field = next(f for f in fields if f.get("type") == "select")
        assert select_field.get("options"), "select field missing options"
        _print(
            "3. GET /pdf-forms/templates/{id}",
            True,
            f"types={sorted(types)} options={select_field.get('options')}",
        )
    except Exception as e:
        failures.append(("3. GET /pdf-forms/templates/{id}", str(e)))
        _print("3. GET /pdf-forms/templates/{id}", False, str(e))

    # ---- 4. POST fill as staff (flatten=false) ----
    staff_submission_id: Optional[str] = None
    try:
        payload = {
            "values": {"full_name": "John Doe", "accept": True, "dept": "Engineering"},
            "flatten": False,
        }
        r = requests.post(
            f"{API}/pdf-forms/templates/{template_id}/fill",
            json=payload,
            headers=hdr(staff_token),
            timeout=60,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        assert d.get("filled_pdf_base64"), "no filled_pdf_base64"
        staff_submission_id = d["id"]
        filled = base64.b64decode(d["filled_pdf_base64"])
        assert filled.startswith(b"%PDF"), "filled bytes are not a valid PDF"
        reader = PdfReader(io.BytesIO(filled))
        fields = reader.get_fields() or {}

        def _v(name):
            f = fields.get(name) or {}
            v = f.get("/V") if isinstance(f, dict) else getattr(f, "value", None)
            return str(v) if v is not None else ""

        v_full = _v("full_name")
        v_accept = _v("accept")
        v_dept = _v("dept")
        assert v_full == "John Doe", f"full_name /V={v_full!r}"
        assert v_accept == "/Yes", f"accept /V={v_accept!r}"
        assert v_dept == "Engineering", f"dept /V={v_dept!r}"
        _print(
            "4. POST fill (flatten=false) — /V verified",
            True,
            f"full_name={v_full} accept={v_accept} dept={v_dept}",
        )
    except Exception as e:
        failures.append(("4. POST fill (flatten=false)", str(e)))
        _print("4. POST fill (flatten=false)", False, str(e))

    # ---- 5. POST fill flatten=true ----
    try:
        payload = {
            "values": {"full_name": "Jane Doe", "accept": True, "dept": "Operations"},
            "flatten": True,
        }
        r = requests.post(
            f"{API}/pdf-forms/templates/{template_id}/fill",
            json=payload,
            headers=hdr(staff_token),
            timeout=60,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        filled = base64.b64decode(d["filled_pdf_base64"])
        assert filled.startswith(b"%PDF"), "flattened PDF invalid"
        reader = PdfReader(io.BytesIO(filled))
        _ = reader.pages[0]
        _print("5. POST fill (flatten=true)", True, f"size={len(filled)}")
    except Exception as e:
        failures.append(("5. POST fill (flatten=true)", str(e)))
        _print("5. POST fill (flatten=true)", False, str(e))

    # Create one admin submission for role-scoping checks
    admin_submission_id: Optional[str] = None
    try:
        r = requests.post(
            f"{API}/pdf-forms/templates/{template_id}/fill",
            json={
                "values": {"full_name": "Admin Tester", "accept": False, "dept": "HR"},
                "flatten": False,
            },
            headers=hdr(admin_token),
            timeout=60,
        )
        if r.status_code == 200:
            admin_submission_id = r.json()["id"]
    except Exception:
        pass

    # ---- 6. GET /pdf-forms/submissions as staff ----
    try:
        r = requests.get(
            f"{API}/pdf-forms/submissions",
            headers=hdr(staff_token),
            timeout=30,
        )
        assert r.status_code == 200, f"status={r.status_code}"
        subs = r.json()
        assert subs, "staff sees no submissions"
        for s in subs:
            assert "filled_pdf_base64" not in s, "list must omit filled_pdf_base64"
            assert s.get("user_id"), "missing user_id"
        ids = {s["id"] for s in subs}
        if admin_submission_id:
            assert admin_submission_id not in ids, "staff seeing admin submission"
        if staff_submission_id:
            assert staff_submission_id in ids, "staff missing own submission"
        _print("6. GET submissions as staff (own only)", True, f"count={len(subs)}")
    except Exception as e:
        failures.append(("6. GET submissions as staff", str(e)))
        _print("6. GET submissions as staff", False, str(e))

    # ---- 7. GET /pdf-forms/submissions as admin ----
    try:
        r = requests.get(
            f"{API}/pdf-forms/submissions",
            headers=hdr(admin_token),
            timeout=30,
        )
        assert r.status_code == 200, f"status={r.status_code}"
        subs = r.json()
        ids = {s["id"] for s in subs}
        if staff_submission_id:
            assert staff_submission_id in ids, "admin missing staff submission"
        if admin_submission_id:
            assert admin_submission_id in ids, "admin missing own submission"
        for s in subs:
            assert "filled_pdf_base64" not in s, "list must omit filled_pdf_base64"
        _print("7. GET submissions as admin (all)", True, f"count={len(subs)}")
    except Exception as e:
        failures.append(("7. GET submissions as admin", str(e)))
        _print("7. GET submissions as admin", False, str(e))

    # ---- 8. GET single submission has filled_pdf_base64 ----
    try:
        r = requests.get(
            f"{API}/pdf-forms/submissions/{staff_submission_id}",
            headers=hdr(staff_token),
            timeout=30,
        )
        assert r.status_code == 200, f"status={r.status_code}"
        d = r.json()
        assert d.get("filled_pdf_base64"), "missing filled_pdf_base64 in detail"
        assert base64.b64decode(d["filled_pdf_base64"]).startswith(b"%PDF")
        _print("8. GET /pdf-forms/submissions/{sid}", True)
    except Exception as e:
        failures.append(("8. GET single submission", str(e)))
        _print("8. GET single submission", False, str(e))

    # ---- 9. Staff trying to read admin's submission -> 403 ----
    try:
        if not admin_submission_id:
            raise AssertionError("admin_submission_id not available")
        r = requests.get(
            f"{API}/pdf-forms/submissions/{admin_submission_id}",
            headers=hdr(staff_token),
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code} body={r.text[:200]}"
        _print("9. Staff reads admin's submission -> 403", True)
    except Exception as e:
        failures.append(("9. Cross-user submission access -> 403", str(e)))
        _print("9. Cross-user submission access -> 403", False, str(e))

    # ---- 10. Staff POST template -> 403 ----
    try:
        r = requests.post(
            f"{API}/pdf-forms/templates",
            json={"title": "x", "description": "x", "pdf_base64": pdf_b64},
            headers=hdr(staff_token),
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code} body={r.text[:200]}"
        _print("10. Staff POST template -> 403", True)
    except Exception as e:
        failures.append(("10. Staff POST template -> 403", str(e)))
        _print("10. Staff POST template -> 403", False, str(e))

    # ---- 12. Staff DELETE template -> 403 ----
    try:
        r = requests.delete(
            f"{API}/pdf-forms/templates/{template_id}",
            headers=hdr(staff_token),
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code} body={r.text[:200]}"
        _print("12. Staff DELETE template -> 403", True)
    except Exception as e:
        failures.append(("12. Staff DELETE template -> 403", str(e)))
        _print("12. Staff DELETE template -> 403", False, str(e))

    # ---- 11. Admin DELETE template + cascade ----
    try:
        r = requests.delete(
            f"{API}/pdf-forms/templates/{template_id}",
            headers=hdr(admin_token),
            timeout=30,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}"
        r2 = requests.get(
            f"{API}/pdf-forms/templates/{template_id}",
            headers=hdr(admin_token),
            timeout=30,
        )
        assert r2.status_code == 404, f"after delete, expected 404, got {r2.status_code}"
        r3 = requests.get(
            f"{API}/pdf-forms/submissions",
            headers=hdr(admin_token),
            timeout=30,
        )
        all_subs = r3.json()
        leftover = [s for s in all_subs if s.get("template_id") == template_id]
        assert not leftover, f"submissions not cascaded: {len(leftover)} leftover"
        _print("11. Admin DELETE template + cascade", True)
    except Exception as e:
        failures.append(("11. Admin DELETE template", str(e)))
        _print("11. Admin DELETE template", False, str(e))

    print("\n=== SUMMARY ===")
    if not failures:
        print("ALL PDF FORM TESTS PASSED")
        sys.exit(0)
    print(f"{len(failures)} failures:")
    for n, msg in failures:
        print(f" - {n}: {msg}")
    sys.exit(1)


if __name__ == "__main__":
    main()
