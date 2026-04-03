from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0022_subjectsectionentry_usage_note"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_viewed_at", models.DateTimeField(auto_now_add=True)),
                ("last_viewed_at", models.DateTimeField(auto_now=True)),
                ("view_count", models.PositiveIntegerField(default=1)),
                ("book", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="views", to="main.book")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Kitob ko'rilishi",
                "verbose_name_plural": "Kitob ko'rilishlari",
            },
        ),
        migrations.AddConstraint(
            model_name="bookview",
            constraint=models.UniqueConstraint(fields=("user", "book"), name="unique_user_book_view"),
        ),
    ]
