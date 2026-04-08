from django.db.models import Count
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render

from main.models import Book, EssayTopic, PracticeSet, Subject, SubjectSectionEntry, Test


def index(request: HttpRequest):
    subject_accents = {
        "tarix": "Tarixiy tafakkur, sanalar, xronologiya va mavzulashtirilgan assessment oqimi.",
        "matem": "Formula, misol va nazorat bloklarini bitta erkin ishlash ritmida yig'adi.",
    }
    subject_queryset = list(Subject.objects.order_by("id", "name"))
    subjects = []
    for subject in subject_queryset:
        lowered = subject.name.lower()
        accent = subject_accents.get(
            "tarix" if "tarix" in lowered else "matem" if "matem" in lowered else "",
            "Grammatika, esse va matn bilan ishlashni AI-ready tayyorlov oqimiga birlashtiradi.",
        )
        subjects.append({"name": subject.name, "accent": accent})

    subject_count = len(subjects)
    tests_count = Test.objects.count()
    books_count = Book.objects.count()
    practice_count = PracticeSet.objects.count()
    essay_count = EssayTopic.objects.count()
    grammar_count = SubjectSectionEntry.objects.filter(section_key="grammar").count()
    reference_count = SubjectSectionEntry.objects.exclude(section_key="grammar").count()
    total_material_count = tests_count + books_count + practice_count + essay_count + reference_count

    resource_metrics = [
        {"value": subject_count or 3, "label": "faol fan", "note": "Tarix, matematika va ona tili"},
        {
            "value": tests_count + practice_count,
            "label": "assessment blok",
            "note": "Test va mashq oqimi ishlayapti",
        },
        {
            "value": grammar_count + essay_count,
            "label": "grammar va esse",
            "note": "Yozma ish va grammar stack mavjud",
        },
        {
            "value": total_material_count,
            "label": "jami material",
            "note": "Resurs, reference va assessment birlashgan",
        },
    ]
    curriculum_points = [
        "Assessment, grammar, esse va kutubxona bir stackda",
        "Fan bo'yicha subscription va bundle modeli tayyor",
        "AI helper, mock va SAT uchun arxitektura ochiq",
    ]
    highlights = [
        "Tarqoq tayyorlovni bitta product oqimiga yig'adi",
        "Milliy sertifikat formatiga mos tarix, matematika va ona tili stacki tayyor",
        "Admin import markazi bilan kontentni tez ko'paytirish mumkin",
    ]
    problem_points = [
        "Tayyorlov ko'pincha Telegram, PDF, test va izohlar o'rtasida bo'linib ketadi.",
        "Esse va grammatika uchun tez feedback yo'qligi o'quvchini sekinlashtiradi.",
        "Bir joyda progress, resurs va assessment ko'rinmasa retention pasayadi.",
    ]
    product_modules = [
        {
            "title": "Test va mashqlar",
            "text": "Test topshirish, mashq ishlash va natijani ko'rish bitta oqimda ishlaydi.",
            "label": "Assessment",
            "meta": f"{tests_count + practice_count} ta blok",
        },
        {
            "title": "Mavzu materiallari",
            "text": "Sanalar, atamalar, qoidalar va qo'shimcha materiallar bir joyda turadi.",
            "label": "Reference",
            "meta": f"{reference_count} ta material",
        },
        {
            "title": "Grammatika va esse",
            "text": "Grammatika darslari, esse mavzulari va yozma ish uchun tayanch bloklar bor.",
            "label": "Language",
            "meta": f"{grammar_count + essay_count} ta dars va mavzu",
        },
        {
            "title": "Kontent qo'shish oson",
            "text": "Admin import markazi orqali yangi test, mashq va materiallarni tez kiritish mumkin.",
            "label": "Ops",
            "meta": "Admin import tayyor",
        },
    ]
    traction_metrics = [
        {"label": "Fanlar", "value": subject_count or 3, "hint": "Tarix, matematika, ona tili"},
        {"label": "Test va mashqlar", "value": tests_count + practice_count, "hint": "Ishlayotgan assessment bloklari"},
        {"label": "Reference material", "value": reference_count, "hint": "Sanalar, atamalar, qoidalar va extras"},
        {"label": "Esse va grammar", "value": grammar_count + essay_count, "hint": "Yozma ish va grammar oqimi"},
    ]
    market_reasons = [
        {
            "title": "Demand mavjud",
            "text": "Milliy sertifikatga tayyorlov bozori strukturali product tarafga siljimoqda.",
        },
        {
            "title": "AI uchun kuchli use case",
            "text": "AI yordamchi esse va feedback layerini yengillashtira oladi.",
        },
        {
            "title": "Monetizatsiya ochiq",
            "text": "Bir fanlik obunadan bundle modelga o'tish monetizatsiyani kengaytiradi.",
        },
    ]
    roadmap_items = [
        {"phase": "01", "stage": "01", "title": "AI helper MVP", "text": "Xato tahlili, esse yo'nalishi va kontekstli tushuntirish."},
        {"phase": "02", "stage": "02", "title": "Mock exam", "text": "To'liq simulyatsiya, natija breakdown va retry logic."},
        {"phase": "03", "stage": "03", "title": "SAT + 3 yangi fan", "text": "Fizika, biologiya, kimyo va SAT liniyasini ochish."},
        {"phase": "04", "stage": "04", "title": "Esse self-check", "text": "Yozma ishni mustaqil tekshirish va rubric-based feedback."},
        {"phase": "05", "stage": "05", "title": "Mentor layer", "text": "Mentor maslahatlari va yo'naltirilgan support."},
    ]
    business_model_cards = [
        {"title": "1 fan", "text": "Bitta kerakli fan bilan boshlash uchun", "meta": "Entry subscription"},
        {"title": "2 fan", "text": "Ikki fan birga tayyorlanish uchun", "meta": "Bundle step"},
        {"title": "3 fan", "text": "Asosiy to'liq tayyorlov paketi", "meta": "Core offer"},
        {"title": "All access", "text": "Barcha fan va keyingi yo'nalishlar uchun", "meta": "Expansion offer"},
    ]
    funding_ask = {
        "amount": "18k USD",
        "title": "Keyingi product sprint uchun ochiq so'rov",
        "text": "Maqsad: AI helper, infra barqarorligi, resurslar va kontrolli reklama testlarini tezlashtirish.",
        "window": "9-12 oy runway",
        "use_case": "AI layer, reklama testlari va product expansion uchun",
    }
    funding_breakdown = [
        {"label": "AI / API", "title": "AI / API", "percent": "30%", "hint": "Helper, explanation va esse layeri", "text": "Helper, explanation va esse layeri"},
        {"label": "Reklama", "title": "Reklama", "percent": "35%", "hint": "Paid acquisition va beta funnel testlari", "text": "Paid acquisition va beta funnel testlari"},
        {"label": "Server / infra", "title": "Server / infra", "percent": "15%", "hint": "AWS, storage, reliability, ops", "text": "AWS, storage, reliability, ops"},
        {"label": "Kontent / resurs", "title": "Kontent / resurs", "percent": "15%", "hint": "Yangi fanlar va batch materiallar", "text": "Yangi fanlar va batch materiallar"},
        {"label": "Reserve", "title": "Reserve", "percent": "5%", "hint": "Unexpected product va growth costlar", "text": "Unexpected product va growth costlar"},
    ]
    cta_links = [
        {"label": "Beta guruh", "href": "https://t.me/+c5-ItPYBkKcyNTU6"},
        {"label": "Hamkorlik", "href": "https://t.me/arvibek_O"},
    ]
    product_flow = [
        {
            "step": "01",
            "title": "Fan tanlang",
            "text": "Kerakli yo'nalishni tanlab, shu fan uchun ochilgan material va assessment oqimiga kiring.",
        },
        {
            "step": "02",
            "title": "Mavzuni tushunib oling",
            "text": "Formula, grammatika, xronologiya yoki qo'shimcha blokdan tayanchni yig'ing.",
        },
        {
            "step": "03",
            "title": "Mashq ishlang",
            "text": "Bitta savollik flow bilan xato qilmasdan mashq va misollarni yeching.",
        },
        {
            "step": "04",
            "title": "Test topshiring",
            "text": "Fan bo'yicha nazorat bloklari orqali tayyorgarlik darajangizni tekshiring.",
        },
        {
            "step": "05",
            "title": "Natijani ko'ring",
            "text": "XP, level va yakuniy natija orqali qaysi joyda kuchli yoki sust ekaningiz ko'rinadi.",
        },
        {
            "step": "06",
            "title": "Keyingi bosqichga o'ting",
            "text": "Platforma sizni navbatdagi mavzu, set yoki yo'nalishga tartibli olib boradi.",
        },
    ]
    subject_details = [
        {
            "name": "Tarix",
            "caption": "Xronologiya, atamalar va test bloklari.",
            "tags": ["Sanalar", "Atamalar", "Testlar"],
        },
        {
            "name": "Matematika",
            "caption": "Formulalar, misol-masalalar va bosqichli mashqlar.",
            "tags": ["Formulalar", "Mashqlar", "Nazorat"],
        },
        {
            "name": "Ona tili va adabiyot",
            "caption": "Grammatika, esse va qo'shimcha materiallar.",
            "tags": ["Grammatika", "Esse", "Kutubxona"],
        },
    ]
    progress_points = [
        {"title": "Daraja tizimi", "text": "S dan A+ gacha o'sish foydalanuvchiga aniq ko'rinadi."},
        {"title": "XP oqimi", "text": "Har bir test, mashq va grammatika bloki umumiy progressga ulanadi."},
        {"title": "Reyting", "text": "Top foydalanuvchilar va shaxsiy o'sish bir joyda ko'rinadi."},
    ]
    context = {
        "subjects": subjects,
        "resource_metrics": resource_metrics,
        "curriculum_points": curriculum_points,
        "highlights": highlights,
        "problem_points": problem_points,
        "product_modules": product_modules,
        "traction_metrics": traction_metrics,
        "market_reasons": market_reasons,
        "roadmap_items": roadmap_items,
        "business_model_cards": business_model_cards,
        "funding_ask": funding_ask,
        "funding_breakdown": funding_breakdown,
        "cta_links": cta_links,
        "product_flow": product_flow,
        "subject_details": subject_details,
        "progress_points": progress_points,
    }
    return render(request, "index.html", context)


def health_check(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})
