from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
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

GRADE_CHOICES = [
    ("5", "5-sinf"),
    ("6", "6-sinf"),
    ("7", "7-sinf"),
    ("8", "8-sinf"),
    ("9", "9-sinf"),
    ("10", "10-sinf"),
    ("11", "11-sinf"),
]


class Subject(models.Model):
    name = models.CharField(max_length=100)
    price = models.IntegerField(default=30000)

    class Meta:
        verbose_name = "Fan"
        verbose_name_plural = "Fanlar"

    def __str__(self):
        return self.name

class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)

    purchased_at = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True)

    class Meta:
        ordering = ("-end_date", "-purchased_at")
        verbose_name = "Obuna"
        verbose_name_plural = "Obunalar"
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

    class Meta:
        verbose_name = "Test"
        verbose_name_plural = "Testlar"

    def __str__(self):
        return self.title

class Question(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, db_index=True)

    text = models.TextField()
    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES)

    class Meta:
        verbose_name = "Savol"
        verbose_name_plural = "Savollar"

    def __str__(self):
        return self.text[:50]


class Choice(models.Model):
    id = models.AutoField(primary_key=True)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, db_index=True)
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Variant"
        verbose_name_plural = "Variantlar"

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

    class Meta:
        verbose_name = "Test urinish"
        verbose_name_plural = "Test urinishlari"

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

    class Meta:
        verbose_name = "Foydalanuvchi javobi"
        verbose_name_plural = "Foydalanuvchi javoblari"

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

    class Meta:
        verbose_name = "Profil"
        verbose_name_plural = "Profillar"

    def __str__(self):
        return self.user.username


class UserSubjectPreference(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    preferred_level = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default="S")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Foydalanuvchi fan sozlamasi"
        verbose_name_plural = "Foydalanuvchi fan sozlamalari"
        constraints = [
            models.UniqueConstraint(fields=("user", "subject"), name="unique_user_subject_preference"),
        ]

    def __str__(self):
        return f"{self.user} - {self.subject} - {self.preferred_level}"


class Book(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=150, blank=True)
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES, blank=True)
    description = models.TextField(blank=True)
    access_level = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES, default="S", blank=True)
    pdf_file = models.FileField(upload_to='books/', blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kitob"
        verbose_name_plural = "Kitoblar"

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
        verbose_name = "Fan bo'limi materiali"
        verbose_name_plural = "Fan bo'limi materiallari"

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
        verbose_name = "Insho mavzusi"
        verbose_name_plural = "Insho mavzulari"

    def __str__(self):
        return f"{self.subject.name} - {self.title}"


class PracticeSet(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    source_book = models.CharField(max_length=255, blank=True)
    topic = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES, default="S")
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-is_featured", "-created_at")
        verbose_name = "Misol / Masala bo'limi"
        verbose_name_plural = "Misol / Masala bo'limlari"

    def __str__(self):
        return f"{self.subject.name} - {self.title}"


class PracticeExercise(models.Model):
    ANSWER_MODE_CHOICES = [
        ("choice", "Variantli javob"),
        ("input", "Input javob"),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    practice_set = models.ForeignKey(
        PracticeSet,
        on_delete=models.CASCADE,
        related_name="exercises",
        db_index=True,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255, blank=True, default="")
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
        verbose_name = "Misol / Masala"
        verbose_name_plural = "Misol / Masalalar"

    def clean(self):
        if self.practice_set:
            existing_count = self.practice_set.exercises.exclude(pk=self.pk).count()
            if existing_count >= 20:
                raise ValidationError("Bitta misol / masala bo'limiga ko'pi bilan 20 ta topshiriq qo'shish mumkin.")

    def save(self, *args, **kwargs):
        if self.practice_set:
            self.subject = self.practice_set.subject
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        label = self.title or self.prompt[:60]
        return f"{self.subject.name} - {label}"


class PracticeChoice(models.Model):
    exercise = models.ForeignKey(PracticeExercise, on_delete=models.CASCADE, related_name="choices", db_index=True)
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Misol / Masala varianti"
        verbose_name_plural = "Misol / Masala variantlari"

    def __str__(self):
        return self.text


class UserPracticeAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    exercise = models.ForeignKey(PracticeExercise, on_delete=models.CASCADE, db_index=True)
    practice_session = models.ForeignKey(
        "PracticeSetAttempt",
        on_delete=models.CASCADE,
        related_name="answers",
        null=True,
        blank=True,
    )
    selected_choice = models.ForeignKey(PracticeChoice, on_delete=models.SET_NULL, null=True, blank=True)
    answer_text = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Misol / Masala urinish"
        verbose_name_plural = "Misol / Masala urinishlari"

    def __str__(self):
        return f"{self.user} - {self.exercise}"


class PracticeSetAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    practice_set = models.ForeignKey(PracticeSet, on_delete=models.CASCADE, db_index=True)
    score = models.IntegerField(default=0)
    correct_count = models.IntegerField(default=0)
    total_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Misol / Masala bo'limi urinish"
        verbose_name_plural = "Misol / Masala bo'limi urinishlari"

    def __str__(self):
        return f"{self.user} - {self.practice_set}"

