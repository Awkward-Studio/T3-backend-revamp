import re

from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema


class CsrfExemptSessionAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "workflow_manager.compat_views.CsrfExemptSessionAuthentication"
    name = "SessionCookieAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": settings.SESSION_COOKIE_NAME,
        }


class CustomAutoSchema(AutoSchema):
    def get_operation_id(self):
        segments = []
        for raw_segment in self.path.strip("/").split("/"):
            if not raw_segment:
                continue
            segment = raw_segment.replace("-", "_")
            if segment.startswith("{") and segment.endswith("}"):
                segment = f"by_{segment[1:-1]}"
            segment = re.sub(r"[^0-9a-zA-Z_]+", "_", segment).strip("_")
            if segment:
                segments.append(segment)

        return "_".join([*segments, self.method.lower()])
