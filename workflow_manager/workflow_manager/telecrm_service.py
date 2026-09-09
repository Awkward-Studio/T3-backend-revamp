import hashlib
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils import timezone
from django.db import transaction

from jobcards.models import TelecrmLeadSync

from .caller_service import caller_car_records


CALL_TYPES = [
    "INCOMING_CALL", "OUTGOING_CALL", "MISSED_CALL", "CALL_ACTION",
    "MAQSAM_INCOMING_CALL", "MAQSAM_OUTGOING_CALL", "IVR_INCOMING_CALL", "IVR_OUTGOING_CALL",
    "MCUBE_INCOMING_CALL", "MCUBE_OUTGOING_CALL", "KNOWLARITY_INCOMING_CALL",
    "KNOWLARITY_OUTGOING_CALL", "CALLER_DESK_INCOMING_CALL", "CALLER_DESK_OUTGOING_CALL",
]
INCOMING_TYPES = [value for value in CALL_TYPES if "INCOMING" in value]
OUTGOING_TYPES = [value for value in CALL_TYPES if "OUTGOING" in value] + ["CALL_ACTION"]
MISSED_TYPES = ["MISSED_CALL"]
MESSAGE_TYPES = [
    "INCOMING_WHATSAPP_MSG", "OUTGOING_WHATSAPP_MSG", "WHATSAPP_ACTION",
    "OUTGOING_SMS", "OUTGOING_EMAIL",
]
FOLLOWUP_TYPES = [
    "CALL_FOLLOWUP_COMPLETION_ACTION", "TODO_TASK_COMPLETION_ACTION",
    "GOOGLE_MEET_COMPLETION_ACTION",
]


class TelecrmError(RuntimeError):
    pass


def _env_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _config():
    return {
        "enterprise_id": os.getenv("TELECRM_ENTERPRISE_ID", "").strip(),
        "sync_token": os.getenv("TELECRM_SYNC_TOKEN", "").strip(),
        "async_token": os.getenv("TELECRM_ASYNC_TOKEN", "").strip(),
        "sync_url": os.getenv("TELECRM_SYNC_BASE_URL", "https://next.telecrm.in/autoupdate/v2").rstrip("/"),
        "async_url": os.getenv("TELECRM_ASYNC_BASE_URL", "https://next-api.telecrm.in").rstrip("/"),
    }


def missing_config(for_upload=False):
    cfg = _config()
    required = {"TELECRM_ENTERPRISE_ID": cfg["enterprise_id"]}
    required["TELECRM_ASYNC_TOKEN" if for_upload else "TELECRM_SYNC_TOKEN"] = (
        cfg["async_token"] if for_upload else cfg["sync_token"]
    )
    return [name for name, value in required.items() if not value]


def _request(url, token, method="GET", body=None, query=None):
    if query:
        url = f"{url}?{urlencode(query)}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        timeout = _env_int("TELECRM_REQUEST_TIMEOUT_SECONDS", 5, 1, 30)
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise TelecrmError(f"TeleCRM returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise TelecrmError(f"TeleCRM request failed: {exc}") from exc


class TelecrmSyncClient:
    def __init__(self):
        cfg = _config()
        self.base = cfg["sync_url"]
        self.enterprise = cfg["enterprise_id"]
        self.token = cfg["sync_token"]

    def call(self, path, method="GET", body=None, query=None):
        return _request(f"{self.base}/enterprise/{self.enterprise}{path}", self.token, method, body, query)

    def search(self, filters=None, limit=1, skip=0):
        return self.call("/lead/search", "POST", filters or {}, {"skip": skip, "limit": limit})

    def count(self, filters=None):
        result = self.search(filters, limit=1)
        return int(result.get("total_count", result.get("totalCount", 0)) or 0)

    def lead_snapshot(self):
        response = self.search(limit=100)
        leads = list(response.get("results", response.get("data", [])) or [])
        total = int(response.get("total_count", response.get("totalCount", len(leads))) or 0)
        return leads[:100], total

    def team(self):
        first = self.call("/team-members", query={"skip": 0, "limit": 10})
        members = list(first.get("results", first.get("data", [])) or [])
        total = int(first.get("total_count", len(members)) or 0)
        skips = list(range(len(members), total, 10))
        if skips:
            workers = _env_int("TELECRM_DASHBOARD_WORKERS", 8, 1, 12)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                pages = executor.map(
                    lambda skip: self.call(
                        "/team-members",
                        query={"skip": skip, "limit": 10},
                    ),
                    skips,
                )
                for response in pages:
                    members.extend(
                        response.get("results", response.get("data", [])) or []
                    )
        return members

    def pipeline(self):
        return self.call("/lead-stage-pipeline")


def _period_filter(days, action_types, performer=None):
    now = timezone.now()
    action = {
        "type": action_types,
        "performed_at": {
            "from": int((now - timedelta(days=days)).timestamp() * 1000),
            "to": int(now.timestamp() * 1000),
        },
    }
    if performer:
        action["performed_by"] = performer
    return {"actions": action}


def build_dashboard(days=30):
    client = TelecrmSyncClient()
    warnings = []
    workers = _env_int("TELECRM_DASHBOARD_WORKERS", 8, 1, 12)
    activity_types = {
        "contacted": CALL_TYPES,
        "outgoing": OUTGOING_TYPES,
        "incoming": INCOMING_TYPES,
        "missed": MISSED_TYPES,
        "messaged": MESSAGE_TYPES,
        "followupsCompleted": FOLLOWUP_TYPES,
    }
    from_ms = int((timezone.now() - timedelta(days=days)).timestamp() * 1000)
    to_ms = int(timezone.now().timestamp() * 1000)

    calls = {
        "leads": ("Lead list", client.lead_snapshot, ([], 0)),
        "team": ("Team members", client.team, []),
        "pipeline": ("Pipeline", client.pipeline, {}),
        "new_count": (
            "New leads",
            lambda: client.count(
                {"fields": {"created_on": {"from": from_ms, "to": to_ms}}}
            ),
            0,
        ),
    }
    for key, types in activity_types.items():
        calls[f"activity:{key}"] = (
            key,
            lambda action_types=types: client.count(
                _period_filter(days, action_types)
            ),
            0,
        )

    values = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(callback): (key, label, default)
            for key, (label, callback, default) in calls.items()
        }
        for future in as_completed(futures):
            key, label, default = futures[future]
            try:
                values[key] = future.result()
            except (TelecrmError, TypeError, ValueError) as exc:
                warnings.append(f"{label}: {exc}")
                values[key] = default

    leads, total_leads = values["leads"]
    if len(leads) < total_leads:
        warnings.append(
            f"Lead breakdowns use the first {len(leads)} of {total_leads} leads "
            "to keep the dashboard responsive."
        )
    fields = [item.get("fields", item) for item in leads]
    team = values["team"]
    pipeline = values["pipeline"]

    def counts(key):
        return dict(Counter(str(item.get(key) or "Unspecified") for item in fields))

    activity = {
        key: values[f"activity:{key}"]
        for key in activity_types
    }

    agents = []
    for member in team:
        email = member.get("email") or member.get("id")
        agents.append({
            "name": member.get("name") or member.get("full_name") or email or "Unknown",
            "email": email,
            "status": member.get("status") or ("Active" if member.get("is_active") else "Unknown"),
            "license": (member.get("license") or {}).get("type") if isinstance(member.get("license"), dict) else member.get("license") or "—",
        })

    return {
        "configured": True,
        "periodDays": days,
        "generatedAt": timezone.now().isoformat(),
        "summary": {
            "totalLeads": total_leads,
            "newLeads": values["new_count"],
            "unassigned": sum(1 for item in fields if not item.get("assignee")),
        },
        "activity": activity,
        "breakdowns": {"status": counts("status"), "assignee": counts("assignee"), "rating": counts("rating")},
        "agents": agents,
        "team": {"total": len(team), "active": sum(1 for item in team if str(item.get("status", "")).lower() in {"active", "working"})},
        "pipeline": pipeline,
        "warnings": warnings,
    }


def normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 10:
        return f"91{digits}"
    if 10 <= len(digits) <= 15:
        return digits
    return ""


def eligible_leads(days=90):
    cutoff = timezone.now() - timedelta(days=days)
    leads_by_event = {}
    invalid = 0
    for record in caller_car_records(cutoff):
        phone = normalize_phone(record["customer_phone"])
        if not phone:
            invalid += 1
            continue
        event_key = (phone, record["car_number"], record["period_date"])
        leads_by_event.setdefault(
            event_key,
            {
                "phone": phone,
                "car_number": record["car_number"],
                "period_date": record["period_date"],
                "payload": {
                    "name": record["customer_name"] or phone,
                    "phone": phone,
                },
            },
        )
    return list(leads_by_event.values()), invalid


def sync_eligible_leads(days=90, dry_run=False):
    leads, invalid = eligible_leads(days)
    summary = {"eligible": len(leads), "queued": 0, "unchanged": 0, "failed": 0, "invalidPhone": invalid, "errors": []}
    if dry_run:
        return summary
    cfg = _config()
    for lead in leads:
        serialized = json.dumps(lead["payload"], sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
        with transaction.atomic():
            record, _ = TelecrmLeadSync.objects.select_for_update().get_or_create(
                phone=lead["phone"],
                car_number=lead["car_number"],
                period_date=lead["period_date"],
            )
            if record.last_queued_at:
                summary["unchanged"] += 1
                continue
            try:
                response = _request(
                    f"{cfg['async_url']}/enterprise/{cfg['enterprise_id']}/autoupdatelead",
                    cfg["async_token"], "POST", {"fields": lead["payload"]},
                )
                if response.get("status") != "QUEUED":
                    raise TelecrmError(f"Unexpected async response: {response}")
                record.payload_hash = fingerprint
                record.last_payload = lead["payload"]
                record.last_queued_at = timezone.now()
                record.last_error = ""
                record.save()
                summary["queued"] += 1
            except TelecrmError as exc:
                record.last_error = str(exc)
                record.save()
                summary["failed"] += 1
                summary["errors"].append({
                    "phone": lead["phone"],
                    "carNumber": lead["car_number"],
                    "periodDate": lead["period_date"].isoformat(),
                    "error": str(exc),
                })
    return summary
