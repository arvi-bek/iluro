

from django.contrib import admin
from django.utils import timezone
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from datetime import timedelta
from django.contrib import messages
from .models import (
    Subject, Subscription, Test,
    Question, Choice, UserTest,
    UserAnswer, Profile, UserSubjectPreference, Book, SubjectSectionEntry, EssayTopic,
    PracticeSet, PracticeExercise, PracticeChoice, UserPracticeAttempt, PracticeSetAttempt, BookView,
    GrammarLessonQuestion, GrammarLessonProgress,
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
    list_display = ("id", "title", "subject", "category", "duration", "difficulty", "created_at")
    list_filter = ("subject", "category", "difficulty")
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


class GrammarQuestionInline(admin.TabularInline):
    model = GrammarLessonQuestion
    extra = 2


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


@admin.register(UserSubjectPreference)
class UserSubjectPreferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject", "preferred_level", "updated_at")
    list_filter = ("preferred_level", "subject")
    search_fields = ("user__username", "subject__name")
    autocomplete_fields = ("user", "subject")
    ordering = ("-updated_at",)


# ---------------- BOOK ----------------
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "grade", "access_level", "author", "viewer_count", "has_pdf", "is_featured", "created_at")
    list_filter = ("subject", "grade", "access_level", "is_featured", "created_at")
    search_fields = ("title", "author", "subject__name", "grade")
    autocomplete_fields = ("subject",)
    ordering = ("-is_featured", "-created_at")

    def has_pdf(self, obj):
        return bool(obj.pdf_file)
    has_pdf.boolean = True
    has_pdf.short_description = "PDF"

    @admin.display(description="Просмотр")
    def viewer_count(self, obj):
        return obj.views.aggregate(total=Coalesce(Sum("view_count"), Value(0))).get("total", 0)


@admin.register(BookView)
class BookViewAdmin(admin.ModelAdmin):
    list_display = ("id", "book", "user", "view_count", "first_viewed_at", "last_viewed_at")
    list_filter = ("book__subject", "first_viewed_at", "last_viewed_at")
    search_fields = ("book__title", "user__username", "book__subject__name")
    autocomplete_fields = ("book", "user")
    ordering = ("-last_viewed_at",)


# ---------------- SUBJECT SECTION ENTRY ----------------
@admin.register(SubjectSectionEntry)
class SubjectSectionEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "section_key", "access_level", "order", "is_featured", "created_at")
    list_filter = ("subject", "section_key", "access_level", "is_featured", "created_at")
    search_fields = ("title", "summary", "body", "usage_note", "subject__name")
    autocomplete_fields = ("subject",)
    ordering = ("subject", "section_key", "order", "-created_at")
    inlines = [GrammarQuestionInline]
    fields = (
        "subject",
        "section_key",
        "title",
        "summary",
        "body",
        "usage_note",
        "access_level",
        "order",
        "is_featured",
    )

    def get_inline_instances(self, request, obj=None):
        if obj and obj.section_key == "grammar":
            return super().get_inline_instances(request, obj)
        return []


@admin.register(GrammarLessonQuestion)
class GrammarLessonQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "order", "short_prompt", "correct_option")
    list_filter = ("lesson__subject", "lesson__access_level")
    search_fields = ("prompt", "lesson__title", "lesson__subject__name")
    autocomplete_fields = ("lesson",)
    ordering = ("lesson", "order", "id")

    @admin.display(description="Savol")
    def short_prompt(self, obj):
        return obj.prompt[:80]


@admin.register(GrammarLessonProgress)
class GrammarLessonProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "lesson", "best_score", "last_score", "attempts_count", "is_completed", "completed_at")
    list_filter = ("is_completed", "lesson__subject", "lesson__access_level", "completed_at")
    search_fields = ("user__username", "lesson__title", "lesson__subject__name")
    autocomplete_fields = ("user", "lesson")
    ordering = ("-updated_at",)


@admin.register(EssayTopic)
class EssayTopicAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "access_level", "is_featured", "created_at")
    list_filter = ("subject", "access_level", "is_featured", "created_at")
    search_fields = ("title", "prompt_text", "thesis_hint", "subject__name")
    autocomplete_fields = ("subject",)
    ordering = ("-is_featured", "-created_at")


@admin.register(PracticeExercise)
class PracticeExerciseAdmin(admin.ModelAdmin):
    list_display = ("id", "display_label", "practice_set", "subject", "answer_mode", "difficulty", "is_featured", "created_at")
    list_filter = ("subject", "practice_set", "answer_mode", "difficulty", "is_featured", "created_at")
    search_fields = ("title", "prompt", "practice_set__title", "subject__name")
    autocomplete_fields = ("subject", "practice_set")
    inlines = [PracticeChoiceInline]
    ordering = ("-is_featured", "-created_at")
    fields = ("practice_set", "title", "prompt", "answer_mode", "correct_text", "difficulty", "is_featured", "explanation")

    @admin.display(description="Topshiriq")
    def display_label(self, obj):
        return obj.title or obj.prompt[:80]


@admin.register(PracticeSet)
class PracticeSetAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "topic", "source_book", "difficulty", "exercise_count", "is_featured", "created_at")
    list_filter = ("subject", "difficulty", "is_featured", "created_at")
    search_fields = ("title", "topic", "source_book", "description", "subject__name")
    autocomplete_fields = ("subject",)
    ordering = ("-is_featured", "-created_at")

    @admin.display(description="Misollar soni")
    def exercise_count(self, obj):
        return obj.exercises.count()


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
    list_display = ("id", "user", "practice_session", "exercise", "selected_choice", "answer_text", "is_correct", "created_at")
    list_filter = ("is_correct", "exercise__subject", "exercise__difficulty", "created_at")
    search_fields = ("user__username", "exercise__title", "answer_text", "practice_session__practice_set__title")
    autocomplete_fields = ("user", "exercise", "practice_session")
    ordering = ("-created_at",)


@admin.register(PracticeSetAttempt)
class PracticeSetAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "practice_set", "score", "correct_count", "total_count", "created_at")
    list_filter = ("practice_set__subject", "practice_set__difficulty", "created_at")
    search_fields = ("user__username", "practice_set__title", "practice_set__topic")
    autocomplete_fields = ("user", "practice_set")
    ordering = ("-created_at",)



