from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import uuid
import bcrypt
import jwt
import asyncio
import logging
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional, Any, Dict

from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId

# ----------------- DB -----------------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_ALGORITHM = "HS256"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("staff-app")

# ----------------- Helpers -----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": now_utc() + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def serialize(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(doc.items()):
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, datetime):
            # Motor returns naive datetimes (no tzinfo) — they're stored as UTC by us via
            # now_utc(). Treat naive datetimes as UTC so JSON output always includes a tz
            # marker; without this JS parses "2026-05-11T14:00:00" as LOCAL time and shows
            # a 1-hour offset (e.g. on the clock-in timer in BST/IST).
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            doc[k] = v.isoformat()
    return doc


# ----------------- Auth dep -----------------
async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user.pop("password_hash", None)
    return serialize(user)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ----------------- Models -----------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "staff"  # staff | admin


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdateIn(BaseModel):
    """Fields a staff member can edit on their own profile."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    dob: Optional[str] = None  # YYYY-MM-DD
    pps_number: Optional[str] = None  # Irish PPS / national ID


class AdminUserUpdateIn(BaseModel):
    """Fields an admin can edit on any user's profile (in addition to their own)."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    pps_number: Optional[str] = None
    start_date: Optional[str] = None  # YYYY-MM-DD employment start
    employment_type: Optional[str] = None  # 'full_time' | 'part_time'
    holiday_entitlement: Optional[int] = None
    role: Optional[str] = None  # 'staff' | 'admin'


class ClockNoteIn(BaseModel):
    note: Optional[str] = None
    location: Optional[str] = None


class HolidayRequestIn(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str
    reason: Optional[str] = None
    type: str = "annual"  # annual | sick | unpaid


class ShiftIn(BaseModel):
    user_id: str
    title: str
    location: Optional[str] = None
    start: str  # ISO datetime
    end: str
    notes: Optional[str] = None
    recurring: Optional[str] = None  # daily|weekly|none
    repeat_count: Optional[int] = 1  # how many shifts to generate (incl. first)
    customer_id: Optional[str] = None
    site_id: Optional[str] = None


class SwapRequestIn(BaseModel):
    target_user_id: str
    reason: Optional[str] = None


class AvailabilityIn(BaseModel):
    date: str  # YYYY-MM-DD
    available: bool
    note: Optional[str] = None


class FolderIn(BaseModel):
    name: str
    parent_id: Optional[str] = None


class FileIn(BaseModel):
    name: str
    folder_id: Optional[str] = None
    mime_type: str
    data_base64: str  # base64 file content
    size: Optional[int] = None


class FormFieldIn(BaseModel):
    key: str
    label: str
    type: str  # text|textarea|date|checkbox|signature|select|number
    required: bool = False
    options: Optional[List[str]] = None


class ChecklistItemIn(BaseModel):
    id: str  # e.g. "HL29"
    label: str  # e.g. "HL 29"
    sub_keys: List[str]  # e.g. ["EXT", "INT"]


class FormTemplateIn(BaseModel):
    title: str
    description: Optional[str] = None
    fields: List[FormFieldIn] = []
    kind: str = "form"  # "form" | "checklist"
    checklist_items: Optional[List[ChecklistItemIn]] = None
    target_percent: Optional[float] = None  # e.g. 100.0 means all items must be done
    depot_id: Optional[str] = None  # optional: tie checklist to a depot
    assigned_user_ids: Optional[List[str]] = None  # empty/None = visible to ALL staff (back-compat)


class FormSubmissionIn(BaseModel):
    template_id: str
    values: Dict[str, Any]


class DepotIn(BaseModel):
    name: str
    lat: float
    lng: float
    radius_m: float = 200.0


class ClockNoteInGeo(BaseModel):
    note: Optional[str] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    depot_id: Optional[str] = None
    shift_id: Optional[str] = None  # optional: link clock-in to a scheduled shift


class ClockEntryPatchIn(BaseModel):
    clock_in: Optional[str] = None  # ISO 8601
    clock_out: Optional[str] = None  # ISO 8601
    note: Optional[str] = None
    location: Optional[str] = None


class BankHolidayIn(BaseModel):
    date: str  # YYYY-MM-DD
    name: str
    hours: float = 8.0  # default 8 hours per bank holiday


class ContactIn(BaseModel):
    name: str
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class SiteIn(BaseModel):
    name: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    radius_m: Optional[float] = 200.0
    description: Optional[str] = None


class CustomerIn(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class CustomerNoteIn(BaseModel):
    body: str
    category: str = "general"  # general | access | hazard | equipment | other
    pinned: bool = False


class PdfFormTemplateIn(BaseModel):
    title: str
    description: Optional[str] = None
    pdf_base64: str  # full PDF as base64
    assigned_user_ids: Optional[List[str]] = None  # empty/None = visible to ALL staff (back-compat)


class TemplateAssignIn(BaseModel):
    assigned_user_ids: List[str] = []  # empty list = visible to ALL staff


class PdfFormSubmissionIn(BaseModel):
    values: Dict[str, Any]
    flatten: bool = True  # flatten fields into static text after filling


class PdfSessionStartIn(BaseModel):
    name: Optional[str] = None


class PdfSessionPatchIn(BaseModel):
    values: Dict[str, Any]


# ----------------- App init -----------------
app = FastAPI(title="StaffHub API")
api = APIRouter(prefix="/api")


# ----------------- Auth endpoints -----------------
@api.post("/auth/register")
async def register(body: RegisterIn, current=Depends(require_admin)):
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": body.name,
        "role": body.role if body.role in ("staff", "admin") else "staff",
        "password_hash": hash_password(body.password),
        "holiday_entitlement": 25,
        "created_at": now_utc(),
        "active": True,
    }
    await db.users.insert_one(user)
    user.pop("password_hash", None)
    return serialize(user)


@api.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account deactivated")
    token = create_access_token(user["id"], user["email"], user.get("role", "staff"))
    user.pop("password_hash", None)
    return {"access_token": token, "token_type": "bearer", "user": serialize(user)}


@api.get("/auth/me")
async def me(current=Depends(get_current_user)):
    return current


# ----------------- Users -----------------
@api.get("/users")
async def list_users(current=Depends(get_current_user)):
    docs = await db.users.find({}, {"password_hash": 0}).to_list(1000)
    return [serialize(d) for d in docs]


@api.patch("/users/{user_id}/deactivate")
async def deactivate_user(user_id: str, _=Depends(require_admin)):
    await db.users.update_one({"id": user_id}, {"$set": {"active": False}})
    return {"ok": True}


@api.patch("/users/{user_id}/entitlement")
async def update_entitlement(user_id: str, value: int, _=Depends(require_admin)):
    if value < 0 or value > 365:
        raise HTTPException(status_code=400, detail="Entitlement must be 0–365 days")
    res = await db.users.update_one({"id": user_id}, {"$set": {"holiday_entitlement": int(value)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "holiday_entitlement": int(value)}


def _validate_iso_date(s: Optional[str], field: str) -> Optional[str]:
    if s is None or s == "":
        return s
    try:
        datetime.fromisoformat(s)
        return s
    except Exception:
        raise HTTPException(status_code=400, detail=f"{field} must be YYYY-MM-DD")


@api.patch("/users/me/profile")
async def update_my_profile(body: ProfileUpdateIn, current=Depends(get_current_user)):
    """Staff edits their own profile: name, email, phone, dob, pps_number."""
    updates: Dict[str, Any] = {}
    if body.name is not None and body.name.strip():
        updates["name"] = body.name.strip()
    if body.email is not None:
        new_email = body.email.lower().strip()
        if new_email != current.get("email"):
            existing = await db.users.find_one({"email": new_email})
            if existing:
                raise HTTPException(status_code=400, detail="Email already in use")
            updates["email"] = new_email
    if body.phone is not None:
        updates["phone"] = body.phone.strip() or None
    if body.dob is not None:
        _validate_iso_date(body.dob, "dob")
        updates["dob"] = body.dob or None
    if body.pps_number is not None:
        updates["pps_number"] = body.pps_number.strip() or None
    if not updates:
        return serialize(current)
    updates["profile_updated_at"] = now_utc()
    await db.users.update_one({"id": current["id"]}, {"$set": updates})
    doc = await db.users.find_one({"id": current["id"]}, {"password_hash": 0})
    return serialize(doc)


@api.patch("/users/{user_id}")
async def admin_update_user(user_id: str, body: AdminUserUpdateIn, _=Depends(require_admin)):
    """Admin updates any user's profile incl. start_date, employment_type, entitlement, role."""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    updates: Dict[str, Any] = {}
    if body.name is not None and body.name.strip():
        updates["name"] = body.name.strip()
    if body.email is not None:
        new_email = body.email.lower().strip()
        if new_email != user.get("email"):
            existing = await db.users.find_one({"email": new_email})
            if existing:
                raise HTTPException(status_code=400, detail="Email already in use")
            updates["email"] = new_email
    if body.phone is not None:
        updates["phone"] = body.phone.strip() or None
    if body.dob is not None:
        _validate_iso_date(body.dob, "dob")
        updates["dob"] = body.dob or None
    if body.pps_number is not None:
        updates["pps_number"] = body.pps_number.strip() or None
    if body.start_date is not None:
        _validate_iso_date(body.start_date, "start_date")
        updates["start_date"] = body.start_date or None
    if body.employment_type is not None:
        if body.employment_type not in ("full_time", "part_time"):
            raise HTTPException(status_code=400, detail="employment_type must be 'full_time' or 'part_time'")
        updates["employment_type"] = body.employment_type
    if body.holiday_entitlement is not None:
        if body.holiday_entitlement < 0 or body.holiday_entitlement > 365:
            raise HTTPException(status_code=400, detail="holiday_entitlement must be 0–365")
        updates["holiday_entitlement"] = int(body.holiday_entitlement)
    if body.role is not None:
        if body.role not in ("staff", "admin"):
            raise HTTPException(status_code=400, detail="role must be 'staff' or 'admin'")
        updates["role"] = body.role
    if not updates:
        u2 = await db.users.find_one({"id": user_id}, {"password_hash": 0})
        return serialize(u2)
    updates["profile_updated_at"] = now_utc()
    await db.users.update_one({"id": user_id}, {"$set": updates})
    doc = await db.users.find_one({"id": user_id}, {"password_hash": 0})
    return serialize(doc)


@api.get("/users/me/eligibility")
async def my_eligibility(current=Depends(get_current_user)):
    """Compute sick-pay and bank-holiday eligibility for the current user.

    Sick Pay (Ireland Statutory Sick Pay): requires 13 continuous weeks of employment
    based on the user's start_date.
    Bank Holiday: full_time users are immediately eligible; part_time users must have
    worked at least 40 hours in the previous 5 weeks (using clock_entries).
    """
    return await _eligibility_for_user(current)


@api.get("/users/{user_id}/eligibility")
async def admin_get_eligibility(user_id: str, _=Depends(require_admin)):
    user = await db.users.find_one({"id": user_id}, {"password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await _eligibility_for_user(user)


async def _eligibility_for_user(user: Dict[str, Any]) -> Dict[str, Any]:
    today_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    employment_type = user.get("employment_type") or "full_time"
    start_date_raw = user.get("start_date")
    weeks_employed: Optional[float] = None
    sick_pay_eligible = False
    sick_pay_starts_on: Optional[str] = None
    if start_date_raw:
        try:
            sd = datetime.fromisoformat(start_date_raw).replace(tzinfo=timezone.utc)
            weeks_employed = round((today_utc - sd).days / 7.0, 1)
            sick_pay_eligible = weeks_employed >= 13.0
            if not sick_pay_eligible:
                sick_pay_starts_on = (sd + timedelta(weeks=13)).strftime("%Y-%m-%d")
        except Exception:
            pass
    # Bank holiday eligibility
    bank_holiday_eligible = False
    hours_last_5_weeks = 0.0
    if employment_type == "full_time":
        bank_holiday_eligible = True
    else:
        five_weeks_ago = today_utc - timedelta(weeks=5)
        entries = await db.clock_entries.find(
            {"user_id": user["id"], "clock_in": {"$gte": five_weeks_ago}}
        ).to_list(2000)
        total_secs = 0
        for e in entries:
            total_secs += _entry_seconds(e, cap_to=today_utc)
        hours_last_5_weeks = round(total_secs / 3600.0, 2)
        bank_holiday_eligible = hours_last_5_weeks >= 40.0
    return {
        "user_id": user["id"],
        "employment_type": employment_type,
        "start_date": start_date_raw,
        "weeks_employed": weeks_employed,
        "sick_pay_eligible": sick_pay_eligible,
        "sick_pay_eligible_on": sick_pay_starts_on,
        "bank_holiday_eligible": bank_holiday_eligible,
        "hours_last_5_weeks": hours_last_5_weeks,
        "bank_holiday_threshold_hours": 40.0 if employment_type == "part_time" else 0.0,
    }


# ----------------- Clock In/Out -----------------
@api.get("/clock/status")
async def clock_status(current=Depends(get_current_user)):
    open_entry = await db.clock_entries.find_one(
        {"user_id": current["id"], "clock_out": None}, sort=[("clock_in", -1)]
    )
    return {"clocked_in": bool(open_entry), "entry": serialize(open_entry) if open_entry else None}


@api.post("/clock/in")
async def clock_in(body: ClockNoteInGeo, current=Depends(get_current_user)):
    existing = await db.clock_entries.find_one({"user_id": current["id"], "clock_out": None})
    if existing:
        raise HTTPException(status_code=400, detail="Already clocked in")

    import math
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1 = math.radians(lat1); phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1); dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    off_site = False
    matched_depot = None
    distance_m = None
    if body.lat is not None and body.lng is not None:
        depots = await db.depots.find().to_list(200)
        if depots:
            best = None
            for d in depots:
                dist = haversine(body.lat, body.lng, d["lat"], d["lng"])
                if best is None or dist < best[0]:
                    best = (dist, d)
            if best:
                distance_m = round(best[0], 1)
                matched_depot = best[1]
                off_site = best[0] > best[1].get("radius_m", 200)

    # Resolve scheduled shift + customer site geofence
    shift_id = body.shift_id
    customer_id = None
    customer_name = None
    site_id = None
    site_name = None
    site_distance_m = None
    arrived_on_site = None

    if not shift_id:
        now_iso = now_utc().isoformat()
        candidate = await db.shifts.find_one({
            "user_id": current["id"],
            "start": {"$lte": now_iso},
            "end": {"$gte": now_iso},
        })
        if candidate:
            shift_id = candidate["id"]

    if shift_id:
        shift = await db.shifts.find_one({"id": shift_id, "user_id": current["id"]})
        if shift:
            customer_id = shift.get("customer_id")
            customer_name = shift.get("customer_name")
            site_id = shift.get("site_id")
            site_name = shift.get("site_name")
            if customer_id and site_id and body.lat is not None and body.lng is not None:
                cust = await db.customers.find_one({"id": customer_id})
                if cust:
                    site = next((s for s in cust.get("sites", []) if s["id"] == site_id), None)
                    if site and site.get("lat") is not None and site.get("lng") is not None:
                        d = haversine(body.lat, body.lng, site["lat"], site["lng"])
                        site_distance_m = round(d, 1)
                        arrived_on_site = d <= (site.get("radius_m") or 200)

    entry = {
        "id": str(uuid.uuid4()),
        "user_id": current["id"],
        "user_name": current["name"],
        "clock_in": now_utc(),
        "clock_out": None,
        "location": body.location,
        "note": body.note,
        "lat": body.lat,
        "lng": body.lng,
        "depot_id": matched_depot["id"] if matched_depot else None,
        "depot_name": matched_depot["name"] if matched_depot else None,
        "distance_m": distance_m,
        "off_site": off_site,
        "shift_id": shift_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "site_id": site_id,
        "site_name": site_name,
        "site_distance_m": site_distance_m,
        "arrived_on_site": arrived_on_site,
    }
    await db.clock_entries.insert_one(entry)
    if off_site:
        await create_admin_notifications(
            kind="off_site",
            title="Off-site clock-in",
            body=f"{current['name']} clocked in {distance_m}m from {matched_depot['name']} (outside {matched_depot['radius_m']}m radius)",
            related_id=entry["id"],
        )
    if arrived_on_site is True:
        await create_admin_notifications(
            kind="arrival",
            title="On-site arrival",
            body=f"{current['name']} arrived at {site_name} ({customer_name}) — {site_distance_m}m",
            related_id=entry["id"],
        )
    elif arrived_on_site is False:
        await create_admin_notifications(
            kind="shift_off_site",
            title="Off scheduled site",
            body=f"{current['name']} clocked in {site_distance_m}m from {site_name} (scheduled for {customer_name})",
            related_id=entry["id"],
        )
    return serialize(entry)


@api.post("/clock/out")
async def clock_out(body: ClockNoteIn, current=Depends(get_current_user)):
    entry = await db.clock_entries.find_one({"user_id": current["id"], "clock_out": None})
    if not entry:
        raise HTTPException(status_code=400, detail="Not clocked in")
    out_time = now_utc()
    duration = (out_time - entry["clock_in"].replace(tzinfo=timezone.utc) if entry["clock_in"].tzinfo is None else out_time - entry["clock_in"]).total_seconds()
    await db.clock_entries.update_one(
        {"id": entry["id"]},
        {"$set": {"clock_out": out_time, "duration_seconds": int(duration), "out_note": body.note}},
    )
    updated = await db.clock_entries.find_one({"id": entry["id"]})
    return serialize(updated)


@api.get("/clock/history")
async def clock_history(current=Depends(get_current_user), user_id: Optional[str] = None):
    query_user = user_id if (user_id and current.get("role") == "admin") else current["id"]
    docs = await db.clock_entries.find({"user_id": query_user}).sort("clock_in", -1).to_list(200)
    return [serialize(d) for d in docs]


# ----------------- Phase 1: Hours, Accrual, Bank Holidays -----------------
def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _entry_seconds(entry: Dict[str, Any], cap_to: Optional[datetime] = None) -> int:
    """Compute duration in seconds for a clock entry. If still open, use cap_to (default now)."""
    cin = _aware(entry.get("clock_in"))
    cout = _aware(entry.get("clock_out"))
    if cin is None:
        return 0
    if cout is None:
        cout = cap_to or _aware(datetime.utcnow().replace(tzinfo=timezone.utc))
    if cout < cin:
        return 0
    return int((cout - cin).total_seconds())


def _week_bounds_mon_sun(ref: datetime) -> tuple:
    """Return (mon_utc, next_mon_utc) for Mon→Sun week containing ref (UTC)."""
    ref = _aware(ref)
    # Monday = 0
    monday = (ref - timedelta(days=ref.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday, monday + timedelta(days=7)


def _accrual_hours(worked_seconds: int) -> Dict[str, float]:
    """Apply company rule: deduct 30 min break PER 8 hours worked (option A: once per ≥8h shift,
    applied here as pro-rata across the period). Then accrue 1 hour holiday per 3 hours net worked.

    For simplicity at the aggregate level, we apply: break = 0.5h * floor(worked_hours / 8).
    """
    worked_h = worked_seconds / 3600.0
    breaks_h = 0.5 * (worked_h // 8.0)
    net_h = max(0.0, worked_h - breaks_h)
    accrued_h = net_h / 3.0
    return {
        "worked_hours": round(worked_h, 2),
        "break_hours": round(breaks_h, 2),
        "net_hours": round(net_h, 2),
        "accrued_holiday_hours": round(accrued_h, 2),
    }


def _bucket_entries_by_day(entries: List[Dict[str, Any]], cap_to: Optional[datetime] = None) -> Dict[str, float]:
    """Sum hours-worked per ISO day (YYYY-MM-DD, UTC)."""
    out: Dict[str, float] = {}
    for e in entries:
        cin = _aware(e.get("clock_in"))
        if cin is None:
            continue
        day = cin.strftime("%Y-%m-%d")
        secs = _entry_seconds(e, cap_to=cap_to)
        out[day] = out.get(day, 0.0) + secs / 3600.0
    return out


@api.get("/clock/weekly-summary")
async def clock_weekly_summary(
    current=Depends(get_current_user),
    user_id: Optional[str] = None,
    week_start: Optional[str] = None,  # YYYY-MM-DD (Monday); defaults to current week
):
    """Return Mon→Sun hours worked for the current or specified week. Staff sees own; admin can pass user_id."""
    query_user = user_id if (user_id and current.get("role") == "admin") else current["id"]
    if week_start:
        try:
            ref = datetime.fromisoformat(week_start).replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(status_code=400, detail="week_start must be YYYY-MM-DD (Monday)")
    else:
        ref = datetime.utcnow().replace(tzinfo=timezone.utc)
    mon, next_mon = _week_bounds_mon_sun(ref)
    entries = await db.clock_entries.find(
        {"user_id": query_user, "clock_in": {"$gte": mon, "$lt": next_mon}}
    ).sort("clock_in", 1).to_list(500)
    cap_to = next_mon  # don't bleed an open shift past the week boundary
    now_aware = datetime.utcnow().replace(tzinfo=timezone.utc)
    if now_aware < cap_to:
        cap_to = now_aware
    per_day = _bucket_entries_by_day(entries, cap_to=cap_to)
    days: List[Dict[str, Any]] = []
    total_secs = 0
    for i in range(7):
        d = (mon + timedelta(days=i)).strftime("%Y-%m-%d")
        h = per_day.get(d, 0.0)
        days.append({"date": d, "hours": round(h, 2)})
        total_secs += int(h * 3600)
    accr = _accrual_hours(total_secs)
    return {
        "user_id": query_user,
        "week_start": mon.strftime("%Y-%m-%d"),
        "week_end": (next_mon - timedelta(days=1)).strftime("%Y-%m-%d"),
        "days": days,
        "total_hours": accr["worked_hours"],
        "break_hours": accr["break_hours"],
        "net_hours": accr["net_hours"],
        "accrued_holiday_hours": accr["accrued_holiday_hours"],
    }


@api.get("/clock/accrual")
async def clock_accrual(
    current=Depends(get_current_user),
    user_id: Optional[str] = None,
    year: Optional[int] = None,
):
    """Return total worked hours + holiday hours accrued for a given year (default current year, UTC)."""
    query_user = user_id if (user_id and current.get("role") == "admin") else current["id"]
    y = year or datetime.utcnow().year
    start = datetime(y, 1, 1, tzinfo=timezone.utc)
    end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    entries = await db.clock_entries.find(
        {"user_id": query_user, "clock_in": {"$gte": start, "$lt": end}}
    ).to_list(5000)
    total_secs = 0
    for e in entries:
        total_secs += _entry_seconds(e, cap_to=end)
    accr = _accrual_hours(total_secs)
    return {
        "user_id": query_user,
        "year": y,
        "entry_count": len(entries),
        **accr,
    }


@api.patch("/clock/entries/{eid}")
async def patch_clock_entry(eid: str, body: ClockEntryPatchIn, _=Depends(require_admin)):
    """Admin override: edit clock_in, clock_out, note, or location of a clock entry."""
    entry = await db.clock_entries.find_one({"id": eid})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    updates: Dict[str, Any] = {}
    if body.clock_in is not None:
        try:
            cin = datetime.fromisoformat(body.clock_in.replace("Z", "+00:00"))
            if cin.tzinfo is None:
                cin = cin.replace(tzinfo=timezone.utc)
            updates["clock_in"] = cin
        except Exception:
            raise HTTPException(status_code=400, detail="clock_in must be ISO 8601")
    if body.clock_out is not None:
        if body.clock_out == "":
            updates["clock_out"] = None
            updates["duration_seconds"] = 0
        else:
            try:
                cout = datetime.fromisoformat(body.clock_out.replace("Z", "+00:00"))
                if cout.tzinfo is None:
                    cout = cout.replace(tzinfo=timezone.utc)
                updates["clock_out"] = cout
            except Exception:
                raise HTTPException(status_code=400, detail="clock_out must be ISO 8601")
    if body.note is not None:
        updates["note"] = body.note
    if body.location is not None:
        updates["location"] = body.location
    if not updates:
        return serialize(entry)
    # Re-derive duration_seconds if either timestamp present
    merged = {**entry, **updates}
    if merged.get("clock_in") and merged.get("clock_out"):
        updates["duration_seconds"] = _entry_seconds(merged)
    updates["edited_at"] = now_utc()
    await db.clock_entries.update_one({"id": eid}, {"$set": updates})
    doc = await db.clock_entries.find_one({"id": eid})
    return serialize(doc)


@api.delete("/clock/entries/{eid}")
async def delete_clock_entry(eid: str, _=Depends(require_admin)):
    res = await db.clock_entries.delete_one({"id": eid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}


# ---------- Bank Holidays (Ireland pre-seeded; custom additions allowed) ----------
# Statutory Ireland public holidays for 2025 & 2026 (Dept of Enterprise list).
_IRELAND_BANK_HOLIDAYS: List[Dict[str, str]] = [
    # 2025
    {"date": "2025-01-01", "name": "New Year's Day"},
    {"date": "2025-02-03", "name": "St Brigid's Day"},
    {"date": "2025-03-17", "name": "St Patrick's Day"},
    {"date": "2025-04-21", "name": "Easter Monday"},
    {"date": "2025-05-05", "name": "May Day"},
    {"date": "2025-06-02", "name": "June Bank Holiday"},
    {"date": "2025-08-04", "name": "August Bank Holiday"},
    {"date": "2025-10-27", "name": "October Bank Holiday"},
    {"date": "2025-12-25", "name": "Christmas Day"},
    {"date": "2025-12-26", "name": "St Stephen's Day"},
    # 2026
    {"date": "2026-01-01", "name": "New Year's Day"},
    {"date": "2026-02-02", "name": "St Brigid's Day"},
    {"date": "2026-03-17", "name": "St Patrick's Day"},
    {"date": "2026-04-06", "name": "Easter Monday"},
    {"date": "2026-05-04", "name": "May Day"},
    {"date": "2026-06-01", "name": "June Bank Holiday"},
    {"date": "2026-08-03", "name": "August Bank Holiday"},
    {"date": "2026-10-26", "name": "October Bank Holiday"},
    {"date": "2026-12-25", "name": "Christmas Day"},
    {"date": "2026-12-26", "name": "St Stephen's Day"},
]


async def _seed_ireland_bank_holidays():
    """Seed default Ireland statutory bank holidays the first time the endpoint is hit.
    Custom additions persist alongside; we only insert dates not already in the collection.
    """
    existing = await db.bank_holidays.find({}, {"date": 1}).to_list(2000)
    have = {d.get("date") for d in existing}
    to_insert = []
    for h in _IRELAND_BANK_HOLIDAYS:
        if h["date"] in have:
            continue
        to_insert.append({
            "id": str(uuid.uuid4()),
            "date": h["date"],
            "name": h["name"],
            "hours": 8.0,
            "country": "IE",
            "custom": False,
            "created_at": now_utc(),
        })
    if to_insert:
        await db.bank_holidays.insert_many(to_insert)


@api.get("/bank-holidays")
async def list_bank_holidays(year: Optional[int] = None, _=Depends(get_current_user)):
    await _seed_ireland_bank_holidays()
    q: Dict[str, Any] = {}
    if year:
        q["date"] = {"$gte": f"{year}-01-01", "$lt": f"{year+1}-01-01"}
    docs = await db.bank_holidays.find(q).sort("date", 1).to_list(500)
    return [serialize(d) for d in docs]


@api.post("/bank-holidays")
async def add_bank_holiday(body: BankHolidayIn, _=Depends(require_admin)):
    # Validate date
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


@api.delete("/bank-holidays/{bid}")
async def delete_bank_holiday(bid: str, _=Depends(require_admin)):
    res = await db.bank_holidays.delete_one({"id": bid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bank holiday not found")
    return {"ok": True}


# ----------------- Holidays -----------------
@api.get("/holidays/balance")
async def holiday_balance(current=Depends(get_current_user)):
    user = await db.users.find_one({"id": current["id"]})
    entitlement = user.get("holiday_entitlement", 25)
    used_cursor = db.holiday_requests.find({"user_id": current["id"], "status": "approved"})
    used_days = 0
    async for r in used_cursor:
        s = datetime.fromisoformat(r["start_date"]).date()
        e = datetime.fromisoformat(r["end_date"]).date()
        used_days += (e - s).days + 1
    pending_cursor = db.holiday_requests.find({"user_id": current["id"], "status": "pending"})
    pending_days = 0
    async for r in pending_cursor:
        s = datetime.fromisoformat(r["start_date"]).date()
        e = datetime.fromisoformat(r["end_date"]).date()
        pending_days += (e - s).days + 1
    # Accrued holiday HOURS from clock entries YTD (1h per 3h net worked).
    # Note: this is informational; the day-based balance above is the official figure.
    year = datetime.utcnow().year
    start_y = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_y = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    entries = await db.clock_entries.find(
        {"user_id": current["id"], "clock_in": {"$gte": start_y, "$lt": end_y}}
    ).to_list(5000)
    total_secs = 0
    for e in entries:
        total_secs += _entry_seconds(e, cap_to=end_y)
    accr = _accrual_hours(total_secs)
    # Bank holiday count for the year (informational)
    bh_count = await db.bank_holidays.count_documents(
        {"date": {"$gte": f"{year}-01-01", "$lt": f"{year+1}-01-01"}}
    )
    remaining = entitlement - used_days - pending_days
    return {
        "entitlement": entitlement,
        "used": used_days,
        "pending": pending_days,
        "remaining": remaining,
        "in_deficit": remaining < 0,
        "accrued_holiday_hours": accr["accrued_holiday_hours"],
        "net_hours_ytd": accr["net_hours"],
        "bank_holiday_count": bh_count,
        "bank_holiday_hours_value": bh_count * 8,
    }


@api.post("/holidays/requests")
async def create_holiday_request(body: HolidayRequestIn, current=Depends(get_current_user)):
    # Compute requested days (informational); allow request even if balance is 0/negative.
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


@api.get("/holidays/requests")
async def list_holiday_requests(current=Depends(get_current_user), all: bool = False):
    if all and current.get("role") == "admin":
        docs = await db.holiday_requests.find().sort("created_at", -1).to_list(500)
    else:
        docs = await db.holiday_requests.find({"user_id": current["id"]}).sort("created_at", -1).to_list(500)
    return [serialize(d) for d in docs]


@api.post("/holidays/requests/{rid}/decision")
async def decide_holiday(rid: str, decision: str, _=Depends(require_admin)):
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid decision")
    res = await db.holiday_requests.update_one({"id": rid}, {"$set": {"status": decision, "decided_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    h = await db.holiday_requests.find_one({"id": rid})
    if h:
        try:
            await notify(
                h["user_id"],
                f"Holiday {decision}",
                f"{h.get('start_date','')} → {h.get('end_date','')}",
                "holiday",
                rid,
            )
        except Exception:
            pass
    return {"ok": True}


@api.post("/holidays/requests/{rid}/cancel")
async def cancel_holiday(rid: str, current=Depends(get_current_user)):
    """Cancel a holiday request. Staff can cancel their own requests in any state
    (pending/approved). Admin can cancel anyone's request. A cancelled request
    refunds days back to the balance automatically (because cancelled is not
    counted as used or pending)."""
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
    # Notify the request owner if cancelled by admin
    if cancelled_by == "admin" and h.get("user_id") != current["id"]:
        try:
            await notify(
                h["user_id"],
                "Holiday cancelled",
                f"{h.get('start_date','')} → {h.get('end_date','')} cancelled by admin",
                "holiday",
                rid,
            )
        except Exception:
            pass
    doc = await db.holiday_requests.find_one({"id": rid})
    return serialize(doc)


# ----------------- Shifts / Scheduler -----------------
@api.post("/shifts")
async def create_shift(body: ShiftIn, _=Depends(require_admin)):
    user = await db.users.find_one({"id": body.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Assignee not found")
    customer_name = None
    site_name = None
    if body.customer_id:
        c = await db.customers.find_one({"id": body.customer_id})
        if c:
            customer_name = c["name"]
            if body.site_id:
                site = next((s for s in c.get("sites", []) if s["id"] == body.site_id), None)
                if site:
                    site_name = site["name"]

    # Determine occurrences (recurring)
    rec = (body.recurring or "none").lower()
    occurrences = max(1, min(int(body.repeat_count or 1), 60)) if rec in ("daily", "weekly") else 1
    delta_days = 1 if rec == "daily" else 7 if rec == "weekly" else 0

    try:
        start_dt = datetime.fromisoformat(body.start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(body.end.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid start/end ISO datetime")

    series_id = str(uuid.uuid4()) if occurrences > 1 else None
    inserts: List[dict] = []
    for i in range(occurrences):
        offset = timedelta(days=delta_days * i)
        s_iso = (start_dt + offset).isoformat()
        e_iso = (end_dt + offset).isoformat()
        inserts.append({
            "id": str(uuid.uuid4()),
            "user_id": body.user_id,
            "user_name": user["name"],
            "title": body.title,
            "location": body.location,
            "start": s_iso,
            "end": e_iso,
            "notes": body.notes,
            "recurring": rec,
            "series_id": series_id,
            "occurrence_index": i,
            "customer_id": body.customer_id,
            "customer_name": customer_name,
            "site_id": body.site_id,
            "site_name": site_name,
            "created_at": now_utc(),
        })
    if inserts:
        await db.shifts.insert_many(inserts)
        try:
            first = inserts[0]
            count = len(inserts)
            await notify(
                body.user_id,
                "New shift assigned",
                f"{body.title} · {first['start'][:16]}" + (f" · +{count - 1} more" if count > 1 else ""),
                "shift",
                first["id"],
            )
        except Exception:
            pass
    return {"created": len(inserts), "series_id": series_id, "first": serialize(inserts[0]) if inserts else None}


@api.get("/shifts")
async def list_shifts(current=Depends(get_current_user), all: bool = False):
    if all and current.get("role") == "admin":
        docs = await db.shifts.find().sort("start", 1).to_list(500)
    else:
        docs = await db.shifts.find({"user_id": current["id"]}).sort("start", 1).to_list(500)
    return [serialize(d) for d in docs]


@api.delete("/shifts/{sid}")
async def delete_shift(sid: str, _=Depends(require_admin)):
    await db.shifts.delete_one({"id": sid})
    return {"ok": True}


@api.patch("/shifts/{sid}")
async def update_shift(sid: str, body: ShiftIn, _=Depends(require_admin)):
    shift = await db.shifts.find_one({"id": sid})
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    user = await db.users.find_one({"id": body.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Assignee not found")
    update: Dict[str, Any] = {
        "user_id": body.user_id,
        "user_name": user["name"],
        "title": body.title,
        "start": body.start,
        "end": body.end,
        "location": body.location,
        "notes": body.notes,
    }
    if body.customer_id is not None:
        update["customer_id"] = body.customer_id or None
        if body.customer_id:
            c = await db.customers.find_one({"id": body.customer_id})
            update["customer_name"] = c["name"] if c else None
            if body.site_id and c:
                site = next((s for s in c.get("sites", []) if s["id"] == body.site_id), None)
                update["site_id"] = body.site_id
                update["site_name"] = site["name"] if site else None
            else:
                update["site_id"] = None
                update["site_name"] = None
        else:
            update["customer_name"] = None
            update["site_id"] = None
            update["site_name"] = None
    await db.shifts.update_one({"id": sid}, {"$set": update})
    new_doc = await db.shifts.find_one({"id": sid})
    try:
        await notify(body.user_id, "Shift updated", f"{body.title} · {body.start[:16]}", "shift")
    except Exception:
        pass
    return serialize(new_doc)


@api.post("/shifts/{sid}/swap")
async def request_swap(sid: str, body: SwapRequestIn, current=Depends(get_current_user)):
    shift = await db.shifts.find_one({"id": sid, "user_id": current["id"]})
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    target = await db.users.find_one({"id": body.target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")
    swap = {
        "id": str(uuid.uuid4()),
        "shift_id": sid,
        "from_user_id": current["id"],
        "from_user_name": current["name"],
        "to_user_id": body.target_user_id,
        "to_user_name": target["name"],
        "reason": body.reason,
        "status": "pending",
        "created_at": now_utc(),
    }
    await db.swap_requests.insert_one(swap)
    return serialize(swap)


@api.get("/shifts/swaps")
async def list_swaps(current=Depends(get_current_user)):
    if current.get("role") == "admin":
        docs = await db.swap_requests.find().sort("created_at", -1).to_list(500)
    else:
        docs = await db.swap_requests.find(
            {"$or": [{"from_user_id": current["id"]}, {"to_user_id": current["id"]}]}
        ).sort("created_at", -1).to_list(500)
    return [serialize(d) for d in docs]


@api.post("/shifts/swaps/{sid}/decision")
async def decide_swap(sid: str, decision: str, _=Depends(require_admin)):
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid decision")
    swap = await db.swap_requests.find_one({"id": sid})
    if not swap:
        raise HTTPException(status_code=404, detail="Swap not found")
    await db.swap_requests.update_one({"id": sid}, {"$set": {"status": decision, "decided_at": now_utc()}})
    if decision == "approved":
        target = await db.users.find_one({"id": swap["to_user_id"]})
        await db.shifts.update_one(
            {"id": swap["shift_id"]},
            {"$set": {"user_id": swap["to_user_id"], "user_name": target["name"]}},
        )
    # Notify both parties
    try:
        await notify(swap["from_user_id"], f"Swap {decision}", f"with {swap['to_user_name']}", "swap", sid)
        await notify(swap["to_user_id"], f"Swap {decision}", f"with {swap['from_user_name']}", "swap", sid)
    except Exception:
        pass
    return {"ok": True}


@api.post("/availability")
async def set_availability(body: AvailabilityIn, current=Depends(get_current_user)):
    doc = {
        "user_id": current["id"],
        "user_name": current["name"],
        "date": body.date,
        "available": body.available,
        "note": body.note,
        "updated_at": now_utc(),
    }
    await db.availability.update_one(
        {"user_id": current["id"], "date": body.date}, {"$set": doc}, upsert=True
    )
    return doc | {"updated_at": doc["updated_at"].isoformat()}


@api.get("/availability")
async def list_availability(current=Depends(get_current_user), all: bool = False):
    if all and current.get("role") == "admin":
        docs = await db.availability.find().sort("date", 1).to_list(500)
    else:
        docs = await db.availability.find({"user_id": current["id"]}).sort("date", 1).to_list(500)
    return [serialize(d) for d in docs]


# ----------------- Drive -----------------
@api.post("/drive/folders")
async def create_folder(body: FolderIn, current=Depends(get_current_user)):
    folder = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "parent_id": body.parent_id,
        "owner_id": current["id"],
        "owner_name": current["name"],
        "created_at": now_utc(),
    }
    await db.folders.insert_one(folder)
    return serialize(folder)


@api.get("/drive/folders")
async def list_folders(parent_id: Optional[str] = None, _=Depends(get_current_user)):
    q = {"parent_id": parent_id}
    docs = await db.folders.find(q).sort("name", 1).to_list(500)
    return [serialize(d) for d in docs]


@api.delete("/drive/folders/{fid}")
async def delete_folder(fid: str, _=Depends(require_admin)):
    await db.folders.delete_one({"id": fid})
    await db.files.delete_many({"folder_id": fid})
    return {"ok": True}


@api.post("/drive/files")
async def upload_file(body: FileIn, current=Depends(get_current_user)):
    f = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "folder_id": body.folder_id,
        "mime_type": body.mime_type,
        "data_base64": body.data_base64,
        "size": body.size or len(body.data_base64),
        "owner_id": current["id"],
        "owner_name": current["name"],
        "created_at": now_utc(),
    }
    await db.files.insert_one(f)
    out = {k: v for k, v in f.items() if k != "data_base64"}
    return serialize(out)


@api.get("/drive/files")
async def list_files(folder_id: Optional[str] = None, _=Depends(get_current_user)):
    docs = await db.files.find({"folder_id": folder_id}, {"data_base64": 0}).sort("name", 1).to_list(500)
    return [serialize(d) for d in docs]


@api.get("/drive/files/{fid}")
async def get_file(fid: str, _=Depends(get_current_user)):
    doc = await db.files.find_one({"id": fid})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    return serialize(doc)


@api.delete("/drive/files/{fid}")
async def delete_file(fid: str, current=Depends(get_current_user)):
    doc = await db.files.find_one({"id": fid})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    if current.get("role") != "admin" and doc.get("owner_id") != current["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.files.delete_one({"id": fid})
    return {"ok": True}


# ----------------- Forms -----------------
@api.post("/forms/templates")
async def create_template(body: FormTemplateIn, current=Depends(require_admin)):
    tpl = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "description": body.description,
        "fields": [f.dict() for f in body.fields],
        "kind": body.kind,
        "checklist_items": [c.dict() for c in (body.checklist_items or [])],
        "target_percent": body.target_percent,
        "depot_id": body.depot_id,
        "assigned_user_ids": list(body.assigned_user_ids or []),
        "created_by": current["id"],
        "created_by_name": current["name"],
        "created_at": now_utc(),
    }
    await db.form_templates.insert_one(tpl)
    return serialize(tpl)


@api.get("/forms/templates/{tid}/stats")
async def template_stats(tid: str, date_from: Optional[str] = None, date_to: Optional[str] = None, _=Depends(get_current_user)):
    tpl = await db.form_templates.find_one({"id": tid})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    q: Dict[str, Any] = {"template_id": tid}
    if date_from or date_to:
        rng: Dict[str, Any] = {}
        if date_from:
            rng["$gte"] = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        if date_to:
            rng["$lte"] = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
        q["created_at"] = rng
    subs = await db.form_submissions.find(q).to_list(2000)
    items = tpl.get("checklist_items") or []
    # Per-item per-subkey counts
    per_item: Dict[str, Dict[str, int]] = {}
    total_done = 0
    total_possible = 0
    for it in items:
        per_item[it["id"]] = {sk: 0 for sk in it["sub_keys"]}
    for s in subs:
        vals = s.get("values") or {}
        for it in items:
            for sk in it["sub_keys"]:
                total_possible += 1
                key = f"{it['id']}_{sk}"
                if vals.get(key) is True or str(vals.get(key, "")).lower() == "true":
                    per_item[it["id"]][sk] += 1
                    total_done += 1
    overall_pct = (total_done / total_possible * 100.0) if total_possible else 0.0
    target = tpl.get("target_percent")
    return {
        "template_id": tid,
        "title": tpl.get("title"),
        "submissions": len(subs),
        "items": [
            {
                "id": it["id"],
                "label": it["label"],
                "sub_keys": it["sub_keys"],
                "counts": per_item[it["id"]],
            }
            for it in items
        ],
        "overall_done": total_done,
        "overall_possible": total_possible,
        "overall_percent": round(overall_pct, 1),
        "target_percent": target,
        "on_target": (target is None) or (overall_pct >= target),
    }


@api.get("/forms/templates")
async def list_templates(current=Depends(get_current_user)):
    docs = await db.form_templates.find().sort("created_at", -1).to_list(500)
    # Admin sees all; staff sees only templates assigned to them (empty assigned_user_ids = visible to ALL)
    if current.get("role") != "admin":
        uid = current["id"]
        docs = [d for d in docs if not d.get("assigned_user_ids") or uid in (d.get("assigned_user_ids") or [])]
    return [serialize(d) for d in docs]


@api.patch("/forms/templates/{tid}/assign")
async def assign_template(tid: str, body: TemplateAssignIn, _=Depends(require_admin)):
    res = await db.form_templates.update_one(
        {"id": tid},
        {"$set": {"assigned_user_ids": list(body.assigned_user_ids or [])}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    doc = await db.form_templates.find_one({"id": tid})
    return serialize(doc)


@api.get("/forms/templates/{tid}")
async def get_template(tid: str, _=Depends(get_current_user)):
    doc = await db.form_templates.find_one({"id": tid})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    return serialize(doc)


@api.delete("/forms/templates/{tid}")
async def delete_template(tid: str, _=Depends(require_admin)):
    await db.form_templates.delete_one({"id": tid})
    return {"ok": True}


@api.post("/forms/submissions")
async def create_submission(body: FormSubmissionIn, current=Depends(get_current_user)):
    tpl = await db.form_templates.find_one({"id": body.template_id})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    # Staff can only submit templates assigned to them (empty list = all)
    if current.get("role") != "admin":
        assigned = tpl.get("assigned_user_ids") or []
        if assigned and current["id"] not in assigned:
            raise HTTPException(status_code=403, detail="Not assigned to you")
    sub = {
        "id": str(uuid.uuid4()),
        "template_id": body.template_id,
        "template_title": tpl["title"],
        "user_id": current["id"],
        "user_name": current["name"],
        "values": body.values,
        "status": "submitted",
        "ai_summary": None,
        "created_at": now_utc(),
    }
    await db.form_submissions.insert_one(sub)

    # Auto-notify admins if checklist submission is below target
    if tpl.get("kind") == "checklist":
        items = tpl.get("checklist_items") or []
        target = tpl.get("target_percent") or 100.0
        total_done = 0
        total_possible = 0
        for it in items:
            for sk in it["sub_keys"]:
                total_possible += 1
                if body.values.get(f"{it['id']}_{sk}") in (True, "true", "True"):
                    total_done += 1
        overall = (total_done / total_possible * 100.0) if total_possible else 0.0
        if overall < target:
            await create_admin_notifications(
                kind="checklist_below_target",
                title=f"{tpl['title']} below target",
                body=f"{current['name']} submitted at {round(overall,1)}% (target {target}%)",
                related_id=tpl["id"],
            )
    return serialize(sub)


@api.get("/forms/submissions")
async def list_submissions(current=Depends(get_current_user), all: bool = False):
    if all and current.get("role") == "admin":
        docs = await db.form_submissions.find().sort("created_at", -1).to_list(500)
    else:
        docs = await db.form_submissions.find({"user_id": current["id"]}).sort("created_at", -1).to_list(500)
    return [serialize(d) for d in docs]


@api.get("/forms/submissions/{sid}/pdf")
async def submission_pdf(sid: str, _=Depends(get_current_user)):
    sub = await db.form_submissions.find_one({"id": sid})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    tpl = await db.form_templates.find_one({"id": sub["template_id"]})
    # Render PDF
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"<b>{tpl['title']}</b>", styles["Title"]), Spacer(1, 12)]
    story.append(Paragraph(f"Submitted by: {sub['user_name']}", styles["Normal"]))
    story.append(Paragraph(f"Date: {sub['created_at']}", styles["Normal"]))
    story.append(Spacer(1, 12))
    for field in tpl.get("fields", []):
        v = sub["values"].get(field["key"], "")
        story.append(Paragraph(f"<b>{field['label']}:</b> {v}", styles["Normal"]))
        story.append(Spacer(1, 6))
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={tpl['title']}.pdf"})


@api.post("/forms/submissions/{sid}/summarize")
async def summarize_submission(sid: str, _=Depends(get_current_user)):
    sub = await db.form_submissions.find_one({"id": sid})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    tpl = await db.form_templates.find_one({"id": sub["template_id"]})
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"form-summary-{sid}",
            system_message="You summarize HR/staff form submissions clearly and concisely (3-4 sentences). Highlight key info and any flags worth admin attention.",
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        body_text = f"Form: {tpl['title']}\nSubmitted by: {sub['user_name']}\n\nResponses:\n"
        for field in tpl.get("fields", []):
            v = sub["values"].get(field["key"], "")
            body_text += f"- {field['label']}: {v}\n"
        resp = await chat.send_message(UserMessage(text=body_text))
        await db.form_submissions.update_one({"id": sid}, {"$set": {"ai_summary": resp}})
        return {"summary": resp}
    except Exception as e:
        logger.exception("AI summary failed")
        raise HTTPException(status_code=500, detail=f"AI failure: {e}")


@api.get("/forms/templates/{tid}/stats/export")
async def export_stats(tid: str, format: str = "csv", date_from: Optional[str] = None, date_to: Optional[str] = None, _=Depends(get_current_user)):
    if format not in ("csv", "pdf"):
        raise HTTPException(status_code=400, detail="format must be csv or pdf")
    tpl = await db.form_templates.find_one({"id": tid})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    q: Dict[str, Any] = {"template_id": tid}
    if date_from or date_to:
        rng: Dict[str, Any] = {}
        if date_from:
            rng["$gte"] = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        if date_to:
            rng["$lte"] = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
        q["created_at"] = rng
    subs = await db.form_submissions.find(q).to_list(2000)
    items = tpl.get("checklist_items") or []
    target = tpl.get("target_percent") or 100.0

    rows = []
    total_done = 0
    total_possible = 0
    for it in items:
        for sk in it["sub_keys"]:
            done = sum(1 for s in subs if (s.get("values") or {}).get(f"{it['id']}_{sk}") in (True, "true", "True"))
            missed = len(subs) - done
            rows.append((it["label"], sk, done, missed, len(subs)))
            total_done += done
            total_possible += len(subs)
    overall = round((total_done / total_possible * 100.0) if total_possible else 0.0, 1)

    if format == "csv":
        import csv as _csv
        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow([f"Template: {tpl['title']}"])
        w.writerow([f"Range: {date_from or 'all'} → {date_to or 'now'}"])
        w.writerow([f"Submissions: {len(subs)}", f"Target: {target}%", f"Overall: {overall}%", f"On target: {overall >= target}"])
        w.writerow([])
        w.writerow(["Item", "Sub-task", "Done", "Missed", "Submissions"])
        for r in rows:
            w.writerow(r)
        out = io.BytesIO(buf.getvalue().encode("utf-8"))
        return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{tpl["title"]}-stats.csv"'})

    # PDF
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors as rcolors

    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=LETTER)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"<b>{tpl['title']} — Stats Report</b>", styles["Title"]),
        Paragraph(f"Range: {date_from or 'all'} → {date_to or 'now'}", styles["Normal"]),
        Paragraph(f"Submissions: {len(subs)} | Target: {target}% | <b>Overall: {overall}%</b> ({'On target' if overall >= target else 'Below target'})", styles["Normal"]),
        Spacer(1, 12),
    ]
    table_data = [["Item", "Sub-task", "Done", "Missed", "Submissions"]] + [list(map(str, r)) for r in rows]
    t = Table(table_data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rcolors.HexColor("#0A0A0A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), rcolors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, rcolors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rcolors.white, rcolors.HexColor("#F4F4F5")]),
    ]))
    story.append(t)
    doc.build(story)
    pdf_buf.seek(0)
    return StreamingResponse(pdf_buf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{tpl["title"]}-stats.pdf"'})


@api.get("/admin/checklist-alerts")
async def checklist_alerts(_=Depends(require_admin)):
    """Return checklist templates that are below target today or missing today's submission."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    templates = await db.form_templates.find({"kind": "checklist"}).to_list(500)
    alerts = []
    for tpl in templates:
        items = tpl.get("checklist_items") or []
        target = tpl.get("target_percent") or 100.0
        subs = await db.form_submissions.find({"template_id": tpl["id"], "created_at": {"$gte": today_start}}).to_list(500)
        if not subs:
            alerts.append({"template_id": tpl["id"], "title": tpl["title"], "reason": "No submission today", "overall_percent": 0, "target_percent": target})
            continue
        total_done = 0
        total_possible = 0
        for it in items:
            for sk in it["sub_keys"]:
                total_possible += len(subs)
                key = f"{it['id']}_{sk}"
                for s in subs:
                    if (s.get("values") or {}).get(key) in (True, "true", "True"):
                        total_done += 1
        overall = (total_done / total_possible * 100.0) if total_possible else 0.0
        if overall < target:
            alerts.append({"template_id": tpl["id"], "title": tpl["title"], "reason": "Below target", "overall_percent": round(overall, 1), "target_percent": target, "submissions": len(subs)})
    return alerts


# ---------- Notifications ----------
async def create_admin_notifications(kind: str, title: str, body: str, related_id: Optional[str] = None):
    admins = await db.users.find({"role": "admin", "active": {"$ne": False}}).to_list(500)
    docs = []
    push_targets: List[str] = []
    for a in admins:
        docs.append({
            "id": str(uuid.uuid4()),
            "user_id": a["id"],
            "kind": kind,
            "title": title,
            "body": body,
            "related_id": related_id,
            "read": False,
            "created_at": now_utc(),
        })
        tok = a.get("expo_push_token")
        if tok:
            push_targets.append(tok)
    if docs:
        await db.notifications.insert_many(docs)
    if push_targets:
        await _send_expo_push(push_targets, title, body, {"kind": kind, "related_id": related_id})


async def notify(user_id: str, title: str, body: str, kind: str = "info", related_id: Optional[str] = None):
    """In-app notification + Expo push (best-effort) for a single user."""
    user = await db.users.find_one({"id": user_id})
    if not user:
        return
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "kind": kind,
        "title": title,
        "body": body,
        "related_id": related_id,
        "read": False,
        "created_at": now_utc(),
    })
    tok = user.get("expo_push_token")
    if tok:
        await _send_expo_push([tok], title, body, {"kind": kind, "related_id": related_id})


def _send_smtp_email(
    to_emails: List[str],
    subject: str,
    body_text: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
) -> bool:
    """Send a plain-text email with optional PDF attachment via SMTP. Returns True on send,
    False on any failure (logged). Never raises."""
    import smtplib, ssl
    from email.message import EmailMessage

    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    user = os.environ.get("SMTP_USER", "").strip()
    pwd = os.environ.get("SMTP_PASS", "").strip()
    sender = os.environ.get("SMTP_FROM", user).strip()
    from_name = os.environ.get("SMTP_FROM_NAME", "StaffHub").strip()
    if not (host and user and pwd and to_emails):
        logger.warning("SMTP not configured or no recipients — MOCK email to %s: %s", to_emails, subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{sender}>" if from_name else sender
    msg["To"] = ", ".join(to_emails)
    msg.set_content(body_text)
    if attachment_bytes and attachment_filename:
        msg.add_attachment(
            attachment_bytes,
            maintype="application",
            subtype="pdf",
            filename=attachment_filename,
        )

    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(user, pwd)
                s.send_message(msg)
        logger.info("SMTP sent to %s — subject=%r", to_emails, subject)
        return True
    except Exception as e:
        logger.warning("SMTP send failed to %s: %s", to_emails, e)
        return False


async def _form_recipient_emails() -> List[str]:
    """Returns admin emails opted-in to receive form submissions. Defaults to all active admins."""
    admins = await db.users.find({"role": "admin", "active": {"$ne": False}}).to_list(200)
    out: List[str] = []
    for a in admins:
        if a.get("receives_forms") is False:  # explicit opt-out
            continue
        em = (a.get("email") or "").strip()
        if em:
            out.append(em)
    return out


async def _send_expo_push(tokens: List[str], title: str, body: str, data: Optional[Dict[str, Any]] = None):
    """Send a push via Expo's push service. Best-effort; logs but never raises."""
    import httpx
    valid = [t for t in tokens if isinstance(t, str) and t.startswith(("ExponentPushToken[", "ExpoPushToken["))]
    if not valid:
        return
    payloads = [
        {
            "to": t,
            "title": title,
            "body": body,
            "sound": "default",
            "data": data or {},
            "priority": "high",
        }
        for t in valid
    ]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=payloads,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            if r.status_code >= 400:
                logger.warning("Expo push non-2xx: %s %s", r.status_code, r.text[:300])
    except Exception as e:
        logger.warning("Expo push failed: %s", e)


class PushTokenIn(BaseModel):
    token: str


@api.post("/users/me/push-token")
async def save_push_token(body: PushTokenIn, current=Depends(get_current_user)):
    tok = (body.token or "").strip()
    if tok and not tok.startswith(("ExponentPushToken[", "ExpoPushToken[")):
        raise HTTPException(status_code=400, detail="Invalid Expo push token")
    await db.users.update_one({"id": current["id"]}, {"$set": {"expo_push_token": tok or None}})
    return {"ok": True}


@api.get("/notifications")
async def list_notifications(current=Depends(get_current_user), unread_only: bool = False):
    q: Dict[str, Any] = {"user_id": current["id"]}
    if unread_only:
        q["read"] = False
    docs = await db.notifications.find(q).sort("created_at", -1).limit(100).to_list(100)
    return [serialize(d) for d in docs]


@api.post("/notifications/{nid}/read")
async def read_notification(nid: str, current=Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": current["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@api.post("/notifications/read-all")
async def read_all(current=Depends(get_current_user)):
    await db.notifications.update_many({"user_id": current["id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@api.post("/admin/scan-alerts")
async def scan_alerts(current=Depends(require_admin)):
    """Scan checklists and create notifications for current alerts (idempotent per day per template)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    templates = await db.form_templates.find({"kind": "checklist"}).to_list(500)
    created = 0
    for tpl in templates:
        items = tpl.get("checklist_items") or []
        target = tpl.get("target_percent") or 100.0
        subs = await db.form_submissions.find({"template_id": tpl["id"], "created_at": {"$gte": today_start}}).to_list(500)
        below = False
        reason = ""
        overall = 0.0
        if not subs:
            below = True
            reason = "no_submission"
        else:
            total_done = 0
            total_possible = 0
            for it in items:
                for sk in it["sub_keys"]:
                    total_possible += len(subs)
                    for s in subs:
                        if (s.get("values") or {}).get(f"{it['id']}_{sk}") in (True, "true", "True"):
                            total_done += 1
            overall = (total_done / total_possible * 100.0) if total_possible else 0.0
            if overall < target:
                below = True
                reason = "below_target"
        if below:
            existing = await db.notifications.find_one({
                "kind": "checklist_alert",
                "related_id": tpl["id"],
                "created_at": {"$gte": today_start},
            })
            if not existing:
                await create_admin_notifications(
                    kind="checklist_alert",
                    title=f"{tpl['title']} below target",
                    body=f"{reason.replace('_',' ').title()} — {round(overall,1)}% / target {target}%",
                    related_id=tpl["id"],
                )
                created += 1
    return {"alerts_created": created}


# ---------- Depots ----------
@api.post("/depots")
async def create_depot(body: DepotIn, _=Depends(require_admin)):
    d = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "lat": body.lat,
        "lng": body.lng,
        "radius_m": body.radius_m,
        "created_at": now_utc(),
    }
    await db.depots.insert_one(d)
    return serialize(d)


@api.get("/depots")
async def list_depots(_=Depends(get_current_user)):
    docs = await db.depots.find().sort("name", 1).to_list(200)
    return [serialize(d) for d in docs]


@api.delete("/depots/{did}")
async def delete_depot(did: str, _=Depends(require_admin)):
    await db.depots.delete_one({"id": did})
    return {"ok": True}


# ---------- Weekly Digest ----------
async def build_digest_csv() -> tuple[str, str]:
    """[Legacy] single CSV summary. Kept for backwards compat."""
    import csv as _csv
    now = now_utc()
    week_ago = now - timedelta(days=7)
    templates = await db.form_templates.find({"kind": "checklist"}).to_list(500)
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["StaffHub Weekly Compliance Digest"])
    w.writerow([f"Range: {week_ago.date()} → {now.date()}"])
    w.writerow([])
    w.writerow(["Checklist", "Target %", "Submissions", "Overall %", "On Target"])
    for tpl in templates:
        items = tpl.get("checklist_items") or []
        target = tpl.get("target_percent") or 100.0
        subs = await db.form_submissions.find({"template_id": tpl["id"], "created_at": {"$gte": week_ago}}).to_list(500)
        total_done = 0; total_possible = 0
        for it in items:
            for sk in it["sub_keys"]:
                total_possible += len(subs)
                for s in subs:
                    if (s.get("values") or {}).get(f"{it['id']}_{sk}") in (True, "true", "True"):
                        total_done += 1
        overall = round((total_done / total_possible * 100.0) if total_possible else 0.0, 1)
        w.writerow([tpl["title"], target, len(subs), overall, "YES" if overall >= target else "NO"])
    return f"staffhub-digest-{now.date()}.csv", buf.getvalue()


async def build_per_depot_digests() -> list[dict]:
    """Build one CSV per depot (templates with no depot_id grouped under 'Unassigned').

    Returns list of {depot_id, depot_name, filename, csv}.
    """
    import csv as _csv
    now = now_utc()
    week_ago = now - timedelta(days=7)
    depots = {d["id"]: d for d in await db.depots.find().to_list(500)}
    templates = await db.form_templates.find({"kind": "checklist"}).to_list(500)
    groups: dict[str, list] = {}
    for tpl in templates:
        groups.setdefault(tpl.get("depot_id") or "", []).append(tpl)

    out = []
    for depot_id, tpls in groups.items():
        depot_name = depots[depot_id]["name"] if depot_id and depot_id in depots else "Unassigned"
        slug = depot_name.replace(" ", "_")
        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow([f"StaffHub Weekly Digest — {depot_name}"])
        w.writerow([f"Range: {week_ago.date()} → {now.date()}"])
        w.writerow([])
        w.writerow(["Checklist", "Target %", "Submissions", "Overall %", "On Target"])
        for tpl in tpls:
            items = tpl.get("checklist_items") or []
            target = tpl.get("target_percent") or 100.0
            subs = await db.form_submissions.find({"template_id": tpl["id"], "created_at": {"$gte": week_ago}}).to_list(500)
            total_done = 0; total_possible = 0
            for it in items:
                for sk in it["sub_keys"]:
                    total_possible += len(subs)
                    for s in subs:
                        if (s.get("values") or {}).get(f"{it['id']}_{sk}") in (True, "true", "True"):
                            total_done += 1
            overall = round((total_done / total_possible * 100.0) if total_possible else 0.0, 1)
            w.writerow([tpl["title"], target, len(subs), overall, "YES" if overall >= target else "NO"])
        out.append({
            "depot_id": depot_id or None,
            "depot_name": depot_name,
            "filename": f"staffhub-digest-{slug}-{now.date()}.csv",
            "csv": buf.getvalue(),
        })
    return out


@api.post("/admin/weekly-digest")
async def send_weekly_digest(current=Depends(require_admin)):
    bundles = await build_per_depot_digests()
    if not bundles:
        # Fallback to single legacy CSV if no checklists exist
        fn, txt = await build_digest_csv()
        bundles = [{"depot_id": None, "depot_name": "All", "filename": fn, "csv": txt}]
    digest_ids = []
    for b in bundles:
        rec = {
            "id": str(uuid.uuid4()),
            "filename": b["filename"],
            "depot_id": b["depot_id"],
            "depot_name": b["depot_name"],
            "csv": b["csv"],
            "generated_by": current["name"],
            "created_at": now_utc(),
        }
        await db.digests.insert_one(rec)
        digest_ids.append(rec["id"])

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
    admins = await db.users.find({"role": "admin", "active": {"$ne": False}}).to_list(200)
    recipients = [a["email"] for a in admins]
    rows = "".join([f"<li><b>{b['depot_name']}</b> — {b['filename']}</li>" for b in bundles])
    html = (
        "<h2>Weekly Compliance Digest</h2>"
        f"<p>Generated by {current['name']}.</p>"
        f"<p>The attached CSV files break down checklist compliance per depot over the last 7 days.</p>"
        f"<ul>{rows}</ul>"
    )
    sent = []
    if api_key and recipients:
        try:
            import base64, resend
            resend.api_key = api_key
            params = {
                "from": sender,
                "to": recipients,
                "subject": "StaffHub — Weekly Compliance Digest (per-depot)",
                "html": html,
                "attachments": [
                    {"filename": b["filename"], "content": base64.b64encode(b["csv"].encode()).decode()}
                    for b in bundles
                ],
            }
            email = await asyncio.to_thread(resend.Emails.send, params)
            sent = recipients
            logger.info(f"Sent per-depot digest id={email.get('id')} to {recipients}")
        except Exception as e:
            logger.exception("Resend send failed")
            return {"ok": False, "error": str(e), "digest_ids": digest_ids}
    else:
        logger.info(f"[MOCKED EMAIL] Per-depot digest to {recipients} | Files: {[b['filename'] for b in bundles]}")
    return {
        "ok": True,
        "mocked": not bool(api_key),
        "recipients": recipients,
        "sent": sent,
        "digest_ids": digest_ids,
        "bundles": [{"depot_name": b["depot_name"], "filename": b["filename"]} for b in bundles],
    }


@api.get("/admin/off-site-clock-ins")
async def list_off_site(
    current=Depends(require_admin),
    days: int = 14,
    depot_id: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    q: Dict[str, Any] = {"off_site": True}
    rng: Dict[str, Any] = {}
    if date_from:
        rng["$gte"] = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
    if date_to:
        rng["$lte"] = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
    if not rng:
        rng["$gte"] = now_utc() - timedelta(days=days)
    q["clock_in"] = rng
    if depot_id:
        q["depot_id"] = depot_id
    if user_id:
        q["user_id"] = user_id
    docs = await db.clock_entries.find(q).sort("clock_in", -1).to_list(500)
    return [serialize(d) for d in docs]


@api.get("/admin/digests")
async def list_digests(_=Depends(require_admin)):
    docs = await db.digests.find({}, {"csv": 0}).sort("created_at", -1).limit(50).to_list(50)
    return [serialize(d) for d in docs]


@api.get("/admin/digests/{did}/download")
async def download_digest(did: str, _=Depends(require_admin)):
    d = await db.digests.find_one({"id": did})
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")
    out = io.BytesIO(d["csv"].encode("utf-8"))
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{d["filename"]}"'})


# ----------------- Customers / CRM -----------------
@api.get("/customers")
async def list_customers(_=Depends(get_current_user)):
    docs = await db.customers.find().sort("name", 1).to_list(500)
    return [serialize(d) for d in docs]


@api.get("/customers/{cid}")
async def get_customer(cid: str, _=Depends(get_current_user)):
    doc = await db.customers.find_one({"id": cid})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")
    return serialize(doc)


@api.post("/customers")
async def create_customer(body: CustomerIn, _=Depends(require_admin)):
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "company": body.company,
        "email": body.email,
        "phone": body.phone,
        "contacts": [],
        "sites": [],
        "created_at": now_utc(),
    }
    await db.customers.insert_one(doc)
    return serialize(doc)


@api.patch("/customers/{cid}")
async def update_customer(cid: str, body: CustomerIn, _=Depends(require_admin)):
    res = await db.customers.update_one({"id": cid}, {"$set": body.dict()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    doc = await db.customers.find_one({"id": cid})
    return serialize(doc)


@api.delete("/customers/{cid}")
async def delete_customer(cid: str, _=Depends(require_admin)):
    await db.customers.delete_one({"id": cid})
    await db.customer_notes.delete_many({"customer_id": cid})
    return {"ok": True}


@api.post("/customers/{cid}/contacts")
async def add_contact(cid: str, body: ContactIn, _=Depends(require_admin)):
    contact = {"id": str(uuid.uuid4()), **body.dict()}
    res = await db.customers.update_one({"id": cid}, {"$push": {"contacts": contact}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return contact


@api.delete("/customers/{cid}/contacts/{coid}")
async def remove_contact(cid: str, coid: str, _=Depends(require_admin)):
    await db.customers.update_one({"id": cid}, {"$pull": {"contacts": {"id": coid}}})
    return {"ok": True}


@api.post("/customers/{cid}/sites")
async def add_site(cid: str, body: SiteIn, _=Depends(require_admin)):
    site = {"id": str(uuid.uuid4()), **body.dict()}
    res = await db.customers.update_one({"id": cid}, {"$push": {"sites": site}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return site


@api.delete("/customers/{cid}/sites/{sid}")
async def remove_site(cid: str, sid: str, _=Depends(require_admin)):
    await db.customers.update_one({"id": cid}, {"$pull": {"sites": {"id": sid}}})
    return {"ok": True}


@api.get("/customers/{cid}/notes")
async def list_customer_notes(cid: str, _=Depends(get_current_user)):
    docs = await db.customer_notes.find({"customer_id": cid}).sort([("pinned", -1), ("created_at", -1)]).to_list(500)
    return [serialize(d) for d in docs]


@api.post("/customers/{cid}/notes")
async def add_customer_note(cid: str, body: CustomerNoteIn, current=Depends(get_current_user)):
    if not await db.customers.find_one({"id": cid}):
        raise HTTPException(status_code=404, detail="Customer not found")
    note = {
        "id": str(uuid.uuid4()),
        "customer_id": cid,
        "body": body.body,
        "category": body.category,
        "pinned": body.pinned,
        "author_id": current["id"],
        "author_name": current["name"],
        "created_at": now_utc(),
    }
    await db.customer_notes.insert_one(note)
    return serialize(note)


@api.patch("/customers/{cid}/notes/{nid}")
async def update_customer_note(cid: str, nid: str, body: CustomerNoteIn, current=Depends(get_current_user)):
    note = await db.customer_notes.find_one({"id": nid, "customer_id": cid})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if current.get("role") != "admin" and note["author_id"] != current["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.customer_notes.update_one({"id": nid}, {"$set": body.dict()})
    doc = await db.customer_notes.find_one({"id": nid})
    return serialize(doc)


@api.delete("/customers/{cid}/notes/{nid}")
async def delete_customer_note(cid: str, nid: str, current=Depends(get_current_user)):
    note = await db.customer_notes.find_one({"id": nid, "customer_id": cid})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if current.get("role") != "admin" and note["author_id"] != current["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.customer_notes.delete_one({"id": nid})
    return {"ok": True}


# ----------------- PDF Fillable Forms -----------------
def _extract_pdf_fields(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse AcroForm fields out of a PDF using pypdf. Returns a list of field dicts.

    Each entry includes per-widget geometry so the UI can render inputs in place:
    { name, type, value, options, page, rect:[x1,y1,x2,y2], page_width, page_height }
    Some fields appear on multiple pages — we emit one entry per widget but reuse the field
    name; UI should treat values as keyed by name.
    """
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        raw_fields = reader.get_fields() or {}
    except Exception:
        return []

    # Build a quick lookup from page object -> index + size for /Annots scanning
    page_meta: List[Dict[str, Any]] = []
    for i, page in enumerate(reader.pages):
        try:
            mb = page.mediabox
            w = float(mb.width)
            h = float(mb.height)
        except Exception:
            w, h = 612.0, 792.0
        page_meta.append({"index": i, "width": w, "height": h})

    # Map widget annotation -> (page_index, rect, full_field_name)
    # Field name often lives on the parent field, not the widget annot itself.
    widget_to_page: Dict[str, Dict[str, Any]] = {}

    def _full_name(obj) -> Optional[str]:
        """Walk /Parent chain joining /T values to build qualified field name."""
        parts: List[str] = []
        seen = set()
        cur = obj
        for _ in range(10):  # safety bound
            if cur is None:
                break
            try:
                key = id(cur)
            except Exception:
                key = None
            if key in seen:
                break
            seen.add(key)
            t = None
            try:
                t = cur.get("/T")
            except Exception:
                t = None
            if t is not None:
                parts.append(str(t))
            try:
                parent = cur.get("/Parent")
                if parent is None:
                    break
                cur = parent.get_object() if hasattr(parent, "get_object") else parent
            except Exception:
                break
        if not parts:
            return None
        parts.reverse()
        return ".".join(p for p in parts if p)

    try:
        for pidx, page in enumerate(reader.pages):
            annots = page.get("/Annots")
            if not annots:
                continue
            for annot_ref in annots:
                try:
                    annot = annot_ref.get_object() if hasattr(annot_ref, "get_object") else annot_ref
                    if annot.get("/Subtype") != "/Widget":
                        continue
                    rect = annot.get("/Rect")
                    if not rect:
                        continue
                    r = [float(x) for x in rect]
                    name = _full_name(annot)
                    if not name or name not in raw_fields:
                        # Try short partial name fallback
                        try:
                            t = annot.get("/T")
                            if t and str(t) in raw_fields:
                                name = str(t)
                        except Exception:
                            pass
                    if not name or name not in raw_fields:
                        continue
                    # Unique key per widget so multi-widget fields get all positions
                    key = f"{name}@{pidx}@{round(r[0],1)}_{round(r[1],1)}"
                    widget_to_page[key] = {
                        "page": pidx,
                        "rect": r,
                        "page_width": page_meta[pidx]["width"],
                        "page_height": page_meta[pidx]["height"],
                        "name": name,
                    }
                except Exception:
                    continue
    except Exception:
        pass

    # Flatten: emit one entry per widget so multi-widget fields position correctly.
    out: List[Dict[str, Any]] = []
    seen_names: set = set()
    for w in widget_to_page.values():
        name = w["name"]
        f = raw_fields.get(name)
        if f is None:
            continue
        ft = (f.get("/FT") or "") if isinstance(f, dict) else (getattr(f, "field_type", "") or "")
        value = f.get("/V") if isinstance(f, dict) else getattr(f, "value", None)
        opts = f.get("/Opt") if isinstance(f, dict) else getattr(f, "options", None)
        flags = f.get("/Ff", 0) if isinstance(f, dict) else 0
        kind = "text"
        options: Optional[List[str]] = None
        if ft == "/Tx":
            kind = "text"
        elif ft == "/Btn":
            if isinstance(flags, int) and flags & (1 << 15):
                kind = "radio"
            else:
                kind = "checkbox"
        elif ft == "/Ch":
            kind = "select"
        if opts:
            clean: List[str] = []
            for o in opts:
                if isinstance(o, list) and len(o) >= 2:
                    clean.append(str(o[1]))
                else:
                    clean.append(str(o))
            options = clean
        out.append({
            "name": name,
            "type": kind,
            "value": "" if value is None else (value if isinstance(value, str) else str(value)),
            "options": options,
            "page": w["page"],
            "rect": w["rect"],
            "page_width": w["page_width"],
            "page_height": w["page_height"],
        })
        seen_names.add(name)

    # Fallback: any fields not found via annotation walk — still emit them WITHOUT rect.
    for name, f in raw_fields.items():
        if name in seen_names:
            continue
        try:
            ft = (f.get("/FT") or "").strip() if isinstance(f, dict) else (getattr(f, "field_type", "") or "")
            value = f.get("/V") if isinstance(f, dict) else getattr(f, "value", None)
            opts = f.get("/Opt") if isinstance(f, dict) else getattr(f, "options", None)
            flags = f.get("/Ff", 0) if isinstance(f, dict) else 0
            kind = "text"
            options: Optional[List[str]] = None
            if ft == "/Tx":
                kind = "text"
            elif ft == "/Btn":
                if isinstance(flags, int) and flags & (1 << 15):
                    kind = "radio"
                else:
                    kind = "checkbox"
            elif ft == "/Ch":
                kind = "select"
            if opts:
                clean: List[str] = []
                for o in opts:
                    if isinstance(o, list) and len(o) >= 2:
                        clean.append(str(o[1]))
                    else:
                        clean.append(str(o))
                options = clean
            out.append({
                "name": str(name),
                "type": kind,
                "value": "" if value is None else (value if isinstance(value, str) else str(value)),
                "options": options,
            })
        except Exception:
            continue
    return out


def _build_overlay_pdf(fields: List[Dict[str, Any]], values: Dict[str, Any], page_sizes: List[tuple]) -> Optional[bytes]:
    """Build a transparent PDF overlay (one page per source page) with text/checkmarks
    drawn at each field's rect. Returns None if reportlab is unavailable.
    page_sizes: [(width, height), ...] per page in points.
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import black
    except Exception:
        return None

    buf = io.BytesIO()
    # Use the size of the first page; we'll setPageSize per page below.
    if not page_sizes:
        return None
    c = canvas.Canvas(buf, pagesize=page_sizes[0])
    c.setFillColor(black)
    c.setStrokeColor(black)

    # Bucket fields by page
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for f in fields:
        if f.get("rect") is None:
            continue
        by_page.setdefault(int(f.get("page") or 0), []).append(f)

    for pi, (pw, ph) in enumerate(page_sizes):
        c.setPageSize((pw, ph))
        for f in by_page.get(pi, []):
            name = f.get("name") or ""
            v = values.get(name, None)
            if v is None or v == "":
                continue
            rect = f["rect"]
            x1, y1, x2, y2 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
            w = max(0.0, x2 - x1)
            h = max(0.0, y2 - y1)
            ftype = (f.get("type") or "text").lower()
            try:
                if ftype == "checkbox":
                    truthy = bool(v) and str(v).lower() not in ("/off", "off", "false", "no", "0", "")
                    if truthy:
                        # Draw a bold check ✓ approximately centered in the box
                        size = max(8.0, min(w, h) * 0.85)
                        c.setFont("Helvetica-Bold", size)
                        cx = x1 + w / 2 - size * 0.3
                        cy = y1 + h / 2 - size * 0.32
                        c.drawString(cx, cy, "X")
                elif ftype == "radio":
                    # Same treatment as checkbox if value matches the export name
                    s = str(v)
                    if s and s.lower() not in ("/off", "off"):
                        size = max(8.0, min(w, h) * 0.85)
                        c.setFont("Helvetica-Bold", size)
                        cx = x1 + w / 2 - size * 0.3
                        cy = y1 + h / 2 - size * 0.32
                        c.drawString(cx, cy, "X")
                else:
                    # text / select / signature — draw the string, clipped within the rect
                    s = str(v)
                    if not s:
                        continue
                    # Font size: scale to fit single-line height; minimum 8pt, max 14pt
                    fs = max(8.0, min(14.0, h * 0.7))
                    c.setFont("Helvetica", fs)
                    # Truncate long strings to roughly fit width
                    # average char width ~ fs*0.5
                    max_chars = max(1, int(w / (fs * 0.5))) if w > 0 else len(s)
                    if len(s) > max_chars:
                        s = s[: max(1, max_chars - 1)] + "…"
                    # Bottom-left aligned with a small inner padding
                    c.drawString(x1 + 2.0, y1 + max(2.0, (h - fs) / 2.0), s)
            except Exception:
                continue
        c.showPage()
    c.save()
    return buf.getvalue()


def _fill_pdf(pdf_bytes: bytes, values: Dict[str, Any], flatten: bool = True) -> bytes:
    """Fill AcroForm fields in PDF and return new PDF bytes.
    When flatten=True, the answers are also visually stamped onto each page via a
    reportlab overlay so they are visible in ANY PDF viewer (including basic mobile
    previews that don't regenerate AcroForm appearances). The AcroForm is preserved
    but its widgets are flagged ReadOnly to prevent further editing.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject, NumberObject

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)

    # Make sure /AcroForm has /NeedAppearances so viewers regenerate field UI
    try:
        if "/AcroForm" in writer._root_object:
            writer._root_object["/AcroForm"].update(
                {NameObject("/NeedAppearances"): BooleanObject(True)}
            )
    except Exception:
        pass

    # Coerce values: bool -> /Yes or /Off for checkboxes; everything else string
    coerced: Dict[str, Any] = {}
    for k, v in values.items():
        if isinstance(v, bool):
            coerced[k] = "/Yes" if v else "/Off"
        elif v is None:
            coerced[k] = ""
        else:
            coerced[k] = str(v)

    for page in writer.pages:
        try:
            writer.update_page_form_field_values(page, coerced)
        except Exception:
            # ignore field errors per page
            pass

    if flatten:
        # 1) Visually stamp values onto each page via reportlab overlay (best-effort).
        try:
            fields = _extract_pdf_fields(pdf_bytes)
            page_sizes: List[tuple] = []
            for page in writer.pages:
                try:
                    mb = page.mediabox
                    page_sizes.append((float(mb.width), float(mb.height)))
                except Exception:
                    page_sizes.append((612.0, 792.0))
            overlay_bytes = _build_overlay_pdf(fields, values, page_sizes)
            if overlay_bytes:
                overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
                for i, page in enumerate(writer.pages):
                    if i < len(overlay_reader.pages):
                        try:
                            page.merge_page(overlay_reader.pages[i])
                        except Exception:
                            pass
        except Exception:
            pass

        # 2) Mark widgets read-only so the answers can't be modified after submit.
        try:
            for page in writer.pages:
                if "/Annots" in page:
                    for annot in page["/Annots"]:
                        try:
                            obj = annot.get_object()
                            if obj.get("/Subtype") == "/Widget":
                                existing = int(obj.get("/Ff", 0) or 0)
                                obj.update({NameObject("/Ff"): NumberObject(existing | 1)})
                        except Exception:
                            continue
        except Exception:
            pass

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@api.post("/pdf-forms/templates")
async def create_pdf_form_template(body: PdfFormTemplateIn, _=Depends(require_admin), current=Depends(get_current_user)):
    import base64
    try:
        pdf_bytes = base64.b64decode(body.pdf_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 PDF")
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Not a valid PDF file")

    fields = _extract_pdf_fields(pdf_bytes)
    tmpl = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "description": body.description or "",
        "pdf_base64": body.pdf_base64,
        "fields": fields,
        "has_acroform": len(fields) > 0,
        "field_count": len(fields),
        "size_bytes": len(pdf_bytes),
        "assigned_user_ids": list(body.assigned_user_ids or []),
        "created_by": current["id"],
        "created_by_name": current.get("name"),
        "created_at": now_utc(),
    }
    await db.pdf_form_templates.insert_one(tmpl)
    res = serialize(tmpl).copy()
    res.pop("pdf_base64", None)
    return res


@api.get("/pdf-forms/templates")
async def list_pdf_form_templates(current=Depends(get_current_user)):
    docs = await db.pdf_form_templates.find().sort("created_at", -1).to_list(500)
    # Admin sees all; staff sees only templates assigned to them (empty assigned_user_ids = visible to ALL)
    if current.get("role") != "admin":
        uid = current["id"]
        docs = [d for d in docs if not d.get("assigned_user_ids") or uid in (d.get("assigned_user_ids") or [])]
    out = []
    for d in docs:
        s = serialize(d)
        s.pop("pdf_base64", None)  # keep listing light
        out.append(s)
    return out


@api.patch("/pdf-forms/templates/{tid}/assign")
async def assign_pdf_template(tid: str, body: TemplateAssignIn, _=Depends(require_admin)):
    res = await db.pdf_form_templates.update_one(
        {"id": tid},
        {"$set": {"assigned_user_ids": list(body.assigned_user_ids or [])}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    doc = await db.pdf_form_templates.find_one({"id": tid})
    s = serialize(doc)
    s.pop("pdf_base64", None)
    return s


@api.get("/pdf-forms/templates/{tid}")
async def get_pdf_form_template(tid: str, current=Depends(get_current_user)):
    doc = await db.pdf_form_templates.find_one({"id": tid})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    # Staff can only access templates assigned to them (empty list = all)
    if current.get("role") != "admin":
        assigned = doc.get("assigned_user_ids") or []
        if assigned and current["id"] not in assigned:
            raise HTTPException(status_code=403, detail="Not assigned to you")
    return serialize(doc)


@api.delete("/pdf-forms/templates/{tid}")
async def delete_pdf_form_template(tid: str, _=Depends(require_admin)):
    res = await db.pdf_form_templates.delete_one({"id": tid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.pdf_form_submissions.delete_many({"template_id": tid})
    return {"ok": True}


@api.post("/pdf-forms/templates/{tid}/fill")
async def fill_pdf_form(tid: str, body: PdfFormSubmissionIn, current=Depends(get_current_user)):
    import base64
    tmpl = await db.pdf_form_templates.find_one({"id": tid})
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    # Staff can only submit templates assigned to them (empty list = all)
    if current.get("role") != "admin":
        assigned = tmpl.get("assigned_user_ids") or []
        if assigned and current["id"] not in assigned:
            raise HTTPException(status_code=403, detail="Not assigned to you")
    try:
        pdf_bytes = base64.b64decode(tmpl["pdf_base64"])
    except Exception:
        raise HTTPException(status_code=400, detail="Stored PDF is corrupt")
    try:
        filled = _fill_pdf(pdf_bytes, body.values or {}, flatten=body.flatten)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fill failed: {e}")
    sub = {
        "id": str(uuid.uuid4()),
        "template_id": tid,
        "template_title": tmpl.get("title"),
        "user_id": current["id"],
        "user_name": current.get("name"),
        "values": body.values or {},
        "flattened": bool(body.flatten),
        "filled_pdf_base64": base64.b64encode(filled).decode("utf-8"),
        "size_bytes": len(filled),
        "created_at": now_utc(),
    }
    await db.pdf_form_submissions.insert_one(sub)
    # Email the filled PDF to admin recipients (best-effort, run in thread to avoid blocking event loop)
    sent_to: List[str] = []
    try:
        recipients = await _form_recipient_emails()
        if recipients:
            safe = (tmpl.get("title") or "form").replace("/", "_")
            fname = f"{safe} - {current.get('name','')}.pdf"
            subj = f"[StaffHub] {tmpl.get('title')} — submitted by {current.get('name','')}"
            text = (
                f"{current.get('name','A staff member')} submitted '{tmpl.get('title')}' on "
                f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}.\n\n"
                f"The completed PDF is attached.\n"
            )
            import asyncio as _asyncio
            ok = await _asyncio.to_thread(
                _send_smtp_email,
                recipients,
                subj,
                text,
                filled,
                fname,
            )
            if ok:
                sent_to = recipients
    except Exception as e:
        logger.warning("Email submission failed: %s", e)
    try:
        await create_admin_notifications(
            "form_submitted",
            f"Form submitted: {tmpl.get('title')}",
            f"{current.get('name','Staff')} completed the form",
            related_id=sub["id"],
        )
    except Exception:
        pass
    res = serialize(sub).copy()
    res["emailed_to"] = sent_to
    return res


@api.get("/pdf-forms/submissions")
async def list_pdf_form_submissions(template_id: Optional[str] = None, current=Depends(get_current_user)):
    q: Dict[str, Any] = {}
    if template_id:
        q["template_id"] = template_id
    if current.get("role") != "admin":
        q["user_id"] = current["id"]
    docs = await db.pdf_form_submissions.find(q).sort("created_at", -1).to_list(500)
    out = []
    for d in docs:
        s = serialize(d)
        s.pop("filled_pdf_base64", None)  # keep light
        out.append(s)
    return out


@api.get("/pdf-forms/submissions/{sid}")
async def get_pdf_form_submission(sid: str, current=Depends(get_current_user)):
    doc = await db.pdf_form_submissions.find_one({"id": sid})
    if not doc:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current.get("role") != "admin" and doc.get("user_id") != current["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return serialize(doc)


# ----------------- PDF Form Sessions (collaborative) -----------------
@api.post("/pdf-forms/templates/{tid}/sessions")
async def start_pdf_session(tid: str, body: PdfSessionStartIn, current=Depends(get_current_user)):
    tmpl = await db.pdf_form_templates.find_one({"id": tid})
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    # Staff can only start sessions for templates assigned to them (empty list = all)
    if current.get("role") != "admin":
        assigned = tmpl.get("assigned_user_ids") or []
        if assigned and current["id"] not in assigned:
            raise HTTPException(status_code=403, detail="Not assigned to you")
    sess = {
        "id": str(uuid.uuid4()),
        "template_id": tid,
        "template_title": tmpl.get("title"),
        "name": (body.name or f"{tmpl.get('title','Form')} #{datetime.utcnow().strftime('%Y%m%d-%H%M')}"),
        "values": {},
        "status": "draft",
        "created_by": current["id"],
        "created_by_name": current.get("name"),
        "created_at": now_utc(),
        "last_editor_id": current["id"],
        "last_editor_name": current.get("name"),
        "last_edited_at": now_utc(),
        "field_count": int(tmpl.get("field_count") or 0),
    }
    await db.pdf_form_sessions.insert_one(sess)
    return serialize(sess)


@api.get("/pdf-forms/sessions")
async def list_pdf_sessions(
    template_id: Optional[str] = None,
    status: Optional[str] = None,
    _=Depends(get_current_user),
):
    q: Dict[str, Any] = {}
    if template_id:
        q["template_id"] = template_id
    if status:
        q["status"] = status
    docs = await db.pdf_form_sessions.find(q).sort("last_edited_at", -1).to_list(500)
    out = []
    for d in docs:
        s = serialize(d)
        s.pop("filled_pdf_base64", None)
        out.append(s)
    return out


@api.get("/pdf-forms/sessions/{sid}")
async def get_pdf_session(sid: str, _=Depends(get_current_user)):
    doc = await db.pdf_form_sessions.find_one({"id": sid})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    return serialize(doc)


@api.patch("/pdf-forms/sessions/{sid}")
async def patch_pdf_session(sid: str, body: PdfSessionPatchIn, current=Depends(get_current_user)):
    doc = await db.pdf_form_sessions.find_one({"id": sid})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    if doc.get("status") == "completed" and current.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Session is locked. Ask admin to reopen.")
    new_values = dict(doc.get("values", {}))
    new_values.update(body.values or {})
    await db.pdf_form_sessions.update_one(
        {"id": sid},
        {"$set": {
            "values": new_values,
            "last_editor_id": current["id"],
            "last_editor_name": current.get("name"),
            "last_edited_at": now_utc(),
        }},
    )
    return {"ok": True, "saved_keys": len(body.values or {}), "total_filled": sum(1 for v in new_values.values() if v not in ("", None, False))}


@api.post("/pdf-forms/sessions/{sid}/complete")
async def complete_pdf_session(sid: str, _=Depends(require_admin), current=Depends(get_current_user)):
    import base64
    sess = await db.pdf_form_sessions.find_one({"id": sid})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    tmpl = await db.pdf_form_templates.find_one({"id": sess["template_id"]})
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template missing")
    try:
        pdf_bytes = base64.b64decode(tmpl["pdf_base64"])
        filled = _fill_pdf(pdf_bytes, sess.get("values") or {}, flatten=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fill failed: {e}")
    await db.pdf_form_sessions.update_one(
        {"id": sid},
        {"$set": {
            "status": "completed",
            "completed_at": now_utc(),
            "completed_by": current["id"],
            "completed_by_name": current.get("name"),
            "filled_pdf_base64": base64.b64encode(filled).decode("utf-8"),
            "size_bytes": len(filled),
        }},
    )
    return {"ok": True}


@api.post("/pdf-forms/sessions/{sid}/reopen")
async def reopen_pdf_session(sid: str, _=Depends(require_admin)):
    res = await db.pdf_form_sessions.update_one(
        {"id": sid},
        {"$set": {"status": "draft"}, "$unset": {"filled_pdf_base64": "", "completed_at": "", "completed_by": "", "completed_by_name": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@api.get("/pdf-forms/sessions/{sid}/pdf")
async def get_pdf_session_pdf(sid: str, _=Depends(get_current_user)):
    """Return current state PDF (filled with whatever values are saved). Works for drafts and completed."""
    import base64
    sess = await db.pdf_form_sessions.find_one({"id": sid})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("status") == "completed" and sess.get("filled_pdf_base64"):
        return {"pdf_base64": sess["filled_pdf_base64"], "status": "completed"}
    tmpl = await db.pdf_form_templates.find_one({"id": sess["template_id"]})
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template missing")
    try:
        pdf_bytes = base64.b64decode(tmpl["pdf_base64"])
        filled = _fill_pdf(pdf_bytes, sess.get("values") or {}, flatten=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fill failed: {e}")
    return {"pdf_base64": base64.b64encode(filled).decode("utf-8"), "status": sess.get("status", "draft")}


@api.delete("/pdf-forms/sessions/{sid}")
async def delete_pdf_session(sid: str, _=Depends(require_admin)):
    res = await db.pdf_form_sessions.delete_one({"id": sid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


# ----------------- Drive ↔ PDF Form bridge -----------------
@api.post("/drive/files/{fid}/as-pdf-form")
async def drive_file_as_pdf_form(fid: str, current=Depends(get_current_user)):
    """Promote (or reuse) a Drive PDF as a PDF Fillable Form template, then return template metadata."""
    drive_file = await db.files.find_one({"id": fid})
    if not drive_file:
        raise HTTPException(status_code=404, detail="Drive file not found")
    mime = (drive_file.get("mime_type") or "").lower()
    name = drive_file.get("name") or "form.pdf"
    pdf_b64 = drive_file.get("data_base64")
    if not pdf_b64:
        raise HTTPException(status_code=400, detail="File has no data")
    is_pdf = "pdf" in mime or name.lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF file")

    # Reuse existing template if already promoted, but re-parse if it has no widget geometry
    existing = await db.pdf_form_templates.find_one({"source_drive_file_id": fid})
    if existing:
        has_rects = any((f or {}).get("rect") for f in (existing.get("fields") or []))
        if has_rects:
            res = serialize(existing).copy()
            res.pop("pdf_base64", None)
            return res
        # Re-parse for geometry
        try:
            import base64 as _b64
            new_fields = _extract_pdf_fields(_b64.b64decode(existing["pdf_base64"]))
            await db.pdf_form_templates.update_one(
                {"id": existing["id"]},
                {"$set": {
                    "fields": new_fields,
                    "field_count": sum(1 for f in new_fields if not f.get("rect") is None) or len(new_fields),
                    "has_acroform": len(new_fields) > 0,
                }},
            )
            existing = await db.pdf_form_templates.find_one({"id": existing["id"]})
        except Exception:
            pass
        res = serialize(existing).copy()
        res.pop("pdf_base64", None)
        return res

    import base64
    try:
        pdf_bytes = base64.b64decode(pdf_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode PDF")
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Stored file is not a valid PDF")

    fields = _extract_pdf_fields(pdf_bytes)
    tmpl = {
        "id": str(uuid.uuid4()),
        "title": name.replace(".pdf", "").replace(".PDF", "")[:120] or "Drive form",
        "description": f"From Drive · {drive_file.get('owner_name','')}",
        "pdf_base64": pdf_b64,
        "fields": fields,
        "has_acroform": len(fields) > 0,
        "field_count": len(fields),
        "size_bytes": len(pdf_bytes),
        "source_drive_file_id": fid,
        "created_by": current["id"],
        "created_by_name": current.get("name"),
        "created_at": now_utc(),
    }
    await db.pdf_form_templates.insert_one(tmpl)
    res = serialize(tmpl).copy()
    res.pop("pdf_base64", None)
    return res


# ----------------- Startup -----------------
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.clock_entries.create_index([("user_id", 1), ("clock_in", -1)])
    await db.shifts.create_index([("user_id", 1), ("start", 1)])
    await db.holiday_requests.create_index([("user_id", 1), ("created_at", -1)])
    await db.form_templates.create_index("id", unique=True)
    await db.form_submissions.create_index([("user_id", 1), ("created_at", -1)])
    await db.notifications.create_index([("user_id", 1), ("read", 1), ("created_at", -1)])
    await db.depots.create_index("id", unique=True)

    # Schedule weekly digest (Mon 09:00 UTC)
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        scheduler = AsyncIOScheduler(timezone="UTC")

        async def weekly_digest_job():
            try:
                filename, csv_text = await build_digest_csv()
                rec = {
                    "id": str(uuid.uuid4()),
                    "filename": filename,
                    "csv": csv_text,
                    "generated_by": "scheduler",
                    "created_at": now_utc(),
                }
                await db.digests.insert_one(rec)
                api_key = os.environ.get("RESEND_API_KEY", "").strip()
                admins = await db.users.find({"role": "admin", "active": {"$ne": False}}).to_list(200)
                recipients = [a["email"] for a in admins]
                if api_key and recipients:
                    import base64, resend
                    resend.api_key = api_key
                    params = {
                        "from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
                        "to": recipients,
                        "subject": "StaffHub — Weekly Compliance Digest",
                        "html": "<h2>Weekly Compliance Digest</h2><p>Attached CSV summarises every checklist's compliance over the last 7 days.</p>",
                        "attachments": [{"filename": filename, "content": base64.b64encode(csv_text.encode()).decode()}],
                    }
                    await asyncio.to_thread(resend.Emails.send, params)
                    logger.info(f"Scheduled digest sent to {recipients}")
                else:
                    logger.info(f"[MOCKED SCHEDULED EMAIL] To {recipients} | {filename}")
            except Exception:
                logger.exception("Scheduled digest failed")

        scheduler.add_job(weekly_digest_job, CronTrigger(day_of_week="mon", hour=9, minute=0))
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("Scheduler started: weekly digest (Mon 09:00 UTC)")
    except Exception:
        logger.exception("Could not start scheduler")

    # Seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@company.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "name": "Admin",
            "role": "admin",
            "password_hash": hash_password(admin_password),
            "holiday_entitlement": 25,
            "active": True,
            "created_at": now_utc(),
        })
        logger.info("Seeded admin user")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}}
        )

    # Seed sample staff
    sample_email = "jane@company.com"
    if not await db.users.find_one({"email": sample_email}):
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": sample_email,
            "name": "Jane Doe",
            "role": "staff",
            "password_hash": hash_password("Staff@123"),
            "holiday_entitlement": 25,
            "active": True,
            "created_at": now_utc(),
        })
        logger.info("Seeded sample staff user")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


@api.get("/")
async def root():
    return {"service": "StaffHub API", "ok": True}


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
