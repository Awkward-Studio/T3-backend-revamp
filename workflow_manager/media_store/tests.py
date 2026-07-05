from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import UploadedAsset


class StorageBucketUploadTests(APITestCase):
    bucket_settings = {
        "STORAGE_BUCKET_NAME": "test-bucket",
        "STORAGE_ACCESS_KEY_ID": "test-access-key",
        "STORAGE_SECRET_ACCESS_KEY": "test-secret-key",
        "STORAGE_ENDPOINT_URL": "https://storage.railway.app",
        "STORAGE_REGION": "auto",
        "STORAGE_S3_ADDRESSING_STYLE": "virtual",
        "STORAGE_PRESIGNED_URL_TTL_SECONDS": 3600,
    }

    @override_settings(**bucket_settings)
    @patch("media_store.views.get_s3_client")
    def test_image_upload_allows_logged_in_session_without_csrf(
        self, get_s3_client
    ):
        user = get_user_model().objects.create_user(
            username="service@example.com",
            email="service@example.com",
            password="password123",
        )
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)

        s3 = Mock()
        get_s3_client.return_value = s3

        upload = SimpleUploadedFile(
            "image.jpg",
            b"fake image content",
            content_type="image/jpeg",
        )

        response = client.post("/api/uploads/images/", {"file": upload})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertRegex(response.data["href"], r"/api/uploads/.+/file/$")

    @override_settings(**bucket_settings)
    @patch("media_store.views.get_s3_client")
    def test_image_upload_saves_stable_asset_url(self, get_s3_client):
        s3 = Mock()
        get_s3_client.return_value = s3

        upload = SimpleUploadedFile(
            "image.jpg",
            b"fake image content",
            content_type="image/jpeg",
        )

        response = self.client.post("/api/uploads/images/", {"file": upload})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        asset = UploadedAsset.objects.get()
        self.assertEqual(asset.kind, UploadedAsset.KIND_IMAGE)
        self.assertEqual(
            asset.file_url,
            reverse("upload-asset-file", kwargs={"asset_id": asset.id}),
        )
        self.assertEqual(response.data["href"], f"http://testserver{asset.file_url}")
        s3.upload_fileobj.assert_called_once()
        _, bucket, object_key = s3.upload_fileobj.call_args.args
        self.assertEqual(bucket, "test-bucket")
        self.assertEqual(object_key, f"image/{asset.id}.jpg")
        self.assertEqual(
            s3.upload_fileobj.call_args.kwargs["ExtraArgs"],
            {"ContentType": "image/jpeg"},
        )

    @override_settings(**bucket_settings)
    @patch("media_store.views.get_s3_client")
    def test_asset_file_redirects_to_presigned_url(self, get_s3_client):
        asset = UploadedAsset.objects.create(
            kind=UploadedAsset.KIND_IMAGE,
            file_url="/api/uploads/00000000-0000-0000-0000-000000000000/file/",
            original_name="image.jpg",
            content_type="image/jpeg",
        )
        s3 = Mock()
        s3.generate_presigned_url.return_value = (
            "https://test-bucket.storage.railway.app/image.jpg?signature=test"
        )
        get_s3_client.return_value = s3

        response = self.client.get(
            reverse("upload-asset-file", kwargs={"asset_id": asset.id})
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response["Location"], s3.generate_presigned_url.return_value)
        s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": f"image/{asset.id}.jpg"},
            ExpiresIn=3600,
        )
