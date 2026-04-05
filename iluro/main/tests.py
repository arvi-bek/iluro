from urllib.parse import quote

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Book,
    Choice,
    PracticeChoice,
    PracticeExercise,
    PracticeSet,
    Profile,
    Question,
    Subject,
    Subscription,
    Test,
    UserTest,
)
from .utils import calculate_practice_set_xp, calculate_single_practice_xp, calculate_test_xp


class MainSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="flowuser",
            password="StrongPass123",
            email="flow@example.com",
            first_name="Flow User",
        )
        self.profile = Profile.objects.create(
            user=self.user,
            full_name="Flow User",
            role="student",
            level="S",
            xp=0,
        )

        self.math = Subject.objects.create(name="Matematika", price=30000)
        self.language = Subject.objects.create(name="Ona tili, Adabiyot", price=30000)
        Subscription.objects.create(
            user=self.user,
            subject=self.math,
            end_date=timezone.now() + timezone.timedelta(days=30),
        )

        self.book = Book.objects.create(
            subject=self.math,
            title="IDC 1",
            author="Muallif",
            description="Test book",
            grade="5",
        )

        self.test = Test.objects.create(
            subject=self.math,
            title="Math Flow Test",
            duration=10,
            difficulty="S",
        )
        self.question = Question.objects.create(
            test=self.test,
            text="2 + 2 = ?",
            difficulty="S",
        )
        self.correct_choice = Choice.objects.create(
            question=self.question,
            text="4",
            is_correct=True,
        )
        Choice.objects.create(question=self.question, text="5", is_correct=False)

        self.practice_set = PracticeSet.objects.create(
            subject=self.math,
            title="Natural sonlar mashqi",
            source_book="IDC 1",
            topic="Natural sonlar",
            difficulty="S",
        )
        self.practice_exercise = PracticeExercise.objects.create(
            subject=self.math,
            practice_set=self.practice_set,
            prompt="3 + 3 = ?",
            answer_mode="choice",
            difficulty="S",
        )
        self.practice_choice = PracticeChoice.objects.create(
            exercise=self.practice_exercise,
            text="6",
            is_correct=True,
        )
        PracticeChoice.objects.create(
            exercise=self.practice_exercise,
            text="7",
            is_correct=False,
        )

        self.client.force_login(self.user)

    def test_core_authenticated_pages_render(self):
        urls = [
            reverse("dashboard"),
            reverse("profile"),
            reverse("settings"),
            reverse("subject-selection"),
            reverse("statistics"),
            reverse("ranking"),
            reverse("books"),
            reverse("subject-workspace", args=[self.math.id]),
            reverse("subject-workspace-section", args=[self.math.id, "books"]),
            reverse("subject-workspace-section", args=[self.math.id, "problems"]),
            reverse("subject-workspace-section", args=[self.math.id, "problems"]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_books_root_shows_subject_cards_before_subject_filter(self):
        response = self.client.get(reverse("books"))
        self.assertContains(response, self.math.name)
        self.assertNotContains(response, self.book.title)

    def test_test_flow_keeps_subject_tests_return_url(self):
        subject_tests_url = reverse("subject-workspace-section", args=[self.math.id, "tests"])
        expected_return_url = reverse("subject-workspace-section", args=[self.math.id, "problems"])
        start_url = f"{reverse('test-start', args=[self.test.id])}?next={quote(subject_tests_url)}"

        response = self.client.get(start_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, subject_tests_url)

        response = self.client.post(
            reverse("test-start", args=[self.test.id]),
            {"next": subject_tests_url},
        )
        self.assertEqual(response.status_code, 302)

        user_test = UserTest.objects.get(user=self.user, test=self.test)
        solve_response = self.client.post(
            reverse("test-solve", args=[user_test.id]),
            {f"question_{self.question.id}": str(self.correct_choice.id)},
        )
        self.assertEqual(solve_response.status_code, 302)

        result_response = self.client.get(reverse("test-result", args=[user_test.id]))
        self.assertEqual(result_response.status_code, 200)
        self.assertContains(result_response, expected_return_url)

    def test_practice_set_flow_keeps_subject_problems_return_url(self):
        subject_problems_url = reverse("subject-workspace-section", args=[self.math.id, "problems"])
        solve_url = f"{reverse('practice-set-solve', args=[self.practice_set.id])}?next={quote(subject_problems_url)}"

        response = self.client.get(solve_url)
        self.assertEqual(response.status_code, 200)

        submit_response = self.client.post(
            reverse("practice-set-solve", args=[self.practice_set.id]),
            {
                "next": subject_problems_url,
                f"exercise_{self.practice_exercise.id}_choice": str(self.practice_choice.id),
            },
        )
        self.assertEqual(submit_response.status_code, 302)

        result_response = self.client.get(submit_response["Location"])
        self.assertEqual(result_response.status_code, 200)
        self.assertContains(result_response, subject_problems_url)


class XPEconomyTests(TestCase):
    def test_harder_test_awards_more_xp_for_same_result(self):
        medium_xp = calculate_test_xp(correct_count=14, total_count=20, difficulty="S")
        hard_xp = calculate_test_xp(correct_count=14, total_count=20, difficulty="A")
        self.assertGreater(hard_xp, medium_xp)

    def test_practice_set_awards_less_than_test_for_same_accuracy(self):
        test_xp = calculate_test_xp(correct_count=16, total_count=20, difficulty="B")
        practice_xp = calculate_practice_set_xp(correct_count=16, total_count=20, difficulty="B")
        self.assertGreater(test_xp, practice_xp)

    def test_single_practice_requires_correct_answer(self):
        self.assertEqual(calculate_single_practice_xp(False, "A+"), 0)
        self.assertGreater(calculate_single_practice_xp(True, "A+"), calculate_single_practice_xp(True, "S"))
