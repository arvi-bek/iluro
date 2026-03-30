# Generated manually for PDF support in books

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0004_book_alter_subject_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='book',
            name='pdf_file',
            field=models.FileField(blank=True, null=True, upload_to='books/'),
        ),
    ]
