from rest_framework import serializers

from .models import CustomUser, Label, Role, RoleName
from .user_management import (
    VALID_ROLE_NAMES,
    build_preferences,
    extract_advisor_roles,
    normalize_role_name,
)


class LabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = ["id", "name"]


class UserSerializer(serializers.ModelSerializer):
    # serialize labels as list of names; create new ones on write
    labels = LabelSerializer(many=True, required=False)

    # DRF handles JSONField automatically
    preferences = serializers.JSONField(required=False)
    role = serializers.ChoiceField(
        choices=RoleName.ALL,
        required=False,
        allow_null=True,
        write_only=True,
    )
    current_role = serializers.SerializerMethodField(read_only=True)
    advisor_roles = serializers.SerializerMethodField(read_only=True)
    created_date = serializers.DateTimeField(source="date_joined", read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

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
            "role",
            "current_role",
            "advisor_roles",
            "created_date",
            "password",
        ]
        read_only_fields = ["id"]

    def get_current_role(self, obj):
        return obj.get_primary_role()

    def get_advisor_roles(self, obj):
        return extract_advisor_roles(obj.preferences)

    def validate_email(self, value):
        email = value.strip().lower()
        qs = CustomUser.objects.filter(email__iexact=email)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_role(self, value):
        normalized_role = normalize_role_name(value)
        if normalized_role is None:
            return None
        if normalized_role not in VALID_ROLE_NAMES:
            raise serializers.ValidationError("Invalid role.")
        return normalized_role

    def validate(self, attrs):
        role_name = attrs.get("role")
        prefs = attrs.get("preferences")

        if self.instance is None:
            if not attrs.get("password"):
                raise serializers.ValidationError(
                    {"password": "This field is required."}
                )
            if not role_name:
                raise serializers.ValidationError({"role": "This field is required."})
        elif role_name is None:
            role_name = self.instance.get_primary_role()

        if prefs is not None and not isinstance(prefs, dict):
            raise serializers.ValidationError(
                {"preferences": "This field must be a JSON object."}
            )

        if role_name != RoleName.SERVICE:
            advisor_roles = extract_advisor_roles(prefs)
            if advisor_roles:
                raise serializers.ValidationError(
                    {
                        "preferences": "Advisor roles are only available for service users."
                    }
                )

        return attrs

    def create(self, validated_data):
        labels_data = validated_data.pop("labels", [])
        role_name = validated_data.pop("role", None)
        password = validated_data.pop("password")
        preferences = build_preferences(
            validated_data.pop("preferences", None),
            role_name=role_name,
        )
        email = validated_data.get("email", "")
        if not validated_data.get("username"):
            validated_data["username"] = email
        user = CustomUser.objects.create_user(**validated_data)
        user.email = email
        user.username = email
        user.preferences = preferences
        user.set_password(password)
        user.save(update_fields=["email", "username", "preferences", "password"])
        for lbl in labels_data:
            label_obj, _ = Label.objects.get_or_create(name=lbl["name"])
            user.labels.add(label_obj)
        if role_name:
            role_obj, _ = Role.objects.get_or_create(name=role_name)
            user.roles.set([role_obj])
        return user

    def update(self, instance, validated_data):
        labels_data = validated_data.pop("labels", None)
        role_name = validated_data.pop("role", None)
        password = validated_data.pop("password", None)

        if labels_data is not None:
            instance.labels.clear()
            for lbl in labels_data:
                label_obj, _ = Label.objects.get_or_create(name=lbl["name"])
                instance.labels.add(label_obj)

        effective_role = (
            role_name if role_name is not None else instance.get_primary_role()
        )
        if role_name is not None:
            role_obj, _ = Role.objects.get_or_create(name=role_name)
            instance.roles.set([role_obj])

        prefs = validated_data.pop("preferences", None)
        instance.preferences = build_preferences(
            instance.preferences,
            role_name=effective_role,
            prefs_payload=prefs,
        )

        email = validated_data.get("email")
        if email is not None:
            validated_data["email"] = email
            validated_data["username"] = email

        instance = super().update(instance, validated_data)

        if password:
            instance.set_password(password)
            instance.save(update_fields=["password"])

        return instance
