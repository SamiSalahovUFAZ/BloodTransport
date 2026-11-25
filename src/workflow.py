from types import MappingProxyType


# A process-wide, immutable transition policy shared by every application instance.
NEXT_STATUS = MappingProxyType({
    "pending": "assigned",
    "assigned": "picked_up",
    "picked_up": "delivered",
    "delivered": "received",
})
EDITABLE_STAGES = frozenset(("pending", "assigned"))


def allows_transition(previous, requested):
    if previous in EDITABLE_STAGES and requested in ("assigned", "cancelled"):
        return True
    return NEXT_STATUS.get(previous) == requested
