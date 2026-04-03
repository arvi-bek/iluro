from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0013_profile_theme_alter_profile_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="difficulty",
            field=models.CharField(
                choices=[("S", "S"), ("S+", "S+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="test",
            name="difficulty",
            field=models.CharField(
                choices=[("S", "S"), ("S+", "S+"), ("B", "B"), ("B+", "B+"), ("A", "A"), ("A+", "A+")],
                max_length=50,
            ),
        ),
    ]
