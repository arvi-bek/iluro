# Generated manually for books and subject pricing defaults

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0003_remove_question_correct_choice_id_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subject',
            name='price',
            field=models.IntegerField(default=30000),
        ),
        migrations.CreateModel(
            name='Book',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('author', models.CharField(blank=True, max_length=150)),
                ('description', models.TextField(blank=True)),
                ('is_featured', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('subject', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, to='main.subject')),
            ],
        ),
    ]
