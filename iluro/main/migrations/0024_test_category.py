from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0023_bookview"),
    ]

    operations = [
        migrations.AddField(
            model_name="test",
            name="category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("general", "Umumiy"),
                    ("terms", "Atamalar bo'yicha"),
                    ("years", "Yillar bo'yicha"),
                ],
                default="general",
                max_length=20,
            ),
        ),
    ]
