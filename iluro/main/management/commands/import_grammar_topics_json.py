import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from main.models import GrammarLessonQuestion, Subject, SubjectSectionEntry
from main.utils import normalize_difficulty_label


class Command(BaseCommand):
    help = "JSON fayldan grammatika mavzulari va mini test savollarini import qiladi."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="JSON fayl yo'li")
        parser.add_argument("--subject", help="Fan nomi yoki ID. JSON dagi qiymatni override qiladi.")
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Importdan oldin shu fan uchun grammar bo'limidagi eski mavzularni o'chiradi.",
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

        topics = payload.get("topics") or []
        if not topics:
            raise CommandError("JSON ichida topics bo'sh.")

        subject_ref = options.get("subject") or payload.get("subject_name") or payload.get("subject")
        subject = self._resolve_subject(subject_ref)
        access_level = normalize_difficulty_label((payload.get("access_level") or "C").strip() or "C")
        valid_levels = {choice[0] for choice in SubjectSectionEntry._meta.get_field("access_level").choices}
        if access_level not in valid_levels:
            raise CommandError(
                f"Noto'g'ri access_level: {access_level}. Mavjudlari: {', '.join(sorted(valid_levels))}"
            )

        if options["clear_existing"]:
            deleted_count, _ = SubjectSectionEntry.objects.filter(
                subject=subject,
                section_key="grammar",
            ).delete()
            self.stdout.write(self.style.WARNING(f"Eski grammar yozuvlari o'chirildi: {deleted_count}"))

        created_count = 0
        updated_count = 0
        question_count = 0

        for index, item in enumerate(topics, start=1):
            if not isinstance(item, dict):
                raise CommandError(f"{index}-topic dict emas.")

            title = (item.get("title") or "").strip()
            summary = (item.get("summary") or "").strip()
            body = (item.get("body") or "").strip()
            usage_note = (item.get("usage_note") or "").strip()
            questions = item.get("questions") or []

            if not title:
                raise CommandError(f"{index}-topic uchun title majburiy.")
            if not questions:
                raise CommandError(f"{title} uchun kamida 1 ta savol kerak.")

            lesson, created = SubjectSectionEntry.objects.update_or_create(
                subject=subject,
                section_key="grammar",
                title=title,
                defaults={
                    "summary": summary,
                    "body": body,
                    "usage_note": usage_note,
                    "access_level": normalize_difficulty_label((item.get("access_level") or access_level).strip() or access_level),
                    "order": item.get("order", index),
                    "is_featured": bool(item.get("is_featured", False)),
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

            lesson.grammar_questions.all().delete()

            for question_order, question in enumerate(questions, start=1):
                if not isinstance(question, dict):
                    raise CommandError(f"{title} mavzusidagi {question_order}-savol dict emas.")

                prompt = (question.get("prompt") or "").strip()
                option_a = (question.get("option_a") or "").strip()
                option_b = (question.get("option_b") or "").strip()
                option_c = (question.get("option_c") or "").strip()
                option_d = (question.get("option_d") or "").strip()
                correct_option = (question.get("correct_option") or "").strip().upper()

                if not prompt:
                    raise CommandError(f"{title} mavzusidagi {question_order}-savol uchun prompt majburiy.")
                if not all([option_a, option_b, option_c, option_d]):
                    raise CommandError(f"{title} mavzusidagi {question_order}-savol uchun barcha 4 variant majburiy.")
                if correct_option not in {"A", "B", "C", "D"}:
                    raise CommandError(f"{title} mavzusidagi {question_order}-savol uchun correct_option A/B/C/D bo'lishi kerak.")

                GrammarLessonQuestion.objects.create(
                    lesson=lesson,
                    prompt=prompt,
                    option_a=option_a,
                    option_b=option_b,
                    option_c=option_c,
                    option_d=option_d,
                    correct_option=correct_option,
                    explanation=(question.get("explanation") or "").strip(),
                    order=question.get("order", question_order),
                )
                question_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Grammar import tugadi: {created_count} ta yangi, {updated_count} ta yangilandi, "
                f"{question_count} ta savol qo'shildi."
            )
        )

    def _resolve_subject(self, subject_ref):
        if not subject_ref:
            raise CommandError("Fan topilmadi. JSON ichida subject_name yoki --subject kerak.")

        if str(subject_ref).isdigit():
            subject = Subject.objects.filter(id=int(subject_ref)).first()
        else:
            subject = Subject.objects.filter(name__iexact=str(subject_ref)).first()
            if not subject:
                subject = Subject.objects.filter(name__icontains=str(subject_ref)).first()

        if not subject:
            raise CommandError(f"Fan topilmadi: {subject_ref}")

        return subject
