import re

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render

from .models import PROFILE_PHOTO_MAX_BYTES, Profile
from .services import clear_pending_referral_code as _clear_pending_referral_code
from .services import get_pending_referral_code as _get_pending_referral_code
from .services import get_or_sync_profile as _get_or_sync_profile
from .services import register_referral_for_user as _register_referral_for_user
from .services import sidebar_context as _sidebar_context
from .services import stash_pending_referral_code as _stash_pending_referral_code

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def _validate_profile_photo(uploaded_file):
    if not uploaded_file:
        return

    if uploaded_file.size > PROFILE_PHOTO_MAX_BYTES:
        raise ValidationError("Profil rasmi 3 MB dan katta bo'lmasligi kerak.")

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise ValidationError("Faqat rasm faylini yuklash mumkin.")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    referral_code_param = (request.GET.get("ref") or "").strip()
    if referral_code_param:
        _stash_pending_referral_code(request, referral_code_param)
    pending_referral_code = _get_pending_referral_code(request)

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

        if not USERNAME_PATTERN.fullmatch(username):
            messages.error(
                request,
                "Username faqat lotin harflari, raqamlar va pastki chiziq (_) dan iborat bo'lishi kerak.",
            )
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

        if pending_referral_code and not Profile.objects.filter(referral_code=pending_referral_code).exists():
            _clear_pending_referral_code(request)
            messages.error(request, "Referral code topilmadi. Qaytadan tekshirib ko'ring.")
            return redirect("register")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=full_name,
        )
        Profile.objects.create(
            user=user,
            full_name=full_name,
            role=role,
        )
        if pending_referral_code:
            try:
                _register_referral_for_user(user, pending_referral_code)
                messages.success(request, "Taklif kodi qabul qilindi. Shartlar bajarilgach chegirma yoziladi.")
            except ValidationError as exc:
                messages.warning(request, exc.messages[0])
            finally:
                _clear_pending_referral_code(request)
        login(request, user)
        return redirect("dashboard")

    return render(
        request,
        "auth/register.html",
        {
            "active_referral_code": pending_referral_code,
            "register_role_choices": [
                {"value": "student", "label": "O'quvchi", "emoji": "рџ“"},
                {"value": "university", "label": "Talaba", "emoji": "рџЋ“"},
                {"value": "teacher", "label": "O'qituvchi", "emoji": "рџ§‘вЂЌрџЏ«"},
            ]
        },
    )


def referral_entry_view(request, referral_code):
    _stash_pending_referral_code(request, referral_code)
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("register")


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

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip() or request.user.username
        role = request.POST.get("role", profile.role)
        theme = request.POST.get("theme", profile.theme)
        uploaded_photo = request.FILES.get("photo")
        remove_photo = request.POST.get("remove_photo") == "on"

        allowed_roles = {choice[0] for choice in Profile.ROLE_CHOICES if choice[0] != "admin"}
        allowed_themes = {choice[0] for choice in Profile.THEME_CHOICES}
        if role not in allowed_roles:
            messages.error(request, "Status noto'g'ri tanlandi.")
            return redirect("settings")
        if theme not in allowed_themes:
            messages.error(request, "Theme noto'g'ri tanlandi.")
            return redirect("settings")
        try:
            _validate_profile_photo(uploaded_photo)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("settings")

        profile.full_name = full_name
        profile.role = role
        profile.theme = theme
        update_fields = ["full_name", "role", "theme"]
        if uploaded_photo:
            profile.photo = uploaded_photo
            update_fields.append("photo")
        elif remove_photo and profile.photo:
            profile.photo.delete(save=False)
            profile.photo = None
            update_fields.append("photo")

        try:
            profile.save(update_fields=update_fields)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("settings")
        request.user.first_name = full_name
        request.user.save(update_fields=["first_name"])
        messages.success(request, "Sozlamalar saqlandi.")
        return redirect("settings")


        messages.success(request, "Настройка saqlandi.")
        return redirect("settings")

    context = {
        **_sidebar_context(request.user),
        "role_choices": [choice for choice in Profile.ROLE_CHOICES if choice[0] != "admin"],
        "theme_choices": Profile.THEME_CHOICES,
        "profile_photo_max_mb": PROFILE_PHOTO_MAX_BYTES // (1024 * 1024),
        "member_since": profile.created_at,
        "premium_is_active": bool(profile.premium_until and profile.premium_until >= timezone.now()),
    }
    return render(request, "settings_refined.html", context)
