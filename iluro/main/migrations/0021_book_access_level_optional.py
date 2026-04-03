from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0020_book_grade"),
    ]

    operations = [
        migrations.AlterField(
            model_name="book",
            name="access_level",
            field=models.CharField(
                blank=True,
                choices=[
                    ("S", "S"),
                    ("S+", "S+"),
                    ("B", "B"),
                    ("B+", "B+"),
                    ("A", "A"),
                    ("A+", "A+"),
                ],
                default="S",
                max_length=50,
            ),
        ),
    ]
