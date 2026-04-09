from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .models import Choice, PracticeChoice, PracticeExercise, PracticeSet, Question, Subject, Test
from .selectors import extract_history_grade_label, get_history_game_grade_options


class HistoryBattleGameTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="gamer",
            password="testpass123",
        )
        self.client.force_login(self.user)
        self.history_subject = Subject.objects.create(name="Tarix", price=50000)
        self.math_subject = Subject.objects.create(name="Matematika", price=50000)

    def _make_question(self, test, text):
        question = Question.objects.create(test=test, text=text, difficulty="C")
        Choice.objects.create(question=question, text="A", is_correct=True)
        Choice.objects.create(question=question, text="B", is_correct=False)
        Choice.objects.create(question=question, text="C", is_correct=False)
        Choice.objects.create(question=question, text="D", is_correct=False)
        return question

    def _make_practice_exercise(self, practice_set, prompt):
        exercise = PracticeExercise.objects.create(
            subject=practice_set.subject,
            practice_set=practice_set,
            title="1-topshiriq",
            topic=practice_set.title,
            prompt=prompt,
            answer_mode="choice",
            difficulty="C",
        )
        PracticeChoice.objects.create(exercise=exercise, text="A", is_correct=True)
        PracticeChoice.objects.create(exercise=exercise, text="B", is_correct=False)
        PracticeChoice.objects.create(exercise=exercise, text="C", is_correct=False)
        PracticeChoice.objects.create(exercise=exercise, text="D", is_correct=False)
        return exercise

    def test_extract_history_grade_label(self):
        self.assertEqual(extract_history_grade_label("7-sinf Jahon tarixi umumiy test"), "7")
        self.assertEqual(extract_history_grade_label("10 sinf O'zbekiston tarixi"), "10")
        self.assertEqual(extract_history_grade_label("Tarix umumiy test"), "")

    def test_history_battle_questions_endpoint_filters_by_grade(self):
        grade_7_test = Test.objects.create(
            subject=self.history_subject,
            title="7-sinf Jahon tarixi umumiy test",
            duration=20,
            difficulty="C",
            category="general",
        )
        grade_8_test = Test.objects.create(
            subject=self.history_subject,
            title="8-sinf Jahon tarixi umumiy test",
            duration=20,
            difficulty="C",
            category="general",
        )
        other_subject_test = Test.objects.create(
            subject=self.math_subject,
            title="7-sinf Algebra",
            duration=20,
            difficulty="C",
            category="general",
        )
        self._make_question(grade_7_test, "7-sinf tarix savoli")
        self._make_question(grade_8_test, "8-sinf tarix savoli")
        self._make_question(other_subject_test, "Matematika savoli")

        response = self.client.get(reverse("history-battle-questions"), {"grade": "7"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["grade"], "7")
        self.assertEqual(payload["grade_label"], "7-sinf")
        self.assertEqual(len(payload["questions"]), 30)
        self.assertTrue(all(item["grade"] == "7" for item in payload["questions"]))
        self.assertIn("7-sinf tarix savoli", payload["questions"][0]["text"])

    def test_games_hub_page_renders(self):
        response = self.client.get(reverse("games-hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tarix jangi")

    def test_history_battle_page_renders_setup_overlay(self):
        grade_7_test = Test.objects.create(
            subject=self.history_subject,
            title="7-sinf Jahon tarixi umumiy test",
            duration=20,
            difficulty="C",
            category="general",
        )
        self._make_question(grade_7_test, "7-sinf tarix savoli")

        response = self.client.get(reverse("history-battle"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jamoalarni tayyorlang")
        self.assertContains(response, "1-jamoa (ko'k)")
        self.assertContains(response, "2-jamoa (qizil)")

    def test_grade_options_fall_back_to_practice_exercises(self):
        practice_set = PracticeSet.objects.create(
            subject=self.history_subject,
            title="9-sinf Jahon tarixi umumiy test",
            topic="9-sinf Jahon tarixi umumiy test",
            difficulty="C",
        )
        self._make_practice_exercise(practice_set, "9-sinf tarix mashq savoli")

        options = get_history_game_grade_options()

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["value"], "9")
        self.assertEqual(options[0]["label"], "9-sinf")
