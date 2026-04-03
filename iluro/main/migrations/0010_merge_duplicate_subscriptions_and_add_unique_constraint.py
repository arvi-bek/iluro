from django.db import migrations, models


def merge_duplicate_subscriptions(apps, schema_editor):
    Subscription = apps.get_model("main", "Subscription")

    grouped = {}
    for subscription in Subscription.objects.all().order_by("user_id", "subject_id", "-end_date", "-purchased_at"):
        key = (subscription.user_id, subscription.subject_id)
        grouped.setdefault(key, []).append(subscription)

    for duplicates in grouped.values():
        if len(duplicates) <= 1:
            continue

        primary = duplicates[0]
        latest_end_date = max(item.end_date for item in duplicates if item.end_date)
        primary.end_date = latest_end_date
        primary.save(update_fields=["end_date"])

        for extra in duplicates[1:]:
            extra.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0009_alter_subscription_options_alter_subscription_end_date"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_subscriptions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                fields=("user", "subject"),
                name="unique_user_subject_subscription",
            ),
        ),
    ]
