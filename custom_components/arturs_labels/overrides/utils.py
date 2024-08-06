"""Override utilities."""


def add_assign_label_id(label_id: str) -> str:
    """Add assign label id."""
    return "assign:" + label_id


def remove_assign_label_id(label_id: str) -> str | None:
    """Remove assign label id."""
    colon = label_id.rfind(":")
    if colon == -1:
        return None
    if label_id[:colon] != "assign":
        return None
    return label_id[colon + 1 :]


def add_assign_label_name(name: str) -> str:
    """Add assign label name."""
    return "assign: " + name
