# Generated manually for profile menu details

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0007_profile_xp_alter_profile_level'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='premium_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='role',
            field=models.CharField(
                choices=[('student', "O'quvchi"), ('teacher', "O'qituvchi"), ('admin', 'Admin')],
                default='student',
                max_length=20,
            ),
        ),
    ]
