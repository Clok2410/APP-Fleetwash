"""
Backend regression for new collaborative PDF form Sessions endpoints.

Run:  python /app/pdf_sessions_test.py
"""
import os
import sys
import io
import base64
import json

import requests

BASE = "https://employee-connect-9.preview.emergentagent.com/api"
ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

results = []


def log(name, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}{(' - ' + detail) if detail else ''}")
    results.append((ok, name, detail))


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data["user"]


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def build_acroform_pdf() -> bytes:
    """Build a tiny reportlab AcroForm PDF with text + checkbox + choice fields."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setFont("Helvetica", 14)
    c.drawString(72, 740, "Crew Check Form")
    c.setFont("Helvetica", 10)

    form = c.acroForm

    c.drawString(72, 700, "Full Name:")
    form.textfield(
        name="full_name",
        tooltip="Full Name",
        x=160, y=692, width=300, height=20,
        borderStyle="inset",
        forceBorder=True,
    )

    c.drawString(72, 660, "Accept Terms:")
    form.checkbox(
        name="accept",
        tooltip="Accept",
        x=160, y=658, size=18,
        buttonStyle="check",
        borderStyle="solid",
        forceBorder=True,
    )

    c.drawString(72, 620, "Department:")
    form.choice(
        name="dept",
        tooltip="Department",
        value="Engineering",
        options=["Engineering", "Operations", "HR", "Finance"],
        x=160, y=612, width=200, height=22,
        borderStyle="inset",
        forceBorder=True,
    )

    c.showPage()
    c.save()
    return buf.getvalue()


def main():
    # ---- Login ----
    admin_tok, admin_user = login(ADMIN)
    staff_tok, staff_user = login(STAFF)
    log("login admin", admin_user.get("role") == "admin", admin_user.get("email"))
    log("login staff", staff_user.get("role") == "staff", staff_user.get("email"))

    admin_name = admin_user["name"]
    staff_name = staff_user["name"]

    # ---- 1) Setup: admin uploads template ----
    pdf_bytes = build_acroform_pdf()
    pdf_b64 = base64.b64encode(pdf_bytes).decode()
    r = requests.post(
        f"{BASE}/pdf-forms/templates",
        headers=hdr(admin_tok),
        json={"title": "Crew Check (Test)", "description": "regression test", "pdf_base64": pdf_b64},
        timeout=30,
    )
    if r.status_code != 200:
        log("1) upload template", False, f"{r.status_code} {r.text[:200]}")
        return
    tmpl = r.json()
    tid = tmpl["id"]
    ok = (
        tmpl.get("has_acroform") is True
        and tmpl.get("field_count") == 3
        and "pdf_base64" not in tmpl
    )
    log("1) upload template (has_acroform=true, field_count=3)", ok,
        f"tid={tid} fields={tmpl.get('field_count')}")

    try:
        # ---- 2) Start sessions ----
        # 2a) Staff with body name
        r = requests.post(
            f"{BASE}/pdf-forms/templates/{tid}/sessions",
            headers=hdr(staff_tok),
            json={"name": "Crew Check #1"},
            timeout=20,
        )
        ok = r.status_code == 200
        sid = None
        if ok:
            s = r.json()
            sid = s["id"]
            ok = (
                s.get("status") == "draft"
                and s.get("values") == {}
                and s.get("last_editor_name") == staff_name
                and s.get("name") == "Crew Check #1"
            )
        log("2a) staff create session w/ name", ok,
            f"sid={sid} last_editor={s.get('last_editor_name') if r.status_code==200 else r.text[:120]}")

        # 2b) Staff without body (default name)
        r = requests.post(
            f"{BASE}/pdf-forms/templates/{tid}/sessions",
            headers=hdr(staff_tok),
            json={},
            timeout=20,
        )
        ok = r.status_code == 200
        sid_default = None
        if ok:
            s2 = r.json()
            sid_default = s2["id"]
            ok = bool(s2.get("name")) and s2.get("status") == "draft"
        log("2b) staff create session default name", ok,
            f"name={(s2.get('name') if r.status_code == 200 else r.text[:120])}")

        # ---- 3) GET sessions list ----
        r = requests.get(f"{BASE}/pdf-forms/sessions", headers=hdr(staff_tok), timeout=20)
        ok = r.status_code == 200
        if ok:
            arr = r.json()
            ids = {x["id"] for x in arr}
            no_pdf = all("filled_pdf_base64" not in x for x in arr)
            ok = sid in ids and sid_default in ids and no_pdf
        log("3) list sessions includes new ones, no filled_pdf_base64",
            ok, f"count={len(arr) if r.status_code==200 else '?'}")

        # filter by template_id
        r = requests.get(
            f"{BASE}/pdf-forms/sessions",
            headers=hdr(staff_tok),
            params={"template_id": tid},
            timeout=20,
        )
        ok = r.status_code == 200 and all(x["template_id"] == tid for x in r.json())
        log("3) filter ?template_id", ok, f"count={len(r.json()) if r.status_code==200 else '?'}")

        # filter by status=draft
        r = requests.get(
            f"{BASE}/pdf-forms/sessions",
            headers=hdr(staff_tok),
            params={"status": "draft"},
            timeout=20,
        )
        ok = r.status_code == 200 and all(x.get("status") == "draft" for x in r.json())
        log("3) filter ?status=draft", ok, f"count={len(r.json()) if r.status_code==200 else '?'}")

        # ---- 4) PATCH session ----
        # 4a) staff patches full_name
        r = requests.patch(
            f"{BASE}/pdf-forms/sessions/{sid}",
            headers=hdr(staff_tok),
            json={"values": {"full_name": "John"}},
            timeout=20,
        )
        ok = r.status_code == 200 and r.json().get("saved_keys") == 1
        log("4a) staff PATCH full_name (saved_keys=1)", ok, json.dumps(r.json()) if r.status_code==200 else r.text[:120])

        # 4b) GET reflects + last_editor=staff
        r = requests.get(f"{BASE}/pdf-forms/sessions/{sid}", headers=hdr(staff_tok), timeout=20)
        ok = r.status_code == 200
        if ok:
            s = r.json()
            ok = (
                s.get("values", {}).get("full_name") == "John"
                and s.get("last_editor_name") == staff_name
            )
        log("4b) GET reflects full_name + last_editor=staff", ok,
            f"values={s.get('values') if r.status_code==200 else '?'} last_editor={s.get('last_editor_name') if r.status_code==200 else '?'}")

        # 4c) admin patches accept=true (collab)
        r = requests.patch(
            f"{BASE}/pdf-forms/sessions/{sid}",
            headers=hdr(admin_tok),
            json={"values": {"accept": True}},
            timeout=20,
        )
        ok = r.status_code == 200 and r.json().get("saved_keys") == 1
        log("4c) admin PATCH accept=true (collab)", ok, json.dumps(r.json()) if r.status_code==200 else r.text[:120])

        # GET reflects merged + last_editor=admin
        r = requests.get(f"{BASE}/pdf-forms/sessions/{sid}", headers=hdr(staff_tok), timeout=20)
        ok = r.status_code == 200
        if ok:
            s = r.json()
            v = s.get("values", {})
            ok = (
                v.get("full_name") == "John"
                and v.get("accept") is True
                and s.get("last_editor_name") == admin_name
            )
        log("4c) GET merged values + last_editor=admin", ok,
            f"values={s.get('values') if r.status_code==200 else '?'} last_editor={s.get('last_editor_name') if r.status_code==200 else '?'}")

        # ---- 8a) PDF endpoint draft state (any user) ----
        r = requests.get(f"{BASE}/pdf-forms/sessions/{sid}/pdf", headers=hdr(staff_tok), timeout=30)
        ok = r.status_code == 200
        if ok:
            data = r.json()
            try:
                raw = base64.b64decode(data.get("pdf_base64", ""))
            except Exception:
                raw = b""
            ok = raw[:4] == b"%PDF" and data.get("status") == "draft"
        log("8a) GET /pdf (draft) starts with %PDF", ok,
            f"first4={(raw[:4].decode('latin-1') if r.status_code==200 else '?')} status={(data.get('status') if r.status_code==200 else '?')}")

        # admin can also fetch
        r = requests.get(f"{BASE}/pdf-forms/sessions/{sid}/pdf", headers=hdr(admin_tok), timeout=30)
        ok = r.status_code == 200 and base64.b64decode(r.json().get("pdf_base64", ""))[:4] == b"%PDF"
        log("8a') admin GET /pdf (draft)", ok)

        # ---- 5) Complete ----
        # 5a) staff -> 403
        r = requests.post(f"{BASE}/pdf-forms/sessions/{sid}/complete", headers=hdr(staff_tok), timeout=30)
        log("5a) staff complete -> 403", r.status_code == 403, f"status={r.status_code} body={r.text[:120]}")

        # 5b) admin -> 200
        r = requests.post(f"{BASE}/pdf-forms/sessions/{sid}/complete", headers=hdr(admin_tok), timeout=60)
        log("5b) admin complete -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:160]}")

        # 5c) GET shows status=completed and filled_pdf_base64 not null
        r = requests.get(f"{BASE}/pdf-forms/sessions/{sid}", headers=hdr(admin_tok), timeout=20)
        ok = r.status_code == 200
        if ok:
            s = r.json()
            ok = s.get("status") == "completed" and bool(s.get("filled_pdf_base64"))
        log("5c) after complete: status=completed, filled_pdf_base64 not null", ok,
            f"status={s.get('status') if r.status_code==200 else '?'} has_pdf={bool(s.get('filled_pdf_base64')) if r.status_code==200 else '?'}")

        # ---- 8b) GET /pdf for completed ----
        r = requests.get(f"{BASE}/pdf-forms/sessions/{sid}/pdf", headers=hdr(staff_tok), timeout=30)
        ok = r.status_code == 200
        if ok:
            data = r.json()
            raw = base64.b64decode(data.get("pdf_base64", ""))
            ok = raw[:4] == b"%PDF" and data.get("status") == "completed"
        log("8b) GET /pdf (completed) starts with %PDF, status=completed", ok,
            f"first4={(raw[:4].decode('latin-1') if r.status_code==200 else '?')} status={(data.get('status') if r.status_code==200 else '?')}")

        # ---- 6) PATCH after lock ----
        # 6a) staff -> 403 with detail mentioning locked
        r = requests.patch(
            f"{BASE}/pdf-forms/sessions/{sid}",
            headers=hdr(staff_tok),
            json={"values": {"full_name": "Hacker"}},
            timeout=20,
        )
        ok = r.status_code == 403
        detail = ""
        try:
            detail = (r.json() or {}).get("detail", "")
        except Exception:
            detail = r.text
        ok = ok and ("lock" in detail.lower())
        log("6a) staff PATCH after lock -> 403 mentions locked", ok, f"status={r.status_code} detail={detail!r}")

        # 6b) admin -> 200 (override)
        r = requests.patch(
            f"{BASE}/pdf-forms/sessions/{sid}",
            headers=hdr(admin_tok),
            json={"values": {"dept": "Operations"}},
            timeout=20,
        )
        log("6b) admin PATCH after lock -> 200 (override)", r.status_code == 200, f"status={r.status_code} body={r.text[:120]}")

        # ---- 7) Reopen ----
        # 7a) staff -> 403
        r = requests.post(f"{BASE}/pdf-forms/sessions/{sid}/reopen", headers=hdr(staff_tok), timeout=20)
        log("7a) staff reopen -> 403", r.status_code == 403, f"status={r.status_code}")

        # 7b) admin -> 200
        r = requests.post(f"{BASE}/pdf-forms/sessions/{sid}/reopen", headers=hdr(admin_tok), timeout=20)
        log("7b) admin reopen -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:120]}")

        # GET shows status=draft and filled_pdf_base64 cleared
        r = requests.get(f"{BASE}/pdf-forms/sessions/{sid}", headers=hdr(admin_tok), timeout=20)
        ok = r.status_code == 200
        if ok:
            s = r.json()
            ok = s.get("status") == "draft" and not s.get("filled_pdf_base64")
        log("7c) reopen: status=draft, filled_pdf_base64 cleared", ok,
            f"status={s.get('status') if r.status_code==200 else '?'} has_pdf={bool(s.get('filled_pdf_base64')) if r.status_code==200 else '?'}")

        # ---- 9) DELETE session ----
        # staff
        r = requests.delete(f"{BASE}/pdf-forms/sessions/{sid}", headers=hdr(staff_tok), timeout=20)
        log("9a) staff DELETE -> 403", r.status_code == 403, f"status={r.status_code}")

        # admin
        r = requests.delete(f"{BASE}/pdf-forms/sessions/{sid}", headers=hdr(admin_tok), timeout=20)
        log("9b) admin DELETE -> 200", r.status_code == 200, f"status={r.status_code}")

        # GET after delete -> 404
        r = requests.get(f"{BASE}/pdf-forms/sessions/{sid}", headers=hdr(admin_tok), timeout=20)
        log("9c) GET after DELETE -> 404", r.status_code == 404, f"status={r.status_code}")

        # cleanup the second session
        requests.delete(f"{BASE}/pdf-forms/sessions/{sid_default}", headers=hdr(admin_tok), timeout=20)

    finally:
        # ---- Cleanup template ----
        r = requests.delete(f"{BASE}/pdf-forms/templates/{tid}", headers=hdr(admin_tok), timeout=20)
        log("cleanup) admin DELETE template", r.status_code == 200, f"status={r.status_code}")

    # Summary
    passed = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    print(f"\n=== {passed}/{total} PASSED ===")
    failed = [(n, d) for ok, n, d in results if not ok]
    if failed:
        print("FAILED:")
        for n, d in failed:
            print(f" - {n}: {d}")
        sys.exit(1)


if __name__ == "__main__":
    main()
