import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import OperationalError, ProgrammingError
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_exempt

from .models import Book, BookView, Subject
from .selectors import (
    apply_book_filter,
    get_book_bucket_label,
    get_book_filter_config,
    get_tests_listing,
    is_language_subject,
)
from .services import (
    get_active_subscription_ids as _get_active_subscription_ids,
    get_or_sync_profile as _get_or_sync_profile,
    sidebar_context as _sidebar_context,
    user_can_access_subject as _user_can_access_subject,
)


@login_required
def tests_list_view(request):
    sidebar = _sidebar_context(request.user)
    tests = get_tests_listing(request.user, sidebar["profile"].level)
    return render(request, "tests_list.html", {**sidebar, "tests": tests})


@login_required
def books_list_view(request):
    sidebar = _sidebar_context(request.user)
    owned_subject_ids = set(_get_active_subscription_ids(request.user))
    selected_subject_id = request.GET.get("subject", "").strip()
    selected_grade = request.GET.get("grade", "").strip()
    subject_queryset = Subject.objects.filter(id__in=owned_subject_ids).order_by("name")
    selected_subject = None
    book_queryset = Book.objects.select_related("subject").order_by("-is_featured", "-created_at")
    book_filter_config = {"title": "Sinf bo'yicha", "choices": []}

    if selected_subject_id.isdigit():
        selected_subject = get_object_or_404(Subject, id=selected_subject_id)
        if not _user_can_access_subject(request.user, selected_subject.id):
            messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
            return redirect("subject-selection")
        book_queryset = book_queryset.filter(subject=selected_subject)
        book_filter_config = get_book_filter_config(selected_subject)
    else:
        book_queryset = book_queryset.none()

    if selected_subject:
        book_queryset = apply_book_filter(book_queryset, selected_subject, selected_grade)

    try:
        book_items = list(book_queryset.annotate(viewer_count=Coalesce(Sum("views__view_count"), Value(0))))
        books = [
            {
                "id": book.id,
                "title": book.title,
                "subject": book.subject.name,
                "grade": get_book_bucket_label(book),
                "author": book.author,
                "description": book.description,
                "pdf_url": book.pdf_file.url if book.pdf_file else "",
                "is_featured": book.is_featured,
                "viewer_count": book.viewer_count,
            }
            for book in book_items
        ]
    except (ProgrammingError, OperationalError):
        books = [
            {
                "id": book.id,
                "title": book.title,
                "subject": book.subject.name,
                "grade": get_book_bucket_label(book),
                "author": book.author,
                "description": book.description,
                "pdf_url": book.pdf_file.url if book.pdf_file else "",
                "is_featured": book.is_featured,
                "viewer_count": 0,
            }
            for book in book_queryset
        ]
    grade_filters = [{"value": "", "label": "Barchasi", "is_active": selected_grade == ""}]
    grade_filters.extend(
        {
            "value": value,
            "label": label,
            "is_active": selected_grade == value,
        }
        for value, label in book_filter_config["choices"]
    )
    grade_filters.append(
        {
            "value": "other",
            "label": "Boshqalar",
            "is_active": selected_grade == "other",
        }
    )
    subject_cards = [
        {
            "id": subject.id,
            "name": subject.name,
            "is_owned": True,
        }
        for subject in subject_queryset
    ]
    return render(
        request,
        "books_list.html",
        {
            **sidebar,
            "books": books,
            "grade_filters": grade_filters,
            "book_filter_title": book_filter_config["title"],
            "selected_grade": selected_grade,
            "selected_subject": selected_subject,
            "show_language_notice": bool(selected_subject and is_language_subject(selected_subject)),
            "subject_cards": subject_cards,
            "current_books_path": request.get_full_path(),
        },
    )


@login_required
def book_read_view(request, book_id):
    book = get_object_or_404(Book.objects.select_related("subject"), id=book_id)
    if not book.pdf_file:
        messages.error(request, "Bu kitob uchun hali PDF yuklanmagan.")
        return redirect("books")
    if not _user_can_access_subject(request.user, book.subject_id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")
    _get_or_sync_profile(request.user)
    try:
        book_view, created = BookView.objects.get_or_create(user=request.user, book=book)
        if not created:
            book_view.view_count += 1
            book_view.save(update_fields=["view_count", "last_viewed_at"])
        viewer_count = book.views.aggregate(total=Coalesce(Sum("view_count"), Value(0))).get("total", 0)
    except (ProgrammingError, OperationalError):
        viewer_count = 0
    reader_tokens = request.session.get("reader_tokens", {})
    token = secrets.token_urlsafe(24)
    reader_tokens[str(book.id)] = token
    request.session["reader_tokens"] = reader_tokens
    request.session.modified = True
    next_url = request.GET.get("next", "").strip()
    reader_mode = (request.GET.get("mode") or "").strip().lower()
    is_full_reader = reader_mode == "full"
    back_url = next_url or f"/subjects/{book.subject_id}/books/"
    full_reader_url = f"/books/{book.id}/read/?mode=full"
    if next_url:
        full_reader_url = f"{full_reader_url}&next={next_url}"
    reader_pdf_url = f"/books/{book.id}/pdf/?token={token}"

    return render(
        request,
        "book_read_full.html" if is_full_reader else "book_read.html",
        {
            "book": book,
            "reader_token": token,
            "back_url": back_url,
            "viewer_count": viewer_count,
            "mobile_pdf_url": f"/books/{book.id}/pdf/?token={token}&reader=mobile#toolbar=0&navpanes=0",
            "full_reader_url": full_reader_url,
            "reader_pdf_url": reader_pdf_url,
        },
    )


@login_required
@xframe_options_exempt
def book_pdf_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    if not book.pdf_file:
        messages.error(request, "Bu kitob uchun hali PDF yuklanmagan.")
        return redirect("books")

    session_tokens = request.session.get("reader_tokens", {})
    provided_token = request.GET.get("token", "")
    expected_token = session_tokens.get(str(book.id))
    fetch_dest = request.META.get("HTTP_SEC_FETCH_DEST", "")
    reader_mode = request.GET.get("reader", "")
    if not expected_token or provided_token != expected_token:
        return HttpResponseForbidden("Bu PDF faqat sayt ichidagi reader orqali ochiladi.")

    if reader_mode != "mobile" and fetch_dest and fetch_dest not in {"iframe", "embed", "object"}:
        return HttpResponseForbidden("Bu PDF alohida ochish uchun yopilgan.")

    response = FileResponse(book.pdf_file.open("rb"), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{book.pdf_file.name.split("/")[-1]}"'
    response["Cache-Control"] = "private, no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response
