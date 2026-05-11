"""Backend regression for two new features:
  1) SMTP email on PDF form submission (POST /pdf-forms/templates/{tid}/fill)
  2) Visual PDF flattening (overlay stamps onto content stream)
Plus regression: existing flatten=false fill still works.
And collab session path: same flatten content-stream checks after /complete.
"""
import os, io, base64, sys, time, json
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

PASS = []
FAIL = []


def _ok(label):
    print(f"   PASS: {label}")
    PASS.append(label)


def _fail(label, detail=""):
    print(f"   FAIL: {label} :: {detail}")
    FAIL.append((label, detail))


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def build_acroform_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    form = c.acroForm
    c.drawString(72, 720, "Employee Onboarding Form")
    c.drawString(72, 680, "Full Name:")
    form.textfield(name="full_name", tooltip="Full legal name",
                   x=170, y=672, width=240, height=22, borderStyle="inset", forceBorder=True)
    c.drawString(72, 640, "Accept Terms:")
    form.checkbox(name="accept", tooltip="Accept terms",
                  x=170, y=638, buttonStyle="check", borderStyle="solid", size=18, forceBorder=True)
    c.drawString(72, 600, "Department:")
    form.choice(name="dept", value="Engineering",
                options=["Engineering", "Operations", "HR", "Finance"],
                x=170, y=590, width=180, height=24, forceBorder=True)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def get_page_content_data(filled_bytes):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(filled_bytes))
    page = r.pages[0]
    contents = page.get_contents()
    if contents is None:
        return b"", r
    if hasattr(contents, "get_data"):
        data = contents.get_data()
    else:
        data = b"".join(c.get_object().get_data() for c in contents)
    return data, r


def main():
    print("== Logging in admin & staff ==")
    admin_tok = login(ADMIN)
    staff_tok = login(STAFF)
    admin_hdr = {"Authorization": f"Bearer {admin_tok}"}
    staff_hdr = {"Authorization": f"Bearer {staff_tok}"}

    print("== Uploading AcroForm template ==")
    pdf_b64 = base64.b64encode(build_acroform_pdf()).decode()
    r = requests.post(
        f"{BASE}/pdf-forms/templates",
        json={"title": "Onboarding (smtp+overlay)", "description": "Regression",
              "pdf_base64": pdf_b64},
        headers=admin_hdr, timeout=30,
    )
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    print(f"   template id={tid}")

    values = {"full_name": "Riley Thompson", "accept": True, "dept": "Operations"}

    # ---------------- Feature 1: SMTP email on fill ----------------
    print("\n== Feature 1: POST /pdf-forms/templates/{tid}/fill flatten=true (SMTP + overlay) ==")
    t0 = time.time()
    r = requests.post(
        f"{BASE}/pdf-forms/templates/{tid}/fill",
        json={"values": values, "flatten": True},
        headers=staff_hdr, timeout=60,
    )
    dur = time.time() - t0
    if r.status_code != 200:
        _fail("fill flatten=true returns 200", f"status={r.status_code} body={r.text[:300]}")
        cleanup(tid, admin_hdr)
        finish()
        return
    _ok(f"fill flatten=true returns 200 (took {dur:.2f}s)")
    if dur > 10:
        _fail("fill returns within ~5s (non-blocking SMTP)", f"took {dur:.2f}s — event loop may be blocked")
    else:
        _ok(f"fill returns within ~10s (event loop not blocked; ~{dur:.2f}s)")

    body = r.json()
    filled_b64 = body.get("filled_pdf_base64")
    if not filled_b64:
        _fail("response contains filled_pdf_base64", "")
        cleanup(tid, admin_hdr); finish(); return
    filled_bytes = base64.b64decode(filled_b64)
    if filled_bytes.startswith(b"%PDF"):
        _ok(f"filled_pdf_base64 decodes to %PDF magic ({len(filled_bytes)} bytes)")
    else:
        _fail("filled_pdf_base64 starts with %PDF", f"starts={filled_bytes[:8]!r}")

    emailed_to = body.get("emailed_to")
    if emailed_to is None:
        _fail("response contains emailed_to field", "missing key")
    else:
        print(f"   emailed_to = {emailed_to!r}")
        if isinstance(emailed_to, list) and len(emailed_to) > 0:
            _ok(f"emailed_to is non-empty list ({len(emailed_to)} recipient(s)): {emailed_to}")
        else:
            _fail("emailed_to should be non-empty (SMTP configured + admins exist)", f"value={emailed_to!r}")

    # Tail backend log for SMTP info line
    try:
        with open("/var/log/supervisor/backend.out.log", "rb") as fh:
            fh.seek(0, 2); sz = fh.tell(); fh.seek(max(0, sz - 20000))
            tail = fh.read().decode("utf-8", errors="replace")
        if "SMTP sent to" in tail:
            ln = [l for l in tail.splitlines() if "SMTP sent to" in l]
            if ln:
                print(f"   Log: {ln[-1]}")
                _ok("Backend log shows 'SMTP sent to ...'")
        else:
            print("   (No 'SMTP sent to' in backend.out.log tail)")
    except Exception as e:
        print(f"   (log tail error: {e})")

    # ---------------- Feature 2: Visual overlay stamping ----------------
    print("\n== Feature 2: Verify overlay stamps in content stream ==")
    data, reader = get_page_content_data(filled_bytes)
    print(f"   content stream size: {len(data)} bytes; first 80: {data[:80]!r}")
    if b"Riley" in data:
        _ok("content stream contains b'Riley' (text overlay stamp)")
    else:
        _fail("content stream contains b'Riley'", f"first 200 bytes: {data[:200]!r}")
    if b"Operations" in data:
        _ok("content stream contains b'Operations' (select overlay stamp)")
    else:
        _fail("content stream contains b'Operations'", "")
    if b"(X)" in data:
        _ok("content stream contains b'(X)' (checkbox X stamp)")
    else:
        snippet = data[max(0,data.find(b'X')-20):data.find(b'X')+20] if b'X' in data else b'no X'
        _fail("content stream contains b'(X)'", f"snippet={snippet!r}")

    # /V values preserved
    fields = reader.get_fields() or {}
    def _gv(f):
        try: return f.get("/V")
        except Exception: return getattr(f, "value", None)
    v_full = str(_gv(fields.get("full_name", {})) or "")
    v_accept = str(_gv(fields.get("accept", {})) or "")
    v_dept = str(_gv(fields.get("dept", {})) or "")
    print(f"   /V values: full_name={v_full!r} accept={v_accept!r} dept={v_dept!r}")
    if v_full == "Riley Thompson":
        _ok("/V full_name preserved == 'Riley Thompson'")
    else:
        _fail("/V full_name preserved", f"got {v_full!r}")
    if v_accept in ("/Yes", "Yes"):
        _ok("/V accept preserved (/Yes)")
    else:
        _fail("/V accept preserved", f"got {v_accept!r}")
    if v_dept == "Operations":
        _ok("/V dept preserved == 'Operations'")
    else:
        _fail("/V dept preserved", f"got {v_dept!r}")

    # /Ff bit-0 on widgets
    ro = total = 0
    for page in reader.pages:
        if "/Annots" in page:
            for a in page["/Annots"]:
                obj = a.get_object()
                if obj.get("/Subtype") == "/Widget":
                    total += 1
                    if int(obj.get("/Ff", 0) or 0) & 1:
                        ro += 1
    if total > 0 and ro == total:
        _ok(f"/Ff bit-0 set on all {total} widgets (read-only after flatten)")
    else:
        _fail("/Ff bit-0 set on all widgets", f"{ro}/{total}")

    # ---------------- Regression: flatten=false ----------------
    print("\n== Regression: POST /fill flatten=false still works ==")
    r = requests.post(
        f"{BASE}/pdf-forms/templates/{tid}/fill",
        json={"values": {"full_name": "Alex Morgan", "accept": True, "dept": "HR"}, "flatten": False},
        headers=staff_hdr, timeout=30,
    )
    if r.status_code == 200:
        fb = base64.b64decode(r.json().get("filled_pdf_base64", ""))
        if fb.startswith(b"%PDF"):
            from pypdf import PdfReader
            rd = PdfReader(io.BytesIO(fb))
            ff = rd.get_fields() or {}
            v1 = str(_gv(ff.get("full_name", {})) or "")
            v2 = str(_gv(ff.get("accept", {})) or "")
            v3 = str(_gv(ff.get("dept", {})) or "")
            if v1 == "Alex Morgan" and v2 in ("/Yes", "Yes") and v3 == "HR":
                _ok("flatten=false returns /V values matching (Alex Morgan / /Yes / HR)")
            else:
                _fail("flatten=false /V values", f"got {v1!r}/{v2!r}/{v3!r}")
            data2, _ = get_page_content_data(fb)
            if b"Alex Morgan" not in data2:
                _ok("flatten=false: 'Alex Morgan' NOT in content stream (no overlay)")
            else:
                _fail("flatten=false should NOT stamp overlay", "found in content stream")
        else:
            _fail("flatten=false PDF magic", "")
    else:
        _fail("flatten=false fill 200", f"status={r.status_code} {r.text[:200]}")

    # ---------------- Collab session flatten check ----------------
    print("\n== Collab session: admin create → staff patch → admin complete → admin GET /pdf ==")
    r = requests.post(
        f"{BASE}/pdf-forms/templates/{tid}/sessions",
        json={"name": "Onboarding (collab smtp+overlay)"},
        headers=admin_hdr, timeout=30,
    )
    if r.status_code != 200:
        _fail("admin create session 200", f"{r.status_code} {r.text[:200]}")
        cleanup(tid, admin_hdr); finish(); return
    sid = r.json()["id"]
    print(f"   session id={sid}")

    r = requests.patch(
        f"{BASE}/pdf-forms/sessions/{sid}",
        json={"values": values},
        headers=staff_hdr, timeout=30,
    )
    if r.status_code == 200:
        _ok("staff PATCH session values 200")
    else:
        _fail("staff PATCH session", f"{r.status_code} {r.text[:200]}")

    r = requests.post(
        f"{BASE}/pdf-forms/sessions/{sid}/complete",
        headers=admin_hdr, timeout=60,
    )
    if r.status_code == 200:
        _ok("admin /complete session 200")
    else:
        _fail("admin /complete session", f"{r.status_code} {r.text[:200]}")

    r = requests.get(
        f"{BASE}/pdf-forms/sessions/{sid}/pdf",
        headers=admin_hdr, timeout=30,
    )
    if r.status_code == 200:
        sess_pdf = base64.b64decode(r.json().get("pdf_base64", ""))
        if sess_pdf.startswith(b"%PDF"):
            _ok(f"session PDF decoded ({len(sess_pdf)} bytes) — status={r.json().get('status')}")
            data3, reader3 = get_page_content_data(sess_pdf)
            if b"Riley" in data3:
                _ok("collab session: content stream contains b'Riley'")
            else:
                _fail("collab session: content stream b'Riley'", "")
            if b"Operations" in data3:
                _ok("collab session: content stream contains b'Operations'")
            else:
                _fail("collab session: content stream b'Operations'", "")
            if b"(X)" in data3:
                _ok("collab session: content stream contains b'(X)'")
            else:
                _fail("collab session: content stream b'(X)'", "")

            ff = reader3.get_fields() or {}
            v1 = str(_gv(ff.get("full_name", {})) or "")
            v2 = str(_gv(ff.get("accept", {})) or "")
            v3 = str(_gv(ff.get("dept", {})) or "")
            if v1 == "Riley Thompson" and v2 in ("/Yes", "Yes") and v3 == "Operations":
                _ok("collab session: /V values preserved")
            else:
                _fail("collab session: /V values", f"{v1!r}/{v2!r}/{v3!r}")

            ro = total = 0
            for page in reader3.pages:
                if "/Annots" in page:
                    for a in page["/Annots"]:
                        obj = a.get_object()
                        if obj.get("/Subtype") == "/Widget":
                            total += 1
                            if int(obj.get("/Ff", 0) or 0) & 1:
                                ro += 1
            if total > 0 and ro == total:
                _ok(f"collab session: /Ff read-only on all {total} widgets")
            else:
                _fail("collab session: /Ff read-only", f"{ro}/{total}")
        else:
            _fail("session PDF magic", f"first {sess_pdf[:8]!r}")
    else:
        _fail("admin GET session/pdf", f"{r.status_code} {r.text[:200]}")

    rd = requests.delete(f"{BASE}/pdf-forms/sessions/{sid}", headers=admin_hdr, timeout=30)
    print(f"   delete session status={rd.status_code}")

    cleanup(tid, admin_hdr)
    finish()


def cleanup(tid, admin_hdr):
    r = requests.delete(f"{BASE}/pdf-forms/templates/{tid}", headers=admin_hdr, timeout=30)
    print(f"\n   cleanup DELETE template status={r.status_code}")


def finish():
    print("\n" + "=" * 60)
    print(f"PASSED: {len(PASS)}")
    print(f"FAILED: {len(FAIL)}")
    for label, detail in FAIL:
        print(f"   - {label} :: {detail}")
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
