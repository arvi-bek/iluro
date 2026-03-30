from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("subjects/", views.subject_selection_view, name="subject-selection"),
    path("tests/", views.tests_list_view, name="tests"),
    path("books/", views.books_list_view, name="books"),
    path("ranking/", views.ranking_view, name="ranking"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
