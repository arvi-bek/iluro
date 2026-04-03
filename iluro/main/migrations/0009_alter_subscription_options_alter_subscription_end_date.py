from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0008_profile_role_profile_premium_until"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="subscription",
            options={"ordering": ("-end_date", "-purchased_at")},
        ),
        migrations.AlterField(
            model_name="subscription",
            name="end_date",
            field=models.DateTimeField(blank=True),
        ),
    ]
