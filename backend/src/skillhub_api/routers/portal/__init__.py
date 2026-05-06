from fastapi import APIRouter

from skillhub_api.routers.portal import (
    governance,
    labels,
    me,
    namespaces,
    notifications,
    profile,
    profile_change,
    promotions,
    reports,
    reviews,
    search,
    security_audit,
    skills,
    social,
    tags,
    web_contract,
)

router = APIRouter()
router.include_router(social.router)
router.include_router(skills.router)
router.include_router(skills.web_router)
router.include_router(search.router)
router.include_router(reviews.router)
router.include_router(reviews.web_router)
router.include_router(promotions.router)
router.include_router(promotions.web_router)
router.include_router(governance.router)
router.include_router(namespaces.router)
router.include_router(reports.router)
router.include_router(security_audit.router)
router.include_router(profile.router)
router.include_router(profile_change.router)
router.include_router(notifications.router)
router.include_router(labels.public_router)
router.include_router(labels.binding_router)
router.include_router(labels.binding_web_router)
router.include_router(tags.router)
router.include_router(me.router_v1)
router.include_router(me.router_web)
router.include_router(web_contract.router)
