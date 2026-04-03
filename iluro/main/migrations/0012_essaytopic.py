from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0011_subjectsectionentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="EssayTopic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("prompt_text", models.TextField()),
                ("thesis_hint", models.TextField(blank=True)),
                ("outline", models.TextField(blank=True)),
                ("sample_intro", models.TextField(blank=True)),
                ("sample_conclusion", models.TextField(blank=True)),
                ("is_featured", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subject", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, to="main.subject")),
            ],
            options={
                "ordering": ("-is_featured", "-created_at"),
            },
        ),
    ]
