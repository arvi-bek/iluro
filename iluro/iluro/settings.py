"""
Django settings for iluro.
"""

import os
from importlib.util import find_spec
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


_load_env_file(BASE_DIR / ".env")


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-local-dev-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost", "testserver"])
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])


# Application definition

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'main'

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'iluro.middleware.FriendlyErrorPagesMiddleware',
]

if find_spec("whitenoise"):
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = 'iluro.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'iluro.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

db_name = os.getenv("DB_NAME")
db_engine = os.getenv("DB_ENGINE", "django.db.backends.postgresql")

if db_name:
    DATABASES = {
        "default": {
            "ENGINE": db_engine,
            "NAME": db_name,
            "USER": os.getenv("DB_USER", ""),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {
                "sslmode": os.getenv("DB_SSLMODE", "prefer"),
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Tashkent'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if find_spec("whitenoise"):
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", not DEBUG)
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

if env_bool("DJANGO_ENABLE_HSTS", not DEBUG):
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

JAZZMIN_SETTINGS = {
    "site_title": "ILURO Admin",
    "site_header": "ILURO",
    "site_brand": "ILURO",
    "site_logo_classes": "img-circle",
    "welcome_sign": "ILURO boshqaruv paneli",
    "copyright": "ILURO",
    "search_model": ["auth.User"],
    "topmenu_links": [
        {"name": "Sayt", "url": "index", "permissions": ["auth.view_user"]},
        {"name": "Asosiy bo'limlar", "app": "main"},
        {"name": "Foydalanuvchilar", "model": "auth.User"},
    ],
    "custom_links": {
        "main": [
            {
                "name": "Import markazi",
                "url": "/admin/import-center/",
                "icon": "fas fa-file-import",
                "permissions": ["auth.view_user"],
            },
        ],
    },
    "order_with_respect_to": [
        "main",
        "auth",
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "main.Subject": "fas fa-book-open",
        "main.Subscription": "fas fa-credit-card",
        "main.Profile": "fas fa-id-badge",
        "main.Test": "fas fa-clipboard-check",
        "main.Question": "fas fa-circle-question",
        "main.Choice": "fas fa-list-ul",
        "main.UserTest": "fas fa-chart-line",
        "main.UserAnswer": "fas fa-square-check",
        "main.Book": "fas fa-file-pdf",
        "main.SubjectSectionEntry": "fas fa-layer-group",
        "main.EssayTopic": "fas fa-pen-nib",
        "main.PracticeSet": "fas fa-shapes",
        "main.PracticeExercise": "fas fa-calculator",
        "main.PracticeChoice": "fas fa-list-check",
        "main.PracticeSetAttempt": "fas fa-chart-column",
        "main.UserPracticeAttempt": "fas fa-square-poll-vertical",
    },
    "custom_css": "css/admin_custom.css",
    "show_sidebar": True,
    "navigation_expanded": True,
    "show_ui_builder": False,
}

JAZZMIN_UI_TWEAKS = {
    "theme": "simplex",
    "dark_mode_theme": None,
    "navbar": "navbar-white navbar-light",
    "no_navbar_border": True,
    "accent": "accent-warning",
    "navbar_small_text": False,
    "sidebar": "sidebar-light-light",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme_colour": "navbar-white",
    "button_classes": {
        "primary": "btn btn-warning",
        "secondary": "btn btn-outline-secondary",
        "info": "btn btn-outline-info",
        "warning": "btn btn-warning",
        "danger": "btn btn-outline-danger",
        "success": "btn btn-outline-success",
    },
}
