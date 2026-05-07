"""Tests for new admin checklist-alerts endpoint and CSV/PDF stats export."""
import os
import requests
import pytest
from datetime import datetime, timezone

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
assert BASE, "EXPO_PUBLIC_BACKEND_URL must be set"
API = f"{BASE}/api"
ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}


def H(t):
    return {"Authorization": f"Bearer {t}"}


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


@pytest.fixture(scope="module")
def alert_template_id(admin_token, staff_token):
    """Create a checklist with target 100 and submit only partial completion today."""
    payload = {
        "title": "TEST_AlertWash",
        "description": "alert testing",
        "kind": "checklist",
        "fields": [],
        "checklist_items": [
            {"id": "AL1", "label": "AL 1", "sub_keys": ["EXT", "INT"]},
            {"id": "AL2", "label": "AL 2", "sub_keys": ["EXT", "INT"]},
        ],
        "target_percent": 100,
    }
    r = requests.post(f"{API}/forms/templates", json=payload, headers=H(admin_token), timeout=30)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    # Submit a partial fill today => Below target
    requests.post(f"{API}/forms/submissions", json={
        "template_id": tid,
        "values": {
            "AL1_EXT": True, "AL1_INT": False,
            "AL2_EXT": False, "AL2_INT": False,
            "_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
    }, headers=H(staff_token), timeout=30).raise_for_status()
    return tid


# ---------------- Admin Checklist Alerts ----------------
class TestChecklistAlerts:
    def test_admin_can_get_alerts(self, admin_token, alert_template_id):
        r = requests.get(f"{API}/admin/checklist-alerts", headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        ids = [a["template_id"] for a in data]
        assert alert_template_id in ids, f"Expected partial-fill template flagged. Got {data}"
        # The created template should be flagged Below target (it has a submission today)
        ours = next(a for a in data if a["template_id"] == alert_template_id)
        assert ours["reason"] in ("Below target", "No submission today")
        assert "overall_percent" in ours
        assert "target_percent" in ours

    def test_staff_cannot_get_alerts(self, staff_token):
        r = requests.get(f"{API}/admin/checklist-alerts", headers=H(staff_token), timeout=30)
        assert r.status_code in (401, 403), f"Staff should be forbidden, got {r.status_code}"


# ---------------- CSV Export ----------------
class TestStatsExport:
    def test_export_csv(self, admin_token, alert_template_id):
        r = requests.get(
            f"{API}/forms/templates/{alert_template_id}/stats/export",
            params={"format": "csv"},
            headers=H(admin_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct, ct
        text = r.text
        assert "Template: TEST_AlertWash" in text
        assert "Item,Sub-task,Done,Missed,Submissions" in text
        # Should include the items
        assert "AL 1" in text and "AL 2" in text

    def test_export_pdf(self, admin_token, alert_template_id):
        r = requests.get(
            f"{API}/forms/templates/{alert_template_id}/stats/export",
            params={"format": "pdf"},
            headers=H(admin_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct
        assert r.content[:4] == b"%PDF", "Not a valid PDF magic"
        assert len(r.content) > 500

    def test_export_invalid_format(self, admin_token, alert_template_id):
        r = requests.get(
            f"{API}/forms/templates/{alert_template_id}/stats/export",
            params={"format": "xls"},
            headers=H(admin_token),
            timeout=30,
        )
        assert r.status_code == 400

    def test_export_404_unknown_tpl(self, admin_token):
        r = requests.get(
            f"{API}/forms/templates/nonexistent-id-xyz/stats/export",
            params={"format": "csv"},
            headers=H(admin_token),
            timeout=30,
        )
        assert r.status_code == 404

    def test_export_with_date_filter_returns_zero_subs(self, admin_token, alert_template_id):
        r = requests.get(
            f"{API}/forms/templates/{alert_template_id}/stats/export",
            params={"format": "csv", "date_from": "2030-01-01", "date_to": "2030-01-02"},
            headers=H(admin_token),
            timeout=30,
        )
        assert r.status_code == 200
        text = r.text
        assert "Submissions: 0" in text

    def test_export_requires_auth(self, alert_template_id):
        r = requests.get(
            f"{API}/forms/templates/{alert_template_id}/stats/export",
            params={"format": "csv"},
            timeout=30,
        )
        assert r.status_code in (401, 403)


# ---------------- Regression: legacy stats still works ----------------
class TestStatsRegression:
    def test_stats_endpoint_unchanged(self, admin_token, alert_template_id):
        r = requests.get(f"{API}/forms/templates/{alert_template_id}/stats", headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Required keys
        for k in ("overall_done", "overall_possible", "overall_percent", "on_target", "items", "submissions", "target_percent"):
            assert k in d, f"missing field {k}"
        assert isinstance(d["items"], list) and len(d["items"]) == 2
        for it in d["items"]:
            assert set(it["sub_keys"]) == {"EXT", "INT"}
            assert "counts" in it

    def test_form_kind_create_and_submit_still_works(self, admin_token, staff_token):
        tpl = requests.post(f"{API}/forms/templates", json={
            "title": "TEST_RegrForm",
            "kind": "form",
            "fields": [{"key": "name", "label": "Name", "type": "text", "required": True}],
        }, headers=H(admin_token), timeout=30)
        assert tpl.status_code == 200
        tid = tpl.json()["id"]
        sub = requests.post(f"{API}/forms/submissions", json={
            "template_id": tid, "values": {"name": "Bob"}
        }, headers=H(staff_token), timeout=30)
        assert sub.status_code == 200
        assert sub.json()["values"]["name"] == "Bob"
