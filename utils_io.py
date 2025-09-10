import os
import json
from typing import List, Dict, Any
from datetime import datetime, UTC

# paths & limits
USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

GLOBAL_MEMORY_FILE = os.path.join(USER_DATA_DIR, "chat_memory_global.json")
FEEDBACK_FILE = os.path.join(USER_DATA_DIR, "chat_feedback.json")

USER_MEMORY_LIMIT = 50
GLOBAL_MEMORY_LIMIT = 20

def get_user_memory_file(user_id: str) -> str:
    return os.path.join(USER_DATA_DIR, f"chat_memory_{user_id}.json")

def get_user_profile_file(user_id: str) -> str:
    return os.path.join(USER_DATA_DIR, f"profile_{user_id}.json")

# json helpers
def load_json_list(filename: str) -> List[Dict[str, Any]]:
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            return []
    return []

def save_json_list(filename: str, data: List[Dict[str, Any]]) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# console views
def show_previous_conversation(user_id: str) -> None:
    from profile import load_profile
    user_mem_file = get_user_memory_file(user_id)
    history = load_json_list(user_mem_file)

    profile = load_profile(user_id)
    name = profile.get("name")
    if name:
        print(f"Welcome back, {name}!\n")

    if not history:
        print("No previous conversation found.\n")
        return

    print("Previous conversation:")
    print("-" * 60)
    for msg in history:
        role = "You" if msg.get("role") == "user" else "Bot"
        ts = msg.get("ts", "")
        ts_disp = f"[{ts}] " if ts else ""
        print(f"{ts_disp}{role}: {msg.get('content','')}")
    print("-" * 60 + "\n")

def clear_user_memory(user_id: str) -> None:
    user_mem_file = get_user_memory_file(user_id)
    save_json_list(user_mem_file, [])
    print("User memory cleared!\n")

def show_full_history(user_id: str) -> None:
    user_mem_file = get_user_memory_file(user_id)
    history = load_json_list(user_mem_file)
    if not history:
        print("No history found.\n"); return
    print("Full conversation history:")
    print("-" * 60)
    for msg in history:
        role = "You" if msg["role"] == "user" else "Bot"
        ts = msg.get("ts", "")
        ts_disp = f"[{ts}] " if ts else ""
        print(f"{ts_disp}{role}: {msg['content']}")
    print("-" * 60 + "\n")

# conservative EN spell-fix
try:
    from spellchecker import SpellChecker  # pyspellchecker
    _HAS_SPELL = True
except Exception:
    _HAS_SPELL = False

def conservative_spell_fix(text: str, language: str) -> str:
    if not _HAS_SPELL or language != "en":
        return text
    sp = SpellChecker(language="en")
    fixed = []
    for tok in text.split():
        if tok.isalpha() and len(tok) > 2 and tok.lower() not in sp:
            fixed.append(sp.correction(tok) or tok)
        else:
            fixed.append(tok)
    return " ".join(fixed)
