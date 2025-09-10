# finance_api.py
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import yfinance as yf
import pandas as pd

# =============== Helpers ===============

def _human_number(x: Optional[float]) -> str:
    try:
        n = float(x)
    except Exception:
        return "-"
    for unit in ["", "K", "M", "B", "T"]:
        if abs(n) < 1000.0:
            return f"{n:.2f}{unit}"
        n /= 1000.0
    return f"{n:.2f}P"

def _pct(a: Optional[float], b: Optional[float]) -> str:
    try:
        return f"{(a - b) / b * 100:.2f}%"
    except Exception:
        return "-"

def _safe(series, idx=-1) -> Optional[float]:
    try:
        return float(series.iloc[idx])
    except Exception:
        return None

def _rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    try:
        delta = series.diff()
        gain = delta.clip(lower=0.0).rolling(period).mean()
        loss = -delta.clip(upper=0.0).rolling(period).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])
    except Exception:
        return None

def _sma(series: pd.Series, window: int) -> Optional[float]:
    try:
        return float(series.rolling(window).mean().iloc[-1])
    except Exception:
        return None

def _volatility(series: pd.Series, window: int = 30) -> Optional[float]:
    try:
        return float(series.pct_change().rolling(window).std().iloc[-1] * math.sqrt(252) * 100)
    except Exception:
        return None

# =============== Data Models ===============

@dataclass
class Quote:
    ticker: str
    name: str
    currency: str
    price: Optional[float]
    prev_close: Optional[float]
    open: Optional[float]
    day_high: Optional[float]
    day_low: Optional[float]
    volume: Optional[float]
    market_cap: Optional[float]
    change_abs: Optional[float]
    change_pct: Optional[float]
    wk52_high: Optional[float]
    wk52_low: Optional[float]
    wk52_from_high_pct: Optional[float]
    wk52_from_low_pct: Optional[float]

@dataclass
class Insight:
    ticker: str
    rsi14: Optional[float]
    sma20: Optional[float]
    sma50: Optional[float]
    sma200: Optional[float]
    sma_trend: str
    volatility_30d_pct: Optional[float]
    gap_vs_open_pct: Optional[float]
    notes: List[str]

# =============== Core fetch ===============

def _fetch_history(ticker: str) -> pd.DataFrame:
    """
    1y dagliga priser för att räkna 52v-nivåer + MA/RSI/vol.
    """
    hist = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=False)
    if hist is None or hist.empty:
        raise RuntimeError(f"Ingen historik för {ticker}")
    return hist

def _fetch_fast_meta(ticker: str) -> Dict:
    t = yf.Ticker(ticker)
    # .fast_info är snabbare och mer stabil än .info
    meta = {}
    try:
        fi = t.fast_info
        meta["currency"] = getattr(fi, "currency", "USD")
        meta["last_price"] = getattr(fi, "last_price", None)
        meta["previous_close"] = getattr(fi, "previous_close", None)
        meta["open"] = getattr(fi, "open", None)
        meta["day_high"] = getattr(fi, "day_high", None)
        meta["day_low"] = getattr(fi, "day_low", None)
        meta["market_cap"] = getattr(fi, "market_cap", None)
        meta["last_volume"] = getattr(fi, "last_volume", None)
    except Exception:
        pass
    # shortName kan saknas i fast_info → hämta från .info men hantera fel
    try:
        info = t.info
        meta["name"] = info.get("shortName") or info.get("longName") or ticker
        meta["currency"] = meta.get("currency") or info.get("currency") or "USD"
        meta["market_cap"] = meta.get("market_cap") or info.get("marketCap")
    except Exception:
        meta["name"] = ticker
    return meta

def get_quote(ticker: str) -> Quote:
    hist = _fetch_history(ticker)
    meta = _fetch_fast_meta(ticker)

    close = hist["Close"]
    wk52_high = float(close.rolling(252, min_periods=60).max().iloc[-1])
    wk52_low  = float(close.rolling(252, min_periods=60).min().iloc[-1])

    price = meta.get("last_price") or _safe(close, -1)
    prev_close = meta.get("previous_close") or _safe(close, -2)
    change_abs = (price - prev_close) if (price is not None and prev_close is not None) else None
    change_pct = (change_abs / prev_close * 100) if (change_abs is not None and prev_close) else None

    return Quote(
        ticker=ticker.upper(),
        name=meta.get("name", ticker.upper()),
        currency=meta.get("currency", "USD"),
        price=price,
        prev_close=prev_close,
        open=meta.get("open"),
        day_high=meta.get("day_high"),
        day_low=meta.get("day_low"),
        volume=meta.get("last_volume"),
        market_cap=meta.get("market_cap"),
        change_abs=change_abs,
        change_pct=change_pct,
        wk52_high=wk52_high,
        wk52_low=wk52_low,
        wk52_from_high_pct=((price - wk52_high) / wk52_high * 100) if (price and wk52_high) else None,
        wk52_from_low_pct=((price - wk52_low) / wk52_low * 100) if (price and wk52_low) else None,
    )

def get_insights(ticker: str) -> Insight:
    hist = _fetch_history(ticker)
    close = hist["Close"]

    rsi14 = _rsi(close, 14)
    sma20 = _sma(close, 20)
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    vol30 = _volatility(close, 30)

    # Gap vs dagens open
    try:
        today_open = float(hist["Open"].iloc[-1])
        today_close = float(hist["Close"].iloc[-1])
        gap = (today_close - today_open) / today_open * 100
    except Exception:
        gap = None

    notes: List[str] = []
    # RSI-regler
    if rsi14 is not None:
        if rsi14 > 70:
            notes.append("RSI>70 (överköpt)")
        elif rsi14 < 30:
            notes.append("RSI<30 (översåld)")
    # SMA-korsningar / trend
    trend = "-"
    if all(x is not None for x in [sma20, sma50, sma200]):
        if sma20 > sma50 > sma200:
            trend = "Stark upptrend (20>50>200)"
        elif sma20 < sma50 < sma200:
            trend = "Nedtrend (20<50<200)"
        else:
            trend = "Blandad trend"
        # färska korsningar (senaste 3 dagar)
        s20 = close.rolling(20).mean()
        s50 = close.rolling(50).mean()
        cross = s20 - s50
        if len(cross.dropna()) >= 3:
            last3 = cross.dropna().iloc[-3:]
            if last3.iloc[-2] < 0 and last3.iloc[-1] > 0:
                notes.append("Gyllene kors (20 över 50) nyligen")
            if last3.iloc[-2] > 0 and last3.iloc[-1] < 0:
                notes.append("Dödskors (20 under 50) nyligen")

    return Insight(
        ticker=ticker.upper(),
        rsi14=rsi14,
        sma20=sma20,
        sma50=sma50,
        sma200=sma200,
        sma_trend=trend,
        volatility_30d_pct=vol30,
        gap_vs_open_pct=gap,
        notes=notes,
    )

# =============== Public API ===============

def format_quote(q: Quote) -> str:
    return (
        f"{q.name} ({q.ticker})\n"
        f"  Price: {q.price:.2f} {q.currency}   Change: "
        f"{(q.change_abs or 0):+.2f} ({q.change_pct or 0:.2f}%)\n"
        f"  Open: {q.open if q.open is not None else '-'}   "
        f"High/Low: {q.day_high}/{q.day_low}\n"
        f"  Volume: {_human_number(q.volume)}   "
        f"Market Cap: {_human_number(q.market_cap)}\n"
        f"  52w High/Low: {q.wk52_high:.2f}/{q.wk52_low:.2f}   "
        f"From High: {(q.wk52_from_high_pct or 0):.2f}%   From Low: {(q.wk52_from_low_pct or 0):.2f}%"
    )

def format_insight(ins: Insight) -> str:
    notes = ("; ".join(ins.notes)) if ins.notes else "-"
    return (
        f"Insights for {ins.ticker}\n"
        f"  RSI(14): {ins.rsi14:.1f}   "
        f"SMA20/50/200: "
        f"{'-' if ins.sma20 is None else f'{ins.sma20:.2f}'} / "
        f"{'-' if ins.sma50 is None else f'{ins.sma50:.2f}'} / "
        f"{'-' if ins.sma200 is None else f'{ins.sma200:.2f}'}\n"
        f"  Trend: {ins.sma_trend}   "
        f"Volatility (30d, annualized): "
        f"{'-' if ins.volatility_30d_pct is None else f'{ins.volatility_30d_pct:.2f}%'}\n"
        f"  Gap vs Open (today): {'-' if ins.gap_vs_open_pct is None else f'{ins.gap_vs_open_pct:.2f}%'}\n"
        f"  Notes: {notes}"
    )

def get_stock_report(tickers: List[str]) -> str:
    lines: List[str] = []
    for t in tickers:
        try:
            q = get_quote(t)
            lines.append(format_quote(q))
        except Exception as e:
            lines.append(f"{t.upper()}: kunde inte hämta quote – {e}")
        try:
            ins = get_insights(t)
            lines.append(format_insight(ins))
        except Exception as e:
            lines.append(f"{t.upper()}: kunde inte räkna insights – {e}")
        lines.append("")  # tom rad mellan tickers
    return "\n".join(lines).strip()

# --- EXTRA: Naturligt språk → tickers, stavfel, och signaler ---
from rapidfuzz import process, fuzz
import re

# Baslista med alias (bygg på efter hand)
_ALIAS_TO_TICKER = {
    # USA
    "tesla": "TSLA",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "oracle": "ORCL",
    "adobe": "ADBE",

    # Sverige .ST (B-aktier)
    "volvo": "VOLV-B.ST",
    "volvob": "VOLV-B.ST",
    "ericsson": "ERIC-B.ST",
    "ericson": "ERIC-B.ST",
    "eric-b": "ERIC-B.ST",
    "astra": "AZN",            # LSE/US ADR; vill du .ST, byt till "AZN.ST"
    "astrazeneca": "AZN",
    "h&m": "HM-B.ST",
    "hm": "HM-B.ST",
    "sandvik": "SAND.ST",
    "atlas copco": "ATCO-B.ST",
    "atlas": "ATCO-B.ST",
    "evolution": "EVO.ST",
}

# Om användaren skriver “ERIC-B” eller “VOLV-B” utan .ST, försök lösa till .ST
_STOCKHOLM_SUFFIX_CANDIDATES = {"VOLV-A", "VOLV-B", "ERIC-A", "ERIC-B", "HM-B", "SAND", "ATCO-A", "ATCO-B", "EVO"}
_ST_SUFFIX = ".ST"

_WORDS_RX = re.compile(r"[A-Za-zÅÄÖåäö\-\.]+")

def _normalize_company_text(text: str) -> str:
    return " ".join(_WORDS_RX.findall((text or "").lower()))

def _maybe_append_st(ticker: str) -> str:
    t = ticker.upper()
    if t in _STOCKHOLM_SUFFIX_CANDIDATES and not t.endswith(".ST"):
        return t + _ST_SUFFIX
    return t

def resolve_tickers_from_text(text: str, limit: int = 3) -> list[str]:
    """
    Försök hitta tickers från fritt skriven text.
    - Matcha direkta tickers (TSLA, AAPL, VOLV-B)
    - Fuzzy-matcha företagsnamn mot _ALIAS_TO_TICKER
    - Lägg .ST för vanliga svenska tickers om saknas
    """
    t = _normalize_company_text(text)

    # 1) Plocka ut rena ticker-liknande tokens
    found = set()
    for token in t.split():
        up = token.upper()
        if re.fullmatch(r"[A-Z]{1,5}(\-[A-Z])?(\.[A-Z]{2,4})?", up):
            found.add(_maybe_append_st(up))

    # 2) Fuzzy på alias-lista
    choices = list(_ALIAS_TO_TICKER.keys())
    matches = process.extract(
        t, choices, scorer=fuzz.WRatio, limit=limit, score_cutoff=80
    )
    for match_name, score, _ in matches:
        found.add(_ALIAS_TO_TICKER[match_name])

    # 3) Extra heuristik: ord som exakt finns i alias
    for w in t.split():
        if w in _ALIAS_TO_TICKER:
            found.add(_ALIAS_TO_TICKER[w])

    # 4) Normalisera svenska suffix
    normalized = [_maybe_append_st(x) for x in found]
    # Liten safety: om både VOLV-A.ST och VOLV-B.ST dyker upp pga text – behåll alla.
    return list(dict.fromkeys(normalized))[:limit]


def analyze_signals(q: Quote, ins: Insight) -> list[str]:
    """
    Skapa enkla läsbara signaler.
    """
    s = []

    # RSI
    if ins.rsi14 is not None:
        if ins.rsi14 > 70:
            s.append("ÖVERKÖPT (RSI>70)")
        elif ins.rsi14 < 30:
            s.append("ÖVERSÅLD (RSI<30)")
        else:
            s.append(f"RSI neutral ({ins.rsi14:.0f})")

    # Avstånd till 52v high/low
    if q.price and q.wk52_high:
        dist_hi = (q.price - q.wk52_high) / q.wk52_high * 100
        s.append(f"{dist_hi:.1f}% från 52v high")
    if q.price and q.wk52_low:
        dist_lo = (q.price - q.wk52_low) / q.wk52_low * 100
        s.append(f"{dist_lo:.1f}% över 52v low")

    # Trend
    if ins.sma_trend and ins.sma_trend != "-":
        s.append(ins.sma_trend)

    # Vol
    if ins.volatility_30d_pct is not None:
        s.append(f"Vol 30d: {ins.volatility_30d_pct:.1f}% (annualiserad)")

    # Dagens gap
    if ins.gap_vs_open_pct is not None:
        s.append(f"Gap vs open: {ins.gap_vs_open_pct:+.2f}%")

    return s


def format_quick_compare(q: Quote) -> str:
    """
    Kort jämförelse idag vs igår (pris / prev close).
    """
    price = q.price
    prev = q.prev_close
    if price is None or prev is None:
        return "Jämförelse idag/igår: -"
    diff = price - prev
    pct = diff / prev * 100 if prev else 0.0
    return f"Idag {price:.2f} vs igår {prev:.2f} ({diff:+.2f}, {pct:+.2f}%)"


def get_freeform_stock_report(text: str) -> str:
    """
    Ta fritt skriven fråga (sv/eng), lös tickers, och returnera en läsbar rapport
    med pris, jämförelse, och signaler.
    """
    tickers = resolve_tickers_from_text(text, limit=3)
    if not tickers:
        return "Hittade inga bolag i din fråga. Prova t.ex. 'pris på tesla idag' eller 'apple igår vs idag'."

    lines = []
    for t in tickers:
        try:
            q = get_quote(t)
            ins = get_insights(t)
            sigs = "; ".join(analyze_signals(q, ins)) or "-"
            lines.append(
                f"{format_quote(q)}\n"
                f"  {format_quick_compare(q)}\n"
                f"  Signaler: {sigs}\n"
                f"{format_insight(ins)}"
            )
        except Exception as e:
            lines.append(f"{t}: kunde inte hämta – {e}")
        lines.append("")  # tom rad
    return "\n".join(lines).strip()

