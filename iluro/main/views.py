from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Max, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Profile, Subject, Subscription, Test, UserTest, Book
from .utils import get_level_info


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        full_name = request.POST.get("full_name")
        password = request.POST.get("password")
        password2 = request.POST.get("password2")

        if password != password2:
            messages.error(request, "Parollar bir xil emas.")
            return redirect("register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Bu username allaqachon mavjud.")
            return redirect("register")

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=full_name
        )
        Profile.objects.create(
            user=user,
            full_name=full_name,
        )
        login(request, user)
        return redirect("dashboard")

    return render(request, "auth/register.html")


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


@login_required
def dashboard_view(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={
            "full_name": request.user.first_name or request.user.username,
        },
    )
    active_subscriptions = Subscription.objects.filter(
        user=request.user,
        end_date__gte=timezone.now(),
    )
    subscribed_subject_ids = list(active_subscriptions.values_list("subject_id", flat=True))
    subject_queryset = Subject.objects.all().annotate(test_count=Count("test"))
    if subscribed_subject_ids:
        subject_queryset = subject_queryset.filter(id__in=subscribed_subject_ids)

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
            }
        )

    latest_test = Test.objects.select_related("subject").order_by("-created_at").first()
    featured_book = Book.objects.select_related("subject").order_by("-is_featured", "-created_at").first()

    user_test_stats = UserTest.objects.filter(user=request.user).aggregate(
        best_score=Max("score"),
        total_tests=Count("id"),
    )
    level_info = get_level_info(user_test_stats["best_score"])
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
            "hint": f'{level_info["score"]}/{level_info["max_score"]} ball, oralig\'i {level_info["range_text"]}',
        },
        {
            "label": "Fanlar",
            "value": f"{len(subjects)} ta",
            "hint": "Dashboardda ko'rinayotgan yo'nalishlar soni",
        },
        {
            "label": "Testlar",
            "value": user_test_stats["total_tests"] or 0,
            "hint": "Ishlangan testlar soni",
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
def subject_selection_view(request):
    active_subscriptions = Subscription.objects.filter(
        user=request.user,
        end_date__gte=timezone.now(),
    )
    subscribed_subject_ids = set(active_subscriptions.values_list("subject_id", flat=True))
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
        "subject_cards": subject_cards,
        "active_count": len(subscribed_subject_ids),
    }
    return render(request, "subject_selection.html", context)


@login_required
def tests_list_view(request):
    active_subscriptions = Subscription.objects.filter(
        user=request.user,
        end_date__gte=timezone.now(),
    )
    subscribed_subject_ids = list(active_subscriptions.values_list("subject_id", flat=True))
    test_queryset = Test.objects.select_related("subject").order_by("-created_at")
    if subscribed_subject_ids:
        test_queryset = test_queryset.filter(subject_id__in=subscribed_subject_ids)

    tests = [
        {
            "title": test.title,
            "subject": test.subject.name,
            "difficulty": test.difficulty,
            "duration": test.duration,
        }
        for test in test_queryset
    ]
    return render(request, "tests_list.html", {"tests": tests})


@login_required
def books_list_view(request):
    book_queryset = Book.objects.select_related("subject").order_by("-is_featured", "-created_at")
    books = [
        {
            "title": book.title,
            "subject": book.subject.name,
            "author": book.author,
            "description": book.description,
            "pdf_url": book.pdf_file.url if book.pdf_file else "",
        }
        for book in book_queryset
    ]
    return render(request, "books_list.html", {"books": books})


@user_passes_test(lambda user: user.is_superuser)
def ranking_view(request):
    users = (
        User.objects.select_related("profile")
        .annotate(
            best_score=Coalesce(Max("usertest__score"), Value(0)),
            total_tests=Count("usertest"),
        )
        .order_by("-best_score", "-total_tests", "username")
    )

    ranking_rows = []
    for index, user in enumerate(users, start=1):
        profile = getattr(user, "profile", None)
        display_name = (
            profile.full_name if profile and profile.full_name
            else user.first_name or user.username
        )
        level_info = get_level_info(user.best_score)
        ranking_rows.append(
            {
                "rank": index,
                "name": display_name,
                "username": user.username,
                "best_score": user.best_score,
                "tests": user.total_tests,
                "level": level_info["label"],
            }
        )

    return render(request, "ranking.html", {"ranking_rows": ranking_rows})
