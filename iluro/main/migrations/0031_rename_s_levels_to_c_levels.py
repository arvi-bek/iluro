from django.db import migrations, models


LEVEL_FIELDS = [
    ("main", "Test", "difficulty"),
    ("main", "Question", "difficulty"),
    ("main", "Profile", "level"),
    ("main", "UserSubjectPreference", "preferred_level"),
    ("main", "Book", "access_level"),
    ("main", "SubjectSectionEntry", "access_level"),
    ("main", "EssayTopic", "access_level"),
    ("main", "PracticeSet", "difficulty"),
    ("main", "PracticeExercise", "difficulty"),
]


def forwards_rename_levels(apps, schema_editor):
    for app_label, model_name, field_name in LEVEL_FIELDS:
        model = apps.get_model(app_label, model_name)
        model.objects.filter(**{field_name: "S"}).update(**{field_name: "C"})
        model.objects.filter(**{field_name: "S+"}).update(**{field_name: "C+"})


def backwards_rename_levels(apps, schema_editor):
    for app_label, model_name, field_name in LEVEL_FIELDS:
        model = apps.get_model(app_label, model_name)
        model.objects.filter(**{field_name: "C"}).update(**{field_name: "S"})
        model.objects.filter(**{field_name: "C+"}).update(**{field_name: "S+"})


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0030_alter_book_grade"),
    ]

    operations = [
        migrations.RunPython(forwards_rename_levels, backwards_rename_levels),
        migrations.AlterField(
            model_name="test",
            name="difficulty",
            field=models.CharField(
                choices=[("C", "C"), ("C+", "C+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="question",
            name="difficulty",
            field=models.CharField(
                choices=[("C", "C"), ("C+", "C+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="profile",
            name="level",
            field=models.CharField(default="C", max_length=20),
        ),
        migrations.AlterField(
            model_name="usersubjectpreference",
            name="preferred_level",
            field=models.CharField(
                choices=[("C", "C"), ("C+", "C+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="C",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="book",
            name="access_level",
            field=models.CharField(
                blank=True,
                choices=[("C", "C"), ("C+", "C+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="C",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="subjectsectionentry",
            name="access_level",
            field=models.CharField(
                choices=[("C", "C"), ("C+", "C+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="C",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="essaytopic",
            name="access_level",
            field=models.CharField(
                choices=[("C", "C"), ("C+", "C+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="C",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="practiceset",
            name="difficulty",
            field=models.CharField(
                choices=[("C", "C"), ("C+", "C+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="C",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="practiceexercise",
            name="difficulty",
            field=models.CharField(
                choices=[("C", "C"), ("C+", "C+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="C",
                max_length=50,
            ),
        ),
    ]
