"""Customers, contacts, sites, notes, and depots endpoints.

Routes mounted under /api/ via include_router in server.py.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import db, now_utc, serialize, get_current_user, require_admin


router = APIRouter()


# ----------------- Models -----------------
class ContactIn(BaseModel):
    name: str
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class SiteIn(BaseModel):
    name: str
    address: Optional[str] = None
    eircode: Optional[str] = None  # A4: Irish postcode (or any postcode-like text)
    lat: Optional[float] = None
    lng: Optional[float] = None
    radius_m: Optional[float] = 200.0
    description: Optional[str] = None


class CustomerIn(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None  # A4: full address line
    eircode: Optional[str] = None  # A4: Irish postcode / postcode text


class CustomerNoteIn(BaseModel):
    body: str
    category: str = "general"  # general | access | hazard | equipment | other
    pinned: bool = False


class DepotIn(BaseModel):
    name: str
    lat: float
    lng: float
    radius_m: float = 200.0


# ----------------- Depots -----------------
@router.post("/depots")
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


@router.get("/depots")
async def list_depots(_=Depends(get_current_user)):
    docs = await db.depots.find().sort("name", 1).to_list(200)
    return [serialize(d) for d in docs]


@router.delete("/depots/{did}")
async def delete_depot(did: str, _=Depends(require_admin)):
    await db.depots.delete_one({"id": did})
    return {"ok": True}


# ----------------- Customers -----------------
@router.get("/customers")
async def list_customers(_=Depends(get_current_user)):
    docs = await db.customers.find().sort("name", 1).to_list(500)
    return [serialize(d) for d in docs]


@router.get("/customers/{cid}")
async def get_customer(cid: str, _=Depends(get_current_user)):
    doc = await db.customers.find_one({"id": cid})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")
    return serialize(doc)


@router.post("/customers")
async def create_customer(body: CustomerIn, _=Depends(require_admin)):
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "company": body.company,
        "email": body.email,
        "phone": body.phone,
        "address": body.address,
        "eircode": body.eircode,
        "contacts": [],
        "sites": [],
        "created_at": now_utc(),
    }
    await db.customers.insert_one(doc)
    return serialize(doc)


@router.patch("/customers/{cid}")
async def update_customer(cid: str, body: CustomerIn, _=Depends(require_admin)):
    res = await db.customers.update_one({"id": cid}, {"$set": body.dict()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    doc = await db.customers.find_one({"id": cid})
    return serialize(doc)


@router.delete("/customers/{cid}")
async def delete_customer(cid: str, _=Depends(require_admin)):
    await db.customers.delete_one({"id": cid})
    await db.customer_notes.delete_many({"customer_id": cid})
    return {"ok": True}


# ----------------- Contacts (embedded sub-docs) -----------------
@router.post("/customers/{cid}/contacts")
async def add_contact(cid: str, body: ContactIn, _=Depends(require_admin)):
    contact = {"id": str(uuid.uuid4()), **body.dict()}
    res = await db.customers.update_one({"id": cid}, {"$push": {"contacts": contact}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return contact


@router.delete("/customers/{cid}/contacts/{coid}")
async def remove_contact(cid: str, coid: str, _=Depends(require_admin)):
    await db.customers.update_one({"id": cid}, {"$pull": {"contacts": {"id": coid}}})
    return {"ok": True}


# ----------------- Sites (embedded sub-docs) -----------------
@router.post("/customers/{cid}/sites")
async def add_site(cid: str, body: SiteIn, _=Depends(require_admin)):
    site = {"id": str(uuid.uuid4()), **body.dict()}
    res = await db.customers.update_one({"id": cid}, {"$push": {"sites": site}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return site


@router.delete("/customers/{cid}/sites/{sid}")
async def remove_site(cid: str, sid: str, _=Depends(require_admin)):
    await db.customers.update_one({"id": cid}, {"$pull": {"sites": {"id": sid}}})
    return {"ok": True}


# ----------------- Customer notes -----------------
@router.get("/customers/{cid}/notes")
async def list_customer_notes(cid: str, _=Depends(get_current_user)):
    docs = (
        await db.customer_notes.find({"customer_id": cid})
        .sort([("pinned", -1), ("created_at", -1)])
        .to_list(500)
    )
    return [serialize(d) for d in docs]


@router.post("/customers/{cid}/notes")
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


@router.patch("/customers/{cid}/notes/{nid}")
async def update_customer_note(cid: str, nid: str, body: CustomerNoteIn, current=Depends(get_current_user)):
    note = await db.customer_notes.find_one({"id": nid, "customer_id": cid})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if current.get("role") != "admin" and note["author_id"] != current["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.customer_notes.update_one({"id": nid}, {"$set": body.dict()})
    doc = await db.customer_notes.find_one({"id": nid})
    return serialize(doc)


@router.delete("/customers/{cid}/notes/{nid}")
async def delete_customer_note(cid: str, nid: str, current=Depends(get_current_user)):
    note = await db.customer_notes.find_one({"id": nid, "customer_id": cid})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if current.get("role") != "admin" and note["author_id"] != current["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.customer_notes.delete_one({"id": nid})
    return {"ok": True}
