from django.db import DatabaseError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UploadedAsset
from .serializers import UploadedAssetSerializer


class AssetUploadBaseView(APIView):
    permission_classes = [permissions.AllowAny]
    asset_kind = None
    tag_name = "Uploads"

    @extend_schema(
        summary="Upload a file",
        description="Upload a file and receive a stable asset id plus absolute URL.",
        tags=["Uploads"],
        responses={201: UploadedAssetSerializer, 400: OpenApiResponse(description="Invalid upload")},
    )
    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": "No file provided under 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            asset = UploadedAsset.objects.create(
                kind=self.asset_kind,
                file=upload,
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
        responses={200: OpenApiResponse(description="Asset URL"), 404: OpenApiResponse(description="Not found")},
    )
    def get(self, request, asset_id):
        asset = get_object_or_404(UploadedAsset, pk=asset_id)
        serializer = UploadedAssetSerializer(asset, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
