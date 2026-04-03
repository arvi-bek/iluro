from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0012_essaytopic"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="theme",
            field=models.CharField(
                choices=[("warm", "Warm Ivory"), ("mist", "Soft Mist"), ("forest", "Forest Sage")],
                default="warm",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="profile",
            name="role",
            field=models.CharField(
                choices=[("student", "O'quvchi"), ("university", "Talaba"), ("teacher", "O'qituvchi"), ("admin", "Admin")],
                default="student",
                max_length=20,
            ),
        ),
    ]
