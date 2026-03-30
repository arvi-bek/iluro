

from django.contrib import admin
from .models import (
    Subject, Subscription, Test,
    Question, Choice, UserTest,
    UserAnswer, Profile, Book
)


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
    list_display = ("id", "user", "subject", "purchased_at", "end_date")
    list_filter = ("subject", "purchased_at", "end_date")
    search_fields = ("user__username", "subject__name")
    autocomplete_fields = ("user", "subject")
    ordering = ("-purchased_at",)


# ---------------- TEST ----------------
@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "duration", "difficulty", "created_at")
    list_filter = ("subject", "difficulty")
    search_fields = ("title",)
    autocomplete_fields = ("subject",)
    ordering = ("-created_at",)


# ---------------- CHOICE INLINE ----------------
class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4


# ---------------- QUESTION ----------------
@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
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
class ChoiceAdmin(admin.ModelAdmin):
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
    list_display = ("id", "user", "full_name", "level", "created_at")
    search_fields = ("user__username", "full_name")
    autocomplete_fields = ("user",)


# ---------------- BOOK ----------------
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "subject", "author", "has_pdf", "is_featured", "created_at")
    list_filter = ("subject", "is_featured", "created_at")
    search_fields = ("title", "author", "subject__name")
    autocomplete_fields = ("subject",)
    ordering = ("-is_featured", "-created_at")

    def has_pdf(self, obj):
        return bool(obj.pdf_file)
    has_pdf.boolean = True
    has_pdf.short_description = "PDF"



