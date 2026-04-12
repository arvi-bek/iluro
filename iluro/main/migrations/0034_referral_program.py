import secrets
import string

from django.conf import settings
from django.db import migrations, models


REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _generate_referral_code(Profile):
    for _ in range(32):
        candidate = "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(8))
        if not Profile.objects.filter(referral_code=candidate).exists():
            return candidate
    raise RuntimeError("Referral code yaratib bo'lmadi.")


def seed_referral_metadata(apps, schema_editor):
    Profile = apps.get_model("main", "Profile")
    UserSubscription = apps.get_model("main", "UserSubscription")

    for profile in Profile.objects.all().iterator():
        update_fields = []
        if not profile.referral_code:
            profile.referral_code = _generate_referral_code(Profile)
            update_fields.append("referral_code")
        if profile.referral_discount_percent is None:
            profile.referral_discount_percent = 0
            update_fields.append("referral_discount_percent")
        if profile.referral_discount_used_percent is None:
            profile.referral_discount_used_percent = 0
            update_fields.append("referral_discount_used_percent")
        if profile.referral_discount_available_percent is None:
            profile.referral_discount_available_percent = 0
            update_fields.append("referral_discount_available_percent")
        if update_fields:
            profile.save(update_fields=update_fields)

    for subscription in UserSubscription.objects.select_related("plan").all().iterator():
        base_price = 0
        if subscription.plan_id and subscription.plan:
            base_price = int(subscription.plan.price or 0)
        update_fields = []
        if not subscription.price_before_discount:
            subscription.price_before_discount = base_price
            update_fields.append("price_before_discount")
        if not subscription.final_price:
            subscription.final_price = base_price
            update_fields.append("final_price")
        if update_fields:
            subscription.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0033_sync_subscription_plan_catalog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="referral_code",
            field=models.CharField(blank=True, max_length=24, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="referral_discount_available_percent",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="profile",
            name="referral_discount_percent",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="profile",
            name="referral_discount_used_percent",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="profile",
            name="referred_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="referred_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="referral_joined_profiles",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="final_price",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="price_before_discount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="referral_discount_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="referral_discount_percent_applied",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="ReferralEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Kutilmoqda"), ("qualified", "Qualified"), ("rejected", "Rad etilgan")], default="pending", max_length=20)),
                ("qualified_at", models.DateTimeField(blank=True, null=True)),
                ("reward_percent", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invited_user", models.OneToOneField(on_delete=models.CASCADE, related_name="referral_event", to=settings.AUTH_USER_MODEL)),
                ("inviter", models.ForeignKey(on_delete=models.CASCADE, related_name="sent_referral_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Referral hodisasi",
                "verbose_name_plural": "Referral hodisalari",
            },
        ),
        migrations.AddConstraint(
            model_name="referralevent",
            constraint=models.UniqueConstraint(fields=("inviter", "invited_user"), name="unique_referral_inviter_invited"),
        ),
        migrations.AddIndex(
            model_name="referralevent",
            index=models.Index(fields=["inviter", "status"], name="main_ref_inv_stat_idx"),
        ),
        migrations.AddIndex(
            model_name="referralevent",
            index=models.Index(fields=["status", "qualified_at"], name="main_ref_stat_qat_idx"),
        ),
        migrations.RunPython(seed_referral_metadata, migrations.RunPython.noop),
    ]
