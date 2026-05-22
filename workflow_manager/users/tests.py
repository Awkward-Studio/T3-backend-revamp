from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from users.models import RoleName


class SeedDefaultUsersTests(TestCase):
    def test_seed_default_users_is_idempotent(self):
        User = get_user_model()

        call_command("seed_default_users")
        call_command("seed_default_users")

        expected_users = {
            "admin@example.local": RoleName.ADMIN,
            "service@example.local": RoleName.SERVICE,
            "biller@example.local": RoleName.BILLER,
            "parts@example.local": RoleName.PARTS,
            "security@example.local": RoleName.SECURITY,
            "caller@example.local": RoleName.CALLER,
        }

        self.assertEqual(User.objects.count(), len(expected_users))
        for email, role_name in expected_users.items():
            user = User.objects.get(email=email)
            self.assertTrue(user.check_password("Example@2026"))
            self.assertTrue(user.has_role(role_name))

        admin = User.objects.get(email="admin@example.local")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
