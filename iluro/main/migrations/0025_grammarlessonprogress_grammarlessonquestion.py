from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0024_test_category"),
    ]

    operations = [
        migrations.CreateModel(
            name="GrammarLessonQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prompt", models.TextField()),
                ("option_a", models.CharField(max_length=255)),
                ("option_b", models.CharField(max_length=255)),
                ("option_c", models.CharField(max_length=255)),
                ("option_d", models.CharField(max_length=255)),
                ("correct_option", models.CharField(choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")], max_length=1)),
                ("explanation", models.TextField(blank=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("lesson", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="grammar_questions", to="main.subjectsectionentry")),
            ],
            options={
                "verbose_name": "Gramatika mini test savoli",
                "verbose_name_plural": "Gramatika mini test savollari",
                "ordering": ("order", "id"),
            },
        ),
        migrations.CreateModel(
            name="GrammarLessonProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("best_score", models.PositiveIntegerField(default=0)),
                ("last_score", models.PositiveIntegerField(default=0)),
                ("attempts_count", models.PositiveIntegerField(default=0)),
                ("is_completed", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("lesson", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="grammar_progress", to="main.subjectsectionentry")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth.user")),
            ],
            options={
                "verbose_name": "Gramatika mavzu progressi",
                "verbose_name_plural": "Gramatika mavzu progresslari",
            },
        ),
        migrations.AddConstraint(
            model_name="grammarlessonprogress",
            constraint=models.UniqueConstraint(fields=("user", "lesson"), name="unique_user_grammar_lesson_progress"),
        ),
    ]
