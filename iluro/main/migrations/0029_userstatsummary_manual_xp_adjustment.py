from django.db import migrations, models


def backfill_manual_xp_adjustment(apps, schema_editor):
    UserStatSummary = apps.get_model("main", "UserStatSummary")
    Profile = apps.get_model("main", "Profile")

    profile_xp_map = {
        row.user_id: int(row.xp or 0)
        for row in Profile.objects.all().only("user_id", "xp")
    }

    for summary in UserStatSummary.objects.all():
        earned_xp = (
            int(summary.test_xp_total or 0)
            + int(summary.practice_xp_total or 0)
            + int(summary.grammar_xp_total or 0)
            + int(summary.essay_xp_total or 0)
        )
        target_xp = profile_xp_map.get(summary.user_id, int(summary.lifetime_xp or 0))
        summary.manual_xp_adjustment = target_xp - earned_xp
        summary.lifetime_xp = target_xp
        summary.save(update_fields=["manual_xp_adjustment", "lifetime_xp", "updated_at"])


def reset_manual_xp_adjustment(apps, schema_editor):
    UserStatSummary = apps.get_model("main", "UserStatSummary")
    UserStatSummary.objects.update(manual_xp_adjustment=0)


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0028_alter_practiceset_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userstatsummary",
            name="manual_xp_adjustment",
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(backfill_manual_xp_adjustment, reset_manual_xp_adjustment),
    ]
