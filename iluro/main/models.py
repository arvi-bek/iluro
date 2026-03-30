from django.db import models
from django.contrib.auth.models import User


class Subject(models.Model):
    name = models.CharField(max_length=100)
    price = models.IntegerField(default=30000)

    def __str__(self):
        return self.name

class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)

    purchased_at = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()

    def __str__(self):
        return f"{self.user} - {self.subject}"

class Test(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)

    duration = models.IntegerField()  # minut
    created_at = models.DateTimeField(auto_now_add=True)

    difficulty = models.CharField(max_length=50)

    def __str__(self):
        return self.title

class Question(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, db_index=True)

    text = models.TextField()
    difficulty = models.CharField(max_length=50)

    def __str__(self):
        return self.text[:50]


class Choice(models.Model):
    id = models.AutoField(primary_key=True)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, db_index=True)
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text

class UserTest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    test = models.ForeignKey(Test, on_delete=models.CASCADE, db_index=True)

    score = models.IntegerField(default=0)
    correct_count = models.IntegerField(default=0)

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()

    snapshot_json = models.JSONField()

    def __str__(self):
        return f"{self.user} - {self.test}"


class UserAnswer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, db_index=True)

    selected_choice = models.ForeignKey(
        Choice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_answers',
    )
    is_correct = models.BooleanField()

    def __str__(self):
        return f"{self.user} - {self.question.id}"



class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    full_name = models.CharField(max_length=150)
    level = models.CharField(max_length=20, default='S')
    xp = models.IntegerField(default=0)

    photo = models.ImageField(upload_to='profiles/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username


class Book(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    pdf_file = models.FileField(upload_to='books/', blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

