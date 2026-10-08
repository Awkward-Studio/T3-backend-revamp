import json

from .models import RoleName

ADVISOR_ROLE_PREFERENCE_KEYS = ("advisorRoles", "advisorRoleId")
MONTHLY_TARGETS_PREFERENCE_KEYS = ("monthlyTargets", "monthly_targets")
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


def normalize_monthly_targets(value, role_name=None):
    if value is None or value == "":
        return {}

    raw_value = value
    if isinstance(raw_value, str):
        try:
            raw_value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError("Monthly targets must be a JSON object.") from exc

    if not isinstance(raw_value, dict):
        raise ValueError("Monthly targets must be an object.")

    normalized_role = normalize_role_name(role_name)
    targets = {}

    if normalized_role == RoleName.SERVICE:
        for key in ("targetCars", "target_cars"):
            if key in raw_value and raw_value[key] is not None and raw_value[key] != "":
                try:
                    targets["targetCars"] = max(0, int(raw_value[key]))
                    break
                except (TypeError, ValueError) as exc:
                    raise ValueError("Target cars must be a non-negative integer.") from exc

        for key in ("targetRevenue", "target_revenue"):
            if key in raw_value and raw_value[key] is not None and raw_value[key] != "":
                try:
                    targets["targetRevenue"] = max(0.0, float(raw_value[key]))
                    break
                except (TypeError, ValueError) as exc:
                    raise ValueError("Target revenue must be a non-negative number.") from exc

    elif normalized_role == RoleName.CALLER:
        for key in ("targetCalls", "target_calls"):
            if key in raw_value and raw_value[key] is not None and raw_value[key] != "":
                try:
                    targets["targetCalls"] = max(0, int(raw_value[key]))
                    break
                except (TypeError, ValueError) as exc:
                    raise ValueError("Target calls must be a non-negative integer.") from exc

    else:
        for k, v in raw_value.items():
            if v is not None and v != "":
                try:
                    targets[k] = float(v) if "." in str(v) else int(v)
                except (TypeError, ValueError):
                    pass

    return targets


def extract_monthly_targets(preferences):
    prefs = preferences if isinstance(preferences, dict) else {}
    for key in MONTHLY_TARGETS_PREFERENCE_KEYS:
        if key in prefs and isinstance(prefs[key], dict):
            return prefs[key]
    return {}


def build_preferences(
    existing_preferences=None,
    *,
    role_name=None,
    advisor_roles=None,
    prefs_payload=None,
    advisor_roles_provided=False,
    monthly_targets=None,
    monthly_targets_provided=False,
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

    targets_input = (
        monthly_targets
        if monthly_targets_provided
        else extract_monthly_targets(merged_preferences)
    )
    if targets_input is not None:
        normalized_targets = normalize_monthly_targets(
            targets_input, role_name=normalized_role
        )
        for key in MONTHLY_TARGETS_PREFERENCE_KEYS:
            merged_preferences.pop(key, None)
        if normalized_targets:
            merged_preferences["monthlyTargets"] = normalized_targets

    return merged_preferences
