import json

from .models import RoleName

ADVISOR_ROLE_PREFERENCE_KEYS = ("advisorRoles", "advisorRoleId")
VALID_ROLE_NAMES = set(RoleName.ALL)


def normalize_role_name(role_name):
    if role_name is None:
        return None
    normalized = str(role_name).strip().lower()
    return normalized or None


def split_full_name(name):
    normalized = str(name or "").strip()
    if " " in normalized:
        return normalized.split(" ", 1)
    return normalized, ""


def normalize_advisor_roles(value):
    if value is None or value == "":
        return []

    raw_value = value
    if isinstance(raw_value, str):
        try:
            raw_value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError("Advisor roles must be a list of ids.") from exc

    if not isinstance(raw_value, list):
        raise ValueError("Advisor roles must be a list of ids.")

    normalized_roles = []
    for item in raw_value:
        try:
            role_id = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError("Advisor roles must contain only numeric ids.") from exc

        if role_id not in normalized_roles:
            normalized_roles.append(role_id)

    return normalized_roles


def extract_advisor_roles(preferences):
    prefs = preferences if isinstance(preferences, dict) else {}

    for key in ADVISOR_ROLE_PREFERENCE_KEYS:
        if key in prefs:
            try:
                return normalize_advisor_roles(prefs.get(key))
            except ValueError:
                return []

    return []


def build_preferences(
    existing_preferences=None,
    *,
    role_name=None,
    advisor_roles=None,
    prefs_payload=None,
    advisor_roles_provided=False,
):
    if prefs_payload is not None and not isinstance(prefs_payload, dict):
        raise ValueError("prefs must be an object")

    merged_preferences = dict(existing_preferences or {})
    if prefs_payload:
        merged_preferences.update(prefs_payload)

    normalized_role = normalize_role_name(role_name)

    if normalized_role == RoleName.SERVICE:
        normalized_advisor_roles = (
            normalize_advisor_roles(advisor_roles)
            if advisor_roles_provided
            else extract_advisor_roles(merged_preferences)
        )
        for key in ADVISOR_ROLE_PREFERENCE_KEYS:
            merged_preferences[key] = normalized_advisor_roles
    else:
        for key in ADVISOR_ROLE_PREFERENCE_KEYS:
            merged_preferences.pop(key, None)

    return merged_preferences
