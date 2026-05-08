"""
Backend regression — Drive ↔ PDF Form bridge
POST /api/drive/files/{fid}/as-pdf-form
"""
import base64
import io
import os
import sys
import requests

BASE = os.environ.get("BASE_URL", "https://employee-connect-9.preview.emergentagent.com").rstrip("/") + "/api"
ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

TIMEOUT = 30


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["access_token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def build_acroform_pdf() -> bytes:
    """Tiny reportlab AcroForm PDF: text + checkbox + choice = 3 fields."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "Drive Bridge Test Form")
    form = c.acroForm
    c.drawString(72, 680, "Full name:")
    form.textfield(name="full_name", x=160, y=675, width=240, height=18, borderStyle="inset")
    c.drawString(72, 640, "Accept terms:")
    form.checkbox(name="accept", x=160, y=638, size=14, buttonStyle="check")
    c.drawString(72, 600, "Department:")
    form.choice(
        name="dept",
        value="Engineering",
        options=["Engineering", "Operations", "HR", "Finance"],
        x=160, y=595, width=160, height=22,
    )
    c.showPage()
    c.save()
    return buf.getvalue()


def build_txt_b64() -> str:
    return base64.b64encode(b"hello world, not a pdf").decode()


def upload_drive(token, name, mime, b64, folder_id=None):
    payload = {"name": name, "folder_id": folder_id, "mime_type": mime, "data_base64": b64, "size": len(base64.b64decode(b64))}
    r = requests.post(f"{BASE}/drive/files", json=payload, headers=auth(token), timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def delete_drive(token, fid):
    return requests.delete(f"{BASE}/drive/files/{fid}", headers=auth(token), timeout=TIMEOUT)


def delete_template(token, tid):
    return requests.delete(f"{BASE}/pdf-forms/templates/{tid}", headers=auth(token), timeout=TIMEOUT)


PASS, FAIL = [], []


def assertEq(name, actual, expected):
    if actual == expected:
        PASS.append(name)
        print(f"PASS  {name}")
    else:
        FAIL.append((name, f"expected={expected!r} got={actual!r}"))
        print(f"FAIL  {name}: expected={expected!r} got={actual!r}")


def assertTrue(name, cond, msg=""):
    if cond:
        PASS.append(name)
        print(f"PASS  {name}")
    else:
        FAIL.append((name, msg or "assertion false"))
        print(f"FAIL  {name}: {msg}")


def main():
    print("BASE:", BASE)
    admin_t = login(ADMIN)
    staff_t = login(STAFF)
    print("Logged in admin + staff")

    pdf_bytes = build_acroform_pdf()
    pdf_b64 = base64.b64encode(pdf_bytes).decode()
    print(f"Built AcroForm PDF: {len(pdf_bytes)} bytes")

    created_drive_files = []
    created_templates = []

    try:
        # Step 1: admin uploads PDF to root folder
        f = upload_drive(admin_t, "drive_bridge_test.pdf", "application/pdf", pdf_b64, folder_id=None)
        fid = f["id"]
        created_drive_files.append(fid)
        assertTrue("1. drive upload PDF returns id", bool(fid))
        assertEq("1. drive upload mime_type", f.get("mime_type"), "application/pdf")

        # Step 2: POST as-pdf-form (admin) → has_acroform=true, field_count=3, no pdf_base64
        r = requests.post(f"{BASE}/drive/files/{fid}/as-pdf-form", headers=auth(admin_t), timeout=TIMEOUT)
        assertEq("2. admin promote PDF status", r.status_code, 200)
        body = r.json()
        tid_first = body.get("id")
        if tid_first:
            created_templates.append(tid_first)
        assertTrue("2. response has template id", bool(tid_first))
        assertEq("2. has_acroform=true", body.get("has_acroform"), True)
        assertEq("2. field_count=3", body.get("field_count"), 3)
        assertTrue("2. pdf_base64 stripped from response", "pdf_base64" not in body, f"keys={list(body.keys())}")
        assertEq("2. source_drive_file_id matches", body.get("source_drive_file_id"), fid)
        # Sanity: fields shape
        fields = body.get("fields") or []
        assertEq("2. fields length=3", len(fields), 3)
        # field key names — pypdf may use 'name' or 'key'; accept either
        keys = sorted([(fld.get("key") or fld.get("name") or "") for fld in fields])
        print(f"   fields shape sample: {fields[0] if fields else None}")
        assertEq("2. field keys", keys, ["accept", "dept", "full_name"])

        # Step 3: POST as-pdf-form again → SAME template id (reuse)
        r2 = requests.post(f"{BASE}/drive/files/{fid}/as-pdf-form", headers=auth(admin_t), timeout=TIMEOUT)
        assertEq("3. second promote status", r2.status_code, 200)
        body2 = r2.json()
        assertEq("3. template id reused (same id)", body2.get("id"), tid_first)
        assertTrue("3. pdf_base64 stripped on reuse", "pdf_base64" not in body2)
        # Sanity that no duplicate template was created in DB by checking only one template references this drive file
        # via list endpoint
        rl = requests.get(f"{BASE}/pdf-forms/templates", headers=auth(admin_t), timeout=TIMEOUT)
        assertEq("3. list templates 200", rl.status_code, 200)
        lst = rl.json()
        matching = [t for t in lst if t.get("source_drive_file_id") == fid]
        assertEq("3. exactly one template per drive file", len(matching), 1)

        # Step 4: POST as-pdf-form as STAFF → should also work
        r3 = requests.post(f"{BASE}/drive/files/{fid}/as-pdf-form", headers=auth(staff_t), timeout=TIMEOUT)
        assertEq("4. staff promote status", r3.status_code, 200)
        body3 = r3.json()
        assertEq("4. staff gets same template id (reuse)", body3.get("id"), tid_first)
        assertTrue("4. pdf_base64 stripped for staff", "pdf_base64" not in body3)

        # Step 5: non-PDF drive file → 400 "Not a PDF file"
        ft = upload_drive(admin_t, "notes.txt", "text/plain", build_txt_b64(), folder_id=None)
        ftid = ft["id"]
        created_drive_files.append(ftid)
        r4 = requests.post(f"{BASE}/drive/files/{ftid}/as-pdf-form", headers=auth(admin_t), timeout=TIMEOUT)
        assertEq("5. non-PDF returns 400", r4.status_code, 400)
        try:
            detail = r4.json().get("detail", "")
        except Exception:
            detail = r4.text
        assertEq("5. error detail = 'Not a PDF file'", detail, "Not a PDF file")

        # Step 6: non-existent file id → 404
        r5 = requests.post(f"{BASE}/drive/files/does-not-exist-xyz/as-pdf-form", headers=auth(admin_t), timeout=TIMEOUT)
        assertEq("6. nonexistent file returns 404", r5.status_code, 404)

        # Bonus: ensure staff cannot delete template (admin only)
        rdel_staff = delete_template(staff_t, tid_first)
        assertEq("BONUS. staff DELETE template → 403", rdel_staff.status_code, 403)

    finally:
        # Cleanup
        for tid in created_templates:
            try:
                rd = delete_template(admin_t, tid)
                assertEq(f"7. cleanup DELETE template {tid[:8]}", rd.status_code, 200)
            except Exception as e:
                FAIL.append((f"cleanup template {tid}", str(e)))
        for fid in created_drive_files:
            try:
                rd = delete_drive(admin_t, fid)
                assertEq(f"7. cleanup DELETE drive file {fid[:8]}", rd.status_code, 200)
            except Exception as e:
                FAIL.append((f"cleanup drive {fid}", str(e)))

    print("\n----- SUMMARY -----")
    print(f"PASS: {len(PASS)}    FAIL: {len(FAIL)}")
    for n, msg in FAIL:
        print(f"  - {n}: {msg}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
