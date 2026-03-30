# Generated manually for XP-based progression

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0006_choice_is_correct_remove_question_correct_choice'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='xp',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='profile',
            name='level',
            field=models.CharField(default='S', max_length=20),
        ),
    ]
