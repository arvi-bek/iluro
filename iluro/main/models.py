from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


DIFFICULTY_CHOICES = [
    ("S", "S"),
    ("S+", "S+"),
    ("B", "B"),
    ("B+", "B+"),
    ("A", "A"),
    ("A+", "A+"),
]


class Subject(models.Model):
    name = models.CharField(max_length=100)
    price = models.IntegerField(default=30000)

    def __str__(self):
        return self.name

class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)

    purchased_at = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True)

    class Meta:
        ordering = ("-end_date", "-purchased_at")
        constraints = [
            models.UniqueConstraint(fields=("user", "subject"), name="unique_user_subject_subscription"),
        ]

    @property
    def is_active(self):
        return self.end_date >= timezone.now()

    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.subject}"

class Test(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)

    duration = models.IntegerField()  # minut
    created_at = models.DateTimeField(auto_now_add=True)
    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES)

    def __str__(self):
        return self.title

class Question(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, db_index=True)

    text = models.TextField()
    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES)

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
    ROLE_CHOICES = [
        ("student", "O'quvchi"),
        ("university", "Talaba"),
        ("teacher", "O'qituvchi"),
        ("admin", "Admin"),
    ]
    THEME_CHOICES = [
        ("warm", "Warm Ivory"),
        ("mist", "Soft Mist"),
        ("forest", "Forest Sage"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    full_name = models.CharField(max_length=150)
    level = models.CharField(max_length=20, default='S')
    xp = models.IntegerField(default=0)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default="warm")
    premium_until = models.DateTimeField(null=True, blank=True)

    photo = models.ImageField(upload_to='profiles/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username


class Book(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    access_level = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES, default="S")
    pdf_file = models.FileField(upload_to='books/', blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class SubjectSectionEntry(models.Model):
    SECTION_CHOICES = [
        ("formulas", "Formulalar"),
        ("problems", "Misol / Masalalar"),
        ("rules", "Qoidalar"),
        ("essay", "Insho"),
        ("extras", "Qo'shimcha ma'lumotlar"),
        ("events", "Tarixiy voqealar"),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    section_key = models.CharField(max_length=50, choices=SECTION_CHOICES)
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    body = models.TextField(blank=True)
    access_level = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES, default="S")
    order = models.PositiveIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "-is_featured", "-created_at")

    def __str__(self):
        return f"{self.subject.name} - {self.title}"


class EssayTopic(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    prompt_text = models.TextField()
    thesis_hint = models.TextField(blank=True)
    outline = models.TextField(blank=True)
    sample_intro = models.TextField(blank=True)
    sample_conclusion = models.TextField(blank=True)
    access_level = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES, default="S")
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-is_featured", "-created_at")

    def __str__(self):
        return f"{self.subject.name} - {self.title}"


class PracticeExercise(models.Model):
    ANSWER_MODE_CHOICES = [
        ("choice", "Variantli javob"),
        ("input", "Input javob"),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    source_book = models.CharField(max_length=255, blank=True)
    topic = models.CharField(max_length=255, blank=True)
    prompt = models.TextField()
    answer_mode = models.CharField(max_length=20, choices=ANSWER_MODE_CHOICES, default="choice")
    correct_text = models.CharField(max_length=255, blank=True)
    explanation = models.TextField(blank=True)
    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES, default="S")
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-is_featured", "-created_at")

    def __str__(self):
        return f"{self.subject.name} - {self.title}"


class PracticeChoice(models.Model):
    exercise = models.ForeignKey(PracticeExercise, on_delete=models.CASCADE, related_name="choices", db_index=True)
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class UserPracticeAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    exercise = models.ForeignKey(PracticeExercise, on_delete=models.CASCADE, db_index=True)
    selected_choice = models.ForeignKey(PracticeChoice, on_delete=models.SET_NULL, null=True, blank=True)
    answer_text = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} - {self.exercise}"

