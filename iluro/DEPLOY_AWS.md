# ILURO AWS Deploy Guide

## 1. Server tayyorlash
- Ubuntu EC2 instance oching.
- Security Group'da `80`, `443`, `22` portlarini ruxsat bering.
- Domain ishlatsangiz DNS'ni serverga ulang.

## 2. Paketlar
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv nginx postgresql postgresql-contrib
```

## 3. Loyiha
```bash
git clone <your-repo-url>
cd iluro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` ichida production qiymatlarni yozing.

## 4. Database
- PostgreSQL ichida `iluro` nomli DB va user yarating.
- `.env` ichidagi `DB_*` qiymatlarini shu userga moslang.

## 5. Django build
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py check --deploy
```

## 6. Gunicorn test
```bash
gunicorn iluro.wsgi:application --bind 0.0.0.0:8000
```

## 7. Nginx reverse proxy
`/etc/nginx/sites-available/iluro`:

```nginx
server {
    server_name your-domain.com www.your-domain.com;

    location /static/ {
        alias /path/to/iluro/staticfiles/;
    }

    location /media/ {
        alias /path/to/iluro/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

So'ng:
```bash
sudo ln -s /etc/nginx/sites-available/iluro /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 8. HTTPS
- `certbot` bilan SSL o'rnating.
- `.env` ichida:
  - `DJANGO_DEBUG=False`
  - `DJANGO_SESSION_COOKIE_SECURE=True`
  - `DJANGO_CSRF_COOKIE_SECURE=True`
  - `DJANGO_SECURE_SSL_REDIRECT=True`
  - `DJANGO_ENABLE_HSTS=True`

## 9. Tavsiya etiladigan yakuniy tekshiruv
- `/health/` 200 qaytaryaptimi
- admin ishlayaptimi
- PDF kitoblar ochilyaptimi
- `python manage.py check --deploy` warningsiz o'tyaptimi
- `.env` Git'ga tushmayotganini tekshiring
