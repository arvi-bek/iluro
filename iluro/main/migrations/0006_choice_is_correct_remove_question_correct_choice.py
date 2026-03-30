# Generated manually to remove circular correct choice dependency

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0005_book_pdf_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='choice',
            name='is_correct',
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveField(
            model_name='question',
            name='correct_choice',
        ),
    ]
