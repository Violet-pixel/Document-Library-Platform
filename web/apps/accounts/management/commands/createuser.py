import getpass

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Cria uma conta. Ex.: python manage.py createuser --email voce@empresa.com --name 'Seu Nome' --admin"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--admin", action="store_true", help="Cria como administrador.")
        parser.add_argument("--password", help="Se omitida, é pedida no terminal.")

    def handle(self, *args, email, name, admin, password, **options):
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("Já existe uma conta com este e-mail.")
        if not password:
            password = getpass.getpass("Senha: ")
            if password != getpass.getpass("Repita a senha: "):
                raise CommandError("As senhas não conferem.")
        try:
            password_validation.validate_password(password, User(email=email, name=name))
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        role = User.Role.ADMIN if admin else User.Role.MEMBER
        User.objects.create_user(email=email, password=password, name=name, role=role)
        self.stdout.write(self.style.SUCCESS(f"Conta criada: {email} ({role})"))
