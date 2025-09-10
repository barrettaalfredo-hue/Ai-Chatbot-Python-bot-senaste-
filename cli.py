import os
import argparse
import uuid
from typing import Dict, Any
from getpass import getpass

from openai import OpenAI
from langdetect import detect, LangDetectException  # kvar för ev. framtida bruk

# Yahoo Finance-hjälpare
from finance_api import (
    get_stock_report,
    get_freeform_stock_report,
    resolve_tickers_from_text,
)

from utils_io import show_previous_conversation, show_full_history, clear_user_memory
from commands_feedback import detect_command, save_feedback, get_feedback_prompt, get_feedback_thanks
from memory import ask_chatbot, summarize_conversation, detect_lang  # robust språkdetektering

# ✅ Debug-stöd: importera logger om den finns (loggar skrivs till debug.log, inte terminal)
try:
    from debug_utils import logger
except Exception:
    logger = None

# Läs .env om python-dotenv finns (tyst fallback om paket saknas)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)  # låt .env override:a miljövariabler
except Exception:
    pass


# (valfri) hooks – lägg egen logik här om du vill
class ext:
    @staticmethod
    def on_startup() -> None:
        pass

    @staticmethod
    def try_handle(user_input: str, user_id: str, client):
        # return (handled, reply, lang, ask_feedback)
        return (False, None, None, False)


def _get_api_key_interactive() -> str:
    """
    Hämta API-nyckel i denna ordning:
      1) Miljövariabeln OPENAI_API_KEY (kan komma från .env eller systemet)
      2) Interaktiv prompt i terminalen (en gång för denna körning)
    """
    key = os.getenv("OPENAI_API_KEY")
    if key and key.strip():
        return key.strip()

    print("⚠️  OPENAI_API_KEY saknas i miljövariablerna/.env.")
    print("Klistra in din OpenAI-nyckel (börjar med 'sk-' eller 'sk-proj-').")
    entered = getpass("OPENAI_API_KEY: ").strip()  # maskerad input
    if not entered:
        raise RuntimeError("Ingen nyckel angiven. Sätt OPENAI_API_KEY i .env eller miljövariabler.")
    # Minimal sanity check mot vanliga misstag
    if entered.startswith("sk-sk-") or entered.startswith("sk-proj-sk-proj-"):
        raise RuntimeError("Nyckeln verkar ha dubbelt prefix (t.ex. 'sk-sk-' eller 'sk-proj-sk-proj-'). Kopiera om den från OpenAI.")
    return entered


def main():
    # ---- Argument ----
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=str, help="User ID (optional)")
    parser.add_argument("--debug", action="store_true", help="Show debug logs in terminal (vi loggar normalt till fil)")
    args = parser.parse_args()

    # ---- Debug-info (vi skriver BARA till debug.log om inget annat ställs in i debug_utils) ----
    if args.debug and logger:
        logger.info("CLI started – debug mode active (loggar skrivs till debug.log)")

    # ---- OpenAI-klient ----
    api_key = _get_api_key_interactive()
    client = OpenAI(api_key=api_key)

    user_id = args.user if args.user else f"user_{uuid.uuid4().hex[:6]}"

    print(f"🤖 AI-chatbot started! (UserID: {user_id})")
    print("Welcome!")
    print("Type 'exit' to quit.\n")

    try:
        ext.on_startup()
    except Exception:
        pass

    show_previous_conversation(user_id)

    last_answer_for_feedback: Dict[str, Any] = {"text": None, "question": None, "lang": "en"}

    # --- Samlade nyckelord för naturliga aktiefrågor (lätt att utöka) ---
    STOCK_KEYWORDS_SV = {
        "pris", "kurs", "aktie", "idag", "igår", "överpris", "överprisad",
        "rsi", "trend", "52w", "52 veckor", "volatilitet", "jämför", "jämförelse"
    }
    STOCK_KEYWORDS_EN = {
        "price", "stock", "today", "yesterday", "overpriced",
        "rsi", "trend", "52w", "volatility", "compare", "comparison"
    }
    STOCK_KEYWORDS_AR = {
        "سعر", "سهم", "اليوم", "أمس", "مبالغ", "مبالغ فيه", "rsi", "اتجاه", "تقلب", "مقارنة", "52"
    }

    # Prefix för kommandoläge
    AR_STOCK_PREFIXES = ("أسهم:", "اسهم:")

    while True:
        try:
            user_input = input("You: ")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.strip().lower() == "exit":
            break

        # låt extension försöka först
        try:
            handled, reply, lang_from_ext, ask_fb = ext.try_handle(user_input, user_id, client)
        except Exception:
            handled, reply, lang_from_ext, ask_fb = (False, None, None, False)

        if handled:
            print(f"Bot: {reply or ''}\n")
            if ask_fb:
                fb_lang = (lang_from_ext or "en")
                print(get_feedback_prompt(fb_lang))
                last_answer_for_feedback = {"text": (reply or ""), "question": user_input, "lang": fb_lang}
            else:
                last_answer_for_feedback = {"text": None, "question": None, "lang": "en"}
            continue

        # naturliga kommandon (clear/history/summary)
        cmd = detect_command(user_input)
        if cmd == "clear":
            clear_user_memory(user_id)
            continue
        if cmd == "history":
            show_full_history(user_id)
            continue
        if cmd == "summary":
            # robust språkdetektering för sammanfattning
            lang_hint = detect_lang(user_input)
            summarize_conversation(client, user_id, lang_hint=lang_hint)
            continue

        # kompatibla slash- och prefix-kommandon
        low = user_input.strip().lower()

        if low == "/clear":
            clear_user_memory(user_id)
            continue
        if low == "/history":
            show_full_history(user_id)
            continue
        if low == "/summary":
            summarize_conversation(client, user_id)
            continue

        # --- Aktier via Yahoo Finance – kommandoläge ---
        # /stock AAPL MSFT TSLA   eller   "aktier: AAPL, MSFT, TSLA"   eller   "أسهم: ..."
        if low.startswith("/stock"):
            parts = user_input.split()
            tickers = [p.strip().upper() for p in parts[1:]] or []
            if not tickers:
                print("Bot: Använd: /stock TICKER [TICKER ...]\n")
                continue
            print("Bot:\n" + get_stock_report(tickers) + "\n")
            continue

        if low.startswith("aktier:") or low.startswith("stocks:") or user_input.strip().startswith(AR_STOCK_PREFIXES):
            # stöd för svenska/engelska/arabiska prefix
            if ":" in user_input:
                tickers_part = user_input.split(":", 1)[1]
            else:
                tickers_part = ""
            tickers = [t.strip().upper().strip(",") for t in tickers_part.split()]
            if not tickers:
                print("Bot: Ange minst en ticker, t.ex. 'aktier: AAPL MSFT TSLA'\n")
                continue
            print("Bot:\n" + get_stock_report(tickers) + "\n")
            continue

        # feedback-ja/nej (språkberoende)
        low_ans = low
        if last_answer_for_feedback["text"] is not None and low_ans in {"ja", "nej", "yes", "no", "y", "n", "نعم", "لا"}:
            normalized = "ja" if low_ans in {"y", "yes", "نعم"} else ("nej" if low_ans in {"n", "no", "لا"} else low_ans)
            save_feedback(
                question=last_answer_for_feedback["question"],
                answer=last_answer_for_feedback["text"],
                helpful=normalized,
                user_id=user_id,
            )
            # använd alltid det språk som sparats tidigare
            print(get_feedback_thanks(last_answer_for_feedback.get("lang", "en")))
            last_answer_for_feedback = {"text": None, "question": None, "lang": "en"}
            continue

        # --- Naturliga aktiefrågor (sv/eng/ar), inkl. stavfel via resolver ---
        low_nospace = low.replace(" ", "")
        # Kolla om någon keyword träffar eller om resolver hittar tickers i fri text
        if (
            any(k in low for k in STOCK_KEYWORDS_SV)
            or any(k in low for k in STOCK_KEYWORDS_EN)
            or any(k in user_input for k in STOCK_KEYWORDS_AR)  # arabiska nyckelord är inte nödvändigtvis lower()
            or resolve_tickers_from_text(user_input)
        ):
            report = get_freeform_stock_report(user_input)
            print("Bot:\n" + report + "\n")
            continue

        # --- normal Q&A ---
        question = user_input
        answer, lang_detected = ask_chatbot(client, question, user_id)

        # bestäm språk baserat på senaste användarmeddelandet
        feedback_lang = detect_lang(question) or lang_detected or "en"

        print(f"Bot: {answer}\n")
        if len(answer) >= 200:
            print(get_feedback_prompt(feedback_lang))
            last_answer_for_feedback = {
                "text": answer,
                "question": question,
                "lang": feedback_lang,   # spara korrekt språk
            }
        else:
            last_answer_for_feedback = {"text": None, "question": None, "lang": "en"}

    print("Goodbye! 👋")


if __name__ == "__main__":
    main()
