"""Customers, contacts, sites, notes, and depots endpoints.

Routes mounted under /api/ via include_router in server.py.
"""
import logging
import uuid
from typing import Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import db, now_utc, serialize, get_current_user, require_admin


router = APIRouter()
log = logging.getLogger("staff-app.customers")


async def _geocode(query: str) -> Optional[Tuple[float, float]]:
    """Best-effort geocoding via OpenStreetMap Nominatim. Returns (lat, lng) or None.
    Free, no API key, fair-use only (max 1 req/sec). Tries multiple query variants
    because Nominatim doesn't reliably resolve full Irish Eircodes — it does resolve
    Eircode routing keys (the first 3 chars) and place names."""
    if not query or not query.strip():
        return None

    import re

    def is_in_ireland(lat: float, lng: float) -> bool:
        # Rough bounding box for Ireland (incl. NI): lat 51.3..55.5, lng -10.7..-5.3
        return 51.3 <= lat <= 55.5 and -10.7 <= lng <= -5.3

    # Try to extract an Eircode (3 chars + optional space + 4 chars) from the query
    eircode_match = re.search(r"\b([A-Z]\d{2})\s*([A-Z0-9]{4})\b", query.upper())
    routing_key = eircode_match.group(1) if eircode_match else None

    # Build candidate queries in priority order
    candidates: list[str] = []
    base = query.strip()
    if not re.search(r"\bIreland\b", base, re.IGNORECASE):
        candidates.append(f"{base}, Ireland")
    candidates.append(base)
    if routing_key:
        # Strip the eircode and try just the placename context + routing key
        stripped = re.sub(r"\b[A-Z]\d{2}\s*[A-Z0-9]{4}\b", "", query, flags=re.IGNORECASE).strip(", ").strip()
        if stripped:
            candidates.append(f"{stripped}, {routing_key}, Ireland")
        candidates.append(f"{routing_key}, Ireland")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for q in candidates:
                try:
                    r = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={"q": q, "format": "json", "limit": 1, "countrycodes": "ie,gb"},
                        headers={"User-Agent": "StaffHub/1.0 (fleetwash.ie)"},
                    )
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    if not isinstance(data, list) or not data:
                        continue
                    lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
                    # Reject results that are clearly not in Ireland (Nominatim sometimes
                    # returns UK postcodes for similar-looking Irish Eircodes)
                    if is_in_ireland(lat, lng):
                        return lat, lng
                except Exception:
                    continue
    except Exception:
        log.exception("Geocode failed for %r (non-fatal)", query)
    return None


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


@router.get("/depots/all")
async def list_all_depots(_=Depends(get_current_user)):
    """Unified view: standalone depots + every customer site (auto-populated).
    Each entry has `source: 'depot' | 'customer_site'` so the UI can label/route accordingly."""
    out = []
    # 1) Standalone depots
    for d in await db.depots.find().sort("name", 1).to_list(500):
        out.append({
            "source": "depot",
            "id": d["id"],
            "name": d.get("name"),
            "lat": d.get("lat"),
            "lng": d.get("lng"),
            "radius_m": d.get("radius_m", 200),
            "address": None,
            "eircode": None,
            "customer_id": None,
            "customer_name": None,
            "site_id": None,
        })
    # 2) Every customer — main address (if geocoded) AND each named site
    for c in await db.customers.find({}).to_list(1000):
        # 2a) Customer's primary address (auto-populated when admin enters customer eircode/address)
        if c.get("lat") is not None and c.get("lng") is not None:
            out.append({
                "source": "customer",
                "id": f"c:{c['id']}",
                "name": c.get("name"),
                "lat": c.get("lat"),
                "lng": c.get("lng"),
                "radius_m": 200,
                "address": c.get("address"),
                "eircode": c.get("eircode"),
                "description": "Customer main address",
                "customer_id": c["id"],
                "customer_name": c.get("name"),
                "site_id": None,
            })
        # 2b) Each named site under the customer
        for s in (c.get("sites") or []):
            out.append({
                "source": "customer_site",
                "id": f"cs:{c['id']}:{s.get('id')}",
                "name": s.get("name") or c.get("name"),
                "lat": s.get("lat"),
                "lng": s.get("lng"),
                "radius_m": s.get("radius_m", 200),
                "address": s.get("address"),
                "eircode": s.get("eircode"),
                "description": s.get("description"),
                "customer_id": c["id"],
                "customer_name": c.get("name"),
                "site_id": s.get("id"),
            })
    # Sort: standalone depots first, then customer entries alphabetically by name
    out.sort(key=lambda x: (0 if x["source"] == "depot" else 1, (x.get("name") or "").lower()))
    return out


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
    # Auto-geocode the customer's main address (eircode/address) so it appears in the Depots tab
    coords = None
    q_parts = [body.eircode, body.address, body.name]
    query = ", ".join([p for p in q_parts if p and p.strip()])
    if query:
        coords = await _geocode(query)
    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "company": body.company,
        "email": body.email,
        "phone": body.phone,
        "address": body.address,
        "eircode": body.eircode,
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        "contacts": [],
        "sites": [],
        "created_at": now_utc(),
    }
    await db.customers.insert_one(doc)
    return serialize(doc)


@router.patch("/customers/{cid}")
async def update_customer(cid: str, body: CustomerIn, _=Depends(require_admin)):
    update = body.dict()
    # If address/eircode/name changed, re-geocode so the depot pin stays accurate
    q_parts = [update.get("eircode"), update.get("address"), update.get("name")]
    query = ", ".join([p for p in q_parts if p and p.strip()])
    if query:
        coords = await _geocode(query)
        if coords:
            update["lat"], update["lng"] = coords
    res = await db.customers.update_one({"id": cid}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    doc = await db.customers.find_one({"id": cid})
    return serialize(doc)


@router.post("/customers/{cid}/geocode")
async def geocode_customer(cid: str, _=Depends(require_admin)):
    """Re-run geocoding for a customer's main address (used to backfill older customers)."""
    cust = await db.customers.find_one({"id": cid})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    q_parts = [cust.get("eircode"), cust.get("address"), cust.get("name")]
    query = ", ".join([p for p in q_parts if p and p.strip()])
    coords = await _geocode(query) if query else None
    if not coords:
        raise HTTPException(status_code=422, detail="Could not geocode this customer's address.")
    await db.customers.update_one({"id": cid}, {"$set": {"lat": coords[0], "lng": coords[1]}})
    return {"id": cid, "lat": coords[0], "lng": coords[1]}


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
    site_data = body.dict()
    # Auto-geocode if admin didn't supply explicit lat/lng but did give an address or eircode
    if (site_data.get("lat") is None or site_data.get("lng") is None):
        q_parts = [site_data.get("eircode"), site_data.get("address"), site_data.get("name")]
        query = ", ".join([p for p in q_parts if p and p.strip()])
        coords = await _geocode(query)
        if coords:
            site_data["lat"], site_data["lng"] = coords
    site = {"id": str(uuid.uuid4()), **site_data}
    res = await db.customers.update_one({"id": cid}, {"$push": {"sites": site}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return site


@router.post("/customers/{cid}/sites/{sid}/geocode")
async def geocode_site(cid: str, sid: str, _=Depends(require_admin)):
    """Re-run geocoding for an existing customer site that's missing lat/lng."""
    cust = await db.customers.find_one({"id": cid})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    site = next((s for s in (cust.get("sites") or []) if s.get("id") == sid), None)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    q_parts = [site.get("eircode"), site.get("address"), site.get("name")]
    query = ", ".join([p for p in q_parts if p and p.strip()])
    coords = await _geocode(query)
    if not coords:
        raise HTTPException(status_code=422, detail="Could not geocode that address. Please add coordinates manually.")
    await db.customers.update_one(
        {"id": cid, "sites.id": sid},
        {"$set": {"sites.$.lat": coords[0], "sites.$.lng": coords[1]}},
    )
    return {"id": sid, "lat": coords[0], "lng": coords[1]}


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
