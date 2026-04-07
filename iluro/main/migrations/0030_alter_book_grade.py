from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0029_userstatsummary_manual_xp_adjustment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="book",
            name="grade",
            field=models.CharField(blank=True, max_length=20, verbose_name="Sinf / janr"),
        ),
    ]
