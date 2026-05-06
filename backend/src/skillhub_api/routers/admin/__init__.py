from fastapi import APIRouter

from skillhub_api.routers.admin import (
    audit,
    labels,
    profile_reviews,
    promotions,
    search,
    skills,
    users,
)

router = APIRouter()
router.include_router(audit.router)
router.include_router(promotions.router)
router.include_router(skills.router)
router.include_router(users.router)
router.include_router(profile_reviews.router)
router.include_router(labels.router)
router.include_router(search.router)
