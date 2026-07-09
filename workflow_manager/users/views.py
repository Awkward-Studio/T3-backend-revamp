from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from .models import CustomUser, Label
from .permissions import IsAdmin
from .serializers import LabelSerializer, UserSerializer


@extend_schema_view(
    get=extend_schema(
        summary="List labels",
        description="Retrieve all labels.",
        tags=["Labels"],
        responses={200: LabelSerializer(many=True)},
    ),
    post=extend_schema(
        summary="Create a label",
        description="Create a new label.",
        tags=["Labels"],
        request=LabelSerializer,
        responses={201: LabelSerializer},
    ),
)
class LabelListCreate(GenericAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    serializer_class = LabelSerializer

    def get(self, request):
        labels = Label.objects.all()
        serializer = self.get_serializer(labels, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve a label",
        description="Retrieve a label by id.",
        tags=["Labels"],
        responses={200: LabelSerializer},
    ),
    put=extend_schema(
        summary="Update a label",
        description="Replace a label by id.",
        tags=["Labels"],
        request=LabelSerializer,
        responses={200: LabelSerializer},
    ),
    delete=extend_schema(
        summary="Delete a label",
        description="Delete a label by id.",
        tags=["Labels"],
        responses={204: None},
    ),
)
class LabelDetail(GenericAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    serializer_class = LabelSerializer

    def get_object(self, pk):
        return get_object_or_404(Label, pk=pk)

    def get(self, request, pk):
        label = self.get_object(pk)
        serializer = self.get_serializer(label)
        return Response(serializer.data)

    def put(self, request, pk):
        label = self.get_object(pk)
        serializer = self.get_serializer(label, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        label = self.get_object(pk)
        label.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(
        summary="List users",
        description="Retrieve users, optionally filtered by role.",
        tags=["Users"],
        responses={200: UserSerializer(many=True)},
    ),
    post=extend_schema(
        summary="Create a user",
        description="Create a user account.",
        tags=["Users"],
        request=UserSerializer,
        responses={201: UserSerializer},
    ),
)
class UserListCreate(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]

    def get(self, request):
        users = CustomUser.objects.all().order_by("id")
        role = (request.query_params.get("role") or "").strip().lower()
        if role:
            users = users.filter(roles__name=role).distinct()
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                self.get_serializer(user).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve a user",
        description="Retrieve a user by id.",
        tags=["Users"],
        responses={200: UserSerializer},
    ),
    put=extend_schema(
        summary="Update a user",
        description="Replace a user by id.",
        tags=["Users"],
        request=UserSerializer,
        responses={200: UserSerializer},
    ),
    patch=extend_schema(
        summary="Partially update a user",
        description="Update a subset of user fields.",
        tags=["Users"],
        request=UserSerializer,
        responses={200: UserSerializer},
    ),
    delete=extend_schema(
        summary="Delete a user",
        description="Delete a user by id.",
        tags=["Users"],
        responses={204: None},
    ),
)
class UserDetail(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.request.method in {"PUT", "PATCH", "DELETE"}:
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]

    def get_object(self, pk):
        return get_object_or_404(CustomUser, pk=pk)

    def get(self, request, pk):
        user = self.get_object(pk)
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    def put(self, request, pk):
        user = self.get_object(pk)
        serializer = self.get_serializer(user, data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(self.get_serializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        user = self.get_object(pk)
        serializer = self.get_serializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            user = serializer.save()
            return Response(self.get_serializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        user = self.get_object(pk)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
