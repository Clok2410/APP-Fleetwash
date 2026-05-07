"""Iter8: Customers / CRM / shift-arrival notifications tests"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def staff_token():
    r = requests.post(f"{API}/auth/login", json=STAFF)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def staff_user(staff_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {staff_token}"})
    assert r.status_code == 200
    return r.json()


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ---------------- Customers CRUD ----------------
class TestCustomers:
    customer_id = None

    def test_create_customer_admin(self, admin_token):
        body = {"name": "TEST_AerLingus", "company": "Aer Lingus", "email": "ops@aerlingus.test", "phone": "+353000"}
        r = requests.post(f"{API}/customers", json=body, headers=H(admin_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == "TEST_AerLingus"
        assert d.get("contacts") == [] and d.get("sites") == []
        TestCustomers.customer_id = d["id"]

    def test_create_customer_forbidden_for_staff(self, staff_token):
        r = requests.post(f"{API}/customers", json={"name": "TEST_x"}, headers=H(staff_token))
        assert r.status_code == 403

    def test_list_customers_any_user(self, staff_token):
        r = requests.get(f"{API}/customers", headers=H(staff_token))
        assert r.status_code == 200
        assert any(c["id"] == TestCustomers.customer_id for c in r.json())

    def test_get_customer_embeds_arrays(self, staff_token):
        r = requests.get(f"{API}/customers/{TestCustomers.customer_id}", headers=H(staff_token))
        assert r.status_code == 200
        d = r.json()
        assert "contacts" in d and "sites" in d

    def test_add_contact_admin(self, admin_token):
        body = {"name": "TEST_Mary", "role": "Manager", "phone": "1", "email": "m@a.io"}
        r = requests.post(f"{API}/customers/{TestCustomers.customer_id}/contacts", json=body, headers=H(admin_token))
        assert r.status_code == 200
        TestCustomers.contact_id = r.json()["id"]
        # verify persisted
        g = requests.get(f"{API}/customers/{TestCustomers.customer_id}", headers=H(admin_token)).json()
        assert any(c["id"] == TestCustomers.contact_id for c in g["contacts"])

    def test_add_contact_forbidden_for_staff(self, staff_token):
        r = requests.post(f"{API}/customers/{TestCustomers.customer_id}/contacts", json={"name": "x"}, headers=H(staff_token))
        assert r.status_code == 403

    def test_add_site_admin(self, admin_token):
        body = {"name": "TEST_DublinHangar", "address": "DUB", "lat": 53.4264, "lng": -6.2499, "radius_m": 200}
        r = requests.post(f"{API}/customers/{TestCustomers.customer_id}/sites", json=body, headers=H(admin_token))
        assert r.status_code == 200
        TestCustomers.site_id = r.json()["id"]

    def test_add_site_forbidden_for_staff(self, staff_token):
        r = requests.post(f"{API}/customers/{TestCustomers.customer_id}/sites", json={"name": "x"}, headers=H(staff_token))
        assert r.status_code == 403


# ---------------- Customer notes ----------------
class TestCustomerNotes:
    def test_staff_can_post_note(self, staff_token, staff_user):
        cid = TestCustomers.customer_id
        body = {"body": "TEST_staff note", "category": "access", "pinned": False}
        r = requests.post(f"{API}/customers/{cid}/notes", json=body, headers=H(staff_token))
        assert r.status_code == 200, r.text
        n = r.json()
        assert n["author_id"] == staff_user["id"]
        TestCustomerNotes.staff_note_id = n["id"]

    def test_admin_pinned_note_then_sort_order(self, admin_token):
        cid = TestCustomers.customer_id
        r = requests.post(f"{API}/customers/{cid}/notes",
                          json={"body": "TEST_admin pinned", "category": "hazard", "pinned": True},
                          headers=H(admin_token))
        assert r.status_code == 200
        TestCustomerNotes.admin_note_id = r.json()["id"]
        lst = requests.get(f"{API}/customers/{cid}/notes", headers=H(admin_token)).json()
        # pinned first
        assert lst[0]["pinned"] is True
        assert lst[0]["id"] == TestCustomerNotes.admin_note_id

    def test_staff_cannot_edit_admin_note(self, staff_token):
        cid = TestCustomers.customer_id
        nid = TestCustomerNotes.admin_note_id
        r = requests.patch(f"{API}/customers/{cid}/notes/{nid}",
                           json={"body": "hack", "category": "general", "pinned": True},
                           headers=H(staff_token))
        assert r.status_code == 403

    def test_staff_can_edit_own_note(self, staff_token):
        cid = TestCustomers.customer_id
        nid = TestCustomerNotes.staff_note_id
        r = requests.patch(f"{API}/customers/{cid}/notes/{nid}",
                           json={"body": "TEST_updated", "category": "access", "pinned": True},
                           headers=H(staff_token))
        assert r.status_code == 200
        assert r.json()["body"] == "TEST_updated"

    def test_admin_can_delete_any_note(self, admin_token):
        cid = TestCustomers.customer_id
        for nid in [TestCustomerNotes.staff_note_id, TestCustomerNotes.admin_note_id]:
            r = requests.delete(f"{API}/customers/{cid}/notes/{nid}", headers=H(admin_token))
            assert r.status_code == 200


# ---------------- Shifts + clock-in geofence ----------------
class TestShiftClockIn:
    def test_create_shift_with_customer_site(self, admin_token, staff_user):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        # Wraps NOW
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=4)).isoformat()
        body = {
            "user_id": staff_user["id"],
            "title": "TEST_Shift",
            "location": "DUB",
            "start": start,
            "end": end,
            "customer_id": TestCustomers.customer_id,
            "site_id": TestCustomers.site_id,
        }
        r = requests.post(f"{API}/shifts", json=body, headers=H(admin_token))
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["customer_name"] == "TEST_AerLingus"
        assert s["site_name"] == "TEST_DublinHangar"
        TestShiftClockIn.shift_id = s["id"]

    def _ensure_clocked_out(self, token):
        st = requests.get(f"{API}/clock/status", headers=H(token)).json()
        if st.get("clocked_in"):
            requests.post(f"{API}/clock/out", json={}, headers=H(token))

    def test_on_site_clock_in(self, staff_token, admin_token):
        self._ensure_clocked_out(staff_token)
        body = {"shift_id": TestShiftClockIn.shift_id, "lat": 53.4264, "lng": -6.2499}
        r = requests.post(f"{API}/clock/in", json=body, headers=H(staff_token))
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["arrived_on_site"] is True
        assert e["customer_name"] == "TEST_AerLingus"
        assert e["site_name"] == "TEST_DublinHangar"
        # admin notification 'arrival'
        time.sleep(0.5)
        notifs = requests.get(f"{API}/notifications", headers=H(admin_token)).json()
        assert any(n["kind"] == "arrival" and n.get("related_id") == e["id"] for n in notifs)
        self._ensure_clocked_out(staff_token)

    def test_off_site_clock_in_creates_shift_off_site(self, staff_token, admin_token):
        self._ensure_clocked_out(staff_token)
        body = {"shift_id": TestShiftClockIn.shift_id, "lat": 51.5, "lng": -0.12}
        r = requests.post(f"{API}/clock/in", json=body, headers=H(staff_token))
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["arrived_on_site"] is False
        time.sleep(0.5)
        notifs = requests.get(f"{API}/notifications", headers=H(admin_token)).json()
        assert any(n["kind"] == "shift_off_site" and n.get("related_id") == e["id"] for n in notifs)
        self._ensure_clocked_out(staff_token)

    def test_auto_resolve_shift_no_shift_id(self, staff_token):
        self._ensure_clocked_out(staff_token)
        body = {"lat": 53.4264, "lng": -6.2499}  # no shift_id
        r = requests.post(f"{API}/clock/in", json=body, headers=H(staff_token))
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["customer_name"] == "TEST_AerLingus"
        assert e["site_name"] == "TEST_DublinHangar"
        assert e["shift_id"] == TestShiftClockIn.shift_id
        self._ensure_clocked_out(staff_token)


# ---------------- Cleanup ----------------
def test_zz_cleanup(admin_token):
    if TestCustomers.customer_id:
        # delete shift first
        if hasattr(TestShiftClockIn, "shift_id"):
            requests.delete(f"{API}/shifts/{TestShiftClockIn.shift_id}", headers=H(admin_token))
        requests.delete(f"{API}/customers/{TestCustomers.customer_id}", headers=H(admin_token))
