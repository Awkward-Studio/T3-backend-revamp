from rest_framework import serializers

from .models import UploadedAsset


class UploadedAssetSerializer(serializers.ModelSerializer):
    href = serializers.SerializerMethodField()

    class Meta:
        model = UploadedAsset
        fields = [
            "id",
            "kind",
            "original_name",
            "content_type",
            "created_at",
            "href",
        ]
        read_only_fields = fields

    def get_href(self, obj):
        request = self.context.get("request")
        if not obj.file_url:
            return None
        url = obj.file_url
        return request.build_absolute_uri(url) if request else url
