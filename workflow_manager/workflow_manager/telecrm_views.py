from rest_framework import status
from rest_framework.response import Response

from users.permissions import IsAdmin
from .compat_views import CompatAPIView
from .telecrm_service import build_dashboard, missing_config, sync_eligible_leads, TelecrmError


class CompatTelecrmDashboardView(CompatAPIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        missing = missing_config()
        if missing:
            return Response({"configured": False, "missing": missing})
        try:
            days = max(1, min(int(request.query_params.get("days", 30)), 365))
            return Response(build_dashboard(days))
        except (ValueError, TelecrmError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class CompatTelecrmLeadSyncView(CompatAPIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({"configured": not missing_config(True), "missing": missing_config(True), **sync_eligible_leads(90, dry_run=True)})

    def post(self, request):
        missing = missing_config(True)
        if missing:
            return Response({"configured": False, "missing": missing}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"configured": True, **sync_eligible_leads(90)})
