from typing import List, Dict
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from debug_utils import logger

PRIMARY = "gpt-4o-mini"
BACKUP  = "gpt-4o-mini-2024-08"  # exempel – byt till en du har tillgång till

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def _once(client: OpenAI, model: str, system_prompt: str, history: List[Dict[str, str]]) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role":"system","content":system_prompt}] + history,
        temperature=0.3,
        max_tokens=800,
        timeout=30,
    )
    return resp.choices[0].message.content.strip()

def call_openai(client: OpenAI, system_prompt: str, history: List[Dict[str, str]]) -> str:
    try:
        return _once(client, PRIMARY, system_prompt, history)
    except Exception as e:
        logger and logger.warning(f"[call_openai] primary failed ({PRIMARY}), trying backup: {e}")
        return _once(client, BACKUP, system_prompt, history)
