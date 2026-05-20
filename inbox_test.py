"""
Phase A2 backend regression: Submissions Inbox + Mark Reviewed.

Targets:
  GET /api/admin/submissions-inbox  (admin-only)
  PATCH /api/forms/submissions/{sid}/review  (admin-only)
  PATCH /api/pdf-forms/submissions/{sid}/review  (admin-only)

Runs against the public proxy URL (EXPO_PUBLIC_BACKEND_URL).
"""
import os
import io
import base64
import sys
import json
import re
import time
from typing import Any, Dict, Optional, List

import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

# ---------------- config ----------------
def _read_env_value(path: str, key: str) -> Optional[str]:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    v = line.split("=", 1)[1].strip()
                    if v.startswith('"') and v.endswith('"'):
                        v = v[1:-1]
                    return v
    except FileNotFoundError:
        return None
    return None


BASE_URL = _read_env_value("/app/frontend/.env", "EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
if not BASE_URL:
    print("ERROR: EXPO_PUBLIC_BACKEND_URL not set"); sys.exit(2)
API = BASE_URL.rstrip("/") + "/api"

ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

PASS = 0
FAIL = 0
FAILS: List[str] = []


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
        return True
    FAIL += 1
    FAILS.append(f"{name} :: {detail}")
    print(f"  ❌ {name} :: {detail}")
    return False


def _login(creds) -> Dict[str, Any]:
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    r.raise_for_status()
    d = r.json()
    return {"token": d["access_token"], "user": d["user"]}


def H(tok: Optional[str]) -> Dict[str, str]:
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def _make_acroform_pdf_b64() -> str:
    """reportlab AcroForm PDF: text full_name + checkbox accept + choice dept."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "A2 Test PDF Form")
    form = c.acroForm
    c.drawString(72, 680, "Full name:")
    form.textfield(name="full_name", tooltip="Full name", x=160, y=675, width=240, height=20, borderStyle="inset")
    c.drawString(72, 640, "Accept terms:")
    form.checkbox(name="accept", x=160, y=635, size=18, buttonStyle="check")
    c.drawString(72, 600, "Department:")
    form.choice(name="dept", x=160, y=595, width=240, height=20,
                options=["Engineering", "Operations", "HR", "Finance"], value="Engineering")
    c.showPage()
    c.save()
    return base64.b64encode(buf.getvalue()).decode()


# ---------------- run ----------------
def main():
    print(f"Testing API at {API}")
    print("Logging in admin + staff...")
    admin_sess = _login(ADMIN)
    staff_sess = _login(STAFF)
    admin_tok = admin_sess["token"]
    staff_tok = staff_sess["token"]
    admin_id = admin_sess["user"]["id"]
    staff_id = staff_sess["user"]["id"]
    print(f"  admin_id={admin_id}, staff_id={staff_id}")

    # ----------------- (A) Inbox baseline shape & sorting -----------------
    print("\n(A) Inbox baseline shape & sorting")
    r = requests.get(f"{API}/admin/submissions-inbox", headers=H(admin_tok), timeout=30)
    _ok("A1 admin GET /admin/submissions-inbox → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    rows_base = r.json() if r.status_code == 200 else []
    _ok("A1 returns list", isinstance(rows_base, list), f"type={type(rows_base).__name__}")
    required_keys = {"id", "kind", "template_id", "template_title", "user_id", "user_name",
                     "created_at", "reviewed", "reviewed_at", "reviewed_by", "reviewed_by_name",
                     "status", "ai_summary"}
    if rows_base:
        sample = rows_base[0]
        missing = required_keys - set(sample.keys())
        _ok("A1 row shape has all required keys", not missing, f"missing={missing}")
        _ok("A1 row kind is form|pdf", all((r.get("kind") in ("form", "pdf")) for r in rows_base),
            f"kinds={set(r.get('kind') for r in rows_base)}")
    else:
        print("  ℹ️  inbox is empty pre-seed; will validate row shape after creating submissions")

    # A2 sorted desc
    if len(rows_base) >= 2:
        srt = all((rows_base[i].get("created_at") or "") <= (rows_base[i-1].get("created_at") or "") for i in range(1, len(rows_base)))
        _ok("A2 sorted by created_at desc", srt)
    else:
        _ok("A2 sorted by created_at desc (vacuous: <2 rows)", True)

    # A3 staff → 403
    r = requests.get(f"{API}/admin/submissions-inbox", headers=H(staff_tok), timeout=30)
    _ok("A3 staff GET → 403", r.status_code == 403, f"status={r.status_code}")

    # A4 unauth → 401
    r = requests.get(f"{API}/admin/submissions-inbox", timeout=30)
    _ok("A4 unauth GET → 401", r.status_code == 401, f"status={r.status_code}")

    # ----------------- (B) Filters: setup -----------------
    print("\n(B) Filters — setup form + pdf template, create one submission each")
    # Create form template
    body = {
        "title": "A2_Test_Form",
        "kind": "form",
        "fields": [{"key": "note", "type": "text", "label": "Note"}],
        "assigned_user_ids": [],
    }
    r = requests.post(f"{API}/forms/templates", headers=H(admin_tok), json=body, timeout=30)
    _ok("B setup admin POST /forms/templates → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    tid_form = r.json().get("id")
    _ok("B setup form template has id", bool(tid_form))

    # Create pdf template
    pdf_b64 = _make_acroform_pdf_b64()
    body = {"title": "A2_Test_PDF", "pdf_base64": pdf_b64, "assigned_user_ids": []}
    r = requests.post(f"{API}/pdf-forms/templates", headers=H(admin_tok), json=body, timeout=60)
    _ok("B setup admin POST /pdf-forms/templates → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    tid_pdf = r.json().get("id")
    _ok("B setup pdf template has_acroform=true", r.json().get("has_acroform") is True)

    # Staff submits form
    r = requests.post(f"{API}/forms/submissions", headers=H(staff_tok),
                      json={"template_id": tid_form, "values": {"note": "x"}}, timeout=30)
    _ok("B setup staff POST /forms/submissions → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    sid_form = r.json().get("id")
    _ok("B setup form submission id present", bool(sid_form))

    # Staff fills pdf
    r = requests.post(f"{API}/pdf-forms/templates/{tid_pdf}/fill", headers=H(staff_tok),
                      json={"values": {"full_name": "Jane T", "accept": True, "dept": "Operations"}, "flatten": False},
                      timeout=60)
    _ok("B setup staff POST /pdf-forms/.../fill → 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    sid_pdf = r.json().get("id")
    _ok("B setup pdf submission id present", bool(sid_pdf), f"resp={r.json() if r.status_code == 200 else r.text[:300]}")

    def _list_inbox(params: Dict[str, Any], tok: str = admin_tok, expect: int = 200) -> Any:
        rr = requests.get(f"{API}/admin/submissions-inbox", headers=H(tok), params=params, timeout=30)
        if rr.status_code != expect:
            return rr
        return rr.json() if rr.status_code == 200 else rr

    # B1 kind=form
    rows = _list_inbox({"kind": "form"})
    _ok("B1 kind=form: all rows are form", isinstance(rows, list) and all(r.get("kind") == "form" for r in rows),
        f"kinds={set(r.get('kind') for r in rows) if isinstance(rows, list) else rows}")
    ids = [r.get("id") for r in rows] if isinstance(rows, list) else []
    _ok("B1 sid_form present", sid_form in ids)
    _ok("B1 sid_pdf NOT present", sid_pdf not in ids)

    # B2 kind=pdf
    rows = _list_inbox({"kind": "pdf"})
    _ok("B2 kind=pdf: all rows are pdf", isinstance(rows, list) and all(r.get("kind") == "pdf" for r in rows))
    ids = [r.get("id") for r in rows] if isinstance(rows, list) else []
    _ok("B2 sid_pdf present", sid_pdf in ids)
    _ok("B2 sid_form NOT present", sid_form not in ids)

    # B3 template_id=tid_form
    rows = _list_inbox({"template_id": tid_form})
    _ok("B3 template_id filter: only sid_form's template", isinstance(rows, list) and all(r.get("template_id") == tid_form for r in rows))
    _ok("B3 sid_form present", sid_form in [r.get("id") for r in rows])

    # B4 user_id=jane
    rows = _list_inbox({"user_id": staff_id})
    _ok("B4 user_id filter: only Jane's submissions", isinstance(rows, list) and all(r.get("user_id") == staff_id for r in rows))
    _ok("B4 includes sid_form and sid_pdf",
        sid_form in [r.get("id") for r in rows] and sid_pdf in [r.get("id") for r in rows])

    # B5 from_date 2099
    rows = _list_inbox({"from_date": "2099-01-01"})
    _ok("B5 from_date=2099-01-01 → empty list", isinstance(rows, list) and len(rows) == 0, f"got n={len(rows) if isinstance(rows, list) else rows}")

    # B6 to_date 2000
    rows = _list_inbox({"to_date": "2000-01-01"})
    _ok("B6 to_date=2000-01-01 → empty list", isinstance(rows, list) and len(rows) == 0, f"got n={len(rows) if isinstance(rows, list) else rows}")

    # B7 reviewed=false
    rows = _list_inbox({"reviewed": "false"})
    if isinstance(rows, list):
        ids = [r.get("id") for r in rows]
        _ok("B7 reviewed=false: all rows have reviewed=false", all(r.get("reviewed") is False for r in rows))
        _ok("B7 includes sid_form and sid_pdf", sid_form in ids and sid_pdf in ids)
    else:
        _ok("B7 reviewed=false returns list", False, str(rows))

    # B8 reviewed=true — should NOT contain ours
    rows = _list_inbox({"reviewed": "true"})
    if isinstance(rows, list):
        ids = [r.get("id") for r in rows]
        _ok("B8 reviewed=true: sid_form NOT present (not yet reviewed)", sid_form not in ids)
        _ok("B8 reviewed=true: sid_pdf NOT present (not yet reviewed)", sid_pdf not in ids)
        _ok("B8 reviewed=true: all rows have reviewed=true", all(r.get("reviewed") is True for r in rows))
    else:
        _ok("B8 reviewed=true returns list", False, str(rows))

    # B9 bad from_date → 400
    r = requests.get(f"{API}/admin/submissions-inbox", headers=H(admin_tok), params={"from_date": "bad-date"}, timeout=30)
    _ok("B9 from_date=bad-date → 400", r.status_code == 400, f"status={r.status_code} body={r.text[:200]}")

    # ----------------- (C) Mark reviewed (form) -----------------
    print("\n(C) Mark reviewed (form)")
    # C1
    r = requests.patch(f"{API}/forms/submissions/{sid_form}/review", headers=H(admin_tok),
                       json={"reviewed": True}, timeout=30)
    _ok("C1 admin PATCH form review reviewed=true → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        d = r.json()
        _ok("C1 response reviewed=true", d.get("reviewed") is True)
        _ok("C1 reviewed_by == admin_id", d.get("reviewed_by") == admin_id, f"got {d.get('reviewed_by')}")
        _ok("C1 reviewed_by_name == 'Admin'", d.get("reviewed_by_name") == "Admin", f"got {d.get('reviewed_by_name')}")
        _ok("C1 reviewed_at populated", bool(d.get("reviewed_at")))
        _ok("C1 kind=form", d.get("kind") == "form")

    # C2 inbox?reviewed=true includes sid_form
    rows = _list_inbox({"reviewed": "true"})
    _ok("C2 inbox?reviewed=true includes sid_form", sid_form in [r.get("id") for r in rows] if isinstance(rows, list) else False)

    # C3 toggle false
    r = requests.patch(f"{API}/forms/submissions/{sid_form}/review", headers=H(admin_tok),
                       json={"reviewed": False}, timeout=30)
    _ok("C3 admin PATCH form review reviewed=false → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        d = r.json()
        _ok("C3 reviewed=false", d.get("reviewed") is False)
        _ok("C3 reviewed_at is null", d.get("reviewed_at") is None)
        _ok("C3 reviewed_by is null", d.get("reviewed_by") is None)
        _ok("C3 reviewed_by_name is null", d.get("reviewed_by_name") is None)

    # C4 staff PATCH → 403
    r = requests.patch(f"{API}/forms/submissions/{sid_form}/review", headers=H(staff_tok),
                       json={"reviewed": True}, timeout=30)
    _ok("C4 staff PATCH form review → 403", r.status_code == 403, f"status={r.status_code}")

    # C5 admin PATCH nonexistent → 404
    r = requests.patch(f"{API}/forms/submissions/nonexistent-zzz/review", headers=H(admin_tok),
                       json={"reviewed": True}, timeout=30)
    _ok("C5 admin PATCH nonexistent form review → 404", r.status_code == 404, f"status={r.status_code} body={r.text[:200]}")

    # C6 unauth → 401
    r = requests.patch(f"{API}/forms/submissions/{sid_form}/review", json={"reviewed": True}, timeout=30)
    _ok("C6 unauth PATCH form review → 401", r.status_code == 401, f"status={r.status_code}")

    # ----------------- (D) Mark reviewed (pdf) -----------------
    print("\n(D) Mark reviewed (pdf)")
    r = requests.patch(f"{API}/pdf-forms/submissions/{sid_pdf}/review", headers=H(admin_tok),
                       json={"reviewed": True}, timeout=30)
    _ok("D1 admin PATCH pdf review reviewed=true → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        d = r.json()
        _ok("D1 reviewed=true", d.get("reviewed") is True)
        _ok("D1 reviewed_by_name == 'Admin'", d.get("reviewed_by_name") == "Admin")
        _ok("D1 reviewed_at populated", bool(d.get("reviewed_at")))
        _ok("D1 kind=pdf", d.get("kind") == "pdf")

    # D2 inbox?kind=pdf&reviewed=true
    rows = _list_inbox({"kind": "pdf", "reviewed": "true"})
    _ok("D2 inbox?kind=pdf&reviewed=true includes sid_pdf",
        isinstance(rows, list) and sid_pdf in [r.get("id") for r in rows])

    # D3 back to false
    r = requests.patch(f"{API}/pdf-forms/submissions/{sid_pdf}/review", headers=H(admin_tok),
                       json={"reviewed": False}, timeout=30)
    _ok("D3 admin PATCH pdf review reviewed=false → 200", r.status_code == 200, f"{r.status_code}")
    if r.status_code == 200:
        d = r.json()
        _ok("D3 reviewed=false + nulls",
            d.get("reviewed") is False and d.get("reviewed_at") is None and d.get("reviewed_by") is None and d.get("reviewed_by_name") is None)

    # D4 staff → 403
    r = requests.patch(f"{API}/pdf-forms/submissions/{sid_pdf}/review", headers=H(staff_tok),
                       json={"reviewed": True}, timeout=30)
    _ok("D4 staff PATCH pdf review → 403", r.status_code == 403, f"status={r.status_code}")

    # D5 admin nonexistent → 404
    r = requests.patch(f"{API}/pdf-forms/submissions/nonexistent-zzz/review", headers=H(admin_tok),
                       json={"reviewed": True}, timeout=30)
    _ok("D5 admin PATCH nonexistent pdf review → 404", r.status_code == 404, f"status={r.status_code}")

    # ----------------- (E) Cleanup -----------------
    print("\n(E) Cleanup")
    r = requests.delete(f"{API}/forms/templates/{tid_form}", headers=H(admin_tok), timeout=30)
    _ok("E DELETE form template → 200", r.status_code == 200, f"status={r.status_code}")
    r = requests.delete(f"{API}/pdf-forms/templates/{tid_pdf}", headers=H(admin_tok), timeout=30)
    _ok("E DELETE pdf template → 200", r.status_code == 200, f"status={r.status_code}")

    # ----------------- Summary -----------------
    print("\n" + "=" * 60)
    print(f"PASS={PASS}  FAIL={FAIL}")
    if FAILS:
        print("\nFailures:")
        for f in FAILS:
            print(f"  - {f}")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
