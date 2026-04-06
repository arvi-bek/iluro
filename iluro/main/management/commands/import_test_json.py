import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from main.services import import_test_from_json_payload, resolve_subject_ref


class Command(BaseCommand):
    help = "JSON fayldan Test, Question va Choice yozuvlarini import qiladi."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="JSON fayl yo'li")
        parser.add_argument("--subject", help="Fan nomi yoki ID. JSON dagi qiymatni override qiladi.")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Agar shu subject/title/difficulty dagi test mavjud bo'lsa, savollarini tozalab qayta yozadi.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"]).expanduser()
        if not file_path.exists():
            raise CommandError(f"JSON fayl topilmadi: {file_path}")

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON format xato: {exc}") from exc

        if not isinstance(payload, dict):
            raise CommandError("JSON top-level dict bo'lishi kerak.")

        subject_override = None
        if options.get("subject"):
            subject_override = resolve_subject_ref(options["subject"])

        try:
            result = import_test_from_json_payload(
                payload,
                subject_override=subject_override,
                replace=options["replace"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        action = "yaratildi" if result["created"] else "yangilandi"
        self.stdout.write(
            self.style.SUCCESS(
                f"Test {action}: {result['test'].title} | {result['subject'].name} | {result['test'].difficulty}. "
                f"Savollar: {result['created_questions']}, variantlar: {result['created_choices']}."
            )
        )
