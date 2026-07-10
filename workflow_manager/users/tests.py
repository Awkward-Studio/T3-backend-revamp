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
            "admin@example.com": (RoleName.ADMIN, "Changeme"),
            "service@example.com": (RoleName.SERVICE, "Changeme"),
            "biller@example.com": (RoleName.BILLER, "Changeme"),
            "parts@example.com": (RoleName.PARTS, "Changeme"),
            "security@example.com": (RoleName.SECURITY, "Changeme"),
            "caller@example.com": (RoleName.CALLER, "Changeme"),
            "mechanic@example.com": (RoleName.MECHANIC, "Changeme"),
        }

        self.assertEqual(User.objects.count(), len(expected_users))
        for email, (role_name, user_password) in expected_users.items():
            user = User.objects.get(email=email)
            self.assertTrue(user.check_password(user_password))
            self.assertTrue(user.has_role(role_name))

        admin = User.objects.get(email="admin@example.com")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_seed_default_users_resets_default_admin_password(self):
        User = get_user_model()

        call_command("seed_default_users")
        admin = User.objects.get(email="admin@example.com")
        admin.set_password("Changed@2026")
        admin.save(update_fields=["password"])

        call_command("seed_default_users")

        admin.refresh_from_db()
        self.assertTrue(admin.check_password("Changeme"))
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
