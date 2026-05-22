from fastapi import APIRouter

from api.crm_routes import crm_router
from api.session_routes import session_router
from api.summary_routes import summary_router
from api.system_routes import system_router


api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(session_router)
api_router.include_router(summary_router)
api_router.include_router(crm_router)
