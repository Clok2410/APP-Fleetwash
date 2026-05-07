"""Iteration 5 tests: Off-site clock-in admin list + per-depot weekly digest bundles."""
import os
import uuid
import pytest
import requests

BASE = os.environ.get("BACKEND_BASE_URL", "https://b863035e-804d-4d41-9158-321900c27687.preview.emergentagent.com")


def hdrs(t):
    return {"Authorization": f"Bearer {t}"}


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


# ---------- Off-site clock-in admin list ----------
class TestOffSiteClockIns:
    def test_admin_can_list(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/off-site-clock-ins", headers=hdrs(admin_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # Every entry must be off_site=True
        for e in data:
            assert e.get("off_site") is True
            # Should have key fields for UI rendering
            for k in ("id", "user_name", "lat", "lng", "distance_m", "depot_name", "clock_in"):
                assert k in e, f"missing key {k} in {e.keys()}"

    def test_staff_forbidden(self, staff_token):
        r = requests.get(f"{BASE}/api/admin/off-site-clock-ins", headers=hdrs(staff_token))
        assert r.status_code == 403

    def test_days_param_honored(self, admin_token, staff_token):
        # ensure clocked out
        requests.post(f"{BASE}/api/clock/out", json={}, headers=hdrs(staff_token))
        # Trigger an off-site entry
        r = requests.post(
            f"{BASE}/api/clock/in",
            json={"lat": 0.0, "lng": -30.0, "note": "TEST_iter5_offsite"},
            headers=hdrs(staff_token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["off_site"] is True
        requests.post(f"{BASE}/api/clock/out", json={}, headers=hdrs(staff_token))

        r1 = requests.get(f"{BASE}/api/admin/off-site-clock-ins?days=14", headers=hdrs(admin_token))
        r2 = requests.get(f"{BASE}/api/admin/off-site-clock-ins?days=1", headers=hdrs(admin_token))
        assert r1.status_code == 200 and r2.status_code == 200
        # 1-day window must be subset (count) of 14-day window
        assert len(r2.json()) <= len(r1.json())


# ---------- Per-depot weekly digest ----------
class TestPerDepotDigest:
    depot_id = None
    template_id = None

    def test_create_depot_and_assigned_checklist(self, admin_token):
        body = {"name": f"TEST_Depot_{uuid.uuid4().hex[:6]}", "lat": 51.5074, "lng": -0.1278, "radius_m": 200}
        r = requests.post(f"{BASE}/api/depots", json=body, headers=hdrs(admin_token))
        assert r.status_code == 200, r.text
        TestPerDepotDigest.depot_id = r.json()["id"]
        depot_name = r.json()["name"]

        # Create a checklist tied to this depot
        tpl = {
            "title": f"TEST_Checklist_{uuid.uuid4().hex[:6]}",
            "kind": "checklist",
            "target_percent": 100.0,
            "fields": [],
            "checklist_items": [{"id": "HL1", "label": "HL 1", "sub_keys": ["EXT"]}],
            "depot_id": TestPerDepotDigest.depot_id,
        }
        rt = requests.post(f"{BASE}/api/forms/templates", json=tpl, headers=hdrs(admin_token))
        assert rt.status_code == 200, rt.text
        td = rt.json()
        assert td.get("depot_id") == TestPerDepotDigest.depot_id, f"depot_id not persisted: {td}"
        assert td.get("kind") == "checklist"
        TestPerDepotDigest.template_id = td["id"]
        # Stash depot name for next test
        TestPerDepotDigest.depot_name = depot_name

    def test_weekly_digest_returns_bundles(self, admin_token):
        r = requests.post(f"{BASE}/api/admin/weekly-digest", headers=hdrs(admin_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("mocked") is True  # no RESEND_API_KEY
        bundles = d.get("bundles")
        assert isinstance(bundles, list) and len(bundles) >= 1, f"no bundles: {d}"
        assert isinstance(d.get("digest_ids"), list) and len(d["digest_ids"]) == len(bundles)

        # Each bundle has depot_name and filename
        for b in bundles:
            assert "depot_name" in b and "filename" in b
            assert b["filename"].endswith(".csv")

        names = [b["depot_name"] for b in bundles]
        # Our test depot's bundle must appear
        assert TestPerDepotDigest.depot_name in names, f"expected {TestPerDepotDigest.depot_name} in {names}"
        TestPerDepotDigest.last_digest_ids = d["digest_ids"]

    def test_digests_list_includes_new(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/digests", headers=hdrs(admin_token))
        assert r.status_code == 200, r.text
        all_ids = {x["id"] for x in r.json()}
        for did in TestPerDepotDigest.last_digest_ids:
            assert did in all_ids, f"digest {did} not in list"
        # New rows should expose depot_name field
        rows_with_depot = [x for x in r.json() if x["id"] in TestPerDepotDigest.last_digest_ids]
        for row in rows_with_depot:
            assert "depot_name" in row

    def test_download_new_digest(self, admin_token):
        did = TestPerDepotDigest.last_digest_ids[0]
        r = requests.get(f"{BASE}/api/admin/digests/{did}/download", headers=hdrs(admin_token))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        # Body should mention StaffHub Weekly Digest
        assert "Weekly Digest" in r.text or "Weekly Compliance Digest" in r.text

    def test_template_appears_under_assigned_depot_bundle(self, admin_token):
        # Re-run digest and verify our depot bundle CSV contains the template title
        r = requests.post(f"{BASE}/api/admin/weekly-digest", headers=hdrs(admin_token))
        assert r.status_code == 200
        d = r.json()
        # Find the digest_id matching our depot_name
        target_did = None
        for b, did in zip(d["bundles"], d["digest_ids"]):
            if b["depot_name"] == TestPerDepotDigest.depot_name:
                target_did = did
                break
        assert target_did, f"no bundle for {TestPerDepotDigest.depot_name}"
        rd = requests.get(f"{BASE}/api/admin/digests/{target_did}/download", headers=hdrs(admin_token))
        assert rd.status_code == 200
        # Look up template title from list
        rt = requests.get(f"{BASE}/api/forms/templates", headers=hdrs(admin_token))
        title = next((t["title"] for t in rt.json() if t["id"] == TestPerDepotDigest.template_id), None)
        assert title is not None
        assert title in rd.text, f"template '{title}' not found in depot bundle CSV"

    def test_zcleanup(self, admin_token):
        if TestPerDepotDigest.template_id:
            requests.delete(f"{BASE}/api/forms/templates/{TestPerDepotDigest.template_id}", headers=hdrs(admin_token))
        if TestPerDepotDigest.depot_id:
            requests.delete(f"{BASE}/api/depots/{TestPerDepotDigest.depot_id}", headers=hdrs(admin_token))


# ---------- Regression: Existing endpoints still work ----------
class TestRegression:
    def test_depots_list(self, admin_token):
        r = requests.get(f"{BASE}/api/depots", headers=hdrs(admin_token))
        assert r.status_code == 200

    def test_notifications_list(self, admin_token):
        r = requests.get(f"{BASE}/api/notifications", headers=hdrs(admin_token))
        assert r.status_code == 200

    def test_scan_alerts(self, admin_token):
        r = requests.post(f"{BASE}/api/admin/scan-alerts", headers=hdrs(admin_token))
        assert r.status_code == 200

    def test_clock_status(self, staff_token):
        r = requests.get(f"{BASE}/api/clock/status", headers=hdrs(staff_token))
        assert r.status_code == 200
