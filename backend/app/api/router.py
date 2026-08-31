from fastapi import APIRouter

from app.modules.approval_policy.router import router as approval_policy_router
from app.modules.identity_tenancy.router import router as identity_router

api_router = APIRouter()
api_router.include_router(identity_router)
api_router.include_router(approval_policy_router)
