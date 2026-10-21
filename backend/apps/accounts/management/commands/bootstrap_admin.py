import getpass
import os

import qrcode
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts import services
from apps.accounts.models import Role, User


class Command(BaseCommand):
    help = "Create the first Admin account and print the QR code for its authenticator app."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--display-name", default="")
        parser.add_argument(
            "--password-env", metavar="VAR", help="Read the password from this environment variable instead of asking."
        )

    def handle(self, *args, username, email, display_name, password_env, **options):
        if User.objects.filter(is_active=True, user_roles__role__name=Role.ADMIN).exists():
            raise CommandError("An active Admin already exists. Create more accounts from the console.")
        if password_env:
            password = os.environ.get(password_env, "")
        else:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("The passwords do not match.")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        with transaction.atomic():
            admin_role = Role.objects.get(name=Role.ADMIN)
            user = services.create_user(
                username=username, email=email, display_name=display_name, password=password, role_ids=[admin_role.pk]
            )
            device = TOTPDevice.objects.create(user=user, name="authenticator", confirmed=True)
            User.objects.filter(pk=user.pk).update(mfa_enabled=True)

        self.stdout.write(self.style.SUCCESS(f"Admin '{username}' created."))
        self.stdout.write("Scan this QR code with an authenticator app (you need it to sign in):")
        qr = qrcode.QRCode(border=1)
        qr.add_data(device.config_url)
        qr.print_ascii(out=self.stdout, invert=True)
        self.stdout.write(f"Or enter this setup URL: {device.config_url}")
