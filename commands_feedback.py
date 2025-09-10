from typing import List
from datetime import datetime, UTC
from utils_io import FEEDBACK_FILE, load_json_list, save_json_list

def detect_command(text: str) -> str | None:
    t = text.strip().lower()
    if t in {"/summary","/clear","/history"}:
        return t[1:]

    sv_summary = ["sammanfatta","summera","kan du sammanfatta","kan du summera","ge en sammanfattning"]
    sv_clear   = ["rensa","radera chatten","ta bort chatten","ta bort konversationen","nollställ"]
    sv_history = ["visa historiken","hela historiken","visa hela historiken","visa konversationen"]

    en_summary = ["summary","summarize","give a summary","show summary"]
    en_clear   = ["clear","clear chat","delete chat","reset conversation","remove conversation"]
    en_history = ["history","show history","full history"]

    ar_summary = ["لخص","ملخص","أعطني ملخص","الخلاصة"]
    ar_clear   = ["امسح","احذف المحادثة","حذف المحادثة","إعادة تعيين"]
    ar_history = ["اعرض السجل","السجل","اعرض التاريخ"]

    def match_any(needles: List[str]) -> bool:
        return any(n in t for n in needles)

    if match_any(sv_summary + en_summary + ar_summary):
        return "summary"
    if match_any(sv_clear + en_clear + ar_clear):
        return "clear"
    if match_any(sv_history + en_history + ar_history):
        return "history"
    return None

def save_feedback(question: str, answer: str, helpful: str, user_id: str) -> None:
    records = load_json_list(FEEDBACK_FILE)
    records.append({
        "user_id": user_id,
        "question": question,
        "answer": answer,
        "helpful": helpful.lower(),
        "ts": datetime.now(UTC).isoformat()
    })
    save_json_list(FEEDBACK_FILE, records)

def get_feedback_prompt(language: str) -> str:
    if language == "sv":
        return "Var detta hjälpsamt? (ja/nej)"
    elif language == "ar":
        return "هل كان هذا مفيداً؟ (نعم/لا)"
    else:
        return "Was this helpful? (yes/no)"

def get_feedback_thanks(language: str) -> str:
    if language == "sv":
        return "Tack för din återkoppling! (sparad)\n"
    elif language == "ar":
        return "شكرًا على ملاحظاتك! (تم الحفظ)\n"
    else:
        return "Thanks for your feedback! (saved)\n"
