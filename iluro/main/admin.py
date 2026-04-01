

from django.contrib import admin
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from .models import (
    Subject, Subscription, Test,
    Question, Choice, UserTest,
    UserAnswer, Profile, Book, SubjectSectionEntry, EssayTopic,
    PracticeExercise, PracticeChoice, UserPracticeAttempt,
)


# ---------------- SUBJECT ----------------
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "price")
    search_fields = ("name",)
    list_filter = ("price",)
    ordering = ("name",)


# ---------------- SUBSCRIPTION ----------------
@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject", "status_badge", "purchased_at", "end_date")
    list_filter = ("subject", "purchased_at", "end_date")
    search_fields = ("user__username", "subject__name")
    autocomplete_fields = ("user", "subject")
    ordering = ("-purchased_at",)
    fields = ("user", "subject", "end_date")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial["end_date"] = timezone.localtime(timezone.now() + timedelta(days=30))
        return initial

    def status_badge(self, obj):
        return "Faol" if obj.is_active else "Tugagan"
    status_badge.short_description = "Holati"

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return

        existing = (
            Subscription.objects.filter(user=obj.user, subject=obj.subject)
            .exclude(pk=obj.pk)
            .first()
        )

        if existing:
            base_date = existing.end_date if existing.end_date >= timezone.now() else timezone.now()
            requested_end_date = obj.end_date or (timezone.now() + timedelta(days=30))
            extension = requested_end_date - timezone.now()
            if extension <= timedelta(0):
                extension = timedelta(days=30)

            existing.end_date = base_date + extension
            existing.save(update_fields=["end_date"])
            self.message_user(
                request,
                f"{existing.user.username} uchun {existing.subject.name} obunasi uzaytirildi.",
                level=messages.SUCCESS,
            )
            return

        super().save_model(request, obj, form, change)


# ---------------- TEST ----------------
@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "duration", "difficulty", "created_at")
    list_filter = ("subject", "difficulty")
    search_fields = ("title",)
    autocomplete_fields = ("subject",)
    ordering = ("-created_at",)


# ---------------- CHOICE INLINE ----------------
class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4


class PracticeChoiceInline(admin.TabularInline):
    model = PracticeChoice
    extra = 4


# ---------------- QUESTION ----------------
@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "short_text", "test", "difficulty", "correct_answer_preview")
    list_filter = ("difficulty", "test__subject")
    search_fields = ("text",)
    autocomplete_fields = ("test",)
    inlines = [ChoiceInline]

    def short_text(self, obj):
        return obj.text[:50]
    short_text.short_description = "Question"

    def correct_answer_preview(self, obj):
        correct_choice = obj.choice_set.filter(is_correct=True).first()
        return correct_choice.text if correct_choice else "-"
    correct_answer_preview.short_description = "Correct Choice"


# ---------------- CHOICE ----------------
@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "text", "question", "is_correct")
    list_filter = ("is_correct", "question__test__subject")
    search_fields = ("text",)
    autocomplete_fields = ("question",)


# ---------------- USER TEST ----------------
@admin.register(UserTest)
class UserTestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "test", "score", "correct_count", "started_at", "finished_at")
    list_filter = ("test__subject", "started_at")
    search_fields = ("user__username", "test__title")
    autocomplete_fields = ("user", "test")
    readonly_fields = ("snapshot_json",)
    ordering = ("-started_at",)


# ---------------- USER ANSWER ----------------
@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "question", "selected_choice", "is_correct")
    list_filter = ("is_correct", "question__test__subject")
    search_fields = ("user__username",)
    autocomplete_fields = ("user", "question", "selected_choice")


# ---------------- PROFILE ----------------
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "full_name", "role", "theme", "level", "xp", "subject_count", "premium_until", "created_at")
    search_fields = ("user__username", "full_name")
    autocomplete_fields = ("user",)
    readonly_fields = ("purchased_subjects_summary",)

    def subject_count(self, obj):
        return obj.user.subscription_set.count()
    subject_count.short_description = "Fanlar"

    def purchased_subjects_summary(self, obj):
        subscriptions = obj.user.subscription_set.select_related("subject").order_by("-end_date")
        if not subscriptions:
            return "Fan biriktirilmagan"

        lines = []
        now = timezone.now()
        for subscription in subscriptions:
            status = "Faol" if subscription.end_date >= now else "Tugagan"
            lines.append(
                f"{subscription.subject.name} - {status} - {subscription.end_date:%d.%m.%Y %H:%M}"
            )
        return "\n".join(lines)
    purchased_subjects_summary.short_description = "Sotib olingan fanlar"


# ---------------- BOOK ----------------
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "access_level", "author", "has_pdf", "is_featured", "created_at")
    list_filter = ("subject", "access_level", "is_featured", "created_at")
    search_fields = ("title", "author", "subject__name")
    autocomplete_fields = ("subject",)
    ordering = ("-is_featured", "-created_at")

    def has_pdf(self, obj):
        return bool(obj.pdf_file)
    has_pdf.boolean = True
    has_pdf.short_description = "PDF"


# ---------------- SUBJECT SECTION ENTRY ----------------
@admin.register(SubjectSectionEntry)
class SubjectSectionEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "section_key", "access_level", "order", "is_featured", "created_at")
    list_filter = ("subject", "section_key", "access_level", "is_featured", "created_at")
    search_fields = ("title", "summary", "body", "subject__name")
    autocomplete_fields = ("subject",)
    ordering = ("subject", "section_key", "order", "-created_at")


@admin.register(EssayTopic)
class EssayTopicAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "access_level", "is_featured", "created_at")
    list_filter = ("subject", "access_level", "is_featured", "created_at")
    search_fields = ("title", "prompt_text", "thesis_hint", "subject__name")
    autocomplete_fields = ("subject",)
    ordering = ("-is_featured", "-created_at")


@admin.register(PracticeExercise)
class PracticeExerciseAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "topic", "source_book", "answer_mode", "difficulty", "is_featured", "created_at")
    list_filter = ("subject", "answer_mode", "difficulty", "is_featured", "created_at")
    search_fields = ("title", "topic", "source_book", "prompt", "subject__name")
    autocomplete_fields = ("subject",)
    inlines = [PracticeChoiceInline]
    ordering = ("-is_featured", "-created_at")


@admin.register(PracticeChoice)
class PracticeChoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "short_text", "exercise", "is_correct")
    list_filter = ("is_correct", "exercise__subject", "exercise__difficulty")
    search_fields = ("text", "exercise__title", "exercise__topic")
    autocomplete_fields = ("exercise",)
    ordering = ("exercise", "id")

    def short_text(self, obj):
        return obj.text[:60]
    short_text.short_description = "Variant"


@admin.register(UserPracticeAttempt)
class UserPracticeAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "exercise", "selected_choice", "answer_text", "is_correct", "created_at")
    list_filter = ("is_correct", "exercise__subject", "exercise__difficulty", "created_at")
    search_fields = ("user__username", "exercise__title", "answer_text")
    autocomplete_fields = ("user", "exercise")
    ordering = ("-created_at",)



