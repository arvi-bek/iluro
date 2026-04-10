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
    PracticeSetAttempt,
    Profile,
    Question,
    SubjectSectionEntry,
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
    trim_user_assessment_history,
)
from .selectors import get_math_formula_quiz_payload, get_user_math_mistake_items
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
        PracticeChoice.objects.create(
            exercise=self.practice_exercise,
            text="8",
            is_correct=False,
        )
        PracticeChoice.objects.create(
            exercise=self.practice_exercise,
            text="9",
            is_correct=False,
        )

        self.formula_entry_one = SubjectSectionEntry.objects.create(
            subject=self.math,
            section_key="formulas",
            title="Kvadrat tenglama formulasi",
            summary="Diskriminant va ildizlarni topishda ishlatiladi.",
            body="x = (-b ± √D) / 2a",
            usage_note="ax² + bx + c = 0 ko'rinishidagi tenglamalarda.",
            access_level="C",
        )
        SubjectSectionEntry.objects.create(
            subject=self.math,
            section_key="formulas",
            title="Qisqartirilgan ko'paytirish formulalari",
            summary="Ko'phadlarni tez ochish va yig'ishda ishlatiladi.",
            body="(a+b)^2 = a^2 + 2ab + b^2",
            usage_note="Algebraik almashtirishlarda.",
            access_level="C",
        )
        SubjectSectionEntry.objects.create(
            subject=self.math,
            section_key="formulas",
            title="Geometrik progressiya yig'indisi",
            summary="Birinchi n ta had yig'indisini topish formulasi.",
            body="S_n = b_1(q^n - 1)/(q - 1)",
            usage_note="Geometrik progressiyada q ≠ 1 bo'lsa.",
            access_level="C+",
        )
        SubjectSectionEntry.objects.create(
            subject=self.math,
            section_key="formulas",
            title="Sinuslar teoremasi",
            summary="Uchburchak tomonlari va qarshi burchaklari orasidagi bog'lanish.",
            body="a/sin A = b/sin B = c/sin C",
            usage_note="Uchburchak geometriyasi masalalarida.",
            access_level="B",
        )

        self.topic_set = PracticeSet.objects.create(
            subject=self.math,
            title="Kvadrat tenglama mini test",
            source_book="IDC 1",
            topic="Kvadrat tenglama",
            description="Kvadrat tenglama va diskriminant bo'yicha nazorat.",
            difficulty="C",
        )
        self.topic_exercise_one = PracticeExercise.objects.create(
            subject=self.math,
            practice_set=self.topic_set,
            title="Diskriminant",
            topic="Kvadrat tenglama",
            prompt="ax² + bx + c = 0 uchun diskriminant qaysi formula bilan topiladi?",
            answer_mode="choice",
            explanation="Diskriminant D = b² - 4ac formula bilan topiladi.",
            difficulty="C",
        )
        for text, is_correct in [
            ("D = b² - 4ac", True),
            ("D = 2ab - c", False),
            ("D = a² + c²", False),
            ("D = b + 4ac", False),
        ]:
            PracticeChoice.objects.create(exercise=self.topic_exercise_one, text=text, is_correct=is_correct)

        self.topic_exercise_two = PracticeExercise.objects.create(
            subject=self.math,
            practice_set=self.topic_set,
            title="Ildizlar soni",
            topic="Kvadrat tenglama",
            prompt="Agar diskriminant noldan katta bo'lsa, kvadrat tenglama nechta haqiqiy ildizga ega bo'ladi?",
            answer_mode="choice",
            explanation="D > 0 bo'lsa, 2 ta haqiqiy ildiz bo'ladi.",
            difficulty="C",
        )
        for text, is_correct in [
            ("2 ta", True),
            ("1 ta", False),
            ("Haqiqiy ildiz yo'q", False),
            ("Cheksiz ko'p", False),
        ]:
            PracticeChoice.objects.create(exercise=self.topic_exercise_two, text=text, is_correct=is_correct)

        wrong_choice = next(choice for choice in self.practice_exercise.choices.all() if not choice.is_correct)
        UserPracticeAttempt.objects.create(
            user=self.user,
            exercise=self.practice_exercise,
            selected_choice=wrong_choice,
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
            reverse("subject-workspace-section", args=[self.math.id, "formula-quiz"]),
            reverse("subject-workspace-section", args=[self.math.id, "mistakes"]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_math_tools_sections_show_expected_content(self):
        formula_response = self.client.get(reverse("subject-workspace-section", args=[self.math.id, "formula-quiz"]))
        self.assertContains(formula_response, "Formulalar bo'yicha savol-javob")
        self.assertContains(formula_response, "Formula testi")

        mistakes_response = self.client.get(reverse("subject-workspace-section", args=[self.math.id, "mistakes"]))
        self.assertContains(mistakes_response, "Mening xatolarim")
        self.assertContains(mistakes_response, self.practice_exercise.prompt)

    def test_math_formula_quiz_payload_builds_multiple_question_types(self):
        payload = get_math_formula_quiz_payload(self.math, max_questions=6)

        self.assertGreaterEqual(len(payload), 4)
        self.assertTrue(any(item["question_type"] == "name_from_formula" for item in payload))
        self.assertTrue(any(item["question_type"] == "usage_from_formula" for item in payload))
        self.assertTrue(any(item["question_type"] == "formula_from_name" for item in payload))
        self.assertTrue(any(item["question_type"] == "name_from_usage" for item in payload))
        self.assertTrue(all(len(item["choices"]) >= 2 for item in payload))

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

    def test_trim_history_keeps_latest_wrong_practice_attempt_per_exercise(self):
        user = User.objects.create_user(username="attemptkeeper", password="StrongPass123")
        subject = Subject.objects.create(name="Matematika", price=30000)
        practice_set = PracticeSet.objects.create(subject=subject, title="Trim set", difficulty="C")
        exercise = PracticeExercise.objects.create(
            subject=subject,
            practice_set=practice_set,
            prompt="5 + 5 = ?",
            answer_mode="choice",
            difficulty="C",
        )
        correct_choice = PracticeChoice.objects.create(exercise=exercise, text="10", is_correct=True)
        wrong_choice = PracticeChoice.objects.create(exercise=exercise, text="11", is_correct=False)

        older_attempt = UserPracticeAttempt.objects.create(
            user=user,
            exercise=exercise,
            selected_choice=wrong_choice,
            is_correct=False,
        )
        newer_attempt = UserPracticeAttempt.objects.create(
            user=user,
            exercise=exercise,
            selected_choice=correct_choice,
            is_correct=True,
        )

        trim_user_assessment_history(user)

        remaining_ids = list(UserPracticeAttempt.objects.filter(user=user).values_list("id", flat=True))
        self.assertEqual(remaining_ids, [older_attempt.id])
        self.assertNotIn(newer_attempt.id, remaining_ids)

    def test_math_mistakes_uses_previous_wrong_attempt_when_latest_is_correct(self):
        user = User.objects.create_user(username="mistakesfallback", password="StrongPass123")
        subject = Subject.objects.create(name="Matematika", price=30000)
        practice_set = PracticeSet.objects.create(
            subject=subject,
            title="Mistakes set",
            topic="Kasrlar",
            difficulty="C",
        )
        exercise = PracticeExercise.objects.create(
            subject=subject,
            practice_set=practice_set,
            title="Kasrni toping",
            topic="Kasrlar",
            prompt="1/2 ga teng variantni tanlang",
            answer_mode="choice",
            difficulty="C",
            explanation="Maxraj va surat nisbatiga qaraladi.",
        )
        correct_choice = PracticeChoice.objects.create(exercise=exercise, text="2/4", is_correct=True)
        wrong_choice = PracticeChoice.objects.create(exercise=exercise, text="3/4", is_correct=False)

        UserPracticeAttempt.objects.create(
            user=user,
            exercise=exercise,
            selected_choice=wrong_choice,
            is_correct=False,
        )
        UserPracticeAttempt.objects.create(
            user=user,
            exercise=exercise,
            selected_choice=correct_choice,
            is_correct=True,
        )

        mistakes = get_user_math_mistake_items(user, subject)

        self.assertEqual(len(mistakes), 1)
        self.assertEqual(mistakes[0]["source_label"], "Mashq")
        self.assertEqual(mistakes[0]["your_answer"], "3/4")
        self.assertEqual(mistakes[0]["correct_answer"], "2/4")

    def test_math_mistakes_uses_previous_wrong_test_answer_when_latest_is_correct(self):
        user = User.objects.create_user(username="testmistakesfallback", password="StrongPass123")
        subject = Subject.objects.create(name="Matematika", price=30000)
        test = Test.objects.create(subject=subject, title="Kasr testi", duration=10, difficulty="C")
        question = Question.objects.create(test=test, text="Qaysi biri 1/2?", difficulty="C")
        wrong_choice = Choice.objects.create(question=question, text="3/4", is_correct=False)
        correct_choice = Choice.objects.create(question=question, text="2/4", is_correct=True)

        UserTest.objects.create(
            user=user,
            test=test,
            score=0,
            correct_count=0,
            started_at=timezone.now() - timezone.timedelta(days=2),
            finished_at=timezone.now() - timezone.timedelta(days=2),
            snapshot_json={
                "status": "completed",
                "question_count": 1,
                "answers": [
                    {
                        "question_id": question.id,
                        "selected_choice_id": wrong_choice.id,
                        "is_correct": False,
                    }
                ],
            },
        )
        UserTest.objects.create(
            user=user,
            test=test,
            score=100,
            correct_count=1,
            started_at=timezone.now() - timezone.timedelta(days=1),
            finished_at=timezone.now() - timezone.timedelta(days=1),
            snapshot_json={
                "status": "completed",
                "question_count": 1,
                "answers": [
                    {
                        "question_id": question.id,
                        "selected_choice_id": correct_choice.id,
                        "is_correct": True,
                    }
                ],
            },
        )

        mistakes = get_user_math_mistake_items(user, subject)

        self.assertEqual(len(mistakes), 1)
        self.assertEqual(mistakes[0]["source_label"], "Test")
        self.assertEqual(mistakes[0]["your_answer"], "3/4")
        self.assertEqual(mistakes[0]["correct_answer"], "2/4")

    def test_trim_history_removes_test_attempts_older_than_week(self):
        user = User.objects.create_user(username="weektrim", password="StrongPass123")
        subject = Subject.objects.create(name="Tarix", price=30000)
        test = Test.objects.create(subject=subject, title="Tarix test", duration=10, difficulty="C")

        old_attempt = UserTest.objects.create(
            user=user,
            test=test,
            score=40,
            correct_count=2,
            started_at=timezone.now() - timezone.timedelta(days=10),
            finished_at=timezone.now() - timezone.timedelta(days=10),
            snapshot_json={"status": "completed", "question_count": 1, "answers": []},
        )
        fresh_attempt = UserTest.objects.create(
            user=user,
            test=test,
            score=80,
            correct_count=4,
            started_at=timezone.now() - timezone.timedelta(days=2),
            finished_at=timezone.now() - timezone.timedelta(days=2),
            snapshot_json={"status": "completed", "question_count": 1, "answers": []},
        )

        trim_user_assessment_history(user)

        remaining_ids = list(UserTest.objects.filter(user=user).values_list("id", flat=True))
        self.assertIn(fresh_attempt.id, remaining_ids)
        self.assertNotIn(old_attempt.id, remaining_ids)

    def test_trim_history_removes_practice_set_attempts_older_than_week(self):
        user = User.objects.create_user(username="practiceweektrim", password="StrongPass123")
        subject = Subject.objects.create(name="Matematika", price=30000)
        practice_set = PracticeSet.objects.create(subject=subject, title="Misol / Masala set", difficulty="C")

        old_attempt = PracticeSetAttempt.objects.create(
            user=user,
            practice_set=practice_set,
            total_count=10,
            correct_count=4,
            score=40,
        )
        fresh_attempt = PracticeSetAttempt.objects.create(
            user=user,
            practice_set=practice_set,
            total_count=10,
            correct_count=8,
            score=80,
        )
        PracticeSetAttempt.objects.filter(id=old_attempt.id).update(created_at=timezone.now() - timezone.timedelta(days=7, hours=1))
        PracticeSetAttempt.objects.filter(id=fresh_attempt.id).update(created_at=timezone.now() - timezone.timedelta(days=3))

        trim_user_assessment_history(user)

        remaining_ids = list(PracticeSetAttempt.objects.filter(user=user).values_list("id", flat=True))
        self.assertIn(fresh_attempt.id, remaining_ids)
        self.assertNotIn(old_attempt.id, remaining_ids)


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
