
from collections import defaultdict
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.cache import cache
from django.conf import settings
from django import forms
from django.db.models import Count, Sum, Value
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models.functions import Coalesce
from django.urls import path, reverse
from django.contrib import messages
from .models import (
    Subject, Subscription, SubscriptionPlan, UserSubscription, UserSubscriptionSubject, Test,
    Question, Choice, UserTest,
    UserAnswer, Profile, UserSubjectPreference, Book, SubjectSectionEntry, EssayTopic,
    PracticeSet, PracticeExercise, PracticeChoice, UserPracticeAttempt, PracticeSetAttempt, BookView,
    GrammarLessonQuestion, GrammarLessonProgress, ReferralEvent, UserStatSummary,
)
from .services import (
    apply_referral_discount_to_subscription,
    cleanup_empty_user_subscriptions,
    consume_referral_discount,
    revoke_subject_access,
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
    ("grammar", "Grammatika"),
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
    json_file = forms.FileField(
        required=False,
        label="JSON fayl",
        help_text=".json fayl yuklash mumkin. Xohlasangiz pastdagi maydonga ham JSON paste qilishingiz mumkin.",
    )
    json_text = forms.CharField(
        required=False,
        label="JSON matni",
        widget=forms.Textarea(attrs={"rows": 22, "class": "vLargeTextField"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        subject = cleaned_data.get("subject")
        import_kind = cleaned_data.get("import_kind")
        json_text = (cleaned_data.get("json_text") or "").strip()
        json_file = cleaned_data.get("json_file")

        if not subject or not import_kind:
            return cleaned_data

        if json_file and not json_text:
            try:
                json_text = json_file.read().decode("utf-8-sig").strip()
            except UnicodeDecodeError as exc:
                raise forms.ValidationError("JSON fayl UTF-8 formatda bo'lishi kerak.") from exc

        if not json_text:
            raise forms.ValidationError("JSON matnini kiriting yoki .json fayl yuklang.")

        try:
            payload = load_json_payload_from_text(json_text)
        except Exception as exc:
            raise forms.ValidationError(str(exc)) from exc

        allowed_kinds = get_allowed_import_kinds(subject.name)
        if import_kind not in allowed_kinds:
            raise forms.ValidationError("Tanlangan fan uchun bu import turi mos emas.")

        cleaned_data["payload"] = payload
        cleaned_data["json_text"] = json_text
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
        form = ContentImportCenterForm(request.POST, request.FILES)
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
                            f"Grammatika import tugadi: {result['created_count']} ta yangi, "
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


def _build_daily_activity_chart(now):
    tests_by_day = defaultdict(int)
    practice_by_day = defaultdict(int)

    window_start = (now - timedelta(days=6)).date()
    for item in (
        UserTest.objects.filter(started_at__date__gte=window_start)
        .values("started_at__date")
        .annotate(total=Count("id"))
    ):
        tests_by_day[item["started_at__date"]] = item["total"]

    for item in (
        PracticeSetAttempt.objects.filter(created_at__date__gte=window_start)
        .values("created_at__date")
        .annotate(total=Count("id"))
    ):
        practice_by_day[item["created_at__date"]] = item["total"]

    bars = []
    peak = 0
    for offset in range(7):
        day = window_start + timedelta(days=offset)
        label = day.strftime("%d.%m")
        test_total = tests_by_day.get(day, 0)
        practice_total = practice_by_day.get(day, 0)
        total = test_total + practice_total
        peak = max(peak, total)
        bars.append(
            {
                "label": label,
                "tests": test_total,
                "practice": practice_total,
                "total": total,
            }
        )

    peak = peak or 1
    for item in bars:
        item["height_pct"] = max(10, round((item["total"] / peak) * 100)) if item["total"] else 8

    return bars


def _build_subject_distribution(now):
    subjects = list(Subject.objects.order_by("name"))
    all_access_user_ids = set(
        UserSubscription.objects.filter(status="active", end_at__gte=now, is_all_access=True).values_list("user_id", flat=True)
    )
    by_subject = {subject.id: set(all_access_user_ids) for subject in subjects}

    for user_id, subject_id in Subscription.objects.filter(end_date__gte=now).values_list("user_id", "subject_id"):
        by_subject.setdefault(subject_id, set()).add(user_id)

    for user_id, subject_id in UserSubscriptionSubject.objects.filter(
        subscription__status="active",
        subscription__end_at__gte=now,
    ).values_list("subscription__user_id", "subject_id"):
        by_subject.setdefault(subject_id, set()).add(user_id)

    peak = 0
    items = []
    for subject in subjects:
        total = len(by_subject.get(subject.id, set()))
        peak = max(peak, total)
        items.append({"name": subject.name, "total": total})

    peak = peak or 1
    for item in items:
        item["width_pct"] = round((item["total"] / peak) * 100) if item["total"] else 0
    return items


def _build_subscription_sources(now):
    palette = {
        "purchase": "#497b56",
        "beta_trial": "#8a5425",
        "manual": "#3667ab",
        "legacy_import": "#6d6d6d",
    }
    label_map = dict(UserSubscription.SOURCE_CHOICES)
    items = []
    peak = 0
    queryset = (
        UserSubscription.objects.filter(status="active", end_at__gte=now)
        .values("source")
        .annotate(total=Count("id"))
        .order_by("-total", "source")
    )
    for item in queryset:
        peak = max(peak, item["total"])
        items.append(
            {
                "name": label_map.get(item["source"], item["source"]),
                "total": item["total"],
                "color": palette.get(item["source"], "#8f735c"),
            }
        )

    peak = peak or 1
    for item in items:
        item["width_pct"] = round((item["total"] / peak) * 100) if item["total"] else 0
    return items


def analytics_dashboard_view(request):
    cache_key = "admin_analytics_snapshot_v1"
    cached_payload = cache.get(cache_key)
    if cached_payload is None:
        cached_payload = _build_admin_analytics_payload()
        cache.set(cache_key, cached_payload, getattr(settings, "ADMIN_ANALYTICS_CACHE_SECONDS", 3600))

    context = {
        **admin.site.each_context(request),
        "title": "Admin statistika",
        "subtitle": "Platformadagi umumiy faollik va foydalanuvchi holati",
        **cached_payload,
    }
    return TemplateResponse(request, "admin/analytics_dashboard.html", context)


def _build_admin_analytics_payload():
    now = timezone.localtime(timezone.now())
    today = now.date()
    week_ago = now - timedelta(days=7)

    total_users = User.objects.count()
    summary_active = set(
        UserStatSummary.objects.filter(last_activity_at__gte=week_ago).values_list("user_id", flat=True)
    )
    login_active = set(User.objects.filter(last_login__gte=week_ago).values_list("id", flat=True))
    active_users_7d = len(summary_active | login_active)

    active_subscription_count = UserSubscription.objects.filter(status="active", end_at__gte=now).count()
    total_subscription_count = UserSubscription.objects.count()

    new_users_today = User.objects.filter(date_joined__date=today).count()
    tests_today = UserTest.objects.filter(started_at__date=today).count()
    practice_today = PracticeSetAttempt.objects.filter(created_at__date=today).count()

    total_xp = UserStatSummary.objects.aggregate(total=Coalesce(Sum("lifetime_xp"), Value(0))).get("total", 0)
    average_xp = round(total_xp / total_users) if total_users else 0

    top_user_rows = []
    for item in (
        UserStatSummary.objects.select_related("user", "user__profile")
        .order_by("-lifetime_xp", "-lifetime_test_count", "-lifetime_practice_count")[:8]
    ):
        profile = getattr(item.user, "profile", None)
        display_name = getattr(profile, "full_name", "") or item.user.get_full_name().strip() or item.user.username
        top_user_rows.append(
            {
                "display_name": display_name,
                "username": item.user.username,
                "xp": item.lifetime_xp,
                "tests": item.lifetime_test_count,
                "practice": item.lifetime_practice_count,
            }
        )

    recent_user_rows = []
    for item in User.objects.select_related("profile").order_by("-date_joined")[:8]:
        profile = getattr(item, "profile", None)
        display_name = getattr(profile, "full_name", "") or item.get_full_name().strip() or item.username
        recent_user_rows.append(
            {
                "display_name": display_name,
                "username": item.username,
                "date_joined": item.date_joined,
                "last_login": item.last_login,
            }
        )

    card_stats = [
        {
            "label": "Jami userlar",
            "value": total_users,
            "note": "Platformadagi umumiy foydalanuvchilar",
        },
        {
            "label": "Aktiv userlar (7 kun)",
            "value": active_users_7d,
            "note": "So'nggi 7 kunda faol bo'lganlar",
        },
        {
            "label": "Hozir faol obunalar",
            "value": active_subscription_count,
            "note": "Ayni paytda faol turgan obunalar",
        },
        {
            "label": "Umumiy olingan obunalar",
            "value": total_subscription_count,
            "note": "Jami yaratilgan obuna yozuvlari",
        },
        {
            "label": "Bugungi yangi userlar",
            "value": new_users_today,
            "note": "Bugun ro'yxatdan o'tganlar",
        },
        {
            "label": "Bugungi testlar",
            "value": tests_today,
            "note": "Bugun boshlangan test sessionlar",
        },
        {
            "label": "Bugungi mashqlar",
            "value": practice_today,
            "note": "Bugungi mashq bo'limi urinishlari",
        },
        {
            "label": "O'rtacha XP",
            "value": average_xp,
            "note": "Barcha userlar bo'yicha o'rtacha XP",
        },
    ]

    return {
        "analytics_cards": card_stats,
        "subject_distribution": _build_subject_distribution(now),
        "subscription_sources": _build_subscription_sources(now),
        "daily_activity": _build_daily_activity_chart(now),
        "top_users": top_user_rows,
        "recent_users": recent_user_rows,
        "generated_at": now,
    }


_default_admin_get_urls = admin.site.get_urls


def _iluro_admin_get_urls():
    custom_urls = [
        path("analytics/", admin.site.admin_view(analytics_dashboard_view), name="analytics_dashboard"),
    ]
    return custom_urls + _default_admin_get_urls()


admin.site.get_urls = _iluro_admin_get_urls


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
    mark_referral_discount_used = forms.BooleanField(
        label="Referral balansini ishlatilgan deb belgilash",
        required=False,
        help_text="Joriy available referral foizini 0 ga tushiradi va used ga o'tkazadi. Keyin user yana qayta yig'a oladi.",
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
class SubscriptionAdmin(HiddenLegacyAdminMixin, admin.ModelAdmin):
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

    def delete_model(self, request, obj):
        user_id = obj.user_id
        subject_id = obj.subject_id
        super().delete_model(request, obj)
        revoke_subject_access(user_id, subject_id, include_legacy=False, include_bundle=True)

    def delete_queryset(self, request, queryset):
        pairs = list(queryset.values_list("user_id", "subject_id"))
        super().delete_queryset(request, queryset)
        for user_id, subject_id in pairs:
            revoke_subject_access(user_id, subject_id, include_legacy=False, include_bundle=True)


class UserSubscriptionSubjectInline(admin.TabularInline):
    model = UserSubscriptionSubject
    extra = 0
    autocomplete_fields = ("subject",)
    verbose_name = "Fan"
    verbose_name_plural = "Ochiq fanlar"


def _plan_scope_label(plan):
    if not plan:
        return "-"
    if plan.is_all_access:
        return "Barcha fanlar"
    if plan.code == "single-subject":
        return "Free + 1 fan"
    if plan.subject_limit:
        return f"{plan.subject_limit} ta fan"
    return "Cheklangan fanlar"


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "display_order",
        "name",
        "code",
        "scope_preview",
        "price",
        "duration_days",
        "stack_mode",
        "is_featured",
        "is_public",
        "is_active",
    )
    list_filter = ("is_all_access", "is_public", "is_featured", "is_active", "stack_mode", "duration_days")
    search_fields = ("name", "code")
    ordering = ("display_order", "price", "name")
    list_display_links = ("name",)
    list_editable = ("display_order", "is_featured", "is_public", "is_active")
    fieldsets = (
        ("Asosiy", {"fields": ("name", "code", "display_order", "price", "duration_days")}),
        ("Qamrov", {"fields": ("subject_limit", "is_all_access", "stack_mode", "is_public", "is_featured", "is_active")}),
        ("Limitlar", {"fields": ("daily_test_limit", "daily_ai_limit")}),
        (
            "Imkoniyatlar",
            {
                "fields": (
                    "can_use_ai",
                    "can_use_full_content",
                    "can_use_advanced_content",
                    "can_use_mock_exam",
                    "can_use_progress_recommendations",
                    "can_use_advanced_stats",
                )
            },
        ),
    )

    @admin.display(description="Qamrov")
    def scope_preview(self, obj):
        return _plan_scope_label(obj)


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_identity", "title", "coverage_preview", "source_badge", "status_badge", "started_at", "end_at")
    list_filter = ("status", "is_all_access", "plan", "source", "end_at", "started_at")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__profile__full_name",
        "title",
        "plan__name",
    )
    autocomplete_fields = ("user", "plan")
    inlines = [UserSubscriptionSubjectInline]
    ordering = ("-end_at", "-created_at")
    readonly_fields = ("pricing_summary",)
    fields = (
        "user",
        "plan",
        "title",
        "source",
        "status",
        "is_all_access",
        "started_at",
        "end_at",
        "pricing_summary",
    )
    list_per_page = 25
    search_help_text = "Username, to'liq ism, email yoki obuna nomi bo'yicha qidiring"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("plan", "user").prefetch_related("subjects__subject")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "plan":
            kwargs["queryset"] = SubscriptionPlan.objects.filter(is_active=True, is_public=True).order_by("display_order", "price", "name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("source", "manual")
        initial.setdefault("status", "active")
        initial.setdefault("started_at", timezone.localtime(timezone.now()))
        initial.setdefault("end_at", timezone.localtime(timezone.now() + timedelta(days=30)))
        return initial

    def coverage_preview(self, obj):
        if obj.is_all_access:
            return mark_safe(
                '<span style="display:inline-flex;align-items:center;min-height:30px;padding:0 12px;border-radius:999px;'
                'background:rgba(168,106,51,0.12);color:#8a5425;font-weight:700;">Barcha fanlar</span>'
            )
        subjects = [item.subject.name for item in obj.subjects.all()]
        if not subjects:
            plan_label = _plan_scope_label(obj.plan)
            return format_html(
                '<span style="display:inline-flex;align-items:center;min-height:30px;padding:0 12px;border-radius:999px;'
                'background:rgba(176,87,67,0.10);color:#b05743;font-weight:700;">Fan biriktirilmagan ({})</span>',
                plan_label,
            )
        preview = ", ".join(subjects[:3])
        if len(subjects) > 3:
            preview = f"{preview} +{len(subjects) - 3}"
        return preview
    coverage_preview.short_description = "Qamrov"

    def user_identity(self, obj):
        profile_name = getattr(getattr(obj.user, "profile", None), "full_name", "") or ""
        display_name = profile_name.strip() or obj.user.get_full_name().strip() or obj.user.username
        secondary = f"@{obj.user.username}"
        if obj.user.email:
            secondary = f"{secondary} · {obj.user.email}"
        return format_html(
            '<div style="display:grid;gap:2px;">'
            '<strong style="color:#24160d;">{}</strong>'
            '<span style="color:#8f735c;font-size:12px;">{}</span>'
            "</div>",
            display_name,
            secondary,
        )
    user_identity.short_description = "Foydalanuvchi"
    user_identity.admin_order_field = "user__username"

    def status_badge(self, obj):
        palette = {
            "active": ("rgba(73,123,86,0.12)", "#497b56", "Faol"),
            "expired": ("rgba(176,87,67,0.10)", "#b05743", "Tugagan"),
            "cancelled": ("rgba(112,112,112,0.10)", "#6d6d6d", "Bekor"),
        }
        bg, color, label = palette.get(obj.status, ("rgba(112,112,112,0.10)", "#6d6d6d", obj.get_status_display()))
        return format_html(
            '<span style="display:inline-flex;align-items:center;min-height:30px;padding:0 12px;border-radius:999px;'
            'background:{};color:{};font-weight:700;">{}</span>',
            bg,
            color,
            label,
        )
    status_badge.short_description = "Holat"
    status_badge.admin_order_field = "status"

    def source_badge(self, obj):
        palette = {
            "purchase": ("rgba(73,123,86,0.10)", "#497b56", "Sotib olish"),
            "beta_trial": ("rgba(168,106,51,0.12)", "#8a5425", "Beta trial"),
            "manual": ("rgba(54,103,171,0.10)", "#3667ab", "Admin"),
            "legacy_import": ("rgba(112,112,112,0.10)", "#6d6d6d", "Legacy"),
        }
        bg, color, label = palette.get(obj.source, ("rgba(112,112,112,0.10)", "#6d6d6d", obj.get_source_display()))
        return format_html(
            '<span style="display:inline-flex;align-items:center;min-height:30px;padding:0 12px;border-radius:999px;'
            'background:{};color:{};font-weight:700;">{}</span>',
            bg,
            color,
            label,
        )
    source_badge.short_description = "Manba"
    source_badge.admin_order_field = "source"

    @admin.display(description="Narx")
    def pricing_summary(self, obj):
        if not obj.plan_id:
            return "-"
        base_price = int(obj.price_before_discount or obj.plan.price or 0)
        if obj.referral_discount_percent_applied:
            return (
                f"Base: {base_price:,} so'm | Referral: {obj.referral_discount_percent_applied}% "
                f"(-{int(obj.referral_discount_amount or 0):,} so'm) | Final: {int(obj.final_price or 0):,} so'm"
            ).replace(",", " ")
        final_price = int(obj.final_price or base_price or 0)
        return f"Base: {base_price:,} so'm | Final: {final_price:,} so'm".replace(",", " ")

    def save_model(self, request, obj, form, change):
        if obj.plan:
            obj.title = obj.plan.name
            obj.is_all_access = obj.plan.is_all_access
            if not obj.price_before_discount:
                obj.price_before_discount = int(obj.plan.price or 0)
            if not obj.final_price:
                obj.final_price = int(obj.plan.price or 0)
            if not change:
                started_at = obj.started_at or timezone.now()
                obj.end_at = obj.end_at or (started_at + timedelta(days=obj.plan.duration_days))
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        subscription = form.instance
        previous_subject_ids = set()
        if subscription.pk:
            previous_subject_ids = set(subscription.subjects.values_list("subject_id", flat=True))

        super().save_related(request, form, formsets, change)

        current_subject_ids = set(subscription.subjects.values_list("subject_id", flat=True))
        removed_subject_ids = previous_subject_ids - current_subject_ids
        for subject_id in removed_subject_ids:
            revoke_subject_access(subscription.user_id, subject_id, include_legacy=True, include_bundle=False)

        removed_ids = cleanup_empty_user_subscriptions([subscription.id])
        if subscription.id in removed_ids:
            self.message_user(
                request,
                "Fan biriktirilmagan obuna avtomatik olib tashlandi. Access ochilishi uchun kamida bitta fan qo'shing.",
                level=messages.WARNING,
            )
            return

        subscription.refresh_from_db()
        if not subscription.is_all_access and not subscription.subjects.exists():
            self.message_user(
                request,
                "Bu obunaga hali fan biriktirilmagan. Access ochilishi uchun kamida bitta fan qo'shing.",
                level=messages.WARNING,
            )
            return

        if subscription.plan and not subscription.is_all_access and subscription.plan.subject_limit:
            subject_count = subscription.subjects.count()
            if subject_count > subscription.plan.subject_limit:
                self.message_user(
                    request,
                    (
                        f"Tanlangan plan '{subscription.plan.name}' uchun limit {subscription.plan.subject_limit} ta fan. "
                        f"Hozir {subject_count} ta fan biriktirilgan."
                    ),
                    level=messages.WARNING,
                )

        if not change and subscription.plan_id:
            applied_percent = apply_referral_discount_to_subscription(subscription)
            if applied_percent:
                subscription.refresh_from_db()
                self.message_user(
                    request,
                    (
                        f"Referral chegirma qo'llandi: {applied_percent}% "
                        f"(-{int(subscription.referral_discount_amount or 0):,} so'm). "
                        f"Final narx: {int(subscription.final_price or 0):,} so'm."
                    ).replace(",", " "),
                    level=messages.SUCCESS,
                )

    def delete_model(self, request, obj):
        subject_ids = list(obj.subjects.values_list("subject_id", flat=True))
        user_id = obj.user_id
        super().delete_model(request, obj)
        for subject_id in subject_ids:
            revoke_subject_access(user_id, subject_id, include_legacy=True, include_bundle=False)

    def delete_queryset(self, request, queryset):
        payload = [
            (subscription.user_id, list(subscription.subjects.values_list("subject_id", flat=True)))
            for subscription in queryset
        ]
        super().delete_queryset(request, queryset)
        for user_id, subject_ids in payload:
            for subject_id in subject_ids:
                revoke_subject_access(user_id, subject_id, include_legacy=True, include_bundle=False)


@admin.register(UserSubscriptionSubject)
class UserSubscriptionSubjectAdmin(HiddenLegacyAdminMixin, admin.ModelAdmin):
    list_display = ("id", "subscription", "subject", "created_at")
    list_filter = ("subject", "created_at")
    search_fields = ("subscription__user__username", "subject__name", "subscription__title")
    autocomplete_fields = ("subscription", "subject")
    ordering = ("-created_at",)

    def delete_model(self, request, obj):
        user_id = obj.subscription.user_id
        subject_id = obj.subject_id
        subscription_id = obj.subscription_id
        super().delete_model(request, obj)
        revoke_subject_access(user_id, subject_id, include_legacy=True, include_bundle=False)
        cleanup_empty_user_subscriptions([subscription_id])

    def delete_queryset(self, request, queryset):
        payload = list(queryset.values_list("subscription__user_id", "subject_id", "subscription_id"))
        super().delete_queryset(request, queryset)
        for user_id, subject_id, subscription_id in payload:
            revoke_subject_access(user_id, subject_id, include_legacy=True, include_bundle=False)
            cleanup_empty_user_subscriptions([subscription_id])


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
    actions = ("mark_referral_discount_as_used",)
    list_display = (
        "id",
        "user",
        "full_name",
        "referral_code",
        "role_badge",
        "theme",
        "level_badge",
        "xp_badge",
        "referral_wallet_badge",
        "subject_count",
        "premium_until",
        "created_at",
    )
    list_filter = ("role", "theme", "premium_until", "created_at")
    search_fields = ("user__username", "full_name")
    autocomplete_fields = ("user",)
    readonly_fields = (
        "referral_code",
        "referral_wallet_badge",
        "referred_by",
        "purchased_subjects_summary",
    )
    fieldsets = (
        ("Asosiy", {"fields": ("user", "full_name", "role", "theme", "photo", "referral_code", "referred_by")}),
        (
            "Progress",
            {
                "fields": ("xp", "level_override", "premium_until"),
                "description": "XP ni qo'lda kiriting yoki daraja tanlab tez o'tkazing. Agar ikkalasi ham o'zgarsa, XP ustun turadi.",
            },
        ),
        (
            "Referral",
            {
                "fields": ("referral_wallet_badge", "mark_referral_discount_used"),
                "description": "Checkbox saqlanganda available referral balansini 0 ga tushiradi. Foydalanuvchi keyin yana 50% gacha qayta yig'a oladi.",
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

    @admin.display(description="Referral wallet")
    def referral_wallet_badge(self, obj):
        return format_html(
            '<div style="display:grid;gap:3px;">'
            '<strong style="font-size:0.95rem;color:#24160d;">Available: {}%</strong>'
            '<span style="font-size:0.78rem;color:#8f735c;">Earned: {}% · Used: {}%</span>'
            "</div>",
            obj.referral_discount_available_percent,
            obj.referral_discount_percent,
            obj.referral_discount_used_percent,
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
            status = "Faol" if subscription["is_permanent"] or (subscription["end_at"] and subscription["end_at"] >= now) else "Tugagan"
            expiry_label = "Doimiy" if subscription["is_permanent"] else f"{subscription['end_at']:%d.%m.%Y %H:%M}"
            lines.append(
                f"{subscription['subject'].name} - {status} - {expiry_label}"
            )
        return "\n".join(lines)
    purchased_subjects_summary.short_description = "Sotib olingan fanlar"

    def save_model(self, request, obj, form, change):
        level_override = form.cleaned_data.get("level_override")
        should_mark_referral_used = bool(form.cleaned_data.get("mark_referral_discount_used"))
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

        if should_mark_referral_used:
            consumed_percent = consume_referral_discount(obj)
            if consumed_percent:
                self.message_user(
                    request,
                    (
                        f"{obj.user.username} uchun {consumed_percent}% referral balans ishlatilgan deb belgilandi. "
                        "User endi yana qayta referral yig'a oladi."
                    ),
                    level=messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    f"{obj.user.username} uchun ishlatishga referral balans topilmadi.",
                    level=messages.WARNING,
                )

    @admin.action(description="Tanlangan profillarda referral balansni ishlatilgan deb belgilash")
    def mark_referral_discount_as_used(self, request, queryset):
        updated_count = 0
        zero_count = 0

        for profile in queryset.select_related("user"):
            consumed_percent = consume_referral_discount(profile)
            if consumed_percent:
                updated_count += 1
            else:
                zero_count += 1

        if updated_count:
            self.message_user(
                request,
                (
                    f"{updated_count} ta profil uchun referral balans ishlatilgan deb belgilandi. "
                    "Bu userlar 0 dan yana qayta yig'a oladi."
                ),
                level=messages.SUCCESS,
            )
        if zero_count:
            self.message_user(
                request,
                f"{zero_count} ta profilda available referral balans yo'q edi.",
                level=messages.WARNING,
            )


@admin.register(ReferralEvent)
class ReferralEventAdmin(admin.ModelAdmin):
    list_display = ("id", "inviter", "invited_user", "status", "reward_percent", "qualified_at", "created_at")
    list_filter = ("status", "qualified_at", "created_at")
    search_fields = ("inviter__username", "invited_user__username", "inviter__profile__full_name", "invited_user__profile__full_name")
    autocomplete_fields = ("inviter", "invited_user")
    ordering = ("-created_at",)


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


