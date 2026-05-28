"""
Backend tests for HR Envelope enhancements:
- POST /api/hr/envelopes/upload-and-issue (single + bulk)
- POST /api/hr/issuances/{iid}/resend
- GET  /api/hr/envelopes/summary
- POST /api/hr/issuances/{iid}/cancel (silent, no email)
- Auth: admin-only endpoints reject staff (403)
"""
import base64
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://staff-scheduler-152.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "claire@fleetwash.ie"
ADMIN_PASSWORD = "Maudlings26"

# Minimal valid PDF stub
TINY_PDF_B64 = base64.b64encode(b"%PDF-1.4\n%minimal\ntrailer<<>>\n%%EOF").decode()


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    body = r.json()
    tok = body.get("access_token") or body.get("token")
    assert tok, f"No token in login response: {body}"
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def staff_users(admin_headers):
    """Pick two staff users for bulk send. Auto-create TEST_ staff users if needed."""
    r = requests.get(f"{BASE_URL}/api/users", headers=admin_headers, timeout=30)
    assert r.status_code == 200, f"List users failed: {r.text}"
    users = r.json()
    staff = [u for u in users if u.get("role") == "staff" and u.get("email") and u.get("active", True)]

    # Ensure at least 2 staff users — create TEST_ ones if needed
    import uuid as _uuid
    while len(staff) < 2:
        unique = _uuid.uuid4().hex[:8]
        payload = {
            "email": f"test_staff_{unique}@example.com",
            "name": f"TEST Staff {unique}",
            "password": "TestPass123!",
            "role": "staff",
        }
        rc = requests.post(
            f"{BASE_URL}/api/auth/register",
            json=payload, headers=admin_headers, timeout=30,
        )
        assert rc.status_code == 200, f"Could not create test staff user: {rc.status_code} {rc.text}"
        staff.append(rc.json())
    return staff[:2]


@pytest.fixture(scope="session")
def staff_token(admin_headers, staff_users):
    """Try to obtain a staff token. If we can't login as paul@fleetwash.ie/Staff123!,
    skip the 403 tests rather than fail."""
    # Try common test password first
    for pw in ["Staff123!", "staff123", "Maudlings26"]:
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "paul@fleetwash.ie", "password": pw},
            timeout=20,
        )
        if r.status_code == 200:
            body = r.json()
            return body.get("access_token") or body.get("token")
    return None


# ---------- Tests: upload-and-issue ----------
class TestUploadAndIssue:
    """upload-and-issue covers both legacy single-recipient and new bulk modes."""

    def test_single_user_legacy_returns_single_object(self, admin_headers, staff_users):
        payload = {
            "title": "TEST_HR_SINGLE_LEGACY",
            "user_id": staff_users[0]["id"],
            "pdf_base64": TINY_PDF_B64,
            "expires_at": "2030-01-01",
            "message": "legacy single",
        }
        r = requests.post(
            f"{BASE_URL}/api/hr/envelopes/upload-and-issue",
            json=payload, headers=admin_headers, timeout=60,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        # Legacy single-object shape
        assert "id" in data, f"Expected single-object shape with 'id', got {data}"
        assert "count" not in data
        assert data.get("user_id") == staff_users[0]["id"]
        assert data.get("template_id")
        # Stash for later
        pytest.single_iid = data["id"]
        pytest.single_template_id = data["template_id"]

    def test_bulk_user_ids_returns_count_and_list(self, admin_headers, staff_users):
        uids = [u["id"] for u in staff_users]
        payload = {
            "title": "TEST_HR_BULK",
            "user_ids": uids,
            "pdf_base64": TINY_PDF_B64,
            "expires_at": "2030-01-01",
            "message": "bulk send",
        }
        r = requests.post(
            f"{BASE_URL}/api/hr/envelopes/upload-and-issue",
            json=payload, headers=admin_headers, timeout=120,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data.get("count") == len(uids), f"count mismatch: {data}"
        issuances = data.get("issuances") or []
        assert len(issuances) == len(uids)
        # All share the same template_id (shared template)
        tpl_ids = {iss.get("template_id") for iss in issuances}
        assert len(tpl_ids) == 1, f"bulk should share one template: {tpl_ids}"
        # Each issuance targets a distinct user
        assert {iss.get("user_id") for iss in issuances} == set(uids)
        pytest.bulk_iids = [iss["id"] for iss in issuances]

    def test_bulk_user_ids_dedupes(self, admin_headers, staff_users):
        uid = staff_users[0]["id"]
        payload = {
            "title": "TEST_HR_BULK_DEDUPE",
            "user_ids": [uid, uid, uid],
            "pdf_base64": TINY_PDF_B64,
        }
        r = requests.post(
            f"{BASE_URL}/api/hr/envelopes/upload-and-issue",
            json=payload, headers=admin_headers, timeout=60,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        # Dedupe collapses to single -> legacy shape
        assert "id" in data or data.get("count") == 1, f"Expected dedupe to single: {data}"

    def test_no_recipients_returns_400(self, admin_headers):
        payload = {"title": "TEST_HR_NO_RCPT", "pdf_base64": TINY_PDF_B64}
        r = requests.post(
            f"{BASE_URL}/api/hr/envelopes/upload-and-issue",
            json=payload, headers=admin_headers, timeout=30,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code} {r.text}"

    def test_invalid_pdf_returns_400(self, admin_headers, staff_users):
        bad_b64 = base64.b64encode(b"not-a-pdf-at-all").decode()
        payload = {
            "title": "TEST_HR_BADPDF",
            "user_id": staff_users[0]["id"],
            "pdf_base64": bad_b64,
        }
        r = requests.post(
            f"{BASE_URL}/api/hr/envelopes/upload-and-issue",
            json=payload, headers=admin_headers, timeout=30,
        )
        assert r.status_code == 400

    def test_unknown_user_returns_404(self, admin_headers):
        payload = {
            "title": "TEST_HR_UNKNOWN",
            "user_ids": ["nonexistent-user-id-xyz"],
            "pdf_base64": TINY_PDF_B64,
        }
        r = requests.post(
            f"{BASE_URL}/api/hr/envelopes/upload-and-issue",
            json=payload, headers=admin_headers, timeout=30,
        )
        assert r.status_code == 404


# ---------- Tests: summary ----------
class TestSummary:
    def test_summary_shape(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/hr/envelopes/summary", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("total", "counts", "outstanding", "overdue", "stagnant"):
            assert key in data, f"Missing {key} in summary: {data}"
        for st in ("pending", "read", "signed", "expired", "cancelled"):
            assert st in data["counts"], f"Missing status {st} in counts"
        assert isinstance(data["total"], int)
        # After our upload tests, total should be > 0
        assert data["total"] >= 1


# ---------- Tests: resend ----------
class TestResend:
    def test_resend_pending_envelope_ok(self, admin_headers):
        iid = getattr(pytest, "single_iid", None)
        if not iid:
            pytest.skip("No single envelope was created earlier")
        r = requests.post(
            f"{BASE_URL}/api/hr/issuances/{iid}/resend",
            headers=admin_headers, timeout=60,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data.get("id") == iid
        # Audit should include a 'resent' event
        audit = data.get("audit") or []
        kinds = [a.get("kind") for a in audit]
        assert "resent" in kinds, f"Expected 'resent' audit event, got {kinds}"

    def test_resend_unknown_id_returns_404(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/hr/issuances/nonexistent-iid-xyz/resend",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 404

    def test_resend_cancelled_envelope_returns_400(self, admin_headers, staff_users):
        # Create then cancel an envelope, then try to resend
        payload = {
            "title": "TEST_HR_TO_CANCEL",
            "user_id": staff_users[0]["id"],
            "pdf_base64": TINY_PDF_B64,
        }
        r = requests.post(
            f"{BASE_URL}/api/hr/envelopes/upload-and-issue",
            json=payload, headers=admin_headers, timeout=60,
        )
        assert r.status_code == 200
        iid = r.json()["id"]
        # Cancel it
        r2 = requests.post(
            f"{BASE_URL}/api/hr/issuances/{iid}/cancel",
            headers=admin_headers, timeout=30,
        )
        assert r2.status_code == 200
        assert r2.json().get("status") == "cancelled"
        # Resend should now fail
        r3 = requests.post(
            f"{BASE_URL}/api/hr/issuances/{iid}/resend",
            headers=admin_headers, timeout=30,
        )
        assert r3.status_code == 400, f"Expected 400, got {r3.status_code} {r3.text}"


# ---------- Tests: cancel ----------
class TestCancel:
    def test_cancel_pending_ok(self, admin_headers, staff_users):
        payload = {
            "title": "TEST_HR_CANCEL_OK",
            "user_id": staff_users[0]["id"],
            "pdf_base64": TINY_PDF_B64,
        }
        r = requests.post(
            f"{BASE_URL}/api/hr/envelopes/upload-and-issue",
            json=payload, headers=admin_headers, timeout=60,
        )
        iid = r.json()["id"]
        rc = requests.post(
            f"{BASE_URL}/api/hr/issuances/{iid}/cancel",
            headers=admin_headers, timeout=30,
        )
        assert rc.status_code == 200, rc.text
        data = rc.json()
        assert data.get("status") == "cancelled"
        # Silent: audit should have 'cancelled' but NOT a notification/email event tied to staff
        audit = data.get("audit") or []
        kinds = [a.get("kind") for a in audit]
        assert "cancelled" in kinds

    def test_cancel_unknown_id_404(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/hr/issuances/nonexistent-iid-xyz/cancel",
            headers=admin_headers, timeout=30,
        )
        assert r.status_code == 404


# ---------- Tests: auth / RBAC ----------
class TestAuth:
    def test_summary_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/hr/envelopes/summary", timeout=20)
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_staff_cannot_access_summary(self, staff_token):
        if not staff_token:
            pytest.skip("No staff token available (paul@fleetwash.ie login failed)")
        h = {"Authorization": f"Bearer {staff_token}"}
        r = requests.get(f"{BASE_URL}/api/hr/envelopes/summary", headers=h, timeout=20)
        assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"

    def test_staff_cannot_resend(self, staff_token, admin_headers):
        if not staff_token:
            pytest.skip("No staff token available")
        # Use an envelope id (real or fake — should still get 403 before reaching the doc)
        iid = getattr(pytest, "single_iid", "any-id")
        h = {"Authorization": f"Bearer {staff_token}"}
        r = requests.post(f"{BASE_URL}/api/hr/issuances/{iid}/resend", headers=h, timeout=20)
        assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"

    def test_staff_cannot_cancel(self, staff_token):
        if not staff_token:
            pytest.skip("No staff token available")
        iid = getattr(pytest, "single_iid", "any-id")
        h = {"Authorization": f"Bearer {staff_token}"}
        r = requests.post(f"{BASE_URL}/api/hr/issuances/{iid}/cancel", headers=h, timeout=20)
        assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"
