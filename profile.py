import json, re
from typing import Dict, Any, List
from datetime import datetime, UTC
from utils_io import get_user_profile_file

_NAME_PATTERNS: List[str] = [
    r"\bjag heter\s+([A-ZÅÄÖ][a-zA-ZÅÄÖåäö\-]+)\b",
    r"\bmitt namn är\s+([A-ZÅÄÖ][a-zA-ZÅÄÖåäö\-]+)\b",
    r"\bmy name is\s+([A-Z][a-zA-Z\-]+)\b",
    r"\bi am\s+([A-Z][a-zA-Z\-]+)\b",
    r"\bI'm\s+([A-Z][a-zA-Z\-]+)\b",
    r"\bاسمي\s+([^\s]+)\b",
]

def load_profile(user_id: str) -> Dict[str, Any]:
    p = get_user_profile_file(user_id)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"name": None, "preferred_language": None, "created_at": datetime.now(UTC).isoformat()}

def save_profile(user_id: str, profile: Dict[str, Any]) -> None:
    p = get_user_profile_file(user_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

def maybe_update_profile_from_text(user_id: str, text: str, lang_hint: str | None = None) -> None:
    profile = load_profile(user_id)
    if not profile.get("preferred_language"):
        profile["preferred_language"] = lang_hint or "en"
    for pat in _NAME_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            profile["name"] = m.group(1)
            break
    save_profile(user_id, profile)
