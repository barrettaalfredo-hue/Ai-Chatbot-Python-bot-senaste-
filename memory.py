from datetime import datetime, UTC
from typing import Dict, Any, List, Tuple
import re
from langdetect import detect, LangDetectException

from utils_io import (
    GLOBAL_MEMORY_FILE,
    USER_MEMORY_LIMIT,
    GLOBAL_MEMORY_LIMIT,
    get_user_memory_file,
    load_json_list,
    save_json_list,
)
from utils_io import conservative_spell_fix
from profile import load_profile, maybe_update_profile_from_text
from prompts import build_system_prompt
from openai_chat import call_openai

# 🟢 DEBUG: importera hjälpare (loggning, historikkontroll, fallback-meddelande)
try:
    from debug_utils import logger, check_history_length, fallback_message
except Exception:
    # Fallback-noops om debug_utils saknas
    class _DummyLogger:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
        def debug(self, *a, **k): pass
    logger = _DummyLogger()
    def check_history_length(history, max_rounds=20): return True
    def fallback_message(lang="en"): return {
        "sv": "Oj, något gick fel när jag kontaktade modellen. Kan du prova igen?",
        "ar": "عذرًا، حدث خطأ أثناء الاتصال بالنموذج. هل يمكنك المحاولة مجددًا؟",
        "en": "Oops, something went wrong contacting the model. Please try again.",
    }.get(lang, "Oops, something went wrong contacting the model. Please try again.")


# -----------------------------
# Robust språkdetektering
# -----------------------------
_SV_HINTS = {"hej", "tack", "snälla", "förlåt", "jag", "heter", "hur", "mår", "bra", "då", "nej", "ja"}
_AR_RANGE = re.compile(r"[\u0600-\u06FF]")  # arabisk unicode-range

def detect_lang(text: str, fallback: str = "en") -> str:
    """
    Försöker avgöra språk (sv/en/ar) från enstaka meddelanden, med enkla heuristiker
    + langdetect som backup. Returnerar fallback (en) om inget kan avgöras.
    """
    t = (text or "").strip().lower()
    if not t:
        return fallback

    # 1) Tydliga tecken
    if _AR_RANGE.search(t):
        return "ar"
    if any(ch in t for ch in "åäö"):
        return "sv"
    if any(w in t.split() for w in _SV_HINTS):
        return "sv"

    # 2) Backup: langdetect
    try:
        code = detect(t)
        if code in {"sv", "en", "ar"}:
            return code
    except Exception:
        pass

    # 3) Hälsnings-heuristik
    if t.startswith(("hej", "tja", "tjena")):
        return "sv"
    if t.startswith(("hello", "hi", "hey")):
        return "en"

    return fallback


# -----------------------------
# Huvud-API
# -----------------------------
def ask_chatbot(client, user_input: str, user_id: str) -> Tuple[str, str]:
    user_input = (user_input or "").strip()
    if not user_input:
        return "Please type something.", "en"

    logger.debug(f"[ask_chatbot] user_id={user_id} input_preview='{user_input[:60]}'")

    profile = load_profile(user_id)

    # Alltid använd aktuellt meddelandes språk (med fallback till profil -> en)
    language = detect_lang(user_input) or profile.get("preferred_language") or "en"
    logger.info(f"[ask_chatbot] detected_language={language}")

    # Uppdatera profil med ev. namn + preferred_language-hint
    maybe_update_profile_from_text(user_id, user_input, lang_hint=language)
    profile = load_profile(user_id)

    corrected_input = conservative_spell_fix(user_input, language)
    if corrected_input != user_input:
        logger.debug("[ask_chatbot] english spell-fix applied")

    user_mem_file = get_user_memory_file(user_id)
    user_history = load_json_list(user_mem_file)
    global_history = load_json_list(GLOBAL_MEMORY_FILE)

    # Debug: historiklängd
    logger.debug(f"[ask_chatbot] user_history_len={len(user_history)} global_history_len={len(global_history)}")
    check_history_length(user_history, max_rounds=20)

    timestamp = datetime.now(UTC).isoformat()
    user_msg = {"role": "user", "content": corrected_input, "ts": timestamp}
    user_history.append(user_msg)
    global_history.append(user_msg)

    # Systemprompt sätts utifrån detekterat aktuellt språk
    system_prompt = build_system_prompt(language, profile.get("name"))

    trimmed = global_history[-GLOBAL_MEMORY_LIMIT:] + user_history[-USER_MEMORY_LIMIT:]
    api_context = [{"role": m["role"], "content": m["content"]} for m in trimmed]
    logger.debug(f"[ask_chatbot] context_size={len(api_context)} (global_limit={GLOBAL_MEMORY_LIMIT}, user_limit={USER_MEMORY_LIMIT})")

    # Säkert anrop med mjuk fallback
    try:
        answer = call_openai(client, system_prompt, api_context)
    except Exception as e:
        logger.error(f"[ask_chatbot] call_openai failed: {e}")
        answer = fallback_message(language)

    assistant_msg = {"role": "assistant", "content": answer, "ts": datetime.now(UTC).isoformat()}
    user_history.append(assistant_msg)
    global_history.append(assistant_msg)

    try:
        save_json_list(user_mem_file, user_history)
        save_json_list(GLOBAL_MEMORY_FILE, global_history)
        logger.debug("[ask_chatbot] histories saved")
    except Exception as e:
        logger.error(f"[ask_chatbot] failed to save histories: {e}")

    return answer, language


def summarize_conversation(client, user_id: str, lang_hint: str | None = None) -> None:
    user_mem_file = get_user_memory_file(user_id)
    history = load_json_list(user_mem_file)
    if not history:
        print("No history to summarize.\n")
        logger.info("[summarize_conversation] no history found")
        return

    conversation_text = "\n".join(
        f"{'You' if msg['role']=='user' else 'Bot'}: {msg['content']}" for msg in history
    )
    logger.debug(f"[summarize_conversation] total_messages={len(history)} text_chars={len(conversation_text)}")

    profile = load_profile(user_id)

    # Ta språk från hint -> senaste user-meddelande -> profil -> en
    if lang_hint:
        lang = lang_hint
    else:
        try:
            last_user = next((h for h in reversed(history) if h.get("role") == "user"), None)
            lang = detect_lang(last_user["content"]) if last_user else (profile.get("preferred_language") or "en")
        except Exception:
            lang = profile.get("preferred_language") or "en"

    logger.info(f"[summarize_conversation] summary_language={lang}")

    if lang == "sv":
        sys = (
            "Sammanfatta konversationen kort, vänligt och mänskligt på svenska. "
            "3–5 punkter, och avsluta med en kort varm fråga."
        )
        header = "\n--- Sammanfattning av er konversation ---"
        footer = "----------------------------------------\n"
    elif lang == "ar":
        sys = (
            "لخّص المحادثة بإيجاز وبنبرة ودودة باللغة العربية. "
            "استخدم 3–5 نقاط واختم بسؤال قصير ودود."
        )
        header = "\n--- ملخص المحادثة ---"
        footer = "----------------------\n"
    else:
        sys = (
            "Summarize the conversation briefly in a warm tone. "
            "Use 3–5 bullets and end with a short friendly question."
        )
        header = "\n--- Conversation Summary ---"
        footer = "----------------------------\n"

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": f"Conversation:\n{conversation_text}"},
            ],
            max_tokens=400,
            temperature=0.4,
        )
        summary = resp.choices[0].message.content.strip()
        print(header)
        print(summary)
        print(footer)
    except Exception as e:
        logger.error(f"[summarize_conversation] OpenAI summary failed: {e}")
        # visa ett vänligt fallback-meddelande i rätt språk
        msg = {
            "sv": "Kunde inte skapa en sammanfattning just nu. Försök gärna igen strax.",
            "ar": "تعذَّر إنشاء الملخص الآن. من فضلك حاول مجددًا بعد قليل.",
            "en": "Couldn't generate the summary right now. Please try again shortly.",
        }.get(lang, "Couldn't generate the summary right now. Please try again shortly.")
        print(msg)
