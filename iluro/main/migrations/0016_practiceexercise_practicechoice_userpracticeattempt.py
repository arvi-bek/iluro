from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0015_book_access_level_essaytopic_access_level_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PracticeExercise",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("source_book", models.CharField(blank=True, max_length=255)),
                ("topic", models.CharField(blank=True, max_length=255)),
                ("prompt", models.TextField()),
                ("answer_mode", models.CharField(choices=[("choice", "Variantli javob"), ("input", "Input javob")], default="choice", max_length=20)),
                ("correct_text", models.CharField(blank=True, max_length=255)),
                ("explanation", models.TextField(blank=True)),
                ("difficulty", models.CharField(choices=[("S", "S"), ("S+", "S+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")], default="S", max_length=50)),
                ("is_featured", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subject", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, to="main.subject")),
            ],
            options={"ordering": ("-is_featured", "-created_at")},
        ),
        migrations.CreateModel(
            name="PracticeChoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(max_length=255)),
                ("is_correct", models.BooleanField(default=False)),
                ("exercise", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="choices", to="main.practiceexercise")),
            ],
        ),
        migrations.CreateModel(
            name="UserPracticeAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("answer_text", models.CharField(blank=True, max_length=255)),
                ("is_correct", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("exercise", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, to="main.practiceexercise")),
                ("selected_choice", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, to="main.practicechoice")),
                ("user", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
