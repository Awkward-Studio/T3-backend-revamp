import logging
import os
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import DatabaseError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import permissions, serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from .models import UploadedAsset
from .serializers import UploadedAssetSerializer

logger = logging.getLogger(__name__)


def get_s3_client():
    if not all(
        [
            settings.STORAGE_ACCESS_KEY_ID,
            settings.STORAGE_SECRET_ACCESS_KEY,
            settings.STORAGE_BUCKET_NAME,
            settings.STORAGE_ENDPOINT_URL,
        ]
    ):
        return None
    return boto3.client(
        "s3",
        endpoint_url=settings.STORAGE_ENDPOINT_URL,
        region_name=settings.STORAGE_REGION,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
        aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.STORAGE_S3_ADDRESSING_STYLE},
        ),
    )


def get_asset_object_key(asset, filename):
    extension = os.path.splitext(filename or "")[1]
    return f"{asset.kind}/{asset.id}{extension}"


def get_asset_file_path(asset):
    return reverse("upload-asset-file", kwargs={"asset_id": asset.id})


def is_external_url(url):
    parsed = urlparse(url or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def generate_presigned_asset_url(asset):
    client = get_s3_client()
    if client is None:
        return None
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.STORAGE_BUCKET_NAME,
            "Key": get_asset_object_key(asset, asset.original_name),
        },
        ExpiresIn=settings.STORAGE_PRESIGNED_URL_TTL_SECONDS,
    )


class AssetUploadBaseView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = UploadedAssetSerializer
    asset_kind = None
    tag_name = "Uploads"

    @extend_schema(
        summary="Upload a file",
        description="Upload a file and receive a stable asset id plus absolute URL.",
        tags=["Uploads"],
        request=inline_serializer(
            name="AssetUploadRequest",
            fields={"file": serializers.FileField()},
        ),
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

        s3 = get_s3_client()
        if s3 is None:
            logger.error("Storage bucket credentials are not configured.")
            return Response(
                {"error": "Storage bucket is not configured on this server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        asset = UploadedAsset(
            kind=self.asset_kind,
            original_name=upload.name,
            content_type=getattr(upload, "content_type", "") or "",
        )
        object_key = get_asset_object_key(asset, upload.name)

        try:
            upload.seek(0)
            extra_args = {}
            if asset.content_type:
                extra_args["ContentType"] = asset.content_type
            s3.upload_fileobj(
                upload,
                settings.STORAGE_BUCKET_NAME,
                object_key,
                ExtraArgs=extra_args or None,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("Storage bucket upload failed.")
            return Response(
                {
                    "error": "Storage bucket rejected the upload.",
                    "upstreamError": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception("Unexpected storage bucket upload error.")
            return Response(
                {"error": "Unexpected storage bucket upload error."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            asset.file_url = get_asset_file_path(asset)
            asset.save()
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

        serializer = self.get_serializer(asset, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ImageUploadView(AssetUploadBaseView):
    asset_kind = UploadedAsset.KIND_IMAGE


class InvoiceUploadView(AssetUploadBaseView):
    asset_kind = UploadedAsset.KIND_INVOICE


class PdfUploadView(AssetUploadBaseView):
    asset_kind = UploadedAsset.KIND_PDF


class AssetUrlView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UploadedAssetSerializer

    @extend_schema(
        summary="Get uploaded asset URL",
        description="Resolve an uploaded asset id to an absolute URL.",
        tags=["Uploads"],
        responses={
            200: UploadedAssetSerializer,
            404: OpenApiResponse(description="Not found"),
        },
    )
    def get(self, request, asset_id):
        asset = get_object_or_404(UploadedAsset, pk=asset_id)
        serializer = self.get_serializer(asset, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AssetFileRedirectView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UploadedAssetSerializer

    @extend_schema(
        summary="Open uploaded asset file",
        description="Redirect to a temporary bucket URL for an uploaded asset file.",
        tags=["Uploads"],
        responses={
            302: OpenApiResponse(description="Redirect to file URL"),
            404: OpenApiResponse(description="Not found"),
            500: OpenApiResponse(description="Storage bucket not configured"),
        },
    )
    def get(self, request, asset_id):
        asset = get_object_or_404(UploadedAsset, pk=asset_id)
        if not asset.file_url:
            raise Http404

        if is_external_url(asset.file_url):
            return HttpResponseRedirect(asset.file_url)

        presigned_url = generate_presigned_asset_url(asset)
        if not presigned_url:
            logger.error("Storage bucket credentials are not configured.")
            return Response(
                {"error": "Storage bucket is not configured on this server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return HttpResponseRedirect(presigned_url)
