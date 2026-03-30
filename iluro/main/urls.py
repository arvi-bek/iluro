from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("subjects/", views.subject_selection_view, name="subject-selection"),
    path("tests/", views.tests_list_view, name="tests"),
    path("tests/<int:test_id>/start/", views.test_start_view, name="test-start"),
    path("tests/session/<int:user_test_id>/solve/", views.test_solve_view, name="test-solve"),
    path("tests/session/<int:user_test_id>/result/", views.test_result_view, name="test-result"),
    path("books/", views.books_list_view, name="books"),
    path("books/<int:book_id>/read/", views.book_read_view, name="book-read"),
    path("books/<int:book_id>/pdf/", views.book_pdf_view, name="book-pdf"),
    path("ranking/", views.ranking_view, name="ranking"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
