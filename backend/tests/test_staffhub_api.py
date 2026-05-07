"""StaffHub API regression tests covering auth, clock, holidays, shifts, drive, forms."""
import os
import base64
import time
import pytest
import requests

BASE = "https://b863035e-804d-4d41-9158-321900c27687.preview.emergentagent.com"
API = f"{BASE}/api"

ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def staff_token():
    r = requests.post(f"{API}/auth/login", json=STAFF, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- Auth ----------
class TestAuth:
    def test_login_admin(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "access_token" in d and d["user"]["role"] == "admin"

    def test_login_staff(self):
        r = requests.post(f"{API}/auth/login", json=STAFF, timeout=30)
        assert r.status_code == 200
        assert r.json()["user"]["email"] == STAFF["email"]

    def test_login_bad(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN["email"], "password": "wrong"}, timeout=30)
        assert r.status_code == 401

    def test_me(self, staff_token):
        r = requests.get(f"{API}/auth/me", headers=H(staff_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["email"] == STAFF["email"]

    def test_me_no_token(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401


# ---------- Clock ----------
class TestClock:
    def test_clock_flow(self, staff_token):
        # ensure clean slate
        st = requests.get(f"{API}/clock/status", headers=H(staff_token)).json()
        if st.get("clocked_in"):
            requests.post(f"{API}/clock/out", json={}, headers=H(staff_token))
        r = requests.post(f"{API}/clock/in", json={"note": "TEST_in"}, headers=H(staff_token))
        assert r.status_code == 200, r.text
        assert r.json()["clock_out"] is None
        # double clock-in fails
        r2 = requests.post(f"{API}/clock/in", json={}, headers=H(staff_token))
        assert r2.status_code == 400
        time.sleep(1)
        r3 = requests.post(f"{API}/clock/out", json={"note": "TEST_out"}, headers=H(staff_token))
        assert r3.status_code == 200
        assert r3.json()["clock_out"] is not None
        hist = requests.get(f"{API}/clock/history", headers=H(staff_token))
        assert hist.status_code == 200 and len(hist.json()) >= 1


# ---------- Holidays ----------
class TestHolidays:
    def test_balance_and_request_decision(self, staff_token, admin_token):
        b = requests.get(f"{API}/holidays/balance", headers=H(staff_token))
        assert b.status_code == 200 and "remaining" in b.json()
        c = requests.post(f"{API}/holidays/requests",
                          json={"start_date": "2026-06-01", "end_date": "2026-06-03",
                                "reason": "TEST_holiday", "type": "annual"},
                          headers=H(staff_token))
        assert c.status_code == 200
        rid = c.json()["id"]
        lst = requests.get(f"{API}/holidays/requests", headers=H(staff_token))
        assert lst.status_code == 200 and any(r["id"] == rid for r in lst.json())
        d = requests.post(f"{API}/holidays/requests/{rid}/decision?decision=approved",
                          headers=H(admin_token))
        assert d.status_code == 200
        # verify status persisted
        lst2 = requests.get(f"{API}/holidays/requests", headers=H(staff_token)).json()
        match = [x for x in lst2 if x["id"] == rid]
        assert match and match[0]["status"] == "approved"


# ---------- Shifts ----------
class TestShifts:
    def test_shift_and_swap(self, admin_token, staff_token):
        # need staff user id
        me = requests.get(f"{API}/auth/me", headers=H(staff_token)).json()
        admin_me = requests.get(f"{API}/auth/me", headers=H(admin_token)).json()
        s = requests.post(f"{API}/shifts",
                          json={"user_id": me["id"], "title": "TEST_Shift",
                                "start": "2026-06-10T09:00:00Z", "end": "2026-06-10T17:00:00Z",
                                "location": "HQ"},
                          headers=H(admin_token))
        assert s.status_code == 200, s.text
        sid = s.json()["id"]
        gl = requests.get(f"{API}/shifts", headers=H(staff_token))
        assert gl.status_code == 200 and any(x["id"] == sid for x in gl.json())
        sw = requests.post(f"{API}/shifts/{sid}/swap",
                           json={"target_user_id": admin_me["id"], "reason": "TEST"},
                           headers=H(staff_token))
        assert sw.status_code == 200
        sl = requests.get(f"{API}/shifts/swaps", headers=H(staff_token))
        assert sl.status_code == 200 and len(sl.json()) >= 1


# ---------- Drive ----------
class TestDrive:
    def test_folder_and_file(self, staff_token):
        f = requests.post(f"{API}/drive/folders", json={"name": "TEST_Folder"},
                          headers=H(staff_token))
        assert f.status_code == 200
        fid = f.json()["id"]
        b64 = base64.b64encode(b"hello world").decode()
        up = requests.post(f"{API}/drive/files",
                           json={"name": "TEST.txt", "folder_id": fid,
                                 "mime_type": "text/plain", "data_base64": b64},
                           headers=H(staff_token))
        assert up.status_code == 200
        fileid = up.json()["id"]
        lst = requests.get(f"{API}/drive/files?folder_id={fid}", headers=H(staff_token))
        assert lst.status_code == 200 and any(x["id"] == fileid for x in lst.json())
        get = requests.get(f"{API}/drive/files/{fileid}", headers=H(staff_token))
        assert get.status_code == 200 and get.json()["data_base64"] == b64


# ---------- Forms ----------
class TestForms:
    def test_template_submission_summary(self, admin_token, staff_token):
        tpl = requests.post(f"{API}/forms/templates",
                            json={"title": "TEST_Incident", "description": "d",
                                  "fields": [
                                      {"key": "what", "label": "What happened", "type": "textarea", "required": True},
                                      {"key": "when", "label": "When", "type": "date"}
                                  ]},
                            headers=H(admin_token))
        assert tpl.status_code == 200, tpl.text
        tid = tpl.json()["id"]
        sub = requests.post(f"{API}/forms/submissions",
                            json={"template_id": tid,
                                  "values": {"what": "Customer slipped near aisle 3", "when": "2026-01-15"}},
                            headers=H(staff_token))
        assert sub.status_code == 200
        sid = sub.json()["id"]
        # AI summary (slow) - allow long timeout
        summ = requests.post(f"{API}/forms/submissions/{sid}/summarize",
                             headers=H(staff_token), timeout=120)
        assert summ.status_code == 200, summ.text
        assert summ.json().get("summary")
