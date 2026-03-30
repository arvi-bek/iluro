from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Max, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from .models import Profile, Subject, Subscription, Test, UserTest, Book, Question, UserAnswer
from .utils import XP_PER_TEST, get_level_info


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


def _get_active_subscription_ids(user):
    return list(
        Subscription.objects.filter(
            user=user,
            end_date__gte=timezone.now(),
        ).values_list("subject_id", flat=True)
    )


def _user_can_access_subject(user, subject_id):
    active_ids = _get_active_subscription_ids(user)
    return not active_ids or subject_id in active_ids


@login_required
def dashboard_view(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={
            "full_name": request.user.first_name or request.user.username,
        },
    )
    subscribed_subject_ids = _get_active_subscription_ids(request.user)
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
def subject_selection_view(request):
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
        "subject_cards": subject_cards,
        "active_count": len(subscribed_subject_ids),
    }
    return render(request, "subject_selection.html", context)


@login_required
def tests_list_view(request):
    subscribed_subject_ids = _get_active_subscription_ids(request.user)
    test_queryset = Test.objects.select_related("subject").annotate(question_count=Count("question")).order_by("-created_at")
    if subscribed_subject_ids:
        test_queryset = test_queryset.filter(subject_id__in=subscribed_subject_ids)

    tests = [
        {
            "id": test.id,
            "title": test.title,
            "subject": test.subject.name,
            "difficulty": test.difficulty,
            "duration": test.duration,
            "question_count": test.question_count,
        }
        for test in test_queryset
    ]
    return render(request, "tests_list.html", {"tests": tests})


@login_required
def books_list_view(request):
    book_queryset = Book.objects.select_related("subject").order_by("-is_featured", "-created_at")
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
    return render(request, "books_list.html", {"books": books})


@login_required
def book_read_view(request, book_id):
    book = get_object_or_404(Book.objects.select_related("subject"), id=book_id)
    if not book.pdf_file:
        messages.error(request, "Bu kitob uchun hali PDF yuklanmagan.")
        return redirect("books")

    return render(request, "book_read.html", {"book": book})


@login_required
@xframe_options_exempt
def book_pdf_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    if not book.pdf_file:
        messages.error(request, "Bu kitob uchun hali PDF yuklanmagan.")
        return redirect("books")

    response = FileResponse(book.pdf_file.open("rb"), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{book.pdf_file.name.split("/")[-1]}"'
    return response


@user_passes_test(lambda user: user.is_superuser)
def ranking_view(request):
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

    return render(request, "ranking.html", {"ranking_rows": ranking_rows})


@login_required
def test_start_view(request, test_id):
    test = get_object_or_404(Test.objects.select_related("subject"), id=test_id)
    if not _user_can_access_subject(request.user, test.subject_id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")

    question_count = Question.objects.filter(test=test).count()
    if question_count == 0:
        messages.error(request, "Bu testga hali savollar qo'shilmagan.")
        return redirect("tests")

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
            },
        )
        return redirect("test-solve", user_test_id=user_test.id)

    context = {
        "test": test,
        "question_count": question_count,
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
        score = round((correct_count / total_questions) * 50) if total_questions else 0
        xp_awarded = XP_PER_TEST if total_questions and correct_count == total_questions else 0
        profile, _ = Profile.objects.get_or_create(
            user=request.user,
            defaults={"full_name": request.user.first_name or request.user.username},
        )
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
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={"full_name": request.user.first_name or request.user.username},
    )
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
    }
    return render(request, "test_result.html", context)
