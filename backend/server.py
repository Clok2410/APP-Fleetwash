from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import uuid
import bcrypt
import jwt
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


class FormTemplateIn(BaseModel):
    title: str
    description: Optional[str] = None
    fields: List[FormFieldIn]


class FormSubmissionIn(BaseModel):
    template_id: str
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


# ----------------- Clock In/Out -----------------
@api.get("/clock/status")
async def clock_status(current=Depends(get_current_user)):
    open_entry = await db.clock_entries.find_one(
        {"user_id": current["id"], "clock_out": None}, sort=[("clock_in", -1)]
    )
    return {"clocked_in": bool(open_entry), "entry": serialize(open_entry) if open_entry else None}


@api.post("/clock/in")
async def clock_in(body: ClockNoteIn, current=Depends(get_current_user)):
    existing = await db.clock_entries.find_one({"user_id": current["id"], "clock_out": None})
    if existing:
        raise HTTPException(status_code=400, detail="Already clocked in")
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": current["id"],
        "user_name": current["name"],
        "clock_in": now_utc(),
        "clock_out": None,
        "location": body.location,
        "note": body.note,
    }
    await db.clock_entries.insert_one(entry)
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
        "created_by": current["id"],
        "created_by_name": current["name"],
        "created_at": now_utc(),
    }
    await db.form_templates.insert_one(tpl)
    return serialize(tpl)


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
