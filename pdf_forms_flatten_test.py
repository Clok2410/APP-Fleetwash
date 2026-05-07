"""Re-test ONLY case 5 for PDF Fillable Forms: POST fill with flatten=true."""
import os, io, base64, sys, json
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

BASE = "https://b863035e-804d-4d41-9158-321900c27687.preview.emergentagent.com/api"
ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def build_acroform_pdf() -> bytes:
    """Build an in-memory AcroForm PDF with text + checkbox + choice fields."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    form = c.acroForm
    c.drawString(72, 720, "Employee Onboarding Form")

    c.drawString(72, 680, "Full Name:")
    form.textfield(name="full_name", tooltip="Full legal name",
                   x=170, y=672, width=240, height=22, borderStyle="inset",
                   forceBorder=True)

    c.drawString(72, 640, "Accept Terms:")
    form.checkbox(name="accept", tooltip="Accept terms",
                  x=170, y=638, buttonStyle="check", borderStyle="solid",
                  size=18, forceBorder=True)

    c.drawString(72, 600, "Department:")
    form.choice(name="dept", value="Engineering",
                options=["Engineering", "Operations", "HR", "Finance"],
                x=170, y=590, width=180, height=24, forceBorder=True)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def main():
    print("== Logging in as admin ==")
    admin_tok = login(ADMIN)
    print("== Building AcroForm PDF ==")
    pdf_bytes = build_acroform_pdf()
    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    print("== Uploading template ==")
    r = requests.post(
        f"{BASE}/pdf-forms/templates",
        json={"title": "Onboarding (flatten retest)", "description": "Retest case 5",
              "pdf_base64": pdf_b64},
        headers={"Authorization": f"Bearer {admin_tok}"}, timeout=30,
    )
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
    tmpl = r.json()
    tid = tmpl["id"]
    print(f"   template id={tid} has_acroform={tmpl.get('has_acroform')} field_count={tmpl.get('field_count')}")
    assert tmpl.get("has_acroform") is True
    assert tmpl.get("field_count") == 3

    print("== Logging in as staff ==")
    staff_tok = login(STAFF)

    print("== Case 5: POST fill with flatten=true ==")
    values = {"full_name": "Riley Thompson", "accept": True, "dept": "Operations"}
    r = requests.post(
        f"{BASE}/pdf-forms/templates/{tid}/fill",
        json={"values": values, "flatten": True},
        headers={"Authorization": f"Bearer {staff_tok}"}, timeout=60,
    )
    if r.status_code != 200:
        print(f"FAIL: status={r.status_code} body={r.text}")
        sys.exit(1)
    sub = r.json()
    assert "filled_pdf_base64" in sub, "missing filled_pdf_base64 in response"
    filled_b64 = sub["filled_pdf_base64"]
    filled_bytes = base64.b64decode(filled_b64)
    assert filled_bytes.startswith(b"%PDF"), f"not a valid PDF, starts with {filled_bytes[:8]!r}"
    print(f"   submission id={sub['id']} flattened={sub.get('flattened')} size={len(filled_bytes)} bytes; %PDF magic OK")

    print("== Re-parsing filled PDF with pypdf ==")
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(filled_bytes))
    fields = reader.get_fields() or {}
    print(f"   fields keys: {list(fields.keys())}")

    # Verify /V values
    def get_v(f):
        try:
            return f.get("/V")
        except Exception:
            return getattr(f, "value", None)

    v_full = str(get_v(fields["full_name"]) or "")
    v_accept = str(get_v(fields["accept"]) or "")
    v_dept = str(get_v(fields["dept"]) or "")
    print(f"   /V full_name={v_full!r}  accept={v_accept!r}  dept={v_dept!r}")
    assert v_full == "Riley Thompson", f"full_name mismatch: {v_full!r}"
    assert v_accept in ("/Yes", "Yes"), f"accept mismatch: {v_accept!r}"
    assert v_dept == "Operations", f"dept mismatch: {v_dept!r}"

    # Sanity: confirm /Ff bit-0 (ReadOnly) set on widget annots
    print("== Sanity: checking /Ff bit-0 on widget annots ==")
    ro_widgets = 0
    total_widgets = 0
    for page in reader.pages:
        if "/Annots" in page:
            for a in page["/Annots"]:
                obj = a.get_object()
                if obj.get("/Subtype") == "/Widget":
                    total_widgets += 1
                    ff = int(obj.get("/Ff", 0) or 0)
                    if ff & 1:
                        ro_widgets += 1
    print(f"   widget annots: {ro_widgets}/{total_widgets} have /Ff bit-0 (ReadOnly)")
    assert total_widgets > 0, "no widget annots found"
    assert ro_widgets == total_widgets, "not all widgets are read-only after flatten=true"

    # Cleanup template (admin)
    r = requests.delete(f"{BASE}/pdf-forms/templates/{tid}",
                        headers={"Authorization": f"Bearer {admin_tok}"}, timeout=30)
    print(f"== cleanup delete status={r.status_code} ==")

    print("\nALL ASSERTIONS PASSED — flatten=true now works correctly.")


if __name__ == "__main__":
    main()
