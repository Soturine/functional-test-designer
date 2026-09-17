"""Synthetic implementation evidence for the public regression fixture."""


def finalize(order: dict, shortage: bool = False) -> dict:
    updated = dict(order)
    if shortage:
        updated["state"] = "PARTIAL"
    else:
        updated["state"] = "PROCESSING"  # Diverges from RF003.
    updated["internal_timestamp"] = "generated internally"
    return updated
