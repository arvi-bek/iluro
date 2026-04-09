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
    SubscriptionPlan,
    Test,
    UserPracticeAttempt,
    UserSubscription,
    UserSubscriptionSubject,
    UserStatSummary,
    UserTest,
)
from .services import (
    get_active_subscription_ids,
    get_or_sync_profile,
    record_single_practice_attempt_stats,
    revoke_subject_access,
)
from .utils import (
    calculate_essay_topic_xp,
    calculate_grammar_lesson_xp,
    calculate_practice_set_xp,
    calculate_single_practice_xp,
    calculate_test_xp,
)


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
            level="C",
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
            difficulty="C",
        )
        self.question = Question.objects.create(
            test=self.test,
            text="2 + 2 = ?",
            difficulty="C",
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
            difficulty="C",
        )
        self.practice_exercise = PracticeExercise.objects.create(
            subject=self.math,
            practice_set=self.practice_set,
            prompt="3 + 3 = ?",
            answer_mode="choice",
            difficulty="C",
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

    def test_register_rejects_non_latin_username_characters(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "Test User",
                "username": "test!user",
                "email": "newuser@example.com",
                "password": "StrongPass123",
                "password2": "StrongPass123",
                "role": "student",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Username faqat lotin harflari, raqamlar va pastki chiziq (_) dan iborat bo'lishi kerak.",
        )
        self.assertFalse(User.objects.filter(email="newuser@example.com").exists())

    def test_register_accepts_latin_username_with_digits_and_underscore(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "Latin User",
                "username": "latin_user01",
                "email": "latinuser@example.com",
                "password": "StrongPass123",
                "password2": "StrongPass123",
                "role": "student",
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="latin_user01").exists())


class XPEconomyTests(TestCase):
    def test_harder_test_awards_more_xp_for_same_result(self):
        medium_xp = calculate_test_xp(correct_count=14, total_count=20, difficulty="C")
        hard_xp = calculate_test_xp(correct_count=14, total_count=20, difficulty="A")
        self.assertGreater(hard_xp, medium_xp)

    def test_practice_set_awards_less_than_test_for_same_accuracy(self):
        test_xp = calculate_test_xp(correct_count=16, total_count=20, difficulty="B")
        practice_xp = calculate_practice_set_xp(correct_count=16, total_count=20, difficulty="B")
        self.assertGreater(test_xp, practice_xp)

    def test_single_practice_requires_correct_answer(self):
        self.assertEqual(calculate_single_practice_xp(False, "A+"), 0)
        self.assertGreater(calculate_single_practice_xp(True, "A+"), calculate_single_practice_xp(True, "C"))

    def test_grammar_completion_rewards_more_than_simple_attempt(self):
        attempted_xp = calculate_grammar_lesson_xp(best_score=55, difficulty="C", is_completed=False, has_attempt=True)
        completed_xp = calculate_grammar_lesson_xp(best_score=85, difficulty="C", is_completed=True, has_attempt=True)
        self.assertGreater(completed_xp, attempted_xp)

    def test_featured_essay_rewards_more_xp(self):
        normal_xp = calculate_essay_topic_xp("C", is_completed=True, is_featured=False)
        featured_xp = calculate_essay_topic_xp("C", is_completed=True, is_featured=True)
        self.assertGreater(featured_xp, normal_xp)

    def test_manual_admin_xp_is_preserved_when_new_practice_xp_is_added(self):
        user = User.objects.create_user(username="xpkeeper", password="StrongPass123")
        Profile.objects.create(user=user, full_name="XP Keeper", xp=1300, level="🔥 Izlanuvchi")
        subject = Subject.objects.create(name="Matematika", price=30000)
        practice_set = PracticeSet.objects.create(subject=subject, title="XP set", difficulty="C+")
        exercise = PracticeExercise.objects.create(
            subject=subject,
            practice_set=practice_set,
            prompt="2 + 2 = ?",
            answer_mode="choice",
            difficulty="C+",
        )
        choice = PracticeChoice.objects.create(exercise=exercise, text="4", is_correct=True)
        summary = UserStatSummary.objects.create(user=user, lifetime_xp=1300, manual_xp_adjustment=1300)

        attempt = UserPracticeAttempt.objects.create(
            user=user,
            exercise=exercise,
            selected_choice=choice,
            is_correct=True,
        )

        record_single_practice_attempt_stats(attempt)
        summary.refresh_from_db()

        earned_delta = calculate_single_practice_xp(True, "C+")
        self.assertEqual(summary.lifetime_xp, 1300 + earned_delta)

        profile = get_or_sync_profile(user)
        self.assertEqual(profile.xp, 1300 + earned_delta)


class SubscriptionAccessTests(TestCase):
    def test_bundle_rows_take_priority_over_legacy_rows(self):
        user = User.objects.create_user(username="subpriority", password="StrongPass123")
        subject = Subject.objects.create(name="Tarix", price=30000)

        Subscription.objects.create(
            user=user,
            subject=subject,
            end_date=timezone.now() + timezone.timedelta(days=30),
        )
        plan = SubscriptionPlan.objects.create(code="sub-priority-plan", name="1 fan", subject_limit=1, price=30000)
        UserSubscription.objects.create(
            user=user,
            plan=plan,
            title="1 fan",
            source="manual",
            status="active",
            is_all_access=False,
            started_at=timezone.now(),
            end_at=timezone.now() + timezone.timedelta(days=30),
        )

        self.assertEqual(get_active_subscription_ids(user), [])

    def test_revoke_subject_access_cleans_legacy_and_bundle_rows(self):
        user = User.objects.create_user(username="subrevoke", password="StrongPass123")
        subject = Subject.objects.create(name="Matematika", price=30000)

        Subscription.objects.create(
            user=user,
            subject=subject,
            end_date=timezone.now() + timezone.timedelta(days=30),
        )
        plan = SubscriptionPlan.objects.create(code="sub-revoke-plan", name="1 fan", subject_limit=1, price=30000)
        bundle = UserSubscription.objects.create(
            user=user,
            plan=plan,
            title="1 fan",
            source="manual",
            status="active",
            is_all_access=False,
            started_at=timezone.now(),
            end_at=timezone.now() + timezone.timedelta(days=30),
        )
        UserSubscriptionSubject.objects.create(subscription=bundle, subject=subject)

        revoke_subject_access(user, subject)

        self.assertFalse(Subscription.objects.filter(user=user, subject=subject).exists())
        self.assertFalse(UserSubscriptionSubject.objects.filter(subscription=bundle, subject=subject).exists())
        self.assertEqual(get_active_subscription_ids(user), [])
