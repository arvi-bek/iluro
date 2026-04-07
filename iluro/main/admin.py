

from django.contrib import admin
from django import forms
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from datetime import timedelta
from django.contrib import messages
from .models import (
    Subject, Subscription, SubscriptionPlan, UserSubscription, UserSubscriptionSubject, Test,
    Question, Choice, UserTest,
    UserAnswer, Profile, UserSubjectPreference, Book, SubjectSectionEntry, EssayTopic,
    PracticeSet, PracticeExercise, PracticeChoice, UserPracticeAttempt, PracticeSetAttempt, BookView,
    GrammarLessonQuestion, GrammarLessonProgress, UserStatSummary,
)
from .services import (
    import_assessment_from_payload,
    import_essay_topics_from_payload,
    import_grammar_topics_from_payload,
    import_subject_entries_from_payload,
    load_json_payload_from_text,
    get_user_subject_access_rows,
)
from .utils import get_level_choices, get_level_info, get_level_min_xp

EssayTopic._meta.verbose_name = "Esse mavzusi"
EssayTopic._meta.verbose_name_plural = "Esse mavzulari"


IMPORT_KIND_CHOICES = [
    ("assessment", "Mashqlar"),
    ("grammar", "Gramatika"),
    ("terms", "Atamalar"),
    ("chronology", "Xronologiya"),
    ("events", "Sanalar / Voqealar"),
    ("formulas", "Formulalar"),
    ("rules", "Qoidalar"),
    ("extras", "Qo'shimcha ma'lumotlar"),
    ("essay", "Esse"),
]


class ContentImportCenterForm(forms.Form):
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.order_by("name"),
        required=True,
        label="Fan",
    )
    import_kind = forms.ChoiceField(
        choices=IMPORT_KIND_CHOICES,
        required=True,
        label="Import turi",
    )
    replace_existing = forms.BooleanField(
        required=False,
        label="Mavjud ma'lumotni yangilash / tozalash",
        help_text="Assessmentlarda replace, qolgan bloklarda esa eski ma'lumotni tozalash sifatida ishlaydi.",
    )
    json_text = forms.CharField(
        required=True,
        label="JSON matni",
        widget=forms.Textarea(attrs={"rows": 22, "class": "vLargeTextField"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        subject = cleaned_data.get("subject")
        import_kind = cleaned_data.get("import_kind")
        json_text = (cleaned_data.get("json_text") or "").strip()

        if not subject or not import_kind or not json_text:
            return cleaned_data

        try:
            payload = load_json_payload_from_text(json_text)
        except Exception as exc:
            raise forms.ValidationError(str(exc)) from exc

        allowed_kinds = get_allowed_import_kinds(subject.name)
        if import_kind not in allowed_kinds:
            raise forms.ValidationError("Tanlangan fan uchun bu import turi mos emas.")

        cleaned_data["payload"] = payload
        return cleaned_data


def get_allowed_import_kinds(subject_name):
    normalized = (subject_name or "").strip().lower()
    if "tarix" in normalized:
        return {"assessment", "terms", "chronology", "events"}
    if "matem" in normalized:
        return {"assessment", "formulas"}
    return {"assessment", "grammar", "rules", "essay", "extras"}


def import_center_view(request):
    if request.method == "POST":
        form = ContentImportCenterForm(request.POST)
        if form.is_valid():
            subject = form.cleaned_data["subject"]
            payload = form.cleaned_data["payload"]
            import_kind = form.cleaned_data["import_kind"]
            replace_existing = form.cleaned_data.get("replace_existing", False)

            try:
                if import_kind == "assessment":
                    result = import_assessment_from_payload(
                        payload,
                        subject_override=subject,
                        replace=replace_existing,
                    )
                    messages.success(
                        request,
                        (
                            f"Mashqlar import tugadi: {result['created_sets']} ta yangi set, "
                            f"{result['updated_sets']} ta yangilandi, {result['created_exercises']} ta "
                            f"topshiriq va {result['created_choices']} ta variant qo'shildi."
                        ),
                    )
                elif import_kind == "grammar":
                    result = import_grammar_topics_from_payload(
                        payload,
                        subject_override=subject,
                        clear_existing=replace_existing,
                    )
                    messages.success(
                        request,
                        (
                            f"Gramatika import tugadi: {result['created_count']} ta yangi, "
                            f"{result['updated_count']} ta yangilandi, {result['question_count']} ta savol qo'shildi."
                        ),
                    )
                elif import_kind == "essay":
                    result = import_essay_topics_from_payload(
                        payload,
                        subject_override=subject,
                        clear_existing=replace_existing,
                    )
                    messages.success(
                        request,
                        (
                            f"Esse import tugadi: {result['created_count']} ta yangi, "
                            f"{result['updated_count']} ta yangilandi."
                        ),
                    )
                else:
                    result = import_subject_entries_from_payload(
                        payload,
                        subject_override=subject,
                        section_key=import_kind,
                        clear_section=replace_existing,
                    )
                    messages.success(
                        request,
                        (
                            f"Section import tugadi: {result['created_count']} ta yangi, "
                            f"{result['updated_count']} ta yangilandi "
                            f"(section={result['section_key']})."
                        ),
                    )
            except Exception as exc:
                form.add_error(None, str(exc))
            else:
                return redirect("content_import_center")
    else:
        form = ContentImportCenterForm()

    context = {
        **admin.site.each_context(request),
        "title": "Kontent import markazi",
        "subtitle": "Fan tanlang, turini belgilang va JSON matnini kiriting",
        "form": form,
        "import_options_map": {
            "math": ["assessment", "formulas"],
            "history": ["assessment", "terms", "chronology", "events"],
            "language": ["assessment", "grammar", "rules", "essay", "extras"],
        },
    }
    return TemplateResponse(request, "admin/import_center.html", context)


class HiddenLegacyAdminMixin:
    def get_model_perms(self, request):
        return {}


class ProfileAdminForm(forms.ModelForm):
    level_override = forms.ChoiceField(
        label="Daraja",
        choices=[],
        required=False,
        help_text="Darajani tez almashtirish uchun tanlang. XP o'zgarmasa, shu bosqichning minimal XP qiymati qo'llanadi.",
    )

    class Meta:
        model = Profile
        fields = ("user", "full_name", "role", "theme", "xp", "level_override", "premium_until", "photo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["level_override"].choices = get_level_choices()
        if self.instance and self.instance.pk:
            self.fields["level_override"].initial = get_level_info(self.instance.xp).get("label")

    def clean_xp(self):
        return max(0, int(self.cleaned_data.get("xp") or 0))


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


class UserSubscriptionSubjectInline(admin.TabularInline):
    model = UserSubscriptionSubject
    extra = 1
    autocomplete_fields = ("subject",)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "subject_limit", "is_all_access", "price", "duration_days", "is_active")
    list_filter = ("is_all_access", "is_active", "duration_days")
    search_fields = ("name", "code")
    ordering = ("price", "name")


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "plan", "title", "status", "is_all_access", "started_at", "end_at")
    list_filter = ("status", "is_all_access", "plan", "source", "end_at")
    search_fields = ("user__username", "title", "plan__name")
    autocomplete_fields = ("user", "plan")
    inlines = [UserSubscriptionSubjectInline]
    ordering = ("-end_at", "-created_at")


@admin.register(UserSubscriptionSubject)
class UserSubscriptionSubjectAdmin(admin.ModelAdmin):
    list_display = ("id", "subscription", "subject", "created_at")
    list_filter = ("subject", "created_at")
    search_fields = ("subscription__user__username", "subject__name", "subscription__title")
    autocomplete_fields = ("subscription", "subject")
    ordering = ("-created_at",)


# ---------------- TEST ----------------
@admin.register(Test)
class TestAdmin(HiddenLegacyAdminMixin, admin.ModelAdmin):
    list_display = ("id", "title", "subject", "category", "duration", "difficulty", "created_at")
    list_filter = ("subject", "category", "difficulty")
    search_fields = ("title",)
    autocomplete_fields = ("subject",)
    ordering = ("-created_at",)
    change_list_template = "admin/main/test/change_list.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_center_url"] = reverse("content_import_center")
        return super().changelist_view(request, extra_context=extra_context)


# ---------------- CHOICE INLINE ----------------
class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4


class PracticeChoiceInline(admin.TabularInline):
    model = PracticeChoice
    extra = 4


class PracticeExerciseInline(admin.TabularInline):
    model = PracticeExercise
    extra = 1
    fields = ("title", "prompt", "answer_mode", "correct_text", "difficulty", "is_featured")
    show_change_link = True


class GrammarQuestionInline(admin.TabularInline):
    model = GrammarLessonQuestion
    extra = 2


# ---------------- QUESTION ----------------
@admin.register(Question)
class QuestionAdmin(HiddenLegacyAdminMixin, admin.ModelAdmin):
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
class ChoiceAdmin(HiddenLegacyAdminMixin, admin.ModelAdmin):
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
    form = ProfileAdminForm
    list_display = (
        "id",
        "user",
        "full_name",
        "role_badge",
        "theme",
        "level_badge",
        "xp_badge",
        "subject_count",
        "premium_until",
        "created_at",
    )
    list_filter = ("role", "theme", "premium_until", "created_at")
    search_fields = ("user__username", "full_name")
    autocomplete_fields = ("user",)
    readonly_fields = ("purchased_subjects_summary",)
    fieldsets = (
        ("Asosiy", {"fields": ("user", "full_name", "role", "theme", "photo")}),
        (
            "Progress",
            {
                "fields": ("xp", "level_override", "premium_until"),
                "description": "XP ni qo'lda kiriting yoki daraja tanlab tez o'tkazing. Agar ikkalasi ham o'zgarsa, XP ustun turadi.",
            },
        ),
        ("Obuna", {"fields": ("purchased_subjects_summary",)}),
    )

    @admin.display(description="Rol")
    def role_badge(self, obj):
        role_map = {
            "student": ("📘", "#2563eb", "#dbeafe"),
            "university": ("🎒", "#7c3aed", "#ede9fe"),
            "teacher": ("🧑‍🏫", "#059669", "#d1fae5"),
            "admin": ("🛠️", "#b45309", "#fef3c7"),
        }
        emoji, color, bg = role_map.get(obj.role, ("👤", "#6b7280", "#f3f4f6"))
        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:{};color:{};font-weight:700;">{} {}</span>',
            bg,
            color,
            emoji,
            obj.get_role_display(),
        )

    @admin.display(description="Daraja", ordering="xp")
    def level_badge(self, obj):
        info = get_level_info(obj.xp)
        return format_html(
            '<span style="display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:#fff7ed;color:#9a5b22;font-weight:800;">{}</span>',
            info["label"],
        )

    @admin.display(description="XP", ordering="xp")
    def xp_badge(self, obj):
        info = get_level_info(obj.xp)
        return format_html(
            '<div style="display:grid;gap:3px;"><strong style="font-size:0.95rem;color:#24160d;">{} XP</strong><span style="font-size:0.78rem;color:#8f735c;">{}</span></div>',
            obj.xp,
            info["range_text"],
        )

    def subject_count(self, obj):
        return len(get_user_subject_access_rows(obj.user, active_only=False))
    subject_count.short_description = "Fanlar"

    def purchased_subjects_summary(self, obj):
        subscriptions = get_user_subject_access_rows(obj.user, active_only=False)
        if not subscriptions:
            return "Fan biriktirilmagan"

        lines = []
        now = timezone.now()
        for subscription in subscriptions:
            status = "Faol" if subscription["end_at"] >= now else "Tugagan"
            lines.append(
                f"{subscription['subject'].name} - {status} - {subscription['end_at']:%d.%m.%Y %H:%M}"
            )
        return "\n".join(lines)
    purchased_subjects_summary.short_description = "Sotib olingan fanlar"

    def save_model(self, request, obj, form, change):
        level_override = form.cleaned_data.get("level_override")
        xp_changed = "xp" in form.changed_data
        level_changed = "level_override" in form.changed_data

        if level_changed and not xp_changed:
            obj.xp = get_level_min_xp(level_override)
        obj.level = get_level_info(obj.xp)["label"]

        super().save_model(request, obj, form, change)

        summary, _ = UserStatSummary.objects.get_or_create(user=obj.user)
        earned_xp = (
            int(summary.test_xp_total or 0)
            + int(summary.practice_xp_total or 0)
            + int(summary.grammar_xp_total or 0)
            + int(summary.essay_xp_total or 0)
        )
        summary.manual_xp_adjustment = obj.xp - earned_xp
        summary.lifetime_xp = obj.xp
        summary.save(update_fields=["manual_xp_adjustment", "lifetime_xp", "updated_at"])

        if level_changed and xp_changed and level_override != obj.level:
            self.message_user(
                request,
                "Daraja XP bo'yicha qayta hisoblandi. Agar aniq darajani xohlasangiz, XP ni o'zgartirmasdan darajani tanlang.",
                level=messages.WARNING,
            )


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
    fields = ("subject", "title", "author", "grade", "description", "access_level", "pdf_file", "is_featured")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "grade":
            formfield.help_text = "Matematika/Tarix uchun: 5, 6, 7... Ona tili va adabiyot uchun: roman, qissa, drama, hikoya, sher."
        return formfield

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
class PracticeExerciseAdmin(HiddenLegacyAdminMixin, admin.ModelAdmin):
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
    inlines = [PracticeExerciseInline]
    fields = ("subject", "title", "topic", "source_book", "difficulty", "description", "is_featured")

    @admin.display(description="Misollar soni")
    def exercise_count(self, obj):
        return obj.exercises.count()


@admin.register(PracticeChoice)
class PracticeChoiceAdmin(HiddenLegacyAdminMixin, admin.ModelAdmin):
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


