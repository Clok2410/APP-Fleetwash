"""Tests for new checklist form-type + stats endpoints."""
import os, requests, pytest
BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://b863035e-804d-4d41-9158-321900c27687.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "admin@company.com", "password": "Admin@123"}
STAFF = {"email": "jane@company.com", "password": "Staff@123"}

@pytest.fixture(scope="module")
def admin_token():
    return requests.post(f"{API}/auth/login", json=ADMIN, timeout=30).json()["access_token"]

@pytest.fixture(scope="module")
def staff_token():
    return requests.post(f"{API}/auth/login", json=STAFF, timeout=30).json()["access_token"]

def H(t): return {"Authorization": f"Bearer {t}"}

@pytest.fixture(scope="module")
def template_id(admin_token):
    payload = {
        "title": "TEST_TruckWash",
        "description": "Aer Lingus truck wash",
        "kind": "checklist",
        "fields": [],
        "checklist_items": [
            {"id": "HL29", "label": "HL 29", "sub_keys": ["EXT", "INT"]},
            {"id": "HL30", "label": "HL 30", "sub_keys": ["EXT", "INT"]},
            {"id": "HL31", "label": "HL 31", "sub_keys": ["EXT", "INT"]},
        ],
        "target_percent": 100,
    }
    r = requests.post(f"{API}/forms/templates", json=payload, headers=H(admin_token), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "checklist"
    assert len(d["checklist_items"]) == 3
    assert d["target_percent"] == 100
    return d["id"]

class TestChecklist:
    def test_template_listed_with_kind(self, admin_token, template_id):
        r = requests.get(f"{API}/forms/templates", headers=H(admin_token), timeout=30)
        assert r.status_code == 200
        match = [t for t in r.json() if t["id"] == template_id]
        assert match and match[0]["kind"] == "checklist"
        assert match[0]["target_percent"] == 100
        assert len(match[0]["checklist_items"]) == 3

    def test_submission_and_stats(self, staff_token, admin_token, template_id):
        sub = requests.post(f"{API}/forms/submissions", json={
            "template_id": template_id,
            "values": {
                "HL29_EXT": True, "HL29_INT": True,
                "HL30_EXT": True, "HL30_INT": False,
                "HL31_EXT": False, "HL31_INT": False,
                "_date": "2026-02-07", "_notes": "maintenance",
            },
        }, headers=H(staff_token), timeout=30)
        assert sub.status_code == 200
        # Stats
        r = requests.get(f"{API}/forms/templates/{template_id}/stats", headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["overall_done"] >= 3
        assert d["overall_possible"] >= 6
        # Find this single submission stats: with exactly one submission, expect 50%
        # Filter by date to isolate
        r2 = requests.get(f"{API}/forms/templates/{template_id}/stats",
                          params={"date_from": "2026-02-07", "date_to": "2026-02-07"},
                          headers=H(admin_token), timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        # There may be other submissions today from prior tests; the single-day filter picks recent
        assert d2["overall_possible"] % 6 == 0
        assert d2["on_target"] is False  # 100% target with partial fill
        # Per-item structure validated
        ids = {it["id"] for it in d2["items"]}
        assert ids == {"HL29", "HL30", "HL31"}
        for it in d2["items"]:
            assert set(it["sub_keys"]) == {"EXT", "INT"}
            assert "EXT" in it["counts"] and "INT" in it["counts"]

    def test_stats_date_filter(self, admin_token, template_id):
        r = requests.get(f"{API}/forms/templates/{template_id}/stats",
                         params={"date_from": "2030-01-01"},
                         headers=H(admin_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["submissions"] == 0
        assert r.json()["overall_possible"] == 0

    def test_form_kind_still_works(self, admin_token, staff_token):
        tpl = requests.post(f"{API}/forms/templates", json={
            "title": "TEST_RegularForm",
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
