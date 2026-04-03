from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0010_merge_duplicate_subscriptions_and_add_unique_constraint"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubjectSectionEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("section_key", models.CharField(choices=[("formulas", "Formulalar"), ("problems", "Misol / Masalalar"), ("rules", "Qoidalar"), ("essay", "Insho"), ("extras", "Qo'shimcha ma'lumotlar"), ("events", "Tarixiy voqealar")], max_length=50)),
                ("title", models.CharField(max_length=255)),
                ("summary", models.TextField(blank=True)),
                ("body", models.TextField(blank=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_featured", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subject", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, to="main.subject")),
            ],
            options={
                "ordering": ("order", "-is_featured", "-created_at"),
            },
        ),
    ]
