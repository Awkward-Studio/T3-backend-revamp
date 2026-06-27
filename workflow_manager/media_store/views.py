import logging

from django.conf import settings
from django.db import DatabaseError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from imagekitio import APIConnectionError, APIStatusError, ImageKit
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UploadedAsset
from .serializers import UploadedAssetSerializer


logger = logging.getLogger(__name__)


def get_imagekit_client():
    if not settings.IMAGEKIT_PRIVATE_KEY:
        return None
    return ImageKit(private_key=settings.IMAGEKIT_PRIVATE_KEY)


class AssetUploadBaseView(APIView):
    permission_classes = [permissions.AllowAny]
    asset_kind = None
    tag_name = "Uploads"

    @extend_schema(
        summary="Upload a file",
        description="Upload a file and receive a stable asset id plus absolute URL.",
        tags=["Uploads"],
        responses={
            201: UploadedAssetSerializer,
            400: OpenApiResponse(description="Invalid upload"),
        },
    )
    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": "No file provided under 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        imagekit = get_imagekit_client()
        if imagekit is None:
            logger.error("IMAGEKIT_PRIVATE_KEY is not configured.")
            return Response(
                {"error": "ImageKit is not configured on this server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            response = imagekit.files.upload(
                file=upload.read(),
                file_name=upload.name,
            )
        except APIStatusError as exc:
            upstream_status = getattr(exc, "status_code", None)
            logger.exception("ImageKit upload failed with status %s.", upstream_status)
            return Response(
                {
                    "error": "ImageKit rejected the upload.",
                    "upstreamStatus": upstream_status,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except APIConnectionError:
            logger.exception("Could not connect to ImageKit.")
            return Response(
                {"error": "Could not connect to ImageKit."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception("Unexpected ImageKit upload error.")
            return Response(
                {"error": "Unexpected ImageKit upload error."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            asset = UploadedAsset.objects.create(
                kind=self.asset_kind,
                file_url=response.url,
                original_name=upload.name,
                content_type=getattr(upload, "content_type", "") or "",
            )
        except DatabaseError as exc:
            return Response(
                {"error": f"Unable to save upload: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            return Response(
                {"error": f"Unexpected upload error: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        serializer = UploadedAssetSerializer(asset, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ImageUploadView(AssetUploadBaseView):
    asset_kind = UploadedAsset.KIND_IMAGE


class InvoiceUploadView(AssetUploadBaseView):
    asset_kind = UploadedAsset.KIND_INVOICE


class PdfUploadView(AssetUploadBaseView):
    asset_kind = UploadedAsset.KIND_PDF


class AssetUrlView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Get uploaded asset URL",
        description="Resolve an uploaded asset id to an absolute URL.",
        tags=["Uploads"],
        responses={
            200: OpenApiResponse(description="Asset URL"),
            404: OpenApiResponse(description="Not found"),
        },
    )
    def get(self, request, asset_id):
        asset = get_object_or_404(UploadedAsset, pk=asset_id)
        serializer = UploadedAssetSerializer(asset, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
