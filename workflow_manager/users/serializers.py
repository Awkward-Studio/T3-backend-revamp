from rest_framework import serializers
from .models import CustomUser, Label


class LabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = ["id", "name"]


class UserSerializer(serializers.ModelSerializer):
    # serialize labels as list of names; create new ones on write
    labels = LabelSerializer(many=True)

    # DRF handles JSONField automatically
    preferences = serializers.JSONField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "labels",
            "preferences",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        labels_data = validated_data.pop("labels", [])
        user = CustomUser.objects.create_user(**validated_data)
        for lbl in labels_data:
            label_obj, _ = Label.objects.get_or_create(name=lbl["name"])
            user.labels.add(label_obj)
        return user

    def update(self, instance, validated_data):
        labels_data = validated_data.pop("labels", None)
        if labels_data is not None:
            instance.labels.clear()
            for lbl in labels_data:
                label_obj, _ = Label.objects.get_or_create(name=lbl["name"])
                instance.labels.add(label_obj)

        # preferences is JSON, so a simple assignment replaces it
        prefs = validated_data.pop("preferences", None)
        if prefs is not None:
            instance.preferences = prefs

        return super().update(instance, validated_data)
