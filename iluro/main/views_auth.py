from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.utils import timezone
from datetime import timedelta

from .models import Profile, Subject, Subscription, UserSubjectPreference
from .services import get_or_sync_profile as _get_or_sync_profile
from .services import sidebar_context as _sidebar_context


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        full_name = (request.POST.get("full_name") or "").strip()
        role = request.POST.get("role", "student")
        password = request.POST.get("password")
        password2 = request.POST.get("password2")
        allowed_roles = {choice[0] for choice in Profile.ROLE_CHOICES if choice[0] != "admin"}

        if len(username) < 4:
            messages.error(request, "Username kamida 4 ta belgidan iborat bo'lishi kerak.")
            return redirect("register")

        if not email:
            messages.error(request, "Email kiritish majburiy.")
            return redirect("register")

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Email formati noto'g'ri.")
            return redirect("register")

        if password != password2:
            messages.error(request, "Parollar bir xil emas.")
            return redirect("register")

        if role not in allowed_roles:
            messages.error(request, "Tanlangan status noto'g'ri.")
            return redirect("register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Bu username allaqachon mavjud.")
            return redirect("register")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Bu email allaqachon ishlatilgan.")
            return redirect("register")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=full_name,
        )
        beta_trial_end = timezone.now() + timedelta(days=14)
        profile = Profile.objects.create(
            user=user,
            full_name=full_name,
            role=role,
            premium_until=beta_trial_end,
        )
        subjects = list(Subject.objects.all())
        if subjects:
            Subscription.objects.bulk_create(
                [
                    Subscription(
                        user=user,
                        subject=subject,
                        end_date=beta_trial_end,
                    )
                    for subject in subjects
                ]
            )
        request.session["beta_trial_notice"] = True
        request.session["beta_trial_expires_at"] = beta_trial_end.isoformat()
        login(request, user)
        return redirect("dashboard")

    return render(
        request,
        "auth/register.html",
        {
            "register_role_choices": [
                {"value": "student", "label": "O'quvchi", "emoji": "рџ“"},
                {"value": "university", "label": "Talaba", "emoji": "рџЋ“"},
                {"value": "teacher", "label": "O'qituvchi", "emoji": "рџ§‘вЂЌрџЏ«"},
            ]
        },
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("dashboard")

        messages.error(request, "Login yoki parol noto'g'ri.")

    return render(request, "auth/login.html")


def logout_view(request):
    logout(request)
    messages.success(request, "Hisobdan muvaffaqiyatli chiqdingiz.")
    return redirect("index")


@login_required
def settings_view(request):
    profile = _get_or_sync_profile(request.user)
    active_subscriptions = list(
        Subscription.objects.filter(user=request.user, end_date__gte=timezone.now())
        .select_related("subject")
        .order_by("subject__name")
    )
    subject_preferences = {
        item.subject_id: item
        for item in UserSubjectPreference.objects.filter(
            user=request.user,
            subject_id__in=[subscription.subject_id for subscription in active_subscriptions],
        )
    }

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip() or request.user.username
        role = request.POST.get("role", profile.role)
        theme = request.POST.get("theme", profile.theme)

        allowed_roles = {choice[0] for choice in Profile.ROLE_CHOICES if choice[0] != "admin"}
        allowed_themes = {choice[0] for choice in Profile.THEME_CHOICES}
        allowed_levels = {"S", "S+", "B", "B+", "A", "A+"}

        if role not in allowed_roles:
            messages.error(request, "Status noto'g'ri tanlandi.")
            return redirect("settings")
        if theme not in allowed_themes:
            messages.error(request, "Theme noto'g'ri tanlandi.")
            return redirect("settings")

        profile.full_name = full_name
        profile.role = role
        profile.theme = theme
        profile.save(update_fields=["full_name", "role", "theme"])
        request.user.first_name = full_name
        request.user.save(update_fields=["first_name"])

        for subscription in active_subscriptions:
            preferred_level = request.POST.get(f"subject_level_{subscription.subject_id}", "S")
            if preferred_level not in allowed_levels:
                continue
            UserSubjectPreference.objects.update_or_create(
                user=request.user,
                subject=subscription.subject,
                defaults={"preferred_level": preferred_level},
            )

        messages.success(request, "Настройка saqlandi.")
        return redirect("settings")

    preferred_subject_levels = []
    for subscription in active_subscriptions:
        preference = subject_preferences.get(subscription.subject_id)
        preferred_subject_levels.append(
            {
                "subject_id": subscription.subject_id,
                "subject_name": subscription.subject.name,
                "current_level": preference.preferred_level if preference else profile.level,
                "expires_at": subscription.end_date,
            }
        )

    context = {
        **_sidebar_context(request.user),
        "role_choices": [choice for choice in Profile.ROLE_CHOICES if choice[0] != "admin"],
        "theme_choices": Profile.THEME_CHOICES,
        "level_choices": ["S", "S+", "B", "B+", "A", "A+"],
        "preferred_subject_levels": preferred_subject_levels,
    }
    return render(request, "settings.html", context)
