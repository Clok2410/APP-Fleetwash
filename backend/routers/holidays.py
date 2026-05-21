"""Holiday requests, balance computation, and bank-holiday endpoints.

Extracted from server.py — mounted under /api/ via include_router.
Uses lazy imports from `server` for helpers (notify, _entry_seconds, _accrual_hours,
_seed_ireland_bank_holidays) to avoid circular imports at module load time.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import db, now_utc, serialize, get_current_user, require_admin, _validate_iso_date


router = APIRouter()


# ----------------- Models -----------------
class HolidayRequestIn(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str
    reason: Optional[str] = None
    type: str = "annual"  # annual | sick | unpaid


class HolidayEditIn(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    reason: Optional[str] = None
    type: Optional[str] = None  # 'annual'|'sick'|'unpaid'


class BankHolidayIn(BaseModel):
    date: str  # YYYY-MM-DD
    name: str
    hours: float = 8.0  # default 8 hours per bank holiday


# ----------------- Bank holidays -----------------
@router.get("/bank-holidays")
async def list_bank_holidays(year: Optional[int] = None, _=Depends(get_current_user)):
    # Seed IE bank holidays the first time anyone calls this
    try:
        from server import _seed_ireland_bank_holidays  # type: ignore  # noqa: E402
        await _seed_ireland_bank_holidays()
    except Exception:
        pass
    q: Dict[str, Any] = {}
    if year:
        q["date"] = {"$gte": f"{year}-01-01", "$lt": f"{year + 1}-01-01"}
    docs = await db.bank_holidays.find(q).sort("date", 1).to_list(500)
    return [serialize(d) for d in docs]


@router.post("/bank-holidays")
async def add_bank_holiday(body: BankHolidayIn, _=Depends(require_admin)):
    try:
        datetime.fromisoformat(body.date)
    except Exception:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    existing = await db.bank_holidays.find_one({"date": body.date})
    if existing:
        raise HTTPException(status_code=400, detail="Bank holiday already exists on that date")
    doc = {
        "id": str(uuid.uuid4()),
        "date": body.date,
        "name": body.name,
        "hours": float(body.hours or 8.0),
        "country": "IE",
        "custom": True,
        "created_at": now_utc(),
    }
    await db.bank_holidays.insert_one(doc)
    return serialize(doc)


@router.delete("/bank-holidays/{bid}")
async def delete_bank_holiday(bid: str, _=Depends(require_admin)):
    res = await db.bank_holidays.delete_one({"id": bid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bank holiday not found")
    return {"ok": True}


# ----------------- Holiday requests / balance -----------------
@router.get("/holidays/balance")
async def holiday_balance(current=Depends(get_current_user)):
    user = await db.users.find_one({"id": current["id"]})
    entitlement = (user or {}).get("holiday_entitlement", 25)
    used_cursor = db.holiday_requests.find({"user_id": current["id"], "status": "approved"})
    used_days = 0
    async for r in used_cursor:
        try:
            s = datetime.fromisoformat(r["start_date"]).date()
            e = datetime.fromisoformat(r["end_date"]).date()
            used_days += (e - s).days + 1
        except Exception:
            continue
    pending_cursor = db.holiday_requests.find({"user_id": current["id"], "status": "pending"})
    pending_days = 0
    async for r in pending_cursor:
        try:
            s = datetime.fromisoformat(r["start_date"]).date()
            e = datetime.fromisoformat(r["end_date"]).date()
            pending_days += (e - s).days + 1
        except Exception:
            continue
    # Accrued hours from clock entries YTD (informational)
    year = datetime.utcnow().year
    start_y = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_y = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    entries = await db.clock_entries.find(
        {"user_id": current["id"], "clock_in": {"$gte": start_y, "$lt": end_y}}
    ).to_list(5000)
    total_secs = 0
    accr: Dict[str, Any] = {"accrued_holiday_hours": 0.0, "net_hours": 0.0}
    try:
        from server import _entry_seconds, _accrual_hours  # type: ignore  # noqa: E402
        for e in entries:
            total_secs += _entry_seconds(e, cap_to=end_y)
        accr = _accrual_hours(total_secs)
    except Exception:
        pass
    bh_count = await db.bank_holidays.count_documents(
        {"date": {"$gte": f"{year}-01-01", "$lt": f"{year + 1}-01-01"}}
    )
    remaining = entitlement - used_days - pending_days
    return {
        "entitlement": entitlement,
        "used": used_days,
        "pending": pending_days,
        "remaining": remaining,
        "in_deficit": remaining < 0,
        "accrued_holiday_hours": accr.get("accrued_holiday_hours", 0.0),
        "net_hours_ytd": accr.get("net_hours", 0.0),
        "bank_holiday_count": bh_count,
        "bank_holiday_hours_value": bh_count * 8,
    }


@router.post("/holidays/requests")
async def create_holiday_request(body: HolidayRequestIn, current=Depends(get_current_user)):
    try:
        s = datetime.fromisoformat(body.start_date).date()
        e = datetime.fromisoformat(body.end_date).date()
        days = (e - s).days + 1
    except Exception:
        days = 0
    req = {
        "id": str(uuid.uuid4()),
        "user_id": current["id"],
        "user_name": current["name"],
        "start_date": body.start_date,
        "end_date": body.end_date,
        "reason": body.reason,
        "type": body.type,
        "days": days,
        "status": "pending",
        "created_at": now_utc(),
    }
    await db.holiday_requests.insert_one(req)
    return serialize(req)


@router.get("/holidays/requests")
async def list_holiday_requests(current=Depends(get_current_user), all: bool = False):
    if all and current.get("role") == "admin":
        docs = await db.holiday_requests.find().sort("created_at", -1).to_list(500)
    else:
        docs = await db.holiday_requests.find({"user_id": current["id"]}).sort("created_at", -1).to_list(500)
    return [serialize(d) for d in docs]


@router.patch("/holidays/requests/{rid}")
async def edit_holiday_request(rid: str, body: HolidayEditIn, current=Depends(get_current_user)):
    """Edit dates/reason/type. Staff can edit ONLY their own pending. Admin can edit any."""
    h = await db.holiday_requests.find_one({"id": rid})
    if not h:
        raise HTTPException(status_code=404, detail="Request not found")
    is_admin = current.get("role") == "admin"
    if not is_admin:
        if h.get("user_id") != current["id"]:
            raise HTTPException(status_code=403, detail="Cannot edit another staff member's request")
        if h.get("status") != "pending":
            raise HTTPException(status_code=400, detail="Only pending requests can be edited by staff")
    updates: Dict[str, Any] = {}
    if body.start_date is not None:
        _validate_iso_date(body.start_date, "start_date")
        updates["start_date"] = body.start_date
    if body.end_date is not None:
        _validate_iso_date(body.end_date, "end_date")
        updates["end_date"] = body.end_date
    if body.reason is not None:
        updates["reason"] = body.reason
    if body.type is not None:
        if body.type not in ("annual", "sick", "unpaid"):
            raise HTTPException(status_code=400, detail="type must be 'annual'|'sick'|'unpaid'")
        updates["type"] = body.type
    if updates:
        s_raw = updates.get("start_date", h.get("start_date"))
        e_raw = updates.get("end_date", h.get("end_date"))
        try:
            s = datetime.fromisoformat(s_raw).date()
            e = datetime.fromisoformat(e_raw).date()
            if e < s:
                raise HTTPException(status_code=400, detail="end_date cannot be before start_date")
            updates["days"] = (e - s).days + 1
        except HTTPException:
            raise
        except Exception:
            pass
        updates["edited_at"] = now_utc()
        updates["edited_by"] = "admin" if is_admin else "self"
        updates["edited_by_name"] = current.get("name")
        await db.holiday_requests.update_one({"id": rid}, {"$set": updates})
    doc = await db.holiday_requests.find_one({"id": rid})
    return serialize(doc)


@router.post("/holidays/requests/{rid}/decision")
async def decide_holiday(rid: str, decision: str, _=Depends(require_admin)):
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid decision")
    res = await db.holiday_requests.update_one(
        {"id": rid}, {"$set": {"status": decision, "decided_at": now_utc()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    h = await db.holiday_requests.find_one({"id": rid})
    if h:
        try:
            from server import notify  # type: ignore  # noqa: E402
            await notify(
                h["user_id"],
                f"Holiday {decision}",
                f"{h.get('start_date', '')} → {h.get('end_date', '')}",
                "holiday",
                rid,
            )
        except Exception:
            pass
    return {"ok": True}


@router.post("/holidays/requests/{rid}/cancel")
async def cancel_holiday(rid: str, current=Depends(get_current_user)):
    """Cancel a holiday request. Staff can cancel their own (any state). Admin can
    cancel anyone's. Days are refunded automatically (cancelled excluded from balance)."""
    h = await db.holiday_requests.find_one({"id": rid})
    if not h:
        raise HTTPException(status_code=404, detail="Request not found")
    if current.get("role") != "admin" and h.get("user_id") != current["id"]:
        raise HTTPException(status_code=403, detail="Cannot cancel another staff member's request")
    if h.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Request already cancelled")
    if h.get("status") == "rejected":
        raise HTTPException(status_code=400, detail="Cannot cancel a rejected request")
    cancelled_by = "admin" if current.get("role") == "admin" else "self"
    await db.holiday_requests.update_one(
        {"id": rid},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": now_utc(),
            "cancelled_by": cancelled_by,
            "cancelled_by_name": current.get("name"),
        }},
    )
    if cancelled_by == "admin" and h.get("user_id") != current["id"]:
        try:
            from server import notify  # type: ignore  # noqa: E402
            await notify(
                h["user_id"],
                "Holiday cancelled",
                f"{h.get('start_date', '')} → {h.get('end_date', '')} cancelled by admin",
                "holiday",
                rid,
            )
        except Exception:
            pass
    doc = await db.holiday_requests.find_one({"id": rid})
    return serialize(doc)
