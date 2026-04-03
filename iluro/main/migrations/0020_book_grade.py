from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0019_usersubjectpreference"),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="grade",
            field=models.CharField(
                blank=True,
                choices=[
                    ("5", "5-sinf"),
                    ("6", "6-sinf"),
                    ("7", "7-sinf"),
                    ("8", "8-sinf"),
                    ("9", "9-sinf"),
                    ("10", "10-sinf"),
                    ("11", "11-sinf"),
                ],
                max_length=2,
            ),
        ),
    ]
