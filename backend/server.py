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

    # Geofence: find nearest depot, flag off-site if outside any depot
    off_site = False
    matched_depot = None
    distance_m = None
    if body.lat is not None and body.lng is not None:
        depots = await db.depots.find().to_list(200)
        if depots:
            import math
            def haversine(lat1, lon1, lat2, lon2):
                R = 6371000
                phi1 = math.radians(lat1); phi2 = math.radians(lat2)
                dphi = math.radians(lat2 - lat1); dlam = math.radians(lon2 - lon1)
                a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
                return 2 * R * math.asin(math.sqrt(a))
            best = None
            for d in depots:
                dist = haversine(body.lat, body.lng, d["lat"], d["lng"])
                if best is None or dist < best[0]:
                    best = (dist, d)
            if best:
                distance_m = round(best[0], 1)
                matched_depot = best[1]
                off_site = best[0] > best[1].get("radius_m", 200)
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
    }
    await db.clock_entries.insert_one(entry)
    if off_site:
        await create_admin_notifications(
            kind="off_site",
            title="Off-site clock-in",
            body=f"{current['name']} clocked in {distance_m}m from {matched_depot['name']} (outside {matched_depot['radius_m']}m radius)",
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
    return {"ok": True}


# ----------------- Shifts / Scheduler -----------------
@api.post("/shifts")
async def create_shift(body: ShiftIn, _=Depends(require_admin)):
    user = await db.users.find_one({"id": body.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Assignee not found")
    shift = {
        "id": str(uuid.uuid4()),
        "user_id": body.user_id,
        "user_name": user["name"],
        "title": body.title,
        "location": body.location,
        "start": body.start,
        "end": body.end,
        "notes": body.notes,
        "recurring": body.recurring or "none",
        "created_at": now_utc(),
    }
    await db.shifts.insert_one(shift)
    return serialize(shift)


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
    if docs:
        await db.notifications.insert_many(docs)


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
async def list_off_site(current=Depends(require_admin), days: int = 14):
    since = now_utc() - timedelta(days=days)
    docs = await db.clock_entries.find(
        {"off_site": True, "clock_in": {"$gte": since}}
    ).sort("clock_in", -1).to_list(500)
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
