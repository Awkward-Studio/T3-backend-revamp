from rest_framework.permissions import BasePermission

from .models import RoleName


class HasAnyRole(BasePermission):
    required_roles = ()
    admin_bypass = True

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if self.admin_bypass and user.has_role(RoleName.ADMIN):
            return True

        if not self.required_roles:
            return False

        return user.has_any_role(self.required_roles)


class IsAdmin(HasAnyRole):
    required_roles = (RoleName.ADMIN,)
    admin_bypass = False


class IsServiceOrAdmin(HasAnyRole):
    required_roles = (RoleName.SERVICE,)


class IsBillerOrAdmin(HasAnyRole):
    required_roles = (RoleName.BILLER,)


class IsPartsOrAdmin(HasAnyRole):
    required_roles = (RoleName.PARTS,)


class IsSecurityOrAdmin(HasAnyRole):
    required_roles = (RoleName.SECURITY,)


class IsCallerOrAdmin(HasAnyRole):
    required_roles = (RoleName.CALLER,)
