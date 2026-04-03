from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0014_alter_question_difficulty_alter_test_difficulty"),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="access_level",
            field=models.CharField(
                choices=[("S", "S"), ("S+", "S+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="S",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="essaytopic",
            name="access_level",
            field=models.CharField(
                choices=[("S", "S"), ("S+", "S+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="S",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="subjectsectionentry",
            name="access_level",
            field=models.CharField(
                choices=[("S", "S"), ("S+", "S+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                default="S",
                max_length=50,
            ),
        ),
    ]
