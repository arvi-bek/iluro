from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import PracticeExercise, PracticeSet, PracticeSetAttempt, Question, Test, UserAnswer, UserPracticeAttempt, UserTest
from .selectors import get_practice_review_items, get_test_answer_review
from .services import get_or_sync_profile as _get_or_sync_profile
from .services import record_practice_session_completion_stats as _record_practice_session_completion_stats
from .services import record_single_practice_attempt_stats as _record_single_practice_attempt_stats
from .services import record_test_completion_stats as _record_test_completion_stats
from .services import resolve_section_return_url as _resolve_section_return_url
from .services import trim_user_assessment_history as _trim_user_assessment_history
from .services import user_can_access_subject as _user_can_access_subject
from .utils import (
    calculate_test_xp,
    get_level_info,
)

@login_required
def test_start_view(request, test_id):
    test = get_object_or_404(Test.objects.select_related("subject"), id=test_id)
    subject_tests_url = f"/subjects/{test.subject_id}/problems/"
    if not _user_can_access_subject(request.user, test.subject_id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")

    question_count = Question.objects.filter(test=test).count()
    if question_count == 0:
        messages.error(request, "Bu testga hali savollar qo'shilmagan.")
        return redirect(subject_tests_url)

    next_url = _resolve_section_return_url(
        request.GET.get("next") or request.POST.get("next") or "",
        subject_tests_url,
    )

    if request.method == "POST":
        started_at = timezone.now()
        user_test = UserTest.objects.create(
            user=request.user,
            test=test,
            score=0,
            correct_count=0,
            started_at=started_at,
            finished_at=started_at,
            snapshot_json={
                "status": "started",
                "question_count": question_count,
                "subject": test.subject.name,
                "next_url": next_url,
            },
        )
        _trim_user_assessment_history(request.user)
        return redirect("test-solve", user_test_id=user_test.id)

    context = {
        "test": test,
        "test_difficulty": test.get_difficulty_display(),
        "question_count": question_count,
        "next_url": next_url,
        "back_url": next_url or subject_tests_url,
    }
    return render(request, "test_start.html", context)


@login_required
def test_solve_view(request, user_test_id):
    user_test = get_object_or_404(
        UserTest.objects.select_related("test", "test__subject"),
        id=user_test_id,
        user=request.user,
    )
    if user_test.snapshot_json.get("status") == "completed":
        return redirect("test-result", user_test_id=user_test.id)

    test = user_test.test
    questions = list(
        Question.objects.filter(test=test)
        .prefetch_related("choice_set")
        .order_by("id")
    )
    subject_tests_url = f"/subjects/{test.subject_id}/problems/"
    return_url = _resolve_section_return_url(
        user_test.snapshot_json.get("next_url", ""),
        subject_tests_url,
    )
    if not questions:
        messages.error(request, "Bu testga hali savollar qo'shilmagan.")
        return redirect(return_url)

    if request.method == "POST":
        correct_count = 0
        submitted_answers = []

        for question in questions:
            selected_choice_id = request.POST.get(f"question_{question.id}")
            selected_choice = None
            is_correct = False

            if selected_choice_id:
                selected_choice = next(
                    (choice for choice in question.choice_set.all() if str(choice.id) == selected_choice_id),
                    None,
                )
                is_correct = bool(selected_choice and selected_choice.is_correct)

            UserAnswer.objects.update_or_create(
                user=request.user,
                question=question,
                defaults={
                    "selected_choice": selected_choice,
                    "is_correct": is_correct,
                },
            )

            if is_correct:
                correct_count += 1

            submitted_answers.append(
                {
                    "question_id": question.id,
                    "selected_choice_id": selected_choice.id if selected_choice else None,
                    "is_correct": is_correct,
                }
            )

        total_questions = len(questions)
        score = round((correct_count / total_questions) * 100) if total_questions else 0
        user_test.correct_count = correct_count
        user_test.score = score
        user_test.finished_at = timezone.now()
        xp_awarded = calculate_test_xp(correct_count, total_questions, test.difficulty)
        user_test.snapshot_json = {
            "status": "completed",
            "question_count": total_questions,
            "answers": submitted_answers,
            "xp_awarded": xp_awarded,
        }
        user_test.save(update_fields=["correct_count", "score", "finished_at", "snapshot_json"])
        _record_test_completion_stats(user_test)
        _trim_user_assessment_history(request.user)
        _get_or_sync_profile(request.user)
        return redirect("test-result", user_test_id=user_test.id)

    context = {
        "user_test": user_test,
        "test": test,
        "questions": questions,
        "next_url": return_url,
    }
    return render(request, "test_solve.html", context)


@login_required
def test_result_view(request, user_test_id):
    user_test = get_object_or_404(
        UserTest.objects.select_related("test", "test__subject"),
        id=user_test_id,
        user=request.user,
    )
    subject_tests_url = f"/subjects/{user_test.test.subject_id}/problems/"
    return_url = _resolve_section_return_url(
        user_test.snapshot_json.get("next_url", ""),
        subject_tests_url,
    )
    total_questions = user_test.snapshot_json.get("question_count", 0)
    profile = _get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    answer_review = get_test_answer_review(request.user, user_test.test)
    context = {
        "user_test": user_test,
        "test": user_test.test,
        "total_questions": total_questions,
        "level_info": level_info,
        "xp_awarded": user_test.snapshot_json.get("xp_awarded", 0),
        "answer_review": answer_review,
        "next_url": return_url,
        "subject_tests_url": subject_tests_url,
    }
    return render(request, "test_result.html", context)


@login_required
def practice_set_solve_view(request, set_id):
    practice_set = get_object_or_404(PracticeSet.objects.select_related("subject"), id=set_id)
    subject_problems_url = f"/subjects/{practice_set.subject_id}/problems/"
    if not _user_can_access_subject(request.user, practice_set.subject_id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")

    exercises = list(
        PracticeExercise.objects.filter(practice_set=practice_set)
        .prefetch_related("choices")
        .order_by("id")[:20]
    )
    if not exercises:
        messages.error(request, "Bu bo'limga hali misol yoki masalalar qo'shilmagan.")
        return redirect(subject_problems_url)

    next_url = _resolve_section_return_url(
        request.GET.get("next") or request.POST.get("next") or "",
        subject_problems_url,
    )

    if request.method == "POST":
        practice_session = PracticeSetAttempt.objects.create(
            user=request.user,
            practice_set=practice_set,
            score=0,
            correct_count=0,
            total_count=len(exercises),
        )
        correct_count = 0

        for exercise in exercises:
            selected_choice = None
            answer_text = ""
            is_correct = False

            if exercise.answer_mode == "choice":
                selected_choice_id = request.POST.get(f"exercise_{exercise.id}_choice")
                if selected_choice_id:
                    selected_choice = next(
                        (choice for choice in exercise.choices.all() if str(choice.id) == selected_choice_id),
                        None,
                    )
                    is_correct = bool(selected_choice and selected_choice.is_correct)
            else:
                answer_text = (request.POST.get(f"exercise_{exercise.id}_input") or "").strip()
                normalized_answer = answer_text.casefold().strip()
                normalized_correct = (exercise.correct_text or "").casefold().strip()
                if normalized_answer and normalized_correct:
                    is_correct = normalized_answer == normalized_correct

            if is_correct:
                correct_count += 1

            UserPracticeAttempt.objects.create(
                user=request.user,
                exercise=exercise,
                practice_session=practice_session,
                selected_choice=selected_choice,
                answer_text=answer_text,
                is_correct=is_correct,
            )

        practice_session.correct_count = correct_count
        practice_session.score = round((correct_count / len(exercises)) * 100) if exercises else 0
        practice_session.save(update_fields=["correct_count", "score"])
        _record_practice_session_completion_stats(practice_session)
        _trim_user_assessment_history(request.user)
        _get_or_sync_profile(request.user)
        request.session["practice_next_url"] = next_url
        return redirect("practice-set-result", session_id=practice_session.id)

    context = {
        "practice_set": practice_set,
        "exercises": exercises,
        "next_url": next_url,
    }
    return render(request, "practice_set_solve.html", context)


@login_required
def practice_set_result_view(request, session_id):
    practice_session = get_object_or_404(
        PracticeSetAttempt.objects.select_related("practice_set", "practice_set__subject"),
        id=session_id,
        user=request.user,
    )
    review_items = get_practice_review_items(practice_session)

    subject_problems_url = f"/subjects/{practice_session.practice_set.subject_id}/problems/"
    return_url = _resolve_section_return_url(
        request.session.get("practice_next_url", ""),
        subject_problems_url,
    )
    context = {
        "practice_session": practice_session,
        "practice_set": practice_session.practice_set,
        "review_items": review_items,
        "next_url": return_url,
    }
    return render(request, "practice_set_result.html", context)


@login_required
def practice_solve_view(request, exercise_id):
    exercise = get_object_or_404(
        PracticeExercise.objects.select_related("subject").prefetch_related("choices"),
        id=exercise_id,
    )
    if not _user_can_access_subject(request.user, exercise.subject_id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")

    subject_problems_url = f"/subjects/{exercise.subject_id}/problems/"
    next_url = _resolve_section_return_url(
        request.GET.get("next") or request.POST.get("next") or "",
        subject_problems_url,
    )

    if request.method == "POST":
        selected_choice = None
        answer_text = ""
        is_correct = False

        if exercise.answer_mode == "choice":
            selected_choice_id = request.POST.get("selected_choice")
            if not selected_choice_id:
                messages.error(request, "Variantlardan birini tanlang.")
                return redirect(f"{request.path}?next={next_url}")
            selected_choice = next((choice for choice in exercise.choices.all() if str(choice.id) == selected_choice_id), None)
            is_correct = bool(selected_choice and selected_choice.is_correct)
        else:
            answer_text = (request.POST.get("answer_text") or "").strip()
            if not answer_text:
                messages.error(request, "Javobni kiriting.")
                return redirect(f"{request.path}?next={next_url}")
            normalized_answer = answer_text.casefold().strip()
            normalized_correct = (exercise.correct_text or "").casefold().strip()
            is_correct = normalized_answer == normalized_correct

        attempt = UserPracticeAttempt.objects.create(
            user=request.user,
            exercise=exercise,
            selected_choice=selected_choice,
            answer_text=answer_text,
            is_correct=is_correct,
        )
        _record_single_practice_attempt_stats(attempt)
        _trim_user_assessment_history(request.user)
        _get_or_sync_profile(request.user)
        request.session["practice_next_url"] = next_url
        return redirect("practice-result", attempt_id=attempt.id)

    context = {
        "exercise": exercise,
        "choices": list(exercise.choices.all()),
        "next_url": next_url,
    }
    return render(request, "practice_solve.html", context)


@login_required
def practice_result_view(request, attempt_id):
    attempt = get_object_or_404(
        UserPracticeAttempt.objects.select_related("exercise", "exercise__subject", "selected_choice"),
        id=attempt_id,
        user=request.user,
    )
    exercise = attempt.exercise
    subject_problems_url = f"/subjects/{exercise.subject_id}/problems/"
    next_url = _resolve_section_return_url(
        request.session.get("practice_next_url", ""),
        subject_problems_url,
    )
    correct_choice = None
    if exercise.answer_mode == "choice":
        correct_choice = exercise.choices.filter(is_correct=True).first()

    context = {
        "attempt": attempt,
        "exercise": exercise,
        "correct_choice": correct_choice,
        "next_url": next_url,
    }
    return render(request, "practice_result.html", context)
