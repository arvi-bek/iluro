import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from main.models import Subject, SubjectSectionEntry
from main.utils import normalize_difficulty_label


class Command(BaseCommand):
    help = (
        "JSON fayldan SubjectSectionEntry yozuvlarini import qiladi. "
        "Atamalar, xronologiya, formulalar va boshqa sectionlar uchun ishlaydi."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="JSON fayl yo'li")
        parser.add_argument("--subject", help="Fan nomi yoki ID")
        parser.add_argument("--section", help="Section key: terms, chronology, formulas, grammar va h.k.")
        parser.add_argument(
            "--clear-section",
            action="store_true",
            help="Importdan oldin shu subject/section dagi eski yozuvlarni o'chiradi",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"]).expanduser()
        if not file_path.exists():
            raise CommandError(f"JSON fayl topilmadi: {file_path}")

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON format xato: {exc}") from exc

        if isinstance(payload, dict):
            entries = payload.get("entries", [])
            subject_ref = options.get("subject") or payload.get("subject")
            section_key = options.get("section") or payload.get("section_key")
        elif isinstance(payload, list):
            entries = payload
            subject_ref = options.get("subject")
            section_key = options.get("section")
        else:
            raise CommandError("JSON top-level list yoki dict bo'lishi kerak.")

        if not entries:
            raise CommandError("Import qilinadigan entries topilmadi.")

        subject = self._resolve_subject(subject_ref)
        if not section_key:
            raise CommandError("--section berilmagan va JSON ichida section_key topilmadi.")

        valid_sections = {choice[0] for choice in SubjectSectionEntry.SECTION_CHOICES}
        if section_key not in valid_sections:
            raise CommandError(
                f"Noto'g'ri section key: {section_key}. "
                f"Mavjudlari: {', '.join(sorted(valid_sections))}"
            )

        if options["clear_section"]:
            deleted_count, _ = SubjectSectionEntry.objects.filter(
                subject=subject,
                section_key=section_key,
            ).delete()
            self.stdout.write(self.style.WARNING(f"Eski yozuvlar o'chirildi: {deleted_count}"))

        created_count = 0
        updated_count = 0

        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise CommandError(f"{index}-entry dict emas.")

            title = (entry.get("title") or "").strip()
            if not title:
                raise CommandError(f"{index}-entry uchun title majburiy.")

            defaults = {
                "summary": (entry.get("summary") or "").strip(),
                "body": (entry.get("body") or "").strip(),
                "usage_note": (entry.get("usage_note") or "").strip(),
                "access_level": normalize_difficulty_label((entry.get("access_level") or "C").strip() or "C"),
                "order": entry.get("order", index),
                "is_featured": bool(entry.get("is_featured", False)),
            }

            obj, created = SubjectSectionEntry.objects.update_or_create(
                subject=subject,
                section_key=section_key,
                title=title,
                defaults=defaults,
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import tugadi: {created_count} ta yangi, {updated_count} ta yangilandi "
                f"(subject={subject.name}, section={section_key})."
            )
        )

    def _resolve_subject(self, subject_ref):
        if not subject_ref:
            raise CommandError("--subject berilmagan va JSON ichida subject topilmadi.")

        if str(subject_ref).isdigit():
            subject = Subject.objects.filter(id=int(subject_ref)).first()
        else:
            subject = Subject.objects.filter(name__iexact=str(subject_ref)).first()
            if not subject:
                subject = Subject.objects.filter(name__icontains=str(subject_ref)).first()

        if not subject:
            raise CommandError(f"Fan topilmadi: {subject_ref}")

        return subject
