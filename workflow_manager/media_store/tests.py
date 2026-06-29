from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import UploadedAsset


class ImageKitUploadTests(APITestCase):
    @override_settings(IMAGEKIT_PRIVATE_KEY="private_test_key")
    @patch("media_store.views.get_imagekit_client")
    def test_image_upload_allows_logged_in_session_without_csrf(
        self, get_imagekit_client
    ):
        user = get_user_model().objects.create_user(
            username="service@example.com",
            email="service@example.com",
            password="password123",
        )
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)

        imagekit = Mock()
        imagekit.files.upload.return_value = SimpleNamespace(
            url="https://ik.imagekit.io/example/authenticated-image.jpg"
        )
        get_imagekit_client.return_value = imagekit

        upload = SimpleUploadedFile(
            "image.jpg",
            b"fake image content",
            content_type="image/jpeg",
        )

        response = client.post("/api/uploads/images/", {"file": upload})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["href"],
            "https://ik.imagekit.io/example/authenticated-image.jpg",
        )

    @override_settings(IMAGEKIT_PRIVATE_KEY="private_test_key")
    @patch("media_store.views.get_imagekit_client")
    def test_image_upload_saves_imagekit_url(self, get_imagekit_client):
        imagekit = Mock()
        imagekit.files.upload.return_value = SimpleNamespace(
            url="https://ik.imagekit.io/example/image.jpg"
        )
        get_imagekit_client.return_value = imagekit

        upload = SimpleUploadedFile(
            "image.jpg",
            b"fake image content",
            content_type="image/jpeg",
        )

        response = self.client.post("/api/uploads/images/", {"file": upload})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["href"], "https://ik.imagekit.io/example/image.jpg"
        )
        asset = UploadedAsset.objects.get()
        self.assertEqual(asset.kind, UploadedAsset.KIND_IMAGE)
        self.assertEqual(asset.file_url, "https://ik.imagekit.io/example/image.jpg")
        imagekit.files.upload.assert_called_once_with(
            file=b"fake image content",
            file_name="image.jpg",
            folder="/image",
            use_unique_file_name=True,
        )

    @override_settings(IMAGEKIT_PRIVATE_KEY="private_test_key")
    @patch("media_store.views.get_imagekit_client")
    def test_image_upload_rejects_missing_imagekit_url(self, get_imagekit_client):
        imagekit = Mock()
        imagekit.files.upload.return_value = SimpleNamespace(url=None)
        get_imagekit_client.return_value = imagekit

        upload = SimpleUploadedFile(
            "image.jpg",
            b"fake image content",
            content_type="image/jpeg",
        )

        response = self.client.post("/api/uploads/images/", {"file": upload})

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(UploadedAsset.objects.count(), 0)
