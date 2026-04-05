from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from main.services import get_or_sync_profile, rebuild_user_statistics


class Command(BaseCommand):
    help = "Barcha foydalanuvchilar uchun stat va XP ni qayta hisoblaydi."

    def handle(self, *args, **options):
        processed = 0
        for user in User.objects.all().iterator():
            rebuild_user_statistics(user)
            get_or_sync_profile(user)
            processed += 1

        self.stdout.write(
            self.style.SUCCESS(f"{processed} ta foydalanuvchi statistikasi qayta hisoblandi.")
        )
