from django.http import HttpRequest, JsonResponse
from django.shortcuts import render


def index(request: HttpRequest):
    subjects = [
        {"name": "Tarix", "accent": "Milliy sertifikat savollari uchun tarixiy tafakkur va tezkor tahlil"},
        {"name": "Matematika", "accent": "Masala, formulalar va vaqtni boshqarish bo'yicha qat'iy mashq"},
        {"name": "Ona tili va adabiyot", "accent": "Matn, grammatika va AI yordamida insho ustida ishlash"},
    ]
    resource_metrics = [
        {"value": "70+", "label": "Gramatika darslari"},
        {"value": "100+", "label": "Formula va qoida"},
        {"value": "700+", "label": "Atama va sanalar"},
    ]
    curriculum_points = [
        "Har kunlik dars ritmi",
        "Mini test va progress nazorati",
        "AI yordamida tushuntirish va tahlil",
    ]
    highlights = [
        "Fanlarni foydalanuvchi o'zi tanlaydi",
        "Milliy sertifikat formatiga mos test oqimi",
        "Natija, urinishlar va AI tavsiyalari bo'yicha shaffof kuzatuv",
    ]
    features = [
        {
            "title": "Milliy sertifikatga mos oqim",
            "text": "Platforma tayyorlovni fan tanlash, mashq va natija kuzatuvi kabi aniq bosqichlarga ajratadi.",
        },
        {
            "title": "AI mutaxassis yo'nalishi",
            "text": "AI bilan ishlash ko'nikmalarini rivojlantirish uchun tahliliy fikrlash va mustaqil ishlash muhiti yaratiladi.",
        },
        {
            "title": "Insho ustida ishlash",
            "text": "Ona tili va adabiyot fanida mavzu, tuzilma va ifodani yaxshilash uchun AI yordamchi oqimi qo'shiladi.",
        },
    ]
    steps = [
        {
            "number": "01",
            "title": "Fanlaringizni tanlang",
            "description": "Kerakli yo'nalishlarni belgilang va o'zingizga mos tayyorlov yo'lini boshlang.",
        },
        {
            "number": "02",
            "title": "Testni real formatda ishlang",
            "description": "Savollar, vaqt va bosqichlar haqiqiy imtihon ritmiga yaqin bo'ladi.",
        },
        {
            "number": "03",
            "title": "Natijani chuqur ko'ring",
            "description": "Qaysi bo'limlar kuchli, qaysi joylar ustida ishlash kerakligini darrov biling.",
        },
    ]
    context = {
        "subjects": subjects,
        "resource_metrics": resource_metrics,
        "curriculum_points": curriculum_points,
        "highlights": highlights,
        "features": features,
        "steps": steps,
    }
    return render(request, "index.html", context)


def health_check(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})
