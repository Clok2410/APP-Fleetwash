"""Iteration 7: off-site clock-ins admin endpoint filter tests
Filters: depot_id, user_id, date_from, date_to combined with legacy days fallback.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("BACKEND_BASE_URL")
    or "https://b863035e-804d-4d41-9158-321900c27687.preview.emergentagent.com"
).rstrip("/")


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


@pytest.fixture(scope="module")
def staff_user_id(admin_token):
    r = requests.get(f"{BASE}/api/users", headers=hdrs(admin_token))
    assert r.status_code == 200
    jane = next((u for u in r.json() if u["email"] == "jane@company.com"), None)
    assert jane is not None
    return jane["id"]


@pytest.fixture(scope="module")
def seed_offsite(admin_token, staff_token):
    """Create at least one fresh off-site clock-in so filter tests have data."""
    # Ensure clocked out
    requests.post(f"{BASE}/api/clock/out", json={}, headers=hdrs(staff_token))
    r = requests.post(
        f"{BASE}/api/clock/in",
        json={"lat": 0.0, "lng": -30.0, "note": "TEST_iter7_offsite"},
        headers=hdrs(staff_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["off_site"] is True
    requests.post(f"{BASE}/api/clock/out", json={}, headers=hdrs(staff_token))
    return True


# ------------ Filter tests -----------
class TestOffsiteFilters:
    def test_baseline_no_filters(self, admin_token, seed_offsite):
        r = requests.get(f"{BASE}/api/admin/off-site-clock-ins", headers=hdrs(admin_token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        for e in data:
            assert e.get("off_site") is True

    def test_days_param_still_works(self, admin_token, seed_offsite):
        r1 = requests.get(f"{BASE}/api/admin/off-site-clock-ins?days=14", headers=hdrs(admin_token))
        r2 = requests.get(f"{BASE}/api/admin/off-site-clock-ins?days=1", headers=hdrs(admin_token))
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert len(r2.json()) <= len(r1.json())

    def test_filter_by_user_id(self, admin_token, staff_user_id, seed_offsite):
        r = requests.get(
            f"{BASE}/api/admin/off-site-clock-ins",
            params={"user_id": staff_user_id, "days": 30},
            headers=hdrs(admin_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        for e in data:
            assert e["user_id"] == staff_user_id, f"foreign user_id leaked: {e}"
            assert e["off_site"] is True

    def test_filter_by_user_id_unknown(self, admin_token):
        bogus = str(uuid.uuid4())
        r = requests.get(
            f"{BASE}/api/admin/off-site-clock-ins",
            params={"user_id": bogus, "days": 30},
            headers=hdrs(admin_token),
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_filter_by_depot_id(self, admin_token, seed_offsite):
        # Get all off-site entries, find one with a depot_id, then filter
        r = requests.get(f"{BASE}/api/admin/off-site-clock-ins?days=60", headers=hdrs(admin_token))
        assert r.status_code == 200
        all_entries = r.json()
        depot_ids = [e["depot_id"] for e in all_entries if e.get("depot_id")]
        if not depot_ids:
            pytest.skip("No off-site entries with a depot_id to filter on")
        target_depot = depot_ids[0]
        r2 = requests.get(
            f"{BASE}/api/admin/off-site-clock-ins",
            params={"depot_id": target_depot, "days": 60},
            headers=hdrs(admin_token),
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert len(data) >= 1
        for e in data:
            assert e["depot_id"] == target_depot
            assert e["off_site"] is True

    def test_filter_by_date_range(self, admin_token, seed_offsite):
        today = datetime.now(timezone.utc).date()
        date_from = (today - timedelta(days=30)).isoformat()
        date_to = today.isoformat()
        r = requests.get(
            f"{BASE}/api/admin/off-site-clock-ins",
            params={"date_from": date_from, "date_to": date_to},
            headers=hdrs(admin_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # Should include the seeded today entry
        assert len(data) >= 1
        for e in data:
            ci = e["clock_in"]  # iso str
            ci_dt = datetime.fromisoformat(ci.replace("Z", "+00:00")) if isinstance(ci, str) else ci
            assert (today - timedelta(days=31)) <= ci_dt.date() <= (today + timedelta(days=1))

    def test_filter_date_range_far_past_empty(self, admin_token):
        r = requests.get(
            f"{BASE}/api/admin/off-site-clock-ins",
            params={"date_from": "2000-01-01", "date_to": "2000-01-02"},
            headers=hdrs(admin_token),
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_filter_combined_user_and_date(self, admin_token, staff_user_id, seed_offsite):
        today = datetime.now(timezone.utc).date()
        r = requests.get(
            f"{BASE}/api/admin/off-site-clock-ins",
            params={
                "user_id": staff_user_id,
                "date_from": (today - timedelta(days=7)).isoformat(),
                "date_to": today.isoformat(),
            },
            headers=hdrs(admin_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for e in data:
            assert e["user_id"] == staff_user_id

    def test_filter_combined_all(self, admin_token, staff_user_id):
        # All filters at once should not error; depot_id may or may not match
        r_all = requests.get(f"{BASE}/api/admin/off-site-clock-ins?days=60", headers=hdrs(admin_token))
        depot_ids = [e["depot_id"] for e in r_all.json() if e.get("depot_id") and e["user_id"] == staff_user_id]
        depot = depot_ids[0] if depot_ids else None
        today = datetime.now(timezone.utc).date()
        params = {
            "user_id": staff_user_id,
            "date_from": (today - timedelta(days=14)).isoformat(),
            "date_to": today.isoformat(),
        }
        if depot:
            params["depot_id"] = depot
        r = requests.get(
            f"{BASE}/api/admin/off-site-clock-ins",
            params=params,
            headers=hdrs(admin_token),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for e in data:
            assert e["user_id"] == staff_user_id
            if depot:
                assert e["depot_id"] == depot

    def test_staff_forbidden(self, staff_token):
        r = requests.get(f"{BASE}/api/admin/off-site-clock-ins", headers=hdrs(staff_token))
        assert r.status_code == 403
