from fastapi import APIRouter

from skillhub_api.routers.auth import account_merge, device, direct, discovery, local, me, oauth, tokens

router = APIRouter()
router.include_router(discovery.router)
router.include_router(direct.router)
router.include_router(local.router)
router.include_router(local.logout_alias_router)
router.include_router(me.router)
router.include_router(tokens.router)
router.include_router(account_merge.router)
router.include_router(device.router)
router.include_router(oauth.router)
