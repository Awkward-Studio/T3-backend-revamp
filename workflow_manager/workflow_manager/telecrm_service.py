import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils import timezone

from jobcards.models import JobCard, TelecrmLeadSync


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
        with urlopen(request, timeout=25) as response:
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

    def all_leads(self):
        first = self.search(limit=100)
        results = list(first.get("results", first.get("data", [])) or [])
        total = int(first.get("total_count", first.get("totalCount", len(results))) or 0)
        while len(results) < total:
            response = self.search(limit=100, skip=len(results))
            batch = response.get("results", response.get("data", [])) or []
            if not batch:
                break
            results.extend(batch)
        return results

    def team(self):
        members = []
        while True:
            result = self.call("/team-members", query={"skip": len(members), "limit": 10})
            batch = result.get("results", result.get("data", [])) or []
            members.extend(batch)
            if not batch or len(members) >= int(result.get("total_count", len(members))):
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

    def safe(label, callback, default):
        try:
            return callback()
        except TelecrmError as exc:
            warnings.append(f"{label}: {exc}")
            return default

    leads = safe("Lead list", client.all_leads, [])
    fields = [item.get("fields", item) for item in leads]
    team = safe("Team members", client.team, [])
    pipeline = safe("Pipeline", client.pipeline, {})
    from_ms = int((timezone.now() - timedelta(days=days)).timestamp() * 1000)
    to_ms = int(timezone.now().timestamp() * 1000)

    def counts(key):
        return dict(Counter(str(item.get(key) or "Unspecified") for item in fields))

    activity = {}
    for key, types in {
        "contacted": CALL_TYPES,
        "outgoing": OUTGOING_TYPES,
        "incoming": INCOMING_TYPES,
        "missed": MISSED_TYPES,
        "messaged": MESSAGE_TYPES,
        "followupsCompleted": FOLLOWUP_TYPES,
    }.items():
        activity[key] = safe(key, lambda t=types: client.count(_period_filter(days, t)), 0)

    agents = []
    for member in team:
        email = member.get("email") or member.get("id")
        handled = safe(
            f"Activity for {email}",
            lambda e=email: client.count(_period_filter(days, CALL_TYPES, e)) if e else 0,
            0,
        )
        agents.append({
            "name": member.get("name") or member.get("full_name") or email or "Unknown",
            "email": email,
            "status": member.get("status") or ("Active" if member.get("is_active") else "Unknown"),
            "license": (member.get("license") or {}).get("type") if isinstance(member.get("license"), dict) else member.get("license") or "—",
            "distinctLeadsHandled": handled,
        })

    new_count = safe(
        "New leads",
        lambda: client.count({"fields": {"created_on": {"from": from_ms, "to": to_ms}}}),
        0,
    )
    return {
        "configured": True,
        "periodDays": days,
        "generatedAt": timezone.now().isoformat(),
        "summary": {
            "totalLeads": len(leads),
            "newLeads": new_count,
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
    latest_by_car = {}
    queryset = JobCard.objects.exclude(post_delivery_completed_at=None).order_by("-post_delivery_completed_at")
    for jobcard in queryset:
        car = re.sub(r"[^A-Z0-9]", "", (jobcard.car_number or "").upper())
        if car and car not in latest_by_car:
            latest_by_car[car] = jobcard

    grouped = defaultdict(list)
    invalid = 0
    for jobcard in latest_by_car.values():
        if jobcard.post_delivery_completed_at > cutoff:
            continue
        phone = normalize_phone(jobcard.customer_phone)
        if not phone:
            invalid += 1
            continue
        grouped[phone].append(jobcard)

    fields = {
        "cars": os.getenv("TELECRM_FIELD_CAR_NUMBERS", "").strip(),
        "service_date": os.getenv("TELECRM_FIELD_LAST_SERVICE_DATE", "").strip(),
        "jobcards": os.getenv("TELECRM_FIELD_T3_JOB_CARD", "").strip(),
        "source": os.getenv("TELECRM_FIELD_SOURCE", "").strip(),
    }
    leads = []
    for phone, jobcards in grouped.items():
        newest = max(jobcards, key=lambda item: item.post_delivery_completed_at)
        payload = {"name": newest.customer_name or phone, "phone": phone}
        optional = {
            fields["cars"]: ", ".join(sorted({item.car_number for item in jobcards})),
            fields["service_date"]: int(newest.post_delivery_completed_at.timestamp() * 1000),
            fields["jobcards"]: ", ".join(str(item.job_card_number) for item in jobcards),
            fields["source"]: "T3 90-Day Follow-up",
        }
        payload.update({key: value for key, value in optional.items() if key})
        if os.getenv("TELECRM_90_DAY_STATUS"):
            payload["status"] = os.getenv("TELECRM_90_DAY_STATUS")
        if os.getenv("TELECRM_90_DAY_ASSIGNEE"):
            payload["assignee"] = os.getenv("TELECRM_90_DAY_ASSIGNEE")
        leads.append({"phone": phone, "payload": payload})
    return leads, invalid


def sync_eligible_leads(days=90, dry_run=False):
    leads, invalid = eligible_leads(days)
    summary = {"eligible": len(leads), "queued": 0, "unchanged": 0, "failed": 0, "invalidPhone": invalid, "errors": []}
    if dry_run:
        return summary
    cfg = _config()
    for lead in leads:
        serialized = json.dumps(lead["payload"], sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
        record, _ = TelecrmLeadSync.objects.get_or_create(phone=lead["phone"])
        if record.payload_hash == fingerprint and record.last_queued_at:
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
            summary["errors"].append({"phone": lead["phone"], "error": str(exc)})
    return summary
