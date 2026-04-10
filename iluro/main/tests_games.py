from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .models import Choice, PracticeChoice, PracticeExercise, PracticeSet, Question, Subject, Test
from .selectors import (
    extract_history_grade_label,
    get_history_game_grade_options,
    get_imlo_duel_grade_options,
    get_language_duel_subject_options,
)


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
        self.assertContains(response, "games-grid")
        self.assertContains(response, "Imlo dueli")

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


class ImloDuelGameTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="speller",
            password="testpass123",
        )
        self.client.force_login(self.user)
        self.language_subject = Subject.objects.create(name="Ona tili, Adabiyot", price=30000)
        self.language_set = PracticeSet.objects.create(
            subject=self.language_subject,
            title="7-sinf Grammatika mashqlari",
            topic="Grammatika",
            difficulty="C",
        )
        self.imlo_set = PracticeSet.objects.create(
            subject=self.language_subject,
            title="7-sinf Yozma savodxonlik (imlo) - 1-qism",
            topic="Imlo",
            difficulty="C",
        )
        self.literature_set = PracticeSet.objects.create(
            subject=self.language_subject,
            title="8-sinf Adabiyot asarlar bo'yicha mashqlar",
            topic="Adabiyot",
            difficulty="C+",
        )

    def _make_language_exercise(
        self,
        prompt,
        correct,
        wrongs,
        difficulty="C",
        title="7-sinf grammatika mashqi",
        source_book="7-sinf ona tili",
        topic="Grammatika",
        practice_set=None,
    ):
        target_set = practice_set or self.language_set
        exercise = PracticeExercise.objects.create(
            subject=self.language_subject,
            practice_set=target_set,
            title=title,
            topic=topic,
            source_book=source_book,
            prompt=prompt,
            answer_mode="choice",
            explanation="Ona tili qoidasi bo'yicha tanlanadi.",
            difficulty=difficulty,
        )
        PracticeChoice.objects.create(exercise=exercise, text=correct, is_correct=True)
        for item in wrongs:
            PracticeChoice.objects.create(exercise=exercise, text=item, is_correct=False)
        return exercise

    def test_imlo_grade_options_are_built_from_exercises(self):
        self._make_language_exercise(
            "Qaysi gapda ravish to'g'ri ishlatilgan?",
            "U juda tez yugurdi.",
            ["U juda tezkor yugurdi.", "U tezlik yugurdi.", "U tez yugurmoqda edi edi."],
            difficulty="C+",
        )

        options = get_imlo_duel_grade_options("language")

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["value"], "7")
        self.assertEqual(options[0]["label"], "7-sinf")

    def test_language_duel_subject_options_available(self):
        options = get_language_duel_subject_options()
        labels = {item["label"] for item in options}
        self.assertIn("Ona tili", labels)
        self.assertIn("Adabiyot", labels)

    def test_imlo_grade_options_filter_by_subject_kind(self):
        self._make_language_exercise(
            "Qaysi so'z turkumi fe'lga kiradi?",
            "o'qimoq",
            ["kitob", "go'zal", "tez"],
            difficulty="C",
            title="7-sinf grammatika mashqi",
            source_book="7-sinf ona tili",
            topic="Grammatika",
            practice_set=self.language_set,
        )
        self._make_language_exercise(
            "Qaysi variant to'g'ri yozilgan?",
            "mustaqillik",
            ["mustaqilik", "mustaqillikg", "mustaqillik'"],
            difficulty="C",
            title="7-sinf imlo mashqi",
            source_book="7-sinf imlo",
            topic="Imlo",
            practice_set=self.imlo_set,
        )
        self._make_language_exercise(
            "Otabek qaysi asar qahramoni?",
            "O'tkan kunlar",
            ["Kecha va kunduz", "Lolazor", "Mehrobdan chayon"],
            difficulty="C+",
            title="8-sinf adabiyot mashqi",
            source_book="8-sinf adabiyot",
            topic="Adabiyot",
            practice_set=self.literature_set,
        )

        language = get_imlo_duel_grade_options("language")
        literature = get_imlo_duel_grade_options("literature")

        self.assertEqual({item["value"] for item in language}, {"7"})
        self.assertEqual({item["value"] for item in literature}, {"8"})

    def test_imlo_duel_questions_endpoint_returns_questions(self):
        self._make_language_exercise(
            "Qaysi so'zda egalik qo'shimchasi bor?",
            "kitobim",
            ["kitob", "kitoblar", "kitobni"],
            difficulty="C",
            title="7-sinf grammatika mashqi - 1",
        )
        self._make_language_exercise(
            "Qaysi gapda ega aniq berilgan?",
            "O'quvchi darsga keldi.",
            ["Darsga keldi.", "Keldi darsga.", "Kelib qoldi."],
            difficulty="C",
            title="7-sinf grammatika mashqi - 2",
        )

        response = self.client.get(reverse("imlo-duel-questions"), {"subject": "language", "grade": "7"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["subject"], "language")
        self.assertEqual(payload["subject_label"], "Ona tili")
        self.assertEqual(payload["grade"], "7")
        self.assertEqual(payload["grade_label"], "7-sinf")
        self.assertEqual(len(payload["questions"]), 30)
        self.assertTrue(all(item["grade"] == "7" for item in payload["questions"]))

    def test_imlo_duel_questions_endpoint_supports_literature_subject(self):
        self._make_language_exercise(
            "Qaysi asar Abdulla Qodiriyga tegishli?",
            "O'tkan kunlar",
            ["Lolazor", "Kecha va kunduz", "Dunyoning ishlari"],
            difficulty="B",
            title="8-sinf adabiyot mashqi - 1",
            source_book="8-sinf adabiyot",
            topic="Adabiyot",
            practice_set=self.literature_set,
        )
        self._make_language_exercise(
            "Qahramon va asarni moslang.",
            "Kumush",
            ["Zebi", "Yodgor", "Anvar"],
            difficulty="B",
            title="8-sinf adabiyot mashqi - 2",
            source_book="8-sinf adabiyot",
            topic="Adabiyot",
            practice_set=self.literature_set,
        )

        response = self.client.get(reverse("imlo-duel-questions"), {"subject": "literature", "grade": "8"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["subject"], "literature")
        self.assertEqual(payload["subject_label"], "Adabiyot")
        self.assertEqual(payload["grade"], "8")
        self.assertEqual(payload["grade_label"], "8-sinf")
        self.assertEqual(len(payload["questions"]), 30)

    def test_imlo_duel_questions_endpoint_excludes_imlo_for_language(self):
        self._make_language_exercise(
            "Qaysi variant to'g'ri yozilgan?",
            "mustaqillik",
            ["mustaqilik", "mustaqillikg", "mustaqillik'"],
            difficulty="C",
            title="7-sinf imlo mashqi",
            source_book="7-sinf imlo",
            topic="Imlo",
            practice_set=self.imlo_set,
        )

        response = self.client.get(reverse("imlo-duel-questions"), {"subject": "language", "grade": "7"})

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("savol topilmadi", payload["message"])

    def test_imlo_duel_page_renders_setup_overlay(self):
        self._make_language_exercise(
            "Qaysi so'z olmosh turkumiga kiradi?",
            "u",
            ["kitob", "o'qimoq", "chiroyli"],
            difficulty="C",
        )

        response = self.client.get(reverse("imlo-duel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imlo dueli")
        self.assertContains(response, "Sinfni tanlang")
        self.assertContains(response, "Ona tili")
        self.assertContains(response, "Adabiyot")

    def test_imlo_duel_page_respects_subject_query(self):
        response = self.client.get(reverse("imlo-duel"), {"subject": "literature"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-selected-subject="literature"')

        response = self.client.get(reverse("imlo-duel"), {"subject": "language"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-selected-subject="language"')

    def test_imlo_duel_uses_aralash_fallback_when_grade_missing(self):
        self.language_set.title = "Grammatika to'plami"
        self.language_set.save(update_fields=["title"])
        self._make_language_exercise(
            "Qaysi gap sodda gapga kiradi?",
            "Men kitob o'qiyman.",
            ["Men kitob o'qiyman va yozaman.", "U kelib, ketdi va qaytdi.", "Dars tugadi, ammo savol qoldi."],
            source_book="",
            title="Qoida mashqi",
            topic="Grammatika",
        )

        options = get_imlo_duel_grade_options("language")

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["value"], "all")
        self.assertEqual(options[0]["label"], "Aralash")
