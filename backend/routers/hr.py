"""HR / DocuSign-replacement endpoints — staff HR profiles, document issuance,
signature capture with audit trail, expiry, and signed PDF download.

Mounted under /api/ via include_router in server.py.
"""
import base64
import io
import uuid
from datetime import datetime, date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deps import db, now_utc, serialize, get_current_user, require_admin, _validate_iso_date


router = APIRouter()


# ----------------- Models -----------------
class HRIssueIn(BaseModel):
    template_id: str  # references pdf_form_templates.id
    user_id: str
    expires_at: Optional[str] = None  # YYYY-MM-DD (optional)
    message: Optional[str] = None     # short note to staff


class HRUploadIssueIn(BaseModel):
    """Upload a PDF and issue an envelope to one or many staff members in one call (DocuSign-style)."""
    title: str
    user_id: Optional[str] = None     # legacy single-target (kept for backward compatibility)
    user_ids: Optional[List[str]] = None  # bulk send: list of staff ids; takes precedence over user_id
    pdf_base64: str
    expires_at: Optional[str] = None
    message: Optional[str] = None


class HRSignIn(BaseModel):
    signature_base64: str             # PNG data (no data: prefix needed; we accept both)
    printed_name: Optional[str] = None
    values: Optional[Dict[str, Any]] = None  # optional AcroForm field values to flatten in


# ----------------- Helpers -----------------
def _audit_event(kind: str, actor_id: Optional[str], actor_name: Optional[str], request: Optional[Request] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ip = ""
    ua = ""
    if request is not None:
        # Honour X-Forwarded-For first (Kubernetes ingress sets this)
        xff = request.headers.get("x-forwarded-for")
        ip = (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")) or ""
        ua = request.headers.get("user-agent", "")[:200]
    evt = {
        "kind": kind,
        "at": now_utc(),
        "actor_id": actor_id,
        "actor_name": actor_name,
        "ip": ip,
        "user_agent": ua,
    }
    if extra:
        evt.update(extra)
    return evt


async def _render_signed_pdf(template_id: str, signature_base64: str, printed_name: str, signed_at: datetime, values: Optional[Dict[str, Any]] = None) -> bytes:
    """Render a flattened signed PDF by overlaying signature image + name + date
    on the last page of the template's original PDF. Uses pypdf + reportlab.

    If `values` is provided, AcroForm fields are filled (and flattened) first.
    """
    tpl = await db.pdf_form_templates.find_one({"id": template_id})
    if not tpl or not tpl.get("pdf_base64"):
        raise HTTPException(status_code=404, detail="HR template not found")
    base_pdf = base64.b64decode(tpl["pdf_base64"])

    # Step 1: Optionally fill AcroForm fields using existing helper from server.py
    # We import lazily to avoid circular import at module load time.
    if values:
        try:
            from server import _fill_pdf  # type: ignore  # noqa: E402
            base_pdf = _fill_pdf(base_pdf, values, flatten=True)
        except Exception:
            # Fallback: continue with the unfilled PDF rather than fail the signature.
            pass

    # Step 2: Overlay signature image + printed name + signed-at date on last page
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader

    reader = PdfReader(io.BytesIO(base_pdf))
    last_idx = len(reader.pages) - 1
    last_page = reader.pages[last_idx]
    pw = float(last_page.mediabox.width)
    ph = float(last_page.mediabox.height)

    # Build a 1-page overlay matching the last page size
    overlay_buf = io.BytesIO()
    c = rl_canvas.Canvas(overlay_buf, pagesize=(pw, ph))

    # Decode signature image (strip optional data: prefix)
    sig_b64 = signature_base64
    if "," in sig_b64:
        sig_b64 = sig_b64.split(",", 1)[1]
    try:
        sig_bytes = base64.b64decode(sig_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature_base64")

    # Draw signature roughly bottom-right of last page
    sig_w = 180  # pt
    sig_h = 60   # pt
    margin = 36
    sig_x = pw - sig_w - margin
    sig_y = margin + 24  # leave room for caption beneath
    try:
        img = ImageReader(io.BytesIO(sig_bytes))
        c.drawImage(img, sig_x, sig_y, width=sig_w, height=sig_h, mask="auto")
    except Exception:
        # If image decode failed, skip image and just draw a line
        c.line(sig_x, sig_y + 30, sig_x + sig_w, sig_y + 30)

    # Caption: printed name + ISO date
    c.setFont("Helvetica", 8)
    c.setFillGray(0.25)
    name_line = (printed_name or "").strip() or "(signed)"
    date_line = signed_at.strftime("%Y-%m-%d %H:%M UTC")
    c.drawString(sig_x, sig_y - 10, f"Signed by: {name_line}")
    c.drawString(sig_x, sig_y - 20, f"Date: {date_line}")
    # Thin separator line above the signature
    c.line(sig_x, sig_y + sig_h + 4, sig_x + sig_w, sig_y + sig_h + 4)
    c.save()
    overlay_buf.seek(0)

    overlay_reader = PdfReader(overlay_buf)
    overlay_page = overlay_reader.pages[0]

    # Merge overlay onto last page
    last_page.merge_page(overlay_page)

    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ----------------- Issuance endpoints -----------------
@router.post("/hr/issue")
async def hr_issue(body: HRIssueIn, request: Request, current=Depends(require_admin)):
    """Admin issues a PDF document template to a staff member. Creates an
    `hr_issuances` doc with status='pending' and writes an audit 'issued' event."""
    tpl = await db.pdf_form_templates.find_one({"id": body.template_id})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    user = await db.users.find_one({"id": body.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _validate_iso_date(body.expires_at, "expires_at")

    iid = str(uuid.uuid4())
    doc = {
        "id": iid,
        "template_id": body.template_id,
        "template_title": tpl.get("title") or "Untitled",
        "user_id": body.user_id,
        "user_name": user.get("name") or "",
        "user_email": user.get("email") or "",
        "issued_by": current["id"],
        "issued_by_name": current.get("name") or "",
        "issued_at": now_utc(),
        "expires_at": body.expires_at or None,
        "message": body.message or "",
        "status": "pending",
        "read_at": None,
        "signed_at": None,
        "signature_image_base64": None,
        "signed_pdf_base64": None,
        "audit": [
            _audit_event(
                "issued",
                current["id"],
                current.get("name"),
                request,
                extra={"template_id": body.template_id, "expires_at": body.expires_at},
            )
        ],
    }
    await db.hr_issuances.insert_one(doc)
    # Best-effort push notification to the assigned staff member.
    try:
        tok = user.get("expo_push_token")
        if tok:
            from server import _send_expo_push  # lazy import to avoid circular at load time
            await _send_expo_push(
                [tok],
                "HR document to sign",
                f"{current.get('name') or 'Admin'} sent you: {tpl.get('title') or 'a document'}",
                data={"kind": "hr_issued", "issuance_id": iid},
            )
    except Exception:
        pass
    return serialize(doc)


@router.post("/hr/envelopes/upload-and-issue")
async def hr_upload_and_issue(body: HRUploadIssueIn, request: Request, current=Depends(require_admin)):
    """One-shot DocuSign-style flow: upload a PDF + create a hidden template + issue it to a staff
    member in a single call. Auto-issues so the staff member gets the envelope immediately.

    Stores the PDF as a `pdf_form_templates` row marked `category='hr_envelope'` so it doesn't
    pollute the staff-facing PDF Forms list while still being signable through the existing flow."""
    if not body.title or not body.title.strip():
        raise HTTPException(status_code=400, detail="Title required")
    user = await db.users.find_one({"id": body.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _validate_iso_date(body.expires_at, "expires_at")
    try:
        pdf_bytes = base64.b64decode(body.pdf_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid PDF base64")
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Not a valid PDF")

    # Create the hidden template row
    tpl_id = str(uuid.uuid4())
    tpl_doc = {
        "id": tpl_id,
        "title": body.title.strip(),
        "category": "hr_envelope",  # hidden from staff PDF Forms tab
        "pdf_base64": body.pdf_base64,
        "size": len(pdf_bytes),
        "fields": [],
        "field_count": 0,
        "assigned_user_ids": [body.user_id],
        "created_by": current["id"],
        "created_by_name": current.get("name"),
        "created_at": now_utc(),
    }
    await db.pdf_form_templates.insert_one(tpl_doc)

    # Issue immediately
    iid = str(uuid.uuid4())
    iss_doc = {
        "id": iid,
        "template_id": tpl_id,
        "template_title": body.title.strip(),
        "user_id": body.user_id,
        "user_name": user.get("name") or "",
        "user_email": user.get("email") or "",
        "issued_by": current["id"],
        "issued_by_name": current.get("name") or "",
        "issued_at": now_utc(),
        "expires_at": body.expires_at or None,
        "message": body.message or "",
        "status": "pending",
        "read_at": None,
        "signed_at": None,
        "signature_image_base64": None,
        "signed_pdf_base64": None,
        "audit": [
            _audit_event(
                "issued",
                current["id"],
                current.get("name"),
                request,
                extra={"template_id": tpl_id, "expires_at": body.expires_at, "uploaded_inline": True},
            )
        ],
    }
    await db.hr_issuances.insert_one(iss_doc)

    # In-app notification for the staff member (powers the bell on their Home tab)
    try:
        from server import notify
        await notify(
            user_id=body.user_id,
            title=f"Envelope to sign: {body.title.strip()}",
            body=f"{current.get('name') or 'Admin'} sent you a document. Tap to read and sign.",
            kind="hr_envelope",
            related_id=iid,
        )
    except Exception:
        pass

    # Best-effort push to staff member
    try:
        tok = user.get("expo_push_token")
        if tok:
            from server import _send_expo_push
            await _send_expo_push(
                [tok],
                "HR envelope to sign",
                f"{current.get('name') or 'Admin'} sent you: {body.title.strip()}",
                data={"kind": "hr_issued", "issuance_id": iid},
            )
    except Exception:
        pass
    # Best-effort email to staff member — deep-link straight to the envelope + ATTACH the full PDF
    # (legal copy: staff receive the contract as a real PDF, signed copy goes to admin after signature)
    try:
        from server import _send_smtp_email
        if user.get("email"):
            deep_link = f"https://staff-scheduler-152.preview.emergentagent.com/forms?envelope={iid}"
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in body.title.strip())[:60]
            attach_name = f"{safe}.pdf"
            _send_smtp_email(
                to_emails=[user["email"]],
                subject=f"[StaffHub] Envelope to sign: {body.title.strip()}",
                body_text=(
                    f"Hi {user.get('name') or ''},\n\n"
                    f"{current.get('name') or 'Admin'} sent you an envelope to sign: "
                    f"{body.title.strip()}\n\n"
                    f"The full document is attached to this email for your records.\n\n"
                    f"{('Note: ' + body.message) if body.message else ''}\n\n"
                    f"To sign electronically, open this link (log in first, it'll take you straight to the document):\n"
                    f"{deep_link}\n\n"
                    f"Or open StaffHub manually and go to:\n"
                    f"  Forms tab → Envelopes sub-tab\n"
                    f"  https://staff-scheduler-152.preview.emergentagent.com"
                ),
                attachment_bytes=pdf_bytes,
                attachment_filename=attach_name,
            )
    except Exception:
        pass

    return serialize(iss_doc)


@router.get("/hr/issuances")
async def hr_list_issuances(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    template_id: Optional[str] = None,
    current=Depends(get_current_user),
):
    """List HR issuances. Staff only see their own. Admin sees all (filterable)."""
    q: Dict[str, Any] = {}
    if current.get("role") != "admin":
        q["user_id"] = current["id"]
    elif user_id:
        q["user_id"] = user_id
    if status:
        q["status"] = status
    if template_id:
        q["template_id"] = template_id
    docs = await db.hr_issuances.find(q).sort("issued_at", -1).to_list(1000)
    # Strip large fields from list response
    out = []
    for d in docs:
        ser = serialize(d)
        ser.pop("signed_pdf_base64", None)
        ser.pop("signature_image_base64", None)
        ser["has_signed_pdf"] = bool(d.get("signed_pdf_base64"))
        out.append(ser)
    return out


@router.get("/hr/issuances/{iid}")
async def hr_get_issuance(iid: str, current=Depends(get_current_user)):
    doc = await db.hr_issuances.find_one({"id": iid})
    if not doc:
        raise HTTPException(status_code=404, detail="Issuance not found")
    if current.get("role") != "admin" and doc.get("user_id") != current["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    ser = serialize(doc)
    # Always return signed image / pdf flag, but only embed the pdf if signed (small enough)
    ser["has_signed_pdf"] = bool(doc.get("signed_pdf_base64"))
    return ser


@router.post("/hr/issuances/{iid}/read")
async def hr_mark_read(iid: str, request: Request, current=Depends(get_current_user)):
    """Staff confirms they have read the document. Idempotent — re-marking doesn't
    add another audit event."""
    doc = await db.hr_issuances.find_one({"id": iid})
    if not doc:
        raise HTTPException(status_code=404, detail="Issuance not found")
    if doc.get("user_id") != current["id"] and current.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if doc.get("status") in ("signed", "cancelled"):
        return serialize(doc)  # no-op once signed/cancelled
    updates: Dict[str, Any] = {}
    if not doc.get("read_at"):
        updates["read_at"] = now_utc()
        if doc.get("status") == "pending":
            updates["status"] = "read"
    if updates:
        ev = _audit_event("read", current["id"], current.get("name"), request)
        await db.hr_issuances.update_one(
            {"id": iid}, {"$set": updates, "$push": {"audit": ev}}
        )
        # Notify admin(s) that staff has READ the envelope
        try:
            from server import create_admin_notifications, _form_recipient_emails, _send_smtp_email
            ts = updates["read_at"].strftime("%Y-%m-%d %H:%M UTC")
            title = doc.get("template_title") or "HR document"
            await create_admin_notifications(
                kind="hr_read",
                title=f"Envelope read: {title}",
                body=f"{current.get('name','Unknown')} opened the envelope at {ts}",
                related_id=iid,
            )
            emails = await _form_recipient_emails()
            if emails:
                _send_smtp_email(
                    to_emails=emails,
                    subject=f"[StaffHub] Envelope read — {title}",
                    body_text=(
                        f"{current.get('name','Unknown')} ({current.get('email','')})\n"
                        f"opened envelope: {title}\n"
                        f"at {ts} from IP {ev.get('ip') or 'unknown'}\n\n"
                        f"You'll receive a second email with the signed PDF attached when they sign."
                    ),
                )
        except Exception:
            pass
    updated = await db.hr_issuances.find_one({"id": iid})
    ser = serialize(updated)
    ser["has_signed_pdf"] = bool(updated.get("signed_pdf_base64"))
    return ser


@router.post("/hr/issuances/{iid}/sign")
async def hr_sign(iid: str, body: HRSignIn, request: Request, current=Depends(get_current_user)):
    """Staff submits their drawn signature. Server renders the signed PDF with the
    signature + printed name + ISO date overlaid on the last page, and writes a
    'signed' audit event capturing IP + user agent."""
    doc = await db.hr_issuances.find_one({"id": iid})
    if not doc:
        raise HTTPException(status_code=404, detail="Issuance not found")
    if doc.get("user_id") != current["id"]:
        raise HTTPException(status_code=403, detail="Only the assigned user may sign")
    if doc.get("status") == "signed":
        raise HTTPException(status_code=400, detail="Already signed")
    if doc.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Issuance has been cancelled")
    if not body.signature_base64:
        raise HTTPException(status_code=400, detail="signature_base64 is required")

    signed_at = now_utc()
    printed = (body.printed_name or current.get("name") or "").strip()
    try:
        signed_pdf_bytes = await _render_signed_pdf(
            template_id=doc["template_id"],
            signature_base64=body.signature_base64,
            printed_name=printed,
            signed_at=signed_at,
            values=body.values,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render signed PDF: {e}")
    signed_pdf_b64 = base64.b64encode(signed_pdf_bytes).decode("ascii")

    # Audit event with IP + UA
    ev = _audit_event(
        "signed",
        current["id"],
        current.get("name"),
        request,
        extra={"printed_name": printed},
    )

    updates = {
        "status": "signed",
        "signed_at": signed_at,
        "signature_image_base64": body.signature_base64,
        "signed_pdf_base64": signed_pdf_b64,
        "signature_ip": ev["ip"],
        "signature_user_agent": ev["user_agent"],
        "printed_name": printed,
    }
    # If they hadn't marked read yet, infer read at sign-time
    if not doc.get("read_at"):
        updates["read_at"] = signed_at

    await db.hr_issuances.update_one(
        {"id": iid}, {"$set": updates, "$push": {"audit": ev}}
    )

    # Notify admin(s) + email signed PDF as attachment (DocuSign-style completion)
    try:
        from server import create_admin_notifications, _form_recipient_emails, _send_smtp_email
        ts = signed_at.strftime("%Y-%m-%d %H:%M UTC")
        title = doc.get("template_title") or "HR document"
        await create_admin_notifications(
            kind="hr_signed",
            title=f"Envelope signed: {title}",
            body=f"{current.get('name','Unknown')} signed the envelope at {ts}",
            related_id=iid,
        )
        emails = await _form_recipient_emails()
        if emails:
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:60]
            attach_name = f"{safe}_{(printed or current.get('name','user')).replace(' ','_')}_{signed_at.strftime('%Y%m%d-%H%M')}.pdf"
            _send_smtp_email(
                to_emails=emails,
                subject=f"[StaffHub] Envelope signed — {title} — {printed or current.get('name','')}",
                body_text=(
                    f"Envelope signed.\n\n"
                    f"Document: {title}\n"
                    f"Signed by: {printed or current.get('name','')} <{current.get('email','')}>\n"
                    f"Signed at: {ts}\n"
                    f"IP: {ev.get('ip') or 'unknown'}\n\n"
                    f"The signed PDF is attached."
                ),
                attachment_bytes=signed_pdf_bytes,
                attachment_filename=attach_name,
            )
        # Also email a copy of the signed PDF to the staff member who signed
        # (both parties retain a legal copy — standard contract practice)
        if current.get("email"):
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:60]
            staff_attach_name = f"{safe}_signed.pdf"
            _send_smtp_email(
                to_emails=[current["email"]],
                subject=f"[StaffHub] Your signed copy: {title}",
                body_text=(
                    f"Hi {current.get('name', '')},\n\n"
                    f"You signed: {title}\n"
                    f"Signed at: {ts}\n\n"
                    f"Your signed PDF is attached for your records.\n\n"
                    f"A copy has also been delivered to your admin team.\n\n"
                    f"— StaffHub"
                ),
                attachment_bytes=signed_pdf_bytes,
                attachment_filename=staff_attach_name,
            )
    except Exception:
        pass

    updated = await db.hr_issuances.find_one({"id": iid})
    ser = serialize(updated)
    ser["has_signed_pdf"] = True
    # Don't return the huge signed_pdf_base64 in the response — caller can /pdf it
    ser.pop("signed_pdf_base64", None)
    return ser


@router.post("/hr/issuances/{iid}/cancel")
async def hr_cancel(iid: str, request: Request, current=Depends(require_admin)):
    doc = await db.hr_issuances.find_one({"id": iid})
    if not doc:
        raise HTTPException(status_code=404, detail="Issuance not found")
    if doc.get("status") == "signed":
        raise HTTPException(status_code=400, detail="Cannot cancel a signed document")
    ev = _audit_event("cancelled", current["id"], current.get("name"), request)
    await db.hr_issuances.update_one(
        {"id": iid},
        {"$set": {"status": "cancelled"}, "$push": {"audit": ev}},
    )
    updated = await db.hr_issuances.find_one({"id": iid})
    return serialize(updated)


@router.get("/hr/issuances/{iid}/pdf")
async def hr_download_signed_pdf(iid: str, current=Depends(get_current_user)):
    """Download the signed PDF — admin can always download, signer can download their own."""
    doc = await db.hr_issuances.find_one({"id": iid})
    if not doc:
        raise HTTPException(status_code=404, detail="Issuance not found")
    if current.get("role") != "admin" and doc.get("user_id") != current["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    b64 = doc.get("signed_pdf_base64")
    if not b64:
        raise HTTPException(status_code=400, detail="Document is not yet signed")
    try:
        pdf_bytes = base64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=500, detail="Stored PDF is corrupted")
    safe_title = (doc.get("template_title") or "document").replace("/", "_")
    safe_user = (doc.get("user_name") or "user").replace("/", "_")
    filename = f"{safe_title}_{safe_user}_signed.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------- HR staff directory -----------------
@router.get("/hr/staff")
async def hr_staff_directory(_=Depends(require_admin)):
    """Returns an alphabetical list of staff users with summary counts of HR docs."""
    users = await db.users.find({"deactivated": {"$ne": True}}).sort("name", 1).to_list(1000)
    out = []
    for u in users:
        if u.get("role") == "admin":
            continue
        # Count by status
        counts = {"pending": 0, "read": 0, "signed": 0, "expired": 0, "cancelled": 0}
        cursor = db.hr_issuances.find({"user_id": u["id"]})
        async for i in cursor:
            st = i.get("status") or "pending"
            counts[st] = counts.get(st, 0) + 1
        u.pop("password_hash", None)
        ser = serialize(u)
        ser["hr_counts"] = counts
        ser["hr_total"] = sum(counts.values())
        ser["hr_pending_signature"] = counts.get("pending", 0) + counts.get("read", 0)
        out.append(ser)
    return out


@router.get("/hr/staff/{uid}/profile")
async def hr_staff_profile(uid: str, _=Depends(require_admin)):
    """Full HR profile for a single staff member: personal details + holiday/sick
    summary + all HR issuances. Used by the admin HR profile drawer."""
    user = await db.users.find_one({"id": uid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Holiday balance: reuse the same calc logic by querying directly
    today_year = datetime.utcnow().year
    used_days = 0
    cursor = db.holiday_requests.find(
        {"user_id": uid, "status": "approved", "type": "annual"}
    )
    async for r in cursor:
        try:
            s = datetime.fromisoformat(r["start_date"]).date()
            e = datetime.fromisoformat(r["end_date"]).date()
            # Only count days in current year
            if s.year == today_year:
                used_days += (e - s).days + 1
        except Exception:
            continue
    pending_days = 0
    pending_cursor = db.holiday_requests.find(
        {"user_id": uid, "status": "pending"}
    )
    async for r in pending_cursor:
        try:
            s = datetime.fromisoformat(r["start_date"]).date()
            e = datetime.fromisoformat(r["end_date"]).date()
            pending_days += (e - s).days + 1
        except Exception:
            continue
    entitlement = user.get("holiday_entitlement", 20)
    # Sick eligibility — simply expose start_date + eligibility flag computed
    # (the canonical /users/{id}/eligibility endpoint already exists for live use)
    # Issuances
    issuances = []
    icursor = db.hr_issuances.find({"user_id": uid}).sort("issued_at", -1)
    async for i in icursor:
        ser = serialize(i)
        ser.pop("signed_pdf_base64", None)
        ser.pop("signature_image_base64", None)
        ser["has_signed_pdf"] = bool(i.get("signed_pdf_base64"))
        issuances.append(ser)
    return {
        "user": serialize(user),
        "holiday": {
            "entitlement": entitlement,
            "used_days": used_days,
            "pending_days": pending_days,
            "remaining": max(0, entitlement - used_days - pending_days),
        },
        "issuances": issuances,
    }


# ----------------- Expiry sweep (called by existing /admin/scan-alerts cron OR manually) -----------------
@router.post("/hr/sweep-expiry")
async def hr_sweep_expiry(_=Depends(require_admin)):
    """Marks any pending/read issuance whose `expires_at` is in the past as
    `expired`. Returns count of newly expired docs."""
    today = date.today().isoformat()
    cursor = db.hr_issuances.find(
        {
            "status": {"$in": ["pending", "read"]},
            "expires_at": {"$ne": None, "$lt": today},
        }
    )
    n = 0
    async for d in cursor:
        await db.hr_issuances.update_one(
            {"id": d["id"]},
            {
                "$set": {"status": "expired"},
                "$push": {
                    "audit": {
                        "kind": "expired",
                        "at": now_utc(),
                        "actor_id": None,
                        "actor_name": "system",
                        "ip": "",
                        "user_agent": "",
                    }
                },
            },
        )
        n += 1
    return {"expired": n}
