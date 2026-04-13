from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0034_referral_program"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralevent",
            name="purchased_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="referralevent",
            name="purchase_reward_percent",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
