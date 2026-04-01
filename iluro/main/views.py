import secrets

from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, HttpResponseForbidden
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from .models import (
    Profile,
    Subject,
    Subscription,
    Test,
    UserTest,
    Book,
    Question,
    UserAnswer,
    SubjectSectionEntry,
    EssayTopic,
    PracticeExercise,
    PracticeChoice,
    UserPracticeAttempt,
)
from .utils import (
    XP_PER_TEST,
    get_allowed_level_labels,
    get_level_info,
    normalize_difficulty_label,
)


def _get_subject_theme(subject_name):
    subject_name_lower = subject_name.lower()

    if "matem" in subject_name_lower:
        return {
            "key": "math",
            "eyebrow": "Mantiq va tezlik",
            "headline": "Formula, masala va ritm bilan ishlaydigan aniq workspace.",
            "description": "Matematika bo'limida tezkor mashqlar, formulalarni mustahkamlash va natijani bosqichma-bosqich oshirish asosiy fokus bo'ladi.",
            "stat_label": "Masala ritmi",
            "stat_value": "Tezkor",
            "cards": [
                {"title": "Bugungi fokus", "text": "Masalani turlarga ajratish, formulani eslash va vaqtni yutish."},
                {"title": "Mashq usuli", "text": "Qisqa bloklarda test ishlab, natijani keyinroq tahlil qilish."},
                {"title": "AI yo'nalishi", "text": "Yechim bosqichlarini sodda tilda tushuntirish va xatoni topish."},
            ],
            "extra_sections": [
                {"key": "formulas", "label": "Formulalar"},
                {"key": "problems", "label": "Misol / Masalalar"},
            ],
        }

    if "tarix" in subject_name_lower:
        return {
            "key": "history",
            "eyebrow": "Davr va tafsilot",
            "headline": "Sanalar, jarayonlar va tarixiy bog'lanishlarni ushlab turadigan workspace.",
            "description": "Tarix bo'limida mavzularni davrlar bo'yicha ajratish, jarayonlarni taqqoslash va testlarda xotirani mustahkamlash markazga chiqadi.",
            "stat_label": "Tarixiy oqim",
            "stat_value": "Davrlar",
            "cards": [
                {"title": "Bugungi fokus", "text": "Davrlar orasidagi bog'lanishni ko'rish va sanalarni joyiga qo'yish."},
                {"title": "Mashq usuli", "text": "Mavzu bo'yicha test ishlashdan oldin qisqa kontsept xarita tuzish."},
                {"title": "AI yo'nalishi", "text": "Voqealar ketma-ketligini soddalashtirib tushuntirish va solishtirish."},
            ],
            "extra_sections": [
                {"key": "events", "label": "Tarixiy voqealar"},
            ],
        }

    return {
        "key": "language",
        "eyebrow": "Matn va insho",
        "headline": "Grammatika, tahlil va insho ustida ishlashga mos ijodiy workspace.",
        "description": "Ona tili va adabiyot bo'limida matn bilan ishlash, grammatik tozalikni oshirish va insho strukturasini kuchaytirish asosiy yo'nalish bo'ladi.",
        "stat_label": "Matn rejimi",
        "stat_value": "Insho",
        "cards": [
            {"title": "Bugungi fokus", "text": "Matnni to'g'ri qurish, uslubni silliqlash va fikrni ravshan berish."},
            {"title": "Mashq usuli", "text": "Grammatika testlari va insho rejasini parallel ishlatish."},
            {"title": "AI yo'nalishi", "text": "Insho uchun reja, xato tahlili va jumla takomillashtirish."},
        ],
        "extra_sections": [
            {"key": "rules", "label": "Qoidalar"},
            {"key": "essay", "label": "Insho"},
            {"key": "extras", "label": "Qo'shimcha ma'lumotlar"},
        ],
    }


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
            first_name=full_name
        )
        Profile.objects.create(
            user=user,
            full_name=full_name,
            role=role,
        )
        login(request, user)
        return redirect("dashboard")

    return render(
        request,
        "auth/register.html",
        {
            "register_role_choices": [
                {"value": "student", "label": "O'quvchi", "emoji": "📘"},
                {"value": "university", "label": "Talaba", "emoji": "🎓"},
                {"value": "teacher", "label": "O'qituvchi", "emoji": "🧑‍🏫"},
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
        else:
            messages.error(request, "Login yoki parol noto'g'ri.")

    return render(request, "auth/login.html")


def logout_view(request):
    logout(request)
    messages.success(request, "Hisobdan muvaffaqiyatli chiqdingiz.")
    return redirect("index")


def _get_active_subscription_ids(user):
    now = timezone.now()
    latest_subject_subscriptions = (
        Subscription.objects.filter(user=user)
        .values("subject_id")
        .annotate(latest_end_date=Max("end_date"))
    )
    return [
        item["subject_id"]
        for item in latest_subject_subscriptions
        if item["latest_end_date"] and item["latest_end_date"] >= now
    ]


def _user_can_access_subject(user, subject_id):
    active_ids = _get_active_subscription_ids(user)
    return not active_ids or subject_id in active_ids


def _get_or_sync_profile(user):
    profile, _ = Profile.objects.get_or_create(
        user=user,
        defaults={
            "full_name": user.first_name or user.username,
        },
    )
    if user.is_superuser and profile.role != "admin":
        profile.role = "admin"
        profile.save(update_fields=["role"])
    elif user.is_staff and not user.is_superuser and profile.role == "student":
        profile.role = "teacher"
        profile.save(update_fields=["role"])
    return profile


def _sidebar_context(user):
    profile = _get_or_sync_profile(user)
    return {
        "profile": profile,
        "level_info": get_level_info(profile.xp),
    }


def _filter_by_allowed_level(queryset, field_name, profile_level):
    return queryset.filter(**{f"{field_name}__in": get_allowed_level_labels(profile_level)})


@login_required
def settings_view(request):
    profile = _get_or_sync_profile(request.user)

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip() or request.user.username
        role = request.POST.get("role", profile.role)
        theme = request.POST.get("theme", profile.theme)
        level = request.POST.get("level", profile.level)

        allowed_roles = {choice[0] for choice in Profile.ROLE_CHOICES if choice[0] != "admin"}
        allowed_themes = {choice[0] for choice in Profile.THEME_CHOICES}
        allowed_levels = {"S", "S+", "B", "B+", "A", "A+"}

        if role not in allowed_roles:
            messages.error(request, "Status noto'g'ri tanlandi.")
            return redirect("settings")
        if theme not in allowed_themes:
            messages.error(request, "Theme noto'g'ri tanlandi.")
            return redirect("settings")
        if level not in allowed_levels:
            messages.error(request, "Daraja noto'g'ri tanlandi.")
            return redirect("settings")

        profile.full_name = full_name
        profile.role = role
        profile.theme = theme
        profile.level = level
        profile.save(update_fields=["full_name", "role", "theme", "level"])
        request.user.first_name = full_name
        request.user.save(update_fields=["first_name"])
        messages.success(request, "Nastroyka saqlandi.")
        return redirect("settings")

    context = {
        **_sidebar_context(request.user),
        "role_choices": [choice for choice in Profile.ROLE_CHOICES if choice[0] != "admin"],
        "theme_choices": Profile.THEME_CHOICES,
        "level_choices": ["S", "S+", "B", "B+", "A", "A+"],
    }
    return render(request, "settings.html", context)


@login_required
def dashboard_view(request):
    profile = _get_or_sync_profile(request.user)
    subscribed_subject_ids = _get_active_subscription_ids(request.user)
    subject_queryset = Subject.objects.all().annotate(test_count=Count("test"))
    selected_subject_id = request.GET.get("subject")

    subjects = []
    for subject in subject_queryset:
        subject_name_lower = subject.name.lower()
        if "ona tili" in subject_name_lower or "adab" in subject_name_lower:
            meta = "Matn, grammatika va AI yordamida insho ustida ishlash"
        elif "tarix" in subject_name_lower:
            meta = "Tarixiy jarayonlar, sanalar va manbalar tahlili"
        elif "matem" in subject_name_lower:
            meta = "Masala, mantiq va tezkor ishlash ritmi"
        else:
            meta = "Milliy sertifikatga mos tayyorlov oqimi"

        subjects.append(
            {
                "name": subject.name,
                "status": "Faol tayyorlov" if subject.id in subscribed_subject_ids else "Mavjud yo'nalish",
                "meta": meta,
                "test_count": subject.test_count,
                "is_owned": subject.id in subscribed_subject_ids,
                "id": subject.id,
                "is_selected": str(subject.id) == str(selected_subject_id),
            }
        )

    latest_test = Test.objects.select_related("subject").order_by("-created_at").first()
    featured_book = Book.objects.select_related("subject").order_by("-is_featured", "-created_at").first()

    user_test_stats = UserTest.objects.filter(user=request.user).aggregate(
        best_score=Max("score"),
        total_tests=Count("id"),
    )
    level_info = get_level_info(profile.xp)
    if profile.level != level_info["label"]:
        profile.level = level_info["label"]
        profile.save(update_fields=["level"])

    quick_actions = [
        "Fanlarni tekshirish va obunalarni ko'rish",
        "Testlar sahifasidan mashqni boshlash",
        "Kitoblar sahifasidan resurslarni ochish",
    ]
    hub_cards = [
        {
            "title": "Testlar / Mashqlar",
            "description": "Alohida sahifada barcha testlar, murakkablik va vaqt bo'yicha ko'rinadi.",
            "href": "tests",
            "meta": latest_test.title if latest_test else "Hali test qo'shilmagan",
        },
        {
            "title": "Kitoblar",
            "description": "PDF formatdagi resurslar va fan bo'yicha tavsiya qilingan materiallar.",
            "href": "books",
            "meta": featured_book.title if featured_book else "Hali kitob qo'shilmagan",
        },
        {
            "title": "Reyting",
            "description": "Admin uchun foydalanuvchilar ro'yxati va natijalarga asoslangan umumiy ko'rinish.",
            "href": "ranking",
            "meta": "Faqat admin uchun",
        },
    ]
    stats = [
        {
            "label": "Daraja",
            "value": level_info["label"],
            "hint": f'{level_info["xp"]} XP, keyingi bosqichgacha {level_info["xp_to_next"]} XP',
        },
        {
            "label": "Fanlar",
            "value": f"{len(subjects)} ta",
            "hint": "Dashboardda ko'rinayotgan yo'nalishlar soni",
        },
        {
            "label": "XP",
            "value": profile.xp,
            "hint": "Faqat to'liq to'g'ri ishlangan test uchun 1 XP",
        },
    ]
    context = {
        "profile": profile,
        "stats": stats,
        "subjects": subjects,
        "hub_cards": hub_cards,
        "quick_actions": quick_actions,
        "level_info": level_info,
    }
    return render(request, "dashboard.html", context)


@login_required
def subject_workspace_view(request, subject_id):
    profile = _get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    allowed_levels = get_allowed_level_labels(profile.level)
    subject = get_object_or_404(Subject.objects.annotate(test_count=Count("test")), id=subject_id)

    if not _user_can_access_subject(request.user, subject.id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")

    active_subject_ids = set(_get_active_subscription_ids(request.user))
    current_section = request.GET.get("section", "home")
    subject_theme = _get_subject_theme(subject.name)
    allowed_sections = {"home", "books", "tests", "ai", "chat"} | {
        item["key"] for item in subject_theme["extra_sections"]
    }
    if current_section not in allowed_sections:
        current_section = "home"

    peer_subjects = [
        {
            "id": item.id,
            "name": item.name,
            "is_owned": item.id in active_subject_ids,
            "is_current": item.id == subject.id,
        }
        for item in Subject.objects.exclude(id=subject.id).order_by("name")[:2]
    ]

    books = list(
        _filter_by_allowed_level(Book.objects.filter(subject=subject), "access_level", profile.level)
        .order_by("-is_featured", "-created_at")[:6]
    )
    tests = list(
        _filter_by_allowed_level(Test.objects.filter(subject=subject), "difficulty", profile.level)
        .annotate(question_count=Count("question"))
        .order_by("-created_at")[:6]
    )
    test_attempt_stats = {
        row["test_id"]: row
        for row in (
            UserTest.objects.filter(user=request.user, test__subject=subject)
            .values("test_id")
            .annotate(
                attempts=Count("id"),
                best_score=Max("score"),
                last_score=Max("score"),
            )
        )
    }
    for test in tests:
        test.display_difficulty = normalize_difficulty_label(test.difficulty)
        attempt_data = test_attempt_stats.get(test.id, {})
        test.attempts = attempt_data.get("attempts", 0)
        test.best_score = attempt_data.get("best_score")
        test.last_score = attempt_data.get("last_score")
    practice_exercises = list(
        _filter_by_allowed_level(PracticeExercise.objects.filter(subject=subject), "difficulty", profile.level)
        .prefetch_related("choices")
        .order_by("-is_featured", "-created_at")[:12]
    )
    practice_attempt_rows = (
        UserPracticeAttempt.objects.filter(user=request.user, exercise__subject=subject)
        .select_related("exercise")
        .order_by("-created_at")
    )
    practice_attempt_map = {}
    for attempt in practice_attempt_rows:
        summary = practice_attempt_map.setdefault(
            attempt.exercise_id,
            {"attempts": 0, "last_is_correct": attempt.is_correct},
        )
        summary["attempts"] += 1
    for exercise in practice_exercises:
        summary = practice_attempt_map.get(exercise.id, {})
        exercise.attempts = summary.get("attempts", 0)
        exercise.last_is_correct = summary.get("last_is_correct")
        exercise.choice_count = exercise.choices.count()

    section_items = [
        {"key": "home", "label": "Asosiy menyu"},
        {"key": "books", "label": "Kitoblar"},
        {"key": "tests", "label": "Mashqlar (Test)"},
    ]
    section_items.extend(subject_theme["extra_sections"])
    section_items.extend(
        [
            {"key": "ai", "label": "Ai yordamchi"},
            {"key": "chat", "label": "Chat"},
        ]
    )
    for item in section_items:
        item["is_active"] = item["key"] == current_section

    user_subject_best = (
        UserTest.objects.filter(user=request.user, test__subject=subject)
        .aggregate(best_score=Max("score"))
        .get("best_score")
    ) or 0
    home_metrics = [
        {"label": "Joriy daraja", "value": level_info["label"], "hint": f"{profile.xp} XP bilan ochilgan umumiy daraja"},
        {"label": "Testlar", "value": subject.test_count, "hint": "Mavjud mashqlar soni"},
        {"label": "Eng yaxshi natija", "value": f"{user_subject_best}%", "hint": "Shu fan bo'yicha eng yaxshi foiz"},
    ]
    formula_query = (request.GET.get("q") or "").strip()
    formula_filter = request.GET.get("formula_filter", "all")
    formulas_queryset = SubjectSectionEntry.objects.filter(subject=subject, section_key="formulas").order_by("order", "-is_featured", "-created_at")
    if formula_query:
        formulas_queryset = formulas_queryset.filter(
            Q(title__icontains=formula_query)
            | Q(summary__icontains=formula_query)
            | Q(body__icontains=formula_query)
        )
    if formula_filter == "featured":
        formulas_queryset = formulas_queryset.filter(is_featured=True)
    formula_entries = list(formulas_queryset)

    section_entries = list(
        _filter_by_allowed_level(
            SubjectSectionEntry.objects.filter(subject=subject, section_key=current_section),
            "access_level",
            profile.level,
        )
    )
    essay_topics = list(
        _filter_by_allowed_level(EssayTopic.objects.filter(subject=subject), "access_level", profile.level)[:6]
    )
    current_section_label = next(
        (item["label"] for item in section_items if item["key"] == current_section),
        "Bo'lim",
    )

    context = {
        "profile": profile,
        "level_info": level_info,
        "subject": subject,
        "peer_subjects": peer_subjects,
        "current_section": current_section,
        "section_items": section_items,
        "books": books,
        "tests": tests,
        "practice_exercises": practice_exercises,
        "subject_theme": subject_theme,
        "home_metrics": home_metrics,
        "section_entries": section_entries,
        "current_section_label": current_section_label,
        "essay_topics": essay_topics,
        "allowed_levels": allowed_levels,
        "current_path": request.get_full_path(),
        "formula_entries": formula_entries,
        "formula_query": formula_query,
        "formula_filter": formula_filter,
    }
    return render(request, "subject_workspace.html", context)


@login_required
def profile_view(request):
    profile = _get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    subscriptions = list(
        Subscription.objects.select_related("subject")
        .filter(user=request.user)
        .order_by("-end_date")
    )

    subject_statuses = []
    active_count = 0
    for subscription in subscriptions:
        is_active = subscription.end_date >= timezone.now()
        if is_active:
            active_count += 1
        best_score = (
            UserTest.objects.filter(user=request.user, test__subject=subscription.subject)
            .aggregate(best_score=Max("score"))
            .get("best_score")
        )
        subject_statuses.append(
            {
                "subject": subscription.subject.name,
                "expires_at": subscription.end_date,
                "is_active": is_active,
                "level": level_info["label"],
                "score": best_score or 0,
            }
        )

    rank_users = (
        User.objects.select_related("profile")
        .annotate(
            best_score=Coalesce(Max("usertest__score"), Value(0)),
            total_tests=Count("usertest"),
        )
        .order_by("-profile__xp", "-best_score", "-total_tests", "username")
    )
    rank_position = next(
        (index for index, user in enumerate(rank_users, start=1) if user.id == request.user.id),
        None,
    )
    total_tests = UserTest.objects.filter(user=request.user).count()
    purchased_subject_names = [item.subject.name for item in subscriptions]
    context = {
        "profile": profile,
        "level_info": level_info,
        "subject_statuses": subject_statuses,
        "rank_position": rank_position,
        "total_tests": total_tests,
        "purchased_subject_names": purchased_subject_names,
        "active_subject_count": active_count,
        "member_since": profile.created_at,
    }
    return render(request, "profile.html", context)


@login_required
def subject_selection_view(request):
    sidebar = _sidebar_context(request.user)
    subscribed_subject_ids = set(_get_active_subscription_ids(request.user))
    subjects = Subject.objects.all().annotate(test_count=Count("test")).order_by("name")

    subject_cards = []
    for subject in subjects:
        subject_cards.append(
            {
                "id": subject.id,
                "name": subject.name,
                "price": subject.price,
                "test_count": subject.test_count,
                "is_active": subject.id in subscribed_subject_ids,
            }
        )

    context = {
        **sidebar,
        "subject_cards": subject_cards,
        "active_count": len(subscribed_subject_ids),
    }
    return render(request, "subject_selection.html", context)


@login_required
def tests_list_view(request):
    sidebar = _sidebar_context(request.user)
    profile = sidebar["profile"]
    subscribed_subject_ids = _get_active_subscription_ids(request.user)
    test_queryset = (
        _filter_by_allowed_level(Test.objects.select_related("subject"), "difficulty", profile.level)
        .annotate(question_count=Count("question"))
        .order_by("-created_at")
    )
    if subscribed_subject_ids:
        test_queryset = test_queryset.filter(subject_id__in=subscribed_subject_ids)

    tests = [
            {
                "id": test.id,
                "title": test.title,
                "subject": test.subject.name,
                "difficulty": normalize_difficulty_label(test.difficulty),
                "duration": test.duration,
                "question_count": test.question_count,
            }
        for test in test_queryset
    ]
    return render(request, "tests_list.html", {**sidebar, "tests": tests})


@login_required
def books_list_view(request):
    sidebar = _sidebar_context(request.user)
    profile = sidebar["profile"]
    book_queryset = _filter_by_allowed_level(
        Book.objects.select_related("subject").order_by("-is_featured", "-created_at"),
        "access_level",
        profile.level,
    )
    books = [
        {
            "id": book.id,
            "title": book.title,
            "subject": book.subject.name,
            "author": book.author,
            "description": book.description,
            "pdf_url": book.pdf_file.url if book.pdf_file else "",
        }
        for book in book_queryset
    ]
    return render(request, "books_list.html", {**sidebar, "books": books})


@login_required
def book_read_view(request, book_id):
    book = get_object_or_404(Book.objects.select_related("subject"), id=book_id)
    profile = _get_or_sync_profile(request.user)
    if not book.pdf_file:
        messages.error(request, "Bu kitob uchun hali PDF yuklanmagan.")
        return redirect("books")
    if not _user_can_access_subject(request.user, book.subject_id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")
    if normalize_difficulty_label(book.access_level) not in get_allowed_level_labels(profile.level):
        messages.error(request, "Sizning hozirgi darajangiz bu kitobni ochish uchun yetarli emas.")
        return redirect("subject-workspace", subject_id=book.subject_id)

    reader_tokens = request.session.get("reader_tokens", {})
    token = secrets.token_urlsafe(24)
    reader_tokens[str(book.id)] = token
    request.session["reader_tokens"] = reader_tokens
    request.session.modified = True

    return render(request, "book_read.html", {"book": book, "reader_token": token})


@login_required
@xframe_options_exempt
def book_pdf_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    profile = _get_or_sync_profile(request.user)
    if not book.pdf_file:
        messages.error(request, "Bu kitob uchun hali PDF yuklanmagan.")
        return redirect("books")
    if normalize_difficulty_label(book.access_level) not in get_allowed_level_labels(profile.level):
        return HttpResponseForbidden("Bu kitob sizning darajangiz uchun yopilgan.")

    session_tokens = request.session.get("reader_tokens", {})
    provided_token = request.GET.get("token", "")
    expected_token = session_tokens.get(str(book.id))
    fetch_dest = request.META.get("HTTP_SEC_FETCH_DEST", "")

    if not expected_token or provided_token != expected_token:
        return HttpResponseForbidden("Bu PDF faqat sayt ichidagi reader orqali ochiladi.")

    if fetch_dest and fetch_dest not in {"iframe", "embed", "object"}:
        return HttpResponseForbidden("Bu PDF alohida ochish uchun yopilgan.")

    response = FileResponse(book.pdf_file.open("rb"), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{book.pdf_file.name.split("/")[-1]}"'
    response["Cache-Control"] = "private, no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@user_passes_test(lambda user: user.is_superuser)
def ranking_view(request):
    sidebar = _sidebar_context(request.user)
    users = (
        User.objects.select_related("profile")
        .annotate(
            best_score=Coalesce(Max("usertest__score"), Value(0)),
            total_tests=Count("usertest"),
        )
        .order_by("-profile__xp", "-best_score", "-total_tests", "username")
    )

    ranking_rows = []
    for index, user in enumerate(users, start=1):
        profile = getattr(user, "profile", None)
        display_name = (
            profile.full_name if profile and profile.full_name
            else user.first_name or user.username
        )
        ranking_rows.append(
            {
                "rank": index,
                "name": display_name,
                "username": user.username,
                "best_score": user.best_score,
                "tests": user.total_tests,
                "level": getattr(profile, "level", "S") if profile else "S",
                "xp": getattr(profile, "xp", 0) if profile else 0,
            }
        )

    return render(request, "ranking.html", {**sidebar, "ranking_rows": ranking_rows})


@login_required
def statistics_view(request):
    sidebar = _sidebar_context(request.user)
    active_subject_ids = set(_get_active_subscription_ids(request.user))
    user_tests = UserTest.objects.filter(user=request.user).select_related("test", "test__subject")

    overall = user_tests.aggregate(
        total_tests=Count("id"),
        best_score=Max("score"),
        total_correct=Coalesce(Sum("correct_count"), Value(0)),
    )

    subject_rows = []
    current_level = sidebar["level_info"]
    for subject in Subject.objects.all().annotate(test_count=Count("test")).order_by("name"):
        subject_tests = user_tests.filter(test__subject=subject)
        best_score = subject_tests.aggregate(best_score=Max("score")).get("best_score") or 0
        attempts = subject_tests.count()
        subject_rows.append(
            {
                "name": subject.name,
                "is_owned": subject.id in active_subject_ids,
                "attempts": attempts,
                "best_score": best_score,
                "level": current_level["label"],
                "progress_percent": best_score,
                "test_count": subject.test_count,
            }
        )

    recent_attempts = [
        {
            "subject": item.test.subject.name,
            "title": item.test.title,
            "score": item.score,
            "correct_count": item.correct_count,
            "finished_at": item.finished_at,
        }
        for item in user_tests.order_by("-finished_at")[:6]
    ]

    stats = [
        {"label": "Jami urinish", "value": overall["total_tests"] or 0, "hint": "Ishlangan testlar soni"},
        {"label": "Eng yaxshi natija", "value": f"{overall['best_score'] or 0}%", "hint": "100 ballik foiz tizimi bo'yicha"},
        {"label": "To'g'ri javoblar", "value": overall["total_correct"] or 0, "hint": "Barcha urinishlar bo'yicha"},
        {"label": "XP", "value": sidebar["profile"].xp, "hint": "Umumiy tajriba ochkolari"},
    ]

    context = {
        **sidebar,
        "stats": stats,
        "subject_rows": subject_rows,
        "recent_attempts": recent_attempts,
    }
    return render(request, "statistics.html", context)


@login_required
def test_start_view(request, test_id):
    test = get_object_or_404(Test.objects.select_related("subject"), id=test_id)
    profile = _get_or_sync_profile(request.user)
    if not _user_can_access_subject(request.user, test.subject_id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")
    if normalize_difficulty_label(test.difficulty) not in get_allowed_level_labels(profile.level):
        messages.error(request, "Sizning hozirgi darajangiz bu testni ochish uchun yetarli emas.")
        return redirect("subject-workspace", subject_id=test.subject_id)

    question_count = Question.objects.filter(test=test).count()
    if question_count == 0:
        messages.error(request, "Bu testga hali savollar qo'shilmagan.")
        return redirect("tests")

    next_url = request.GET.get("next") or request.POST.get("next") or ""

    if request.method == "POST":
        started_at = timezone.now()
        user_test = UserTest.objects.create(
            user=request.user,
            test=test,
            score=0,
            correct_count=0,
            started_at=started_at,
            finished_at=started_at,
            snapshot_json={
                "status": "started",
                "question_count": question_count,
                "subject": test.subject.name,
                "next_url": next_url,
            },
        )
        return redirect("test-solve", user_test_id=user_test.id)

    context = {
        "test": test,
        "test_difficulty": normalize_difficulty_label(test.difficulty),
        "question_count": question_count,
        "next_url": next_url,
    }
    return render(request, "test_start.html", context)


@login_required
def test_solve_view(request, user_test_id):
    user_test = get_object_or_404(
        UserTest.objects.select_related("test", "test__subject"),
        id=user_test_id,
        user=request.user,
    )
    if user_test.snapshot_json.get("status") == "completed":
        return redirect("test-result", user_test_id=user_test.id)

    test = user_test.test
    questions = list(
        Question.objects.filter(test=test)
        .prefetch_related("choice_set")
        .order_by("id")
    )
    if not questions:
        messages.error(request, "Bu testga hali savollar qo'shilmagan.")
        return redirect("tests")

    if request.method == "POST":
        correct_count = 0
        submitted_answers = []

        for question in questions:
            selected_choice_id = request.POST.get(f"question_{question.id}")
            selected_choice = None
            is_correct = False

            if selected_choice_id:
                selected_choice = next(
                    (choice for choice in question.choice_set.all() if str(choice.id) == selected_choice_id),
                    None,
                )
                is_correct = bool(selected_choice and selected_choice.is_correct)

            UserAnswer.objects.update_or_create(
                user=request.user,
                question=question,
                defaults={
                    "selected_choice": selected_choice,
                    "is_correct": is_correct,
                },
            )

            if is_correct:
                correct_count += 1

            submitted_answers.append(
                {
                    "question_id": question.id,
                    "selected_choice_id": selected_choice.id if selected_choice else None,
                    "is_correct": is_correct,
                }
            )

        total_questions = len(questions)
        score = round((correct_count / total_questions) * 100) if total_questions else 0
        xp_awarded = XP_PER_TEST if total_questions and correct_count == total_questions else 0
        profile = _get_or_sync_profile(request.user)
        profile.xp += xp_awarded
        updated_level = get_level_info(profile.xp)
        profile.level = updated_level["label"]
        profile.save(update_fields=["xp", "level"])

        user_test.correct_count = correct_count
        user_test.score = score
        user_test.finished_at = timezone.now()
        user_test.snapshot_json = {
            "status": "completed",
            "question_count": total_questions,
            "answers": submitted_answers,
            "xp_awarded": xp_awarded,
        }
        user_test.save(update_fields=["correct_count", "score", "finished_at", "snapshot_json"])
        return redirect("test-result", user_test_id=user_test.id)

    context = {
        "user_test": user_test,
        "test": test,
        "questions": questions,
        "next_url": user_test.snapshot_json.get("next_url", ""),
    }
    return render(request, "test_solve.html", context)


@login_required
def test_result_view(request, user_test_id):
    user_test = get_object_or_404(
        UserTest.objects.select_related("test", "test__subject"),
        id=user_test_id,
        user=request.user,
    )
    total_questions = user_test.snapshot_json.get("question_count", 0)
    profile = _get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    questions = list(
        Question.objects.filter(test=user_test.test)
        .prefetch_related("choice_set")
        .order_by("id")
    )
    user_answers = {
        answer.question_id: answer
        for answer in UserAnswer.objects.select_related("selected_choice").filter(
            user=request.user,
            question__test=user_test.test,
        )
    }
    answer_review = []
    for question in questions:
        correct_choice = next((choice for choice in question.choice_set.all() if choice.is_correct), None)
        user_answer = user_answers.get(question.id)
        answer_review.append(
            {
                "question": question.text,
                "selected": user_answer.selected_choice.text if user_answer and user_answer.selected_choice else "Javob tanlanmagan",
                "correct": correct_choice.text if correct_choice else "To'g'ri javob belgilanmagan",
                "is_correct": bool(user_answer and user_answer.is_correct),
            }
        )
    context = {
        "user_test": user_test,
        "test": user_test.test,
        "total_questions": total_questions,
        "level_info": level_info,
        "xp_awarded": user_test.snapshot_json.get("xp_awarded", 0),
        "answer_review": answer_review,
        "next_url": user_test.snapshot_json.get("next_url", ""),
    }
    return render(request, "test_result.html", context)


@login_required
def practice_solve_view(request, exercise_id):
    exercise = get_object_or_404(
        PracticeExercise.objects.select_related("subject").prefetch_related("choices"),
        id=exercise_id,
    )
    profile = _get_or_sync_profile(request.user)
    if not _user_can_access_subject(request.user, exercise.subject_id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")
    if normalize_difficulty_label(exercise.difficulty) not in get_allowed_level_labels(profile.level):
        messages.error(request, "Sizning hozirgi darajangiz bu mashqni ochish uchun yetarli emas.")
        return redirect("subject-workspace", subject_id=exercise.subject_id)

    next_url = request.GET.get("next") or request.POST.get("next") or ""

    if request.method == "POST":
        selected_choice = None
        answer_text = ""
        is_correct = False

        if exercise.answer_mode == "choice":
            selected_choice_id = request.POST.get("selected_choice")
            if not selected_choice_id:
                messages.error(request, "Variantlardan birini tanlang.")
                return redirect(f"{request.path}?next={next_url}")
            selected_choice = next((choice for choice in exercise.choices.all() if str(choice.id) == selected_choice_id), None)
            is_correct = bool(selected_choice and selected_choice.is_correct)
        else:
            answer_text = (request.POST.get("answer_text") or "").strip()
            if not answer_text:
                messages.error(request, "Javobni kiriting.")
                return redirect(f"{request.path}?next={next_url}")
            normalized_answer = answer_text.casefold().strip()
            normalized_correct = (exercise.correct_text or "").casefold().strip()
            is_correct = normalized_answer == normalized_correct

        attempt = UserPracticeAttempt.objects.create(
            user=request.user,
            exercise=exercise,
            selected_choice=selected_choice,
            answer_text=answer_text,
            is_correct=is_correct,
        )
        request.session["practice_next_url"] = next_url
        return redirect("practice-result", attempt_id=attempt.id)

    context = {
        "exercise": exercise,
        "choices": list(exercise.choices.all()),
        "next_url": next_url,
    }
    return render(request, "practice_solve.html", context)


@login_required
def practice_result_view(request, attempt_id):
    attempt = get_object_or_404(
        UserPracticeAttempt.objects.select_related("exercise", "exercise__subject", "selected_choice"),
        id=attempt_id,
        user=request.user,
    )
    exercise = attempt.exercise
    next_url = request.session.get("practice_next_url", "")
    correct_choice = None
    if exercise.answer_mode == "choice":
        correct_choice = exercise.choices.filter(is_correct=True).first()

    context = {
        "attempt": attempt,
        "exercise": exercise,
        "correct_choice": correct_choice,
        "next_url": next_url,
    }
    return render(request, "practice_result.html", context)
