from fastapi import APIRouter

from app.modules.ai_governance.router import router as ai_governance_router
from app.modules.approval_policy.router import router as approval_policy_router
from app.modules.execution_registry.router import router as execution_registry_router
from app.modules.identity_tenancy.router import router as identity_router
from app.modules.quota_governance.router import router as quota_governance_router
from app.modules.results_evidence.router import router as results_evidence_router

api_router = APIRouter()
api_router.include_router(identity_router)
api_router.include_router(approval_policy_router)
api_router.include_router(ai_governance_router)
api_router.include_router(quota_governance_router)
api_router.include_router(results_evidence_router)
api_router.include_router(execution_registry_router)
