from django.db import migrations


def sync_subscription_plan_catalog(apps, schema_editor):
    SubscriptionPlan = apps.get_model("main", "SubscriptionPlan")
    UserSubscription = apps.get_model("main", "UserSubscription")

    desired_catalog = [
        {
            "code": "free",
            "name": "FREE",
            "subject_limit": 1,
            "is_all_access": False,
            "price": 0,
            "duration_days": 30,
            "display_order": 10,
            "stack_mode": "replace",
            "daily_test_limit": 3,
            "daily_ai_limit": 3,
            "is_public": True,
            "is_featured": False,
            "can_use_ai": True,
            "can_use_full_content": False,
            "can_use_advanced_content": False,
            "can_use_mock_exam": False,
            "can_use_progress_recommendations": False,
            "can_use_advanced_stats": False,
            "is_active": True,
        },
        {
            "code": "single-subject",
            "name": "SINGLE SUBJECT",
            "subject_limit": 1,
            "is_all_access": False,
            "price": 30000,
            "duration_days": 30,
            "display_order": 20,
            "stack_mode": "additive",
            "daily_test_limit": None,
            "daily_ai_limit": None,
            "is_public": True,
            "is_featured": False,
            "can_use_ai": True,
            "can_use_full_content": True,
            "can_use_advanced_content": False,
            "can_use_mock_exam": False,
            "can_use_progress_recommendations": False,
            "can_use_advanced_stats": False,
            "is_active": True,
        },
        {
            "code": "triple-subject",
            "name": "PRO",
            "subject_limit": 3,
            "is_all_access": False,
            "price": 70000,
            "duration_days": 30,
            "display_order": 30,
            "stack_mode": "additive",
            "daily_test_limit": None,
            "daily_ai_limit": None,
            "is_public": True,
            "is_featured": True,
            "can_use_ai": True,
            "can_use_full_content": True,
            "can_use_advanced_content": True,
            "can_use_mock_exam": False,
            "can_use_progress_recommendations": True,
            "can_use_advanced_stats": False,
            "is_active": True,
        },
        {
            "code": "all-access",
            "name": "PREMIUM",
            "subject_limit": None,
            "is_all_access": True,
            "price": 120000,
            "duration_days": 30,
            "display_order": 40,
            "stack_mode": "replace",
            "daily_test_limit": None,
            "daily_ai_limit": None,
            "is_public": True,
            "is_featured": True,
            "can_use_ai": True,
            "can_use_full_content": True,
            "can_use_advanced_content": True,
            "can_use_mock_exam": True,
            "can_use_progress_recommendations": True,
            "can_use_advanced_stats": True,
            "is_active": True,
        },
        {
            "code": "beta-trial-all-access",
            "name": "Beta trial",
            "subject_limit": None,
            "is_all_access": True,
            "price": 0,
            "duration_days": 14,
            "display_order": 90,
            "stack_mode": "replace",
            "daily_test_limit": None,
            "daily_ai_limit": None,
            "is_public": False,
            "is_featured": False,
            "can_use_ai": True,
            "can_use_full_content": True,
            "can_use_advanced_content": True,
            "can_use_mock_exam": True,
            "can_use_progress_recommendations": True,
            "can_use_advanced_stats": True,
            "is_active": True,
        },
    ]

    name_updates = {
        "single-subject": {"old_titles": {"1 fan"}, "new_title": "SINGLE SUBJECT"},
        "triple-subject": {"old_titles": {"3 fan"}, "new_title": "PRO"},
        "all-access": {"old_titles": {"All access"}, "new_title": "PREMIUM"},
    }

    for item in desired_catalog:
        plan, _ = SubscriptionPlan.objects.update_or_create(
            code=item["code"],
            defaults=item,
        )
        rename_config = name_updates.get(item["code"])
        if rename_config:
            UserSubscription.objects.filter(
                plan_id=plan.id,
                title__in=rename_config["old_titles"],
            ).update(title=rename_config["new_title"])
            UserSubscription.objects.filter(plan_id=plan.id, title="").update(title=rename_config["new_title"])

    SubscriptionPlan.objects.filter(code="double-subject").update(
        name="Legacy 2 fan",
        is_active=False,
        is_public=False,
        is_featured=False,
        display_order=80,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0032_alter_essaytopic_options_and_more"),
    ]

    operations = [
        migrations.RunPython(sync_subscription_plan_catalog, migrations.RunPython.noop),
    ]
