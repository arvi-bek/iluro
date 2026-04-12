import html
import os
import shutil
import uuid
from io import BytesIO
from unittest.mock import PropertyMock, patch
from urllib.parse import quote

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .models import (
    Book,
    Choice,
    PROFILE_PHOTO_MAX_BYTES,
    PracticeChoice,
    PracticeExercise,
    PracticeSet,
    PracticeSetAttempt,
    Profile,
    Question,
    ReferralEvent,
    SubjectSectionEntry,
    Subject,
    Subscription,
    SubscriptionPlan,
    Test,
    UserPracticeAttempt,
    UserDailyQuotaUsage,
    UserSubscription,
    UserSubscriptionSubject,
    UserStatSummary,
    UserTest,
)
from .services import (
    assign_free_subject,
    apply_referral_discount_to_subscription,
    consume_referral_discount,
    evaluate_referral_qualification,
    get_active_subscription_ids,
    get_referral_summary,
    get_user_subject_access_rows,
    get_or_sync_profile,
    register_referral_for_user,
    record_single_practice_attempt_stats,
    revoke_subject_access,
    trim_user_assessment_history,
)
from .selectors import (
    get_math_formula_quiz_payload,
    get_practice_review_items,
    get_test_attempt_answer_review,
    get_user_math_mistake_items,
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
        self.media_root_base = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".tmp-test-media",
        )
        os.makedirs(self.media_root_base, exist_ok=True)
        self.media_root = os.path.join(self.media_root_base, uuid.uuid4().hex)
        os.makedirs(self.media_root, exist_ok=True)
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

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

        self.advanced_test = Test.objects.create(
            subject=self.math,
            title="Advanced Math Flow Test",
            duration=15,
            difficulty="A+",
        )
        self.advanced_question = Question.objects.create(
            test=self.advanced_test,
            text="x^2 = 16 bo'lsa, musbat ildizni toping.",
            difficulty="A+",
        )
        self.advanced_correct_choice = Choice.objects.create(
            question=self.advanced_question,
            text="4",
            is_correct=True,
        )
        Choice.objects.create(question=self.advanced_question, text="8", is_correct=False)

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

        self.advanced_practice_set = PracticeSet.objects.create(
            subject=self.math,
            title="Funksiya va grafik mashqi",
            source_book="IDC 1",
            topic="Funksiya",
            difficulty="A+",
        )
        self.advanced_practice_exercise = PracticeExercise.objects.create(
            subject=self.math,
            practice_set=self.advanced_practice_set,
            prompt="y = 2x + 1 funksiyada x = 3 bo'lsa, y ni toping.",
            answer_mode="choice",
            difficulty="A+",
        )
        self.advanced_practice_choice = PracticeChoice.objects.create(
            exercise=self.advanced_practice_exercise,
            text="7",
            is_correct=True,
        )
        PracticeChoice.objects.create(
            exercise=self.advanced_practice_exercise,
            text="6",
            is_correct=False,
        )
        PracticeChoice.objects.create(
            exercise=self.advanced_practice_exercise,
            text="8",
            is_correct=False,
        )
        PracticeChoice.objects.create(
            exercise=self.advanced_practice_exercise,
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

    def _make_test_image(self, name="avatar.png", size=(900, 900), color=(180, 120, 80)):
        buffer = BytesIO()
        Image.new("RGB", size, color).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

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

    def test_workspace_and_assessment_show_all_difficulty_levels(self):
        problems_response = self.client.get(reverse("subject-workspace-section", args=[self.math.id, "problems"]))
        self.assertContains(problems_response, self.test.title)
        self.assertContains(problems_response, self.advanced_test.title)
        self.assertContains(problems_response, self.practice_set.title)
        self.assertContains(problems_response, self.advanced_practice_set.title)

    def test_high_difficulty_test_and_practice_are_accessible_without_manual_level_setting(self):
        test_start_response = self.client.get(reverse("test-start", args=[self.advanced_test.id]))
        self.assertEqual(test_start_response.status_code, 200)
        self.assertContains(test_start_response, self.advanced_test.title)

        practice_response = self.client.get(reverse("practice-set-solve", args=[self.advanced_practice_set.id]))
        self.assertEqual(practice_response.status_code, 200)
        self.assertContains(practice_response, self.advanced_practice_set.title)

    def test_settings_page_no_longer_shows_per_subject_level_controls(self):
        response = self.client.get(reverse("settings"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Kerakli daraja")
        self.assertNotContains(response, "subject_level_")

    def test_settings_accepts_profile_photo_and_optimizes_it(self):
        response = self.client.post(
            reverse("settings"),
            {
                "full_name": "Flow User",
                "role": self.profile.role,
                "theme": self.profile.theme,
                "photo": self._make_test_image(),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.photo.name.endswith(".jpg"))

        with Image.open(self.profile.photo.path) as image:
            self.assertLessEqual(max(image.size), 600)

    def test_replacing_profile_photo_updates_to_new_file_without_error(self):
        self.client.post(
            reverse("settings"),
            {
                "full_name": "Flow User",
                "role": self.profile.role,
                "theme": self.profile.theme,
                "photo": self._make_test_image(name="first.png", color=(150, 90, 80)),
            },
        )
        self.profile.refresh_from_db()
        old_path = self.profile.photo.path

        self.client.post(
            reverse("settings"),
            {
                "full_name": "Flow User",
                "role": self.profile.role,
                "theme": self.profile.theme,
                "photo": self._make_test_image(name="second.png", color=(80, 120, 170)),
            },
        )

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.photo.path.endswith(".jpg"))
        self.assertNotEqual(self.profile.photo.path, old_path)
        self.assertTrue(os.path.exists(self.profile.photo.path))

    def test_settings_rejects_oversized_profile_photo(self):
        oversized_photo = SimpleUploadedFile(
            "big.jpg",
            b"x" * (PROFILE_PHOTO_MAX_BYTES + 1),
            content_type="image/jpeg",
        )

        response = self.client.post(
            reverse("settings"),
            {
                "full_name": "Flow User",
                "role": self.profile.role,
                "theme": self.profile.theme,
                "photo": oversized_photo,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Profil rasmi 3 MB dan katta bo'lmasligi kerak.",
            html.unescape(response.content.decode("utf-8", errors="ignore")),
        )

    def test_settings_rejects_invalid_image_payload(self):
        invalid_photo = SimpleUploadedFile(
            "fake.png",
            b"not-a-real-image",
            content_type="image/png",
        )

        response = self.client.post(
            reverse("settings"),
            {
                "full_name": "Flow User",
                "role": self.profile.role,
                "theme": self.profile.theme,
                "photo": invalid_photo,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Yuklangan fayl to'g'ri rasm formatida emas.",
            html.unescape(response.content.decode("utf-8", errors="ignore")),
        )

    def test_settings_page_stays_open_when_profile_photo_url_lookup_fails(self):
        self.profile.photo = self._make_test_image(name="broken-url.png", color=(90, 110, 140))
        self.profile.save()

        with patch("django.db.models.fields.files.FieldFile.url", new_callable=PropertyMock) as mocked_url:
            mocked_url.side_effect = ValueError("broken media url")
            response = self.client.get(reverse("settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sozlamalar")

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
        self.client.logout()
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
            "Username faqat lotin harflari, raqamlar va pastki chiziq (_)",
        )
        self.assertFalse(User.objects.filter(email="newuser@example.com").exists())

    def test_register_accepts_latin_username_with_digits_and_underscore(self):
        self.client.logout()
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

    def test_math_mistakes_keep_original_question_numbers(self):
        user = User.objects.create_user(username="mistakepositionuser", password="StrongPass123")
        subject = Subject.objects.create(name="Matematika", price=30000)

        practice_set = PracticeSet.objects.create(
            subject=subject,
            title="Tartib testi",
            topic="Aralash mashqlar",
            difficulty="C",
        )
        wrong_practice_positions = set()
        for index in range(1, 16):
            exercise = PracticeExercise.objects.create(
                subject=subject,
                practice_set=practice_set,
                prompt=f"{index}-mashq",
                answer_mode="choice",
                difficulty="C",
            )
            correct_choice = PracticeChoice.objects.create(exercise=exercise, text="To'g'ri", is_correct=True)
            wrong_choice = PracticeChoice.objects.create(exercise=exercise, text="Noto'g'ri", is_correct=False)
            if index in {11, 15}:
                wrong_practice_positions.add(index)
                UserPracticeAttempt.objects.create(
                    user=user,
                    exercise=exercise,
                    selected_choice=wrong_choice,
                    is_correct=False,
                )
            else:
                UserPracticeAttempt.objects.create(
                    user=user,
                    exercise=exercise,
                    selected_choice=correct_choice,
                    is_correct=True,
                )

        test = Test.objects.create(subject=subject, title="Tartib testi 2", duration=10, difficulty="C")
        answers = []
        wrong_test_positions = set()
        for index in range(1, 16):
            question = Question.objects.create(test=test, text=f"{index}-savol", difficulty="C")
            wrong_choice = Choice.objects.create(question=question, text="Noto'g'ri", is_correct=False)
            correct_choice = Choice.objects.create(question=question, text="To'g'ri", is_correct=True)
            is_correct = index not in {11, 15}
            if not is_correct:
                wrong_test_positions.add(index)
            answers.append(
                {
                    "question_id": question.id,
                    "selected_choice_id": correct_choice.id if is_correct else wrong_choice.id,
                    "is_correct": is_correct,
                }
            )

        UserTest.objects.create(
            user=user,
            test=test,
            score=87,
            correct_count=13,
            started_at=timezone.now(),
            finished_at=timezone.now(),
            snapshot_json={
                "status": "completed",
                "question_count": 15,
                "answers": answers,
            },
        )

        mistakes = get_user_math_mistake_items(user, subject, limit=10)

        practice_numbers = {item["question_number"] for item in mistakes if item["kind"] == "practice"}
        test_numbers = {item["question_number"] for item in mistakes if item["kind"] == "test"}
        self.assertEqual(practice_numbers, wrong_practice_positions)
        self.assertEqual(test_numbers, wrong_test_positions)

    def test_result_review_keeps_original_question_numbers(self):
        user = User.objects.create_user(username="reviewpositionuser", password="StrongPass123")
        subject = Subject.objects.create(name="Matematika", price=30000)

        practice_set = PracticeSet.objects.create(subject=subject, title="Natija tartibi", difficulty="C")
        practice_session = PracticeSetAttempt.objects.create(
            user=user,
            practice_set=practice_set,
            total_count=15,
            correct_count=13,
            score=87,
        )
        for index in range(1, 16):
            exercise = PracticeExercise.objects.create(
                subject=subject,
                practice_set=practice_set,
                prompt=f"{index}-topshiriq matni",
                answer_mode="choice",
                difficulty="C",
            )
            correct_choice = PracticeChoice.objects.create(exercise=exercise, text="To'g'ri", is_correct=True)
            wrong_choice = PracticeChoice.objects.create(exercise=exercise, text="Noto'g'ri", is_correct=False)
            UserPracticeAttempt.objects.create(
                user=user,
                exercise=exercise,
                practice_session=practice_session,
                selected_choice=correct_choice if index not in {11, 15} else wrong_choice,
                is_correct=index not in {11, 15},
            )

        practice_review = get_practice_review_items(practice_session)
        wrong_practice_numbers = {item["question_number"] for item in practice_review if not item["is_correct"]}
        self.assertEqual(wrong_practice_numbers, {11, 15})

        test = Test.objects.create(subject=subject, title="Review test", duration=10, difficulty="C")
        answers = []
        for index in range(1, 16):
            question = Question.objects.create(test=test, text=f"{index}-savol matni", difficulty="C")
            wrong_choice = Choice.objects.create(question=question, text="Noto'g'ri", is_correct=False)
            correct_choice = Choice.objects.create(question=question, text="To'g'ri", is_correct=True)
            is_correct = index not in {11, 15}
            answers.append(
                {
                    "question_id": question.id,
                    "selected_choice_id": correct_choice.id if is_correct else wrong_choice.id,
                    "is_correct": is_correct,
                }
            )

        user_test = UserTest.objects.create(
            user=user,
            test=test,
            score=87,
            correct_count=13,
            started_at=timezone.now(),
            finished_at=timezone.now(),
            snapshot_json={
                "status": "completed",
                "question_count": 15,
                "answers": answers,
            },
        )

        test_review = get_test_attempt_answer_review(user_test)
        wrong_test_numbers = {item["question_number"] for item in test_review if not item["is_correct"]}
        self.assertEqual(wrong_test_numbers, {11, 15})

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


class FreeAccessFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="freeuser", password="StrongPass123")
        self.profile = Profile.objects.create(user=self.user, full_name="Free User", role="student", xp=0, level="C")
        self.math = Subject.objects.create(name="Matematika", price=30000)
        self.history = Subject.objects.create(name="Tarix", price=30000)
        self.client.force_login(self.user)

    def _create_basic_test(self, subject, title):
        test = Test.objects.create(subject=subject, title=title, duration=10, difficulty="C")
        question = Question.objects.create(test=test, text=f"{title} savoli", difficulty="C")
        Choice.objects.create(question=question, text="To'g'ri", is_correct=True)
        Choice.objects.create(question=question, text="Noto'g'ri", is_correct=False)
        return test

    def test_dashboard_shows_free_subject_modal_without_any_active_access(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bepul fanni tanlang")
        self.assertContains(response, "Bu tanlov umrbod amal qiladi")

    def test_user_can_still_open_profile_before_choosing_free_subject(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)

    def test_user_can_choose_one_free_subject_and_it_becomes_permanent_access(self):
        response = self.client.post(
            reverse("dashboard"),
            {"free_subject_id": str(self.math.id)},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dashboard"))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.free_subject_id, self.math.id)
        self.assertIsNotNone(self.profile.free_subject_locked_at)
        self.assertEqual(get_active_subscription_ids(self.user), [self.math.id])

        math_response = self.client.get(reverse("subject-workspace", args=[self.math.id]))
        self.assertEqual(math_response.status_code, 200)

        history_response = self.client.get(reverse("subject-workspace", args=[self.history.id]))
        self.assertEqual(history_response.status_code, 302)
        self.assertEqual(history_response["Location"], reverse("subject-selection"))

    def test_games_hub_is_available_for_free_user_after_subject_selection(self):
        assign_free_subject(self.user, self.math)

        response = self.client.get(reverse("games-hub"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qal&#x27;a o&#x27;yini", html=True)
        self.assertContains(response, "Imlo dueli")

    def test_free_user_can_start_only_three_assessments_per_day(self):
        assign_free_subject(self.user, self.math)
        tests = [self._create_basic_test(self.math, f"Math test {index}") for index in range(1, 5)]

        for test in tests[:3]:
            response = self.client.post(reverse("test-start", args=[test.id]))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response["Location"].startswith("/tests/session/"))

        fourth_response = self.client.post(reverse("test-start", args=[tests[3].id]))

        self.assertEqual(fourth_response.status_code, 302)
        self.assertEqual(fourth_response["Location"], f"/subjects/{self.math.id}/problems/")
        self.assertEqual(UserTest.objects.filter(user=self.user).count(), 3)

        usage = UserDailyQuotaUsage.objects.get(user=self.user, date=timezone.localdate())
        self.assertEqual(usage.tests_started, 3)

    def test_free_subject_stays_active_after_bundle_subscription_expires(self):
        assign_free_subject(self.user, self.math)
        plan = SubscriptionPlan.objects.create(code="expired-bundle", name="1 fan", subject_limit=1, price=30000)
        expired_bundle = UserSubscription.objects.create(
            user=self.user,
            plan=plan,
            title="1 fan",
            source="manual",
            status="expired",
            is_all_access=False,
            started_at=timezone.now() - timezone.timedelta(days=40),
            end_at=timezone.now() - timezone.timedelta(days=10),
        )
        UserSubscriptionSubject.objects.create(subscription=expired_bundle, subject=self.math)

        active_rows = get_user_subject_access_rows(self.user, active_only=True)
        full_rows = get_user_subject_access_rows(self.user, active_only=False)

        self.assertEqual(get_active_subscription_ids(self.user), [self.math.id])
        self.assertEqual(active_rows[0]["subject_id"], self.math.id)
        self.assertTrue(active_rows[0]["is_permanent"])
        self.assertIsNone(active_rows[0]["end_at"])
        self.assertEqual(full_rows[0]["subject_id"], self.math.id)
        self.assertTrue(full_rows[0]["is_permanent"])
        self.assertEqual(full_rows[0]["source"], "free")


class ReferralProgramTests(TestCase):
    def setUp(self):
        self.inviter = User.objects.create_user(username="inviter", password="StrongPass123", first_name="Inviter")
        self.inviter_profile = get_or_sync_profile(self.inviter)
        self.subject = Subject.objects.create(name="Tarix", price=30000)

    def test_register_view_captures_referral_code_and_creates_pending_event(self):
        response = self.client.get(reverse("referral-entry", args=[self.inviter_profile.referral_code]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("register"))

        post_response = self.client.post(
            reverse("register"),
            {
                "full_name": "Referral User",
                "username": "ref_user",
                "email": "ref_user@example.com",
                "password": "StrongPass123",
                "password2": "StrongPass123",
                "role": "student",
            },
            follow=False,
        )

        self.assertEqual(post_response.status_code, 302)
        referred_user = User.objects.get(username="ref_user")
        referred_profile = Profile.objects.get(user=referred_user)
        self.assertEqual(referred_profile.referred_by_id, self.inviter.id)
        event = ReferralEvent.objects.get(invited_user=referred_user)
        self.assertEqual(event.inviter_id, self.inviter.id)
        self.assertEqual(event.status, "pending")

    def test_referral_qualifies_once_after_free_subject_and_three_assessments(self):
        referred_user = User.objects.create_user(username="qualified_ref", password="StrongPass123")
        Profile.objects.create(user=referred_user, full_name="Qualified Referral")
        register_referral_for_user(referred_user, self.inviter_profile.referral_code)

        assign_free_subject(referred_user, self.subject)
        attempt = UserPracticeAttempt.objects.create(
            user=referred_user,
            exercise=PracticeExercise.objects.create(
                subject=self.subject,
                prompt="1+1?",
                answer_mode="input",
                correct_text="2",
                difficulty="C",
            ),
            answer_text="2",
            is_correct=True,
        )
        record_single_practice_attempt_stats(attempt)
        event = evaluate_referral_qualification(referred_user)
        self.inviter_profile.refresh_from_db()

        self.assertEqual(event.status, "qualified")
        self.assertEqual(event.reward_percent, 2)
        self.assertEqual(self.inviter_profile.referral_discount_available_percent, 2)
        self.assertEqual(self.inviter_profile.referral_discount_percent, 2)

        event = evaluate_referral_qualification(referred_user)
        self.inviter_profile.refresh_from_db()
        self.assertEqual(event.reward_percent, 2)
        self.assertEqual(self.inviter_profile.referral_discount_available_percent, 2)

    def test_referral_reward_respects_fifty_percent_cap(self):
        self.inviter_profile.referral_discount_percent = 50
        self.inviter_profile.referral_discount_available_percent = 50
        self.inviter_profile.save(update_fields=["referral_discount_percent", "referral_discount_available_percent"])

        referred_user = User.objects.create_user(username="cap_ref", password="StrongPass123")
        Profile.objects.create(user=referred_user, full_name="Cap Referral")
        register_referral_for_user(referred_user, self.inviter_profile.referral_code)
        assign_free_subject(referred_user, self.subject)
        attempt = UserPracticeAttempt.objects.create(
            user=referred_user,
            exercise=PracticeExercise.objects.create(
                subject=self.subject,
                prompt="2+2?",
                answer_mode="input",
                correct_text="4",
                difficulty="C",
            ),
            answer_text="4",
            is_correct=True,
        )
        record_single_practice_attempt_stats(attempt)

        event = evaluate_referral_qualification(referred_user)
        self.inviter_profile.refresh_from_db()

        self.assertEqual(event.status, "qualified")
        self.assertEqual(event.reward_percent, 0)
        self.assertEqual(self.inviter_profile.referral_discount_available_percent, 50)

    def test_next_paid_subscription_consumes_full_referral_wallet(self):
        self.inviter_profile.referral_discount_percent = 12
        self.inviter_profile.referral_discount_available_percent = 12
        self.inviter_profile.save(update_fields=["referral_discount_percent", "referral_discount_available_percent"])

        plan = SubscriptionPlan.objects.get(code="single-subject")
        subscription = UserSubscription.objects.create(
            user=self.inviter,
            plan=plan,
            title=plan.name,
            source="manual",
            status="active",
            is_all_access=False,
            started_at=timezone.now(),
            end_at=timezone.now() + timezone.timedelta(days=30),
        )

        applied_percent = apply_referral_discount_to_subscription(subscription)
        subscription.refresh_from_db()
        self.inviter_profile.refresh_from_db()

        self.assertEqual(applied_percent, 12)
        self.assertEqual(subscription.price_before_discount, 30000)
        self.assertEqual(subscription.referral_discount_amount, 3600)
        self.assertEqual(subscription.final_price, 26400)
        self.assertEqual(self.inviter_profile.referral_discount_available_percent, 0)
        self.assertEqual(self.inviter_profile.referral_discount_used_percent, 12)

    def test_user_can_start_collecting_referral_discount_again_after_balance_is_used(self):
        self.inviter_profile.referral_discount_percent = 50
        self.inviter_profile.referral_discount_available_percent = 50
        self.inviter_profile.save(update_fields=["referral_discount_percent", "referral_discount_available_percent"])

        consumed_percent = consume_referral_discount(self.inviter_profile)
        self.inviter_profile.refresh_from_db()

        self.assertEqual(consumed_percent, 50)
        self.assertEqual(self.inviter_profile.referral_discount_available_percent, 0)
        self.assertEqual(self.inviter_profile.referral_discount_used_percent, 50)

        referred_user = User.objects.create_user(username="recollect_ref", password="StrongPass123")
        Profile.objects.create(user=referred_user, full_name="Recollect Referral")
        register_referral_for_user(referred_user, self.inviter_profile.referral_code)
        assign_free_subject(referred_user, self.subject)
        attempt = UserPracticeAttempt.objects.create(
            user=referred_user,
            exercise=PracticeExercise.objects.create(
                subject=self.subject,
                prompt="4+4?",
                answer_mode="input",
                correct_text="8",
                difficulty="C",
            ),
            answer_text="8",
            is_correct=True,
        )
        record_single_practice_attempt_stats(attempt)

        event = evaluate_referral_qualification(referred_user)
        self.inviter_profile.refresh_from_db()

        self.assertEqual(event.status, "qualified")
        self.assertEqual(event.reward_percent, 2)
        self.assertEqual(self.inviter_profile.referral_discount_available_percent, 2)
        self.assertEqual(self.inviter_profile.referral_discount_used_percent, 50)
        self.assertEqual(self.inviter_profile.referral_discount_percent, 52)

    def test_referral_summary_reports_progress_for_referred_user(self):
        referred_user = User.objects.create_user(username="progress_ref", password="StrongPass123")
        Profile.objects.create(user=referred_user, full_name="Progress Referral")
        register_referral_for_user(referred_user, self.inviter_profile.referral_code)
        assign_free_subject(referred_user, self.subject)
        attempt = UserPracticeAttempt.objects.create(
            user=referred_user,
            exercise=PracticeExercise.objects.create(
                subject=self.subject,
                prompt="3+3?",
                answer_mode="input",
                correct_text="6",
                difficulty="C",
            ),
            answer_text="6",
            is_correct=True,
        )
        record_single_practice_attempt_stats(attempt)

        summary = get_referral_summary(referred_user)

        self.assertIsNotNone(summary["qualification_progress"])
        self.assertEqual(summary["qualification_progress"]["completion_remaining"], 0)
        self.assertTrue(summary["qualification_progress"]["free_subject_selected"])
