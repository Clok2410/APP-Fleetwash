"""Iteration 4 tests: Notifications + Depots/Geofencing + Weekly Digest"""
import os
import uuid
import pytest
import requests

BASE = "https://b863035e-804d-4d41-9158-321900c27687.preview.emergentagent.com"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "admin@company.com", "password": "Admin@123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def staff_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "jane@company.com", "password": "Staff@123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def hdrs(t):
    return {"Authorization": f"Bearer {t}"}


# ---------------- Depots ----------------
class TestDepots:
    depot_id = None

    def test_create_depot_admin(self, admin_token):
        body = {"name": f"TEST_London_{uuid.uuid4().hex[:6]}", "lat": 51.5074, "lng": -0.1278, "radius_m": 200}
        r = requests.post(f"{BASE}/api/depots", json=body, headers=hdrs(admin_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == body["name"]
        assert d["lat"] == 51.5074
        assert d["radius_m"] == 200
        assert "id" in d
        TestDepots.depot_id = d["id"]

    def test_list_depots_any_user(self, staff_token):
        r = requests.get(f"{BASE}/api/depots", headers=hdrs(staff_token))
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert TestDepots.depot_id in ids

    def test_create_depot_staff_forbidden(self, staff_token):
        r = requests.post(f"{BASE}/api/depots", json={"name": "Nope", "lat": 0, "lng": 0, "radius_m": 100}, headers=hdrs(staff_token))
        assert r.status_code == 403


# ---------------- Geofence Clock-in ----------------
class TestGeofence:
    def _ensure_clocked_out(self, token):
        # Try to clock out if currently in
        requests.post(f"{BASE}/api/clock/out", json={}, headers=hdrs(token))

    def test_offsite_creates_notification(self, admin_token, staff_token):
        # Use the depot from TestDepots (London) – clock in from Dublin (way outside)
        self._ensure_clocked_out(staff_token)
        # capture current admin notif count
        r0 = requests.get(f"{BASE}/api/notifications", headers=hdrs(admin_token))
        before = len(r0.json())

        # Mid-Atlantic — guaranteed >200m from any plausible depot
        r = requests.post(f"{BASE}/api/clock/in", json={"lat": 0.0, "lng": -30.0, "note": "TEST_offsite"}, headers=hdrs(staff_token))
        assert r.status_code == 200, r.text
        entry = r.json()
        assert entry["off_site"] is True
        assert entry["distance_m"] is not None and entry["distance_m"] > 200
        assert entry["depot_id"] is not None  # nearest depot recorded

        # Verify notification created for admin
        r1 = requests.get(f"{BASE}/api/notifications", headers=hdrs(admin_token))
        after = r1.json()
        assert len(after) > before
        assert any(n["kind"] == "off_site" for n in after)

        # Cleanup: clock out
        self._ensure_clocked_out(staff_token)

    def test_onsite_no_notification(self, admin_token, staff_token):
        self._ensure_clocked_out(staff_token)
        r0 = requests.get(f"{BASE}/api/notifications", headers=hdrs(admin_token))
        before = len([n for n in r0.json() if n["kind"] == "off_site"])

        # London depot lat/lng — clock in exactly there
        r = requests.post(f"{BASE}/api/clock/in", json={"lat": 51.5074, "lng": -0.1278, "note": "TEST_onsite"}, headers=hdrs(staff_token))
        assert r.status_code == 200, r.text
        entry = r.json()
        assert entry["off_site"] is False
        assert entry["depot_id"] is not None

        r1 = requests.get(f"{BASE}/api/notifications", headers=hdrs(admin_token))
        after = len([n for n in r1.json() if n["kind"] == "off_site"])
        assert after == before  # no new off-site notif

        self._ensure_clocked_out(staff_token)


# ---------------- Notifications ----------------
class TestNotifications:
    def test_admin_only_sees_own(self, admin_token, staff_token):
        # Staff should not see admin's notifications (their own list)
        r_admin = requests.get(f"{BASE}/api/notifications", headers=hdrs(admin_token))
        r_staff = requests.get(f"{BASE}/api/notifications", headers=hdrs(staff_token))
        assert r_admin.status_code == 200 and r_staff.status_code == 200
        admin_ids = {n["id"] for n in r_admin.json()}
        staff_ids = {n["id"] for n in r_staff.json()}
        assert admin_ids.isdisjoint(staff_ids)

    def test_unread_filter(self, admin_token):
        r = requests.get(f"{BASE}/api/notifications?unread_only=true", headers=hdrs(admin_token))
        assert r.status_code == 200
        for n in r.json():
            assert n["read"] is False

    def test_mark_read_single(self, admin_token):
        r = requests.get(f"{BASE}/api/notifications?unread_only=true", headers=hdrs(admin_token))
        items = r.json()
        if not items:
            pytest.skip("No unread notifications to mark")
        nid = items[0]["id"]
        rr = requests.post(f"{BASE}/api/notifications/{nid}/read", headers=hdrs(admin_token))
        assert rr.status_code == 200
        # Verify
        r2 = requests.get(f"{BASE}/api/notifications", headers=hdrs(admin_token))
        target = next((x for x in r2.json() if x["id"] == nid), None)
        assert target is not None and target["read"] is True

    def test_mark_all_read(self, admin_token):
        rr = requests.post(f"{BASE}/api/notifications/read-all", headers=hdrs(admin_token))
        assert rr.status_code == 200
        r = requests.get(f"{BASE}/api/notifications?unread_only=true", headers=hdrs(admin_token))
        assert r.status_code == 200 and r.json() == []


# ---------------- Scan alerts (idempotent) ----------------
class TestScanAlerts:
    def test_scan_alerts_admin_only(self, staff_token):
        r = requests.post(f"{BASE}/api/admin/scan-alerts", headers=hdrs(staff_token))
        assert r.status_code == 403

    def test_scan_alerts_runs(self, admin_token):
        r1 = requests.post(f"{BASE}/api/admin/scan-alerts", headers=hdrs(admin_token))
        assert r1.status_code == 200
        first = r1.json().get("alerts_created", 0)
        # Idempotent: second call same day shouldn't create duplicates
        r2 = requests.post(f"{BASE}/api/admin/scan-alerts", headers=hdrs(admin_token))
        assert r2.status_code == 200
        assert r2.json().get("alerts_created", 0) == 0


# ---------------- Checklist below target auto-notif ----------------
class TestChecklistAutoNotif:
    def test_below_target_creates_notification(self, admin_token, staff_token):
        # Create a checklist template with target 100%
        tpl_body = {
            "title": f"TEST_DailyCheck_{uuid.uuid4().hex[:6]}",
            "kind": "checklist",
            "target_percent": 100.0,
            "fields": [],
            "checklist_items": [
                {"id": "HL1", "label": "HL 1", "sub_keys": ["EXT", "INT"]}
            ],
        }
        r = requests.post(f"{BASE}/api/forms/templates", json=tpl_body, headers=hdrs(admin_token))
        assert r.status_code == 200, r.text
        tid = r.json()["id"]

        # mark all read first
        requests.post(f"{BASE}/api/notifications/read-all", headers=hdrs(admin_token))

        # Submit BELOW target (only one of two ticked)
        sub = {"template_id": tid, "values": {"HL1_EXT": True, "HL1_INT": False}}
        rs = requests.post(f"{BASE}/api/forms/submissions", json=sub, headers=hdrs(staff_token))
        assert rs.status_code == 200, rs.text

        # Admin should now have a checklist_below_target notification
        r2 = requests.get(f"{BASE}/api/notifications?unread_only=true", headers=hdrs(admin_token))
        notifs = r2.json()
        assert any(n["kind"] == "checklist_below_target" and n["related_id"] == tid for n in notifs), \
            f"Expected checklist_below_target notif for {tid}, got {notifs}"

        # cleanup template
        requests.delete(f"{BASE}/api/forms/templates/{tid}", headers=hdrs(admin_token))


# ---------------- Weekly Digest ----------------
class TestWeeklyDigest:
    digest_id = None

    def test_send_weekly_digest_mocked(self, admin_token):
        r = requests.post(f"{BASE}/api/admin/weekly-digest", headers=hdrs(admin_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["mocked"] is True  # no API key
        assert "admin@company.com" in d["recipients"]
        assert d["filename"].startswith("staffhub-digest-")
        assert d["filename"].endswith(".csv")
        assert d["digest_id"]
        TestWeeklyDigest.digest_id = d["digest_id"]

    def test_list_digests(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/digests", headers=hdrs(admin_token))
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert TestWeeklyDigest.digest_id in ids

    def test_list_digests_staff_forbidden(self, staff_token):
        r = requests.get(f"{BASE}/api/admin/digests", headers=hdrs(staff_token))
        assert r.status_code == 403

    def test_download_digest_csv(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/digests/{TestWeeklyDigest.digest_id}/download", headers=hdrs(admin_token))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "StaffHub Weekly Compliance Digest" in r.text


# ---------------- Cleanup depot last ----------------
class TestZCleanup:
    def test_delete_depot(self, admin_token):
        if TestDepots.depot_id:
            r = requests.delete(f"{BASE}/api/depots/{TestDepots.depot_id}", headers=hdrs(admin_token))
            assert r.status_code == 200
            r2 = requests.get(f"{BASE}/api/depots", headers=hdrs(admin_token))
            ids = [d["id"] for d in r2.json()]
            assert TestDepots.depot_id not in ids
