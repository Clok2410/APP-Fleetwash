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
    return {
        "entitlement": entitlement,
        "used": used_days,
        "pending": pending_days,
        "remaining": entitlement - used_days - pending_days,
    }


@api.post("/holidays/requests")
async def create_holiday_request(body: HolidayRequestIn, current=Depends(get_current_user)):
    req = {
        "id": str(uuid.uuid4()),
        "user_id": current["id"],
        "user_name": current["name"],
        "start_date": body.start_date,
        "end_date": body.end_date,
        "reason": body.reason,
        "type": body.type,
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
async def list_templates(_=Depends(get_current_user)):
    docs = await db.form_templates.find().sort("created_at", -1).to_list(500)
    return [serialize(d) for d in docs]


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


def _fill_pdf(pdf_bytes: bytes, values: Dict[str, Any], flatten: bool = True) -> bytes:
    """Fill AcroForm fields in PDF and return new PDF bytes. If flatten, mark read-only."""
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
        # Best-effort flatten — mark fields read-only via /Ff bit 0 (numeric flag)
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
        "created_by": current["id"],
        "created_by_name": current.get("name"),
        "created_at": now_utc(),
    }
    await db.pdf_form_templates.insert_one(tmpl)
    res = serialize(tmpl).copy()
    res.pop("pdf_base64", None)
    return res


@api.get("/pdf-forms/templates")
async def list_pdf_form_templates(_=Depends(get_current_user)):
    docs = await db.pdf_form_templates.find().sort("created_at", -1).to_list(500)
    out = []
    for d in docs:
        s = serialize(d)
        s.pop("pdf_base64", None)  # keep listing light
        out.append(s)
    return out


@api.get("/pdf-forms/templates/{tid}")
async def get_pdf_form_template(tid: str, _=Depends(get_current_user)):
    doc = await db.pdf_form_templates.find_one({"id": tid})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
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
    res = serialize(sub).copy()
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
