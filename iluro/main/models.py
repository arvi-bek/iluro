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

TEST_CATEGORY_CHOICES = [
    ("general", "Umumiy"),
    ("terms", "Atamalar bo'yicha"),
    ("years", "Yillar bo'yicha"),
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


class SubscriptionPlan(models.Model):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    subject_limit = models.PositiveIntegerField(null=True, blank=True)
    is_all_access = models.BooleanField(default=False)
    price = models.IntegerField(default=0)
    duration_days = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("price", "name")
        verbose_name = "Obuna rejasi"
        verbose_name_plural = "Obuna rejalari"

    def __str__(self):
        return self.name


class UserSubscription(models.Model):
    STATUS_CHOICES = [
        ("active", "Faol"),
        ("expired", "Tugagan"),
        ("cancelled", "Bekor qilingan"),
    ]
    SOURCE_CHOICES = [
        ("purchase", "Sotib olish"),
        ("beta_trial", "Beta trial"),
        ("legacy_import", "Legacy import"),
        ("manual", "Qo'lda"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bundle_subscriptions", db_index=True)
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
    )
    title = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="purchase")
    is_all_access = models.BooleanField(default=False)
    started_at = models.DateTimeField(default=timezone.now)
    end_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-end_at", "-created_at")
        verbose_name = "Foydalanuvchi obunasi"
        verbose_name_plural = "Foydalanuvchi obunalari"
        indexes = [
            models.Index(fields=("user", "status", "end_at"), name="main_usub_user_stat_end_idx"),
            models.Index(fields=("user", "created_at"), name="main_usub_user_created_idx"),
        ]

    @property
    def is_active(self):
        return self.status == "active" and self.end_at >= timezone.now()

    def save(self, *args, **kwargs):
        if not self.title and self.plan_id:
            self.title = self.plan.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.title or self.plan or 'Obuna'}"


class UserSubscriptionSubject(models.Model):
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.CASCADE,
        related_name="subjects",
        db_index=True,
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="subscription_items", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Obunadagi fan"
        verbose_name_plural = "Obunadagi fanlar"
        constraints = [
            models.UniqueConstraint(fields=("subscription", "subject"), name="unique_subscription_subject"),
        ]
        indexes = [
            models.Index(fields=("subscription", "subject"), name="main_usubj_subj_idx"),
            models.Index(fields=("subject",), name="main_usubj_subject_idx"),
        ]

    def __str__(self):
        return f"{self.subscription_id} - {self.subject.name}"

class Test(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)

    duration = models.IntegerField()  # minut
    created_at = models.DateTimeField(auto_now_add=True)
    difficulty = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES)
    category = models.CharField(max_length=20, choices=TEST_CATEGORY_CHOICES, default="general", blank=True)

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
        indexes = [
            models.Index(fields=("user", "finished_at"), name="main_usert_user_finish_idx"),
            models.Index(fields=("user", "test"), name="main_usert_user_test_idx"),
        ]

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
        indexes = [
            models.Index(fields=("user", "question"), name="main_uans_user_question_idx"),
        ]

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


class UserStatSummary(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="stat_summary")
    lifetime_xp = models.IntegerField(default=0)
    lifetime_test_count = models.PositiveIntegerField(default=0)
    lifetime_practice_count = models.PositiveIntegerField(default=0)
    total_correct_answers = models.PositiveIntegerField(default=0)
    total_correct_test_answers = models.PositiveIntegerField(default=0)
    total_correct_practice_answers = models.PositiveIntegerField(default=0)
    best_test_score = models.PositiveIntegerField(default=0)
    best_practice_score = models.PositiveIntegerField(default=0)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Foydalanuvchi umumiy statistikasi"
        verbose_name_plural = "Foydalanuvchi umumiy statistikasi"
        indexes = [
            models.Index(fields=("lifetime_xp",), name="main_ustat_xp_idx"),
            models.Index(fields=("last_activity_at",), name="main_ustat_last_act_idx"),
        ]

    def __str__(self):
        return f"{self.user.username} statistikasi"


class UserSubjectStat(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subject_stats", db_index=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="user_stats", db_index=True)
    xp = models.IntegerField(default=0)
    tests_taken = models.PositiveIntegerField(default=0)
    practice_taken = models.PositiveIntegerField(default=0)
    total_correct_answers = models.PositiveIntegerField(default=0)
    total_correct_test_answers = models.PositiveIntegerField(default=0)
    total_correct_practice_answers = models.PositiveIntegerField(default=0)
    best_score = models.PositiveIntegerField(default=0)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Foydalanuvchi fan statistikasi"
        verbose_name_plural = "Foydalanuvchi fan statistikasi"
        constraints = [
            models.UniqueConstraint(fields=("user", "subject"), name="unique_user_subject_stat"),
        ]
        indexes = [
            models.Index(fields=("user", "subject"), name="main_usub_user_subject_idx"),
            models.Index(fields=("subject", "xp"), name="main_usub_subject_xp_idx"),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.subject.name}"


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


class BookView(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="views", db_index=True)
    first_viewed_at = models.DateTimeField(auto_now_add=True)
    last_viewed_at = models.DateTimeField(auto_now=True)
    view_count = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Kitob ko'rilishi"
        verbose_name_plural = "Kitob ko'rilishlari"
        constraints = [
            models.UniqueConstraint(fields=("user", "book"), name="unique_user_book_view"),
        ]

    def __str__(self):
        return f"{self.user} - {self.book}"


class SubjectSectionEntry(models.Model):
    SECTION_CHOICES = [
        ("formulas", "Formulalar"),
        ("problems", "Misol / Masalalar"),
        ("terms", "Atamalar"),
        ("chronology", "Xronologiya"),
        ("grammar", "Gramatika"),
        ("rules", "Qoidalar"),
        ("essay", "Insho"),
        ("extras", "Qo'shimcha ma'lumotlar"),
        ("events", "Sanalar / Voqealar"),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, db_index=True)
    section_key = models.CharField(max_length=50, choices=SECTION_CHOICES)
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    body = models.TextField(blank=True)
    usage_note = models.TextField(blank=True)
    access_level = models.CharField(max_length=50, choices=DIFFICULTY_CHOICES, default="S")
    order = models.PositiveIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "-is_featured", "-created_at")
        verbose_name = "Fan bo'limi materiali"
        verbose_name_plural = "Fan bo'limi materiallari"
        indexes = [
            models.Index(fields=("subject", "section_key", "order"), name="main_ssect_sub_sec_ord_idx"),
        ]

    def __str__(self):
        return f"{self.subject.name} - {self.title}"


class GrammarLessonQuestion(models.Model):
    OPTION_CHOICES = [
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
        ("D", "D"),
    ]

    lesson = models.ForeignKey(
        SubjectSectionEntry,
        on_delete=models.CASCADE,
        related_name="grammar_questions",
        db_index=True,
    )
    prompt = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_option = models.CharField(max_length=1, choices=OPTION_CHOICES)
    explanation = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Gramatika mini test savoli"
        verbose_name_plural = "Gramatika mini test savollari"

    def __str__(self):
        return f"{self.lesson.title} - {self.prompt[:60]}"


class GrammarLessonProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    lesson = models.ForeignKey(
        SubjectSectionEntry,
        on_delete=models.CASCADE,
        related_name="grammar_progress",
        db_index=True,
    )
    best_score = models.PositiveIntegerField(default=0)
    last_score = models.PositiveIntegerField(default=0)
    attempts_count = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Gramatika mavzu progressi"
        verbose_name_plural = "Gramatika mavzu progresslari"
        constraints = [
            models.UniqueConstraint(fields=("user", "lesson"), name="unique_user_grammar_lesson_progress"),
        ]

    def __str__(self):
        return f"{self.user} - {self.lesson}"


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
        verbose_name = "Mashq"
        verbose_name_plural = "Mashqlar"

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
        indexes = [
            models.Index(fields=("practice_set", "created_at"), name="main_pexpr_set_created_idx"),
            models.Index(fields=("subject", "difficulty"), name="main_pexpr_subject_diff_idx"),
        ]

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
        indexes = [
            models.Index(fields=("user", "created_at"), name="main_upra_user_created_idx"),
            models.Index(fields=("user", "practice_session"), name="main_upra_user_session_idx"),
        ]

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
        indexes = [
            models.Index(fields=("user", "created_at"), name="main_pset_user_created_idx"),
            models.Index(fields=("user", "practice_set"), name="main_pset_user_set_idx"),
        ]

    def __str__(self):
        return f"{self.user} - {self.practice_set}"

