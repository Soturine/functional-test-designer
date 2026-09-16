"""Synthetic implementation evidence selected with the example requirements."""


def submit_order(order: dict) -> dict:
    """Illustrate an implementation gap: the requirement says SUBMITTED."""
    updated = dict(order)
    updated["state"] = "PROCESSING"
    return updated
