"""Built-in listeners registered at startup."""

from skillhub_api.events.listeners.audit import register_audit_listeners
from skillhub_api.events.listeners.notifications import register_notification_listeners
from skillhub_api.events.listeners.search_index import register_search_listeners
from skillhub_api.events.listeners.social import register_social_listeners

__all__ = [
    "register_audit_listeners",
    "register_notification_listeners",
    "register_search_listeners",
    "register_social_listeners",
]
