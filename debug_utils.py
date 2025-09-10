import logging
import os
import time
from functools import wraps

# ---- LOGGING ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log", encoding="utf-8"),
        # logging.StreamHandler()  # 👈 om du vill se i terminal också
    ]
)
logger = logging.getLogger("chatbot-debug")

# ---- API KEY CHECK ----
def check_api_key():
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        logger.error("❌ OPENAI_API_KEY saknas!")
        return False
    if not (key.startswith("sk-") or key.startswith("sk-proj-")):
        logger.warning(f"⚠️ API-nyckeln ser konstig ut: {key[:8]}...")
    logger.info(f"🔑 API key prefix: {key[:8]}... (len={len(key)})")
    return True

# ---- RETRY DECORATOR (med exponentiell backoff) ----
def retry_on_fail(max_retries: int = 3, delay: float = 2.0,
                  backoff_base: float = 1.5, max_backoff: float = 30.0):
    """
    Wrappar en funktion med retry-logik + exponentiell backoff.
    - max_retries: antal försök (inkl första körningen räknas separat i loopen)
    - delay: startfördröjning i sekunder inför nästa försök
    - backoff_base: multipliceras på delay efter varje misslyckande (ex 1.6)
    - max_backoff: tak för delay
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            current_delay = float(delay)
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    # logga och vänta innan nästa försök om det finns fler försök kvar
                    if i < max_retries - 1:
                        logger.warning(
                            f"⚠️ Error: {e} (försök {i+1}/{max_retries}), väntar {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        # exponentiell backoff (begränsa till max_backoff)
                        current_delay = min(current_delay * backoff_base, max_backoff)
                    else:
                        logger.error("❌ Alla försök misslyckades!")
                        raise last_err
        return wrapper
    return decorator

# ---- TOKEN / HISTORIK KOLL ----
def check_history_length(history, max_rounds=20):
    if len(history) > max_rounds * 2:
        logger.warning(f"⚠️ Historiken är lång ({len(history)} meddelanden). "
                       f"Överväg att sammanfatta eller trimma.")
        return False
    return True

# ---- FALLBACK-RESPONS ----
def fallback_message(lang="en"):
    texts = {
        "sv": "Oj, något gick fel när jag kontaktade modellen. Kan du prova igen?",
        "ar": "عذرًا، حدث خطأ أثناء الاتصال بالنموذج. هل يمكنك المحاولة مجددًا؟",
        "en": "Oops, something went wrong contacting the model. Please try again.",
    }
    return texts.get(lang, texts["en"])

# ---- DEBUG MODE CHECK ----
if os.getenv("DEBUG_FORCE_OPENAI_FAIL") == "1":
    logger.warning("🚨 DEBUG MODE: Alla OpenAI-anrop kommer att FEJKA fel (fallback aktiverad).")
else:
    logger.info("✅ NORMAL MODE: OpenAI-anrop körs på riktigt.")
