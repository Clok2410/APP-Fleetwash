"""Modular FastAPI routers extracted from monolithic server.py.

All routers should be registered on the main /api APIRouter in server.py via
`api.include_router(<router>.router)` so the existing ingress prefix is preserved.
"""
