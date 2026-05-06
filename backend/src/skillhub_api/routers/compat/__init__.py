from fastapi import APIRouter

from skillhub_api.routers.compat import clawhub, well_known

router = APIRouter()
router.include_router(clawhub.router)
router.include_router(well_known.router)
