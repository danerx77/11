"""
krs_downloader.py – automatyczne wyszukiwanie KRS/NIP po nazwie firmy
oraz pobieranie danych odpisu KRS.

Ważna zmiana względem poprzedniej wersji:
- oficjalne Open API KRS Ministerstwa Sprawiedliwości zwraca JSON, a nie PDF;
- endpoint `.../OdpisAktualny/{krs}?rejestr=P&format=pdf` często zwraca 400/403;
- dlatego program najpierw próbuje pobrać prawdziwy PDF ze starego/nieudokumentowanego
  endpointu, a jeśli się nie uda, pobiera oficjalny JSON z `api-krs.ms.gov.pl`
  i generuje lokalny PDF-techniczny z tych danych.

Lokalnie wygenerowany PDF NIE jest oryginalnym urzędowym PDF-em z identyfikatorem
wydruku MS. Do czynności wymagających urzędowego odpisu pobierz dokument ręcznie
z https://wyszukiwarka-krs.ms.gov.pl/ albo użyj oficjalnie udostępnionej usługi,
jeżeli MS udostępni dla Twojego przypadku endpoint PDF.
"""

from __future__ import annotations

import html
import json
import logging
import os
import random
import re
import string
import threading
import time
import unicodedata
import webbrowser
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QGroupBox, QSplitter,
    QHeaderView, QTextEdit, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QMarginsF
from PySide6.QtGui import QColor, QDesktopServices

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


# -----------------------------------------------------------------------------
# Logowanie
# -----------------------------------------------------------------------------
LOG_FILE = Path(__file__).parent.parent / "dane" / "krs_logs.txt"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("KRS_Downloader")
logger.setLevel(logging.DEBUG)

# Bez tej osłony przy ponownym importowaniu modułu logi dublują się po kilka razy.
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(LOG_FILE) for h in logger.handlers):
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(fh)


API_KRS_BASE = "https://api-krs.ms.gov.pl/api/krs"
KRS_POBIERZ_SEARCH = "https://krs-pobierz.pl/szukaj"
MS_KRS_HOME = "https://wyszukiwarka-krs.ms.gov.pl/"
MS_KRS_PDF_BASE = "https://wyszukiwarka-krs.ms.gov.pl/api/krs"

# Strona MS potrafi blokować automaty i źle znosi kilka równoległych sesji.
# Dlatego pobieranie PDF przez realną przeglądarkę robimy pojedynczo.
_PLAYWRIGHT_DOWNLOAD_LOCK = threading.Lock()

PLAYWRIGHT_SPEED_SETTINGS = {
    # szybka: minimalne pauzy; dobra, gdy strona MS działa stabilnie
    "fast": {
        "label": "Szybka",
        "default_timeout_ms": 20000,
        "type_delay_ms": 0,
        "slow_mo_ms": 0,
        "after_search_wait_ms": 700,
        "after_details_wait_ms": 500,
        "after_pdf_click_wait_ms": 1200,
    },
    # normalna: kompromis – domyślne ustawienie
    "normal": {
        "label": "Normalna",
        "default_timeout_ms": 30000,
        "type_delay_ms": 20,
        "slow_mo_ms": 0,
        "after_search_wait_ms": 1500,
        "after_details_wait_ms": 1000,
        "after_pdf_click_wait_ms": 3000,
    },
    # wolna: większe pauzy dla słabszego internetu / wolnego Angulara MS
    "slow": {
        "label": "Wolna / stabilna",
        "default_timeout_ms": 60000,
        "type_delay_ms": 70,
        "slow_mo_ms": 120,
        "after_search_wait_ms": 3000,
        "after_details_wait_ms": 2000,
        "after_pdf_click_wait_ms": 5000,
    },
}


def _playwright_speed_settings(speed_mode: str) -> dict[str, int | str]:
    return PLAYWRIGHT_SPEED_SETTINGS.get(speed_mode, PLAYWRIGHT_SPEED_SETTINGS["normal"])


# -----------------------------------------------------------------------------
# Normalizacja i dopasowanie nazw
# -----------------------------------------------------------------------------
LEGAL_PATTERNS = [
    r"\bSPÓŁKA\s+Z\s+OGRANICZONĄ\s+ODPOWIEDZIALNOŚCIĄ\b",
    r"\bSPOLKA\s+Z\s+OGRANICZONA\s+ODPOWIEDZIALNOSCIA\b",
    r"\bSPÓŁKA\s+KOMANDYTOWO\s+AKCYJNA\b",
    r"\bSPOLKA\s+KOMANDYTOWO\s+AKCYJNA\b",
    r"\bSPÓŁKA\s+KOMANDYTOWA\b",
    r"\bSPOLKA\s+KOMANDYTOWA\b",
    r"\bSPÓŁKA\s+AKCYJNA\b",
    r"\bSPOLKA\s+AKCYJNA\b",
    r"\bPROSTA\s+SPÓŁKA\s+AKCYJNA\b",
    r"\bPROSTA\s+SPOLKA\s+AKCYJNA\b",
    r"\bSPÓŁKA\s+JAWNA\b",
    r"\bSPOLKA\s+JAWNA\b",
    r"\bSPÓŁKA\s+PARTNERSKA\b",
    r"\bSPOLKA\s+PARTNERSKA\b",
    r"\bSPÓŁKA\s+CYWILNA\b",
    r"\bSPOLKA\s+CYWILNA\b",
    r"\bSP\.?\s*Z\s*O\.?\s*O\.?\b",
    r"\bSP\.?\s*K\.?\b",
    r"\bS\.?\s*K\.?\s*A\.?\b",
    r"\bP\.?\s*S\.?\s*A\.?\b",
    r"\bS\.?\s*A\.?\b",
    r"\bS\.?\s*J\.?\b",
    r"\bS\.?\s*C\.?\b",
    r"\bW\s+LIKWIDACJI\b",
    r"\bW\s+UPADŁOŚCI\b",
    r"\bW\s+UPADLOSCI\b",
]


def _find_browser_executable(browser_mode: str) -> str:
    """Zwraca ścieżkę do Opery/Firefoksa, jeśli są zainstalowane."""
    import os
    import shutil
    candidates = []
    if browser_mode == "opera":
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Opera", "opera.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Opera GX", "opera.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Opera", "opera.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Opera", "launcher.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Opera", "opera.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Opera", "launcher.exe"),
            shutil.which("opera") or "",
            shutil.which("opera.exe") or "",
        ]
    elif browser_mode == "firefox":
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Mozilla Firefox", "firefox.exe"),
            shutil.which("firefox") or "",
            shutil.which("firefox.exe") or "",
        ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return ""


def _strip_accents(text: str) -> str:
    """Zamienia ąęłńóśźż na odpowiedniki ASCII do porównań."""
    text = str(text or "")
    # Ł/ł nie rozkłada się dobrze przez NFKD, więc obsługujemy ręcznie.
    text = text.replace("Ł", "L").replace("ł", "l")
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def clean_company_name(name: str) -> str:
    """Usuwa przyrostki prawne z nazwy, by ułatwić wyszukiwanie."""
    cleaned = html.unescape(str(name or "")).strip()
    cleaned = re.sub(r"[\"'„”‚’`]+", " ", cleaned)

    for phrase in LEGAL_PATTERNS:
        cleaned = re.sub(phrase, " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"[,.;:/\\\-\s]+$", "", cleaned).strip()
    return cleaned


def _norm_for_match(name: str) -> str:
    text = clean_company_name(name)
    text = _strip_accents(text).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens_for_match(name: str) -> list[str]:
    return [t for t in _norm_for_match(name).split() if len(t) >= 2]


def _name_score(query_name: str, candidate_name: str) -> float:
    """
    Wynik 0..1. Stosujemy konserwatywne dopasowanie: wszystkie istotne tokeny
    szukanej nazwy powinny pojawić się w kandydacie. Dzięki temu nie bierzemy
    pierwszego lepszego NIP/KRS ze strony.
    """
    q_norm = _norm_for_match(query_name)
    c_norm = _norm_for_match(candidate_name)
    if not q_norm or not c_norm:
        return 0.0

    q_tokens = _tokens_for_match(query_name)
    c_tokens = set(_tokens_for_match(candidate_name))
    if not q_tokens:
        return 0.0

    matched = sum(1 for t in q_tokens if t in c_tokens)
    token_ratio = matched / len(q_tokens)

    # Jeśli nazwa ma kilka słów, a brakuje choć jednego, odrzucamy agresywnie.
    if len(q_tokens) >= 2 and token_ratio < 1.0:
        return min(0.49, token_ratio)

    # Przy nazwie jednowyrazowej dopuszczamy tylko pełny token, nie fragment.
    if len(q_tokens) == 1 and token_ratio < 1.0:
        return 0.0

    seq = SequenceMatcher(None, q_norm, c_norm).ratio()

    if c_norm == q_norm:
        return 1.0
    if c_norm.startswith(q_norm + " ") or q_norm.startswith(c_norm + " "):
        return max(0.95, seq)

    return max(seq, token_ratio * 0.9)


def _remove_tags(fragment: str) -> str:
    fragment = re.sub(r"<script.*?</script>", " ", fragment, flags=re.I | re.S)
    fragment = re.sub(r"<style.*?</style>", " ", fragment, flags=re.I | re.S)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    return re.sub(r"\s+", " ", fragment).strip()


def _only_digits(value: Any, max_len: Optional[int] = None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if max_len:
        digits = digits[:max_len]
    return digits


def normalize_krs(krs: str) -> str:
    digits = _only_digits(krs, 10)
    return digits.zfill(10) if digits else ""


def normalize_nip(nip: str) -> str:
    digits = _only_digits(nip, 10)
    return digits if len(digits) == 10 else ""


def is_valid_nip(nip: str) -> bool:
    """Walidacja sumy kontrolnej NIP. Nie blokuje wyszukiwania, ale pomaga odsiać śmieci."""
    nip = normalize_nip(nip)
    if len(nip) != 10:
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    checksum = sum(int(nip[i]) * weights[i] for i in range(9)) % 11
    return checksum != 10 and checksum == int(nip[9])


# -----------------------------------------------------------------------------
# Pobieranie i parsowanie danych KRS
# -----------------------------------------------------------------------------
@dataclass
class KrsSearchCandidate:
    name: str
    krs: str
    nip: str = ""
    url: str = ""
    source: str = ""
    score: float = 0.0


def _extract_first_json_value(data: Any, key_name: str) -> str:
    """Rekurencyjnie znajduje pierwszą wartość dla klucza o podanej nazwie."""
    if isinstance(data, dict):
        for k, v in data.items():
            if str(k).lower() == key_name.lower() and v not in (None, ""):
                return str(v)
        for v in data.values():
            found = _extract_first_json_value(v, key_name)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _extract_first_json_value(item, key_name)
            if found:
                return found
    return ""


def extract_basic_from_krs_json(data: dict[str, Any]) -> dict[str, str]:
    """Wyciąga podstawowe dane z odpowiedzi Open API KRS."""
    odpis = data.get("odpis", {}) if isinstance(data, dict) else {}
    naglowek = odpis.get("naglowekA", {}) if isinstance(odpis, dict) else {}
    dane = odpis.get("dane", {}) if isinstance(odpis, dict) else {}
    dzial1 = dane.get("dzial1", {}) if isinstance(dane, dict) else {}
    dane_podmiotu = dzial1.get("danePodmiotu", {}) if isinstance(dzial1, dict) else {}
    ident = dane_podmiotu.get("identyfikatory", {}) if isinstance(dane_podmiotu, dict) else {}

    return {
        "krs": normalize_krs(naglowek.get("numerKRS") or _extract_first_json_value(data, "numerKRS")),
        "nip": normalize_nip(ident.get("nip") or _extract_first_json_value(data, "nip")),
        "regon": _only_digits(ident.get("regon") or _extract_first_json_value(data, "regon")),
        "name": str(dane_podmiotu.get("nazwa") or _extract_first_json_value(data, "nazwa") or ""),
        "rejestr": str(naglowek.get("rejestr") or ""),
        "data": str(naglowek.get("dataCzasOdpisu") or ""),
    }


def fetch_krs_json(krs: str, session: Optional["requests.Session"] = None) -> tuple[Optional[dict[str, Any]], str, str]:
    """
    Pobiera oficjalny JSON z api-krs.ms.gov.pl.
    Zwraca: (json, rejestr 'P'/'S', komunikat). Próbuje P i S.
    """
    if not requests:
        return None, "", "Brak biblioteki requests."

    krs = normalize_krs(krs)
    sess = session or requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    last_msg = ""
    for rejestr in ("P", "S"):
        url = f"{API_KRS_BASE}/OdpisAktualny/{krs}?rejestr={rejestr}&format=json"
        try:
            resp = sess.get(url, headers=headers, timeout=20)
        except Exception as exc:
            last_msg = f"Błąd sieci dla rejestru {rejestr}: {exc}"
            continue

        if resp.status_code == 200:
            try:
                return resp.json(), rejestr, f"OK, rejestr {rejestr}"
            except Exception as exc:
                last_msg = f"Niepoprawny JSON dla rejestru {rejestr}: {exc}"
        elif resp.status_code == 404:
            last_msg = f"Brak podmiotu w rejestrze {rejestr}."
        else:
            last_msg = f"Open API KRS: HTTP {resp.status_code} dla rejestru {rejestr}: {resp.text[:200]}"

    return None, "", last_msg or "Nie znaleziono podmiotu w Open API KRS."


def _parse_krs_pobierz_company_page(raw_html: str, raw_name: str, url: str = "") -> Optional[KrsSearchCandidate]:
    text = _remove_tags(raw_html)

    # Najczęściej NIP/KRS są w meta description: "NIP ... | KRS ... | REGON ...".
    krs_match = re.search(r"\bKRS\s*[: ]\s*(000\d{7})\b", text, re.I)
    nip_match = re.search(r"\bNIP\s*[: ]\s*(\d{10})\b", text, re.I)

    # Nazwa bywa w H1 albo w tytule strony.
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", raw_html, re.I | re.S)
    title = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.I | re.S)
    candidate_name = _remove_tags(h1.group(1)) if h1 else ""
    if not candidate_name and title:
        candidate_name = _remove_tags(title.group(1)).split("|")[0].strip()

    if not candidate_name:
        # Awaryjnie spróbuj z og:title.
        og_title = re.search(r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']", raw_html, re.I)
        if og_title:
            candidate_name = html.unescape(og_title.group(1)).split("|")[0].strip()

    if krs_match:
        krs = normalize_krs(krs_match.group(1))
        nip = normalize_nip(nip_match.group(1) if nip_match else "")
        score = _name_score(raw_name, candidate_name or raw_name)
        return KrsSearchCandidate(
            name=candidate_name or raw_name,
            krs=krs,
            nip=nip,
            url=url,
            source="krs-pobierz.pl",
            score=score,
        )
    return None


def search_krs_pobierz(raw_name: str) -> list[KrsSearchCandidate]:
    """Szuka po nazwie w krs-pobierz.pl i zwraca przefiltrowane kandydatury."""
    if not requests:
        return []

    clean_name = clean_company_name(raw_name)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        resp = requests.get(KRS_POBIERZ_SEARCH, params={"q": clean_name}, headers=headers, timeout=15)
    except Exception as exc:
        logger.warning("KRS-Pobierz search error for %s: %s", raw_name, exc)
        return []

    if resp.status_code != 200:
        logger.warning("KRS-Pobierz returned HTTP %s for %s", resp.status_code, raw_name)
        return []

    raw = resp.text
    candidates: list[KrsSearchCandidate] = []

    # Jeśli wyszukiwarka przekierowała od razu na stronę podmiotu.
    if "/szukaj" not in resp.url:
        direct = _parse_krs_pobierz_company_page(raw, raw_name, resp.url)
        if direct:
            candidates.append(direct)

    # Lista wyników: każdy kafelek zawiera h4/a, KRS, NIP.
    blocks = re.findall(
        r"<div\s+class=[\"']col-9[\"'][^>]*>\s*(.*?)\s*<hr\s*/?>",
        raw,
        flags=re.I | re.S,
    )

    for block in blocks:
        name_match = re.search(r"<h4[^>]*>\s*<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>\s*</h4>", block, re.I | re.S)
        if not name_match:
            continue
        url = html.unescape(name_match.group(1))
        candidate_name = _remove_tags(name_match.group(2))
        block_text = _remove_tags(block)
        krs_match = re.search(r"\bKRS\s*[: ]\s*(000\d{7})\b", block_text, re.I)
        nip_match = re.search(r"\bNIP\s*[: ]\s*(\d{10})\b", block_text, re.I)
        if not krs_match:
            continue
        krs = normalize_krs(krs_match.group(1))
        nip = normalize_nip(nip_match.group(1) if nip_match else "")
        score = _name_score(raw_name, candidate_name)
        if score >= 0.72:
            candidates.append(KrsSearchCandidate(
                name=candidate_name,
                krs=krs,
                nip=nip,
                url=url,
                source="krs-pobierz.pl",
                score=score,
            ))

    # Usuwanie duplikatów po KRS.
    unique: dict[str, KrsSearchCandidate] = {}
    for c in candidates:
        if c.krs and (c.krs not in unique or c.score > unique[c.krs].score):
            unique[c.krs] = c

    return sorted(unique.values(), key=lambda c: c.score, reverse=True)


def search_duckduckgo_precise(raw_name: str) -> list[KrsSearchCandidate]:
    """
    Ostateczny fallback. Parsujemy tylko wyniki zawierające jednocześnie nazwę, KRS i NIP.
    Nie bierzemy przypadkowych liczb ze stopki/reklam.
    """
    if not requests:
        return []

    clean_name = clean_company_name(raw_name)
    query = f'"{clean_name}" "KRS" "NIP"'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=headers,
            timeout=15,
        )
    except Exception as exc:
        logger.warning("DuckDuckGo search error for %s: %s", raw_name, exc)
        return []

    if resp.status_code != 200:
        return []

    # Wyniki DDG są w blokach result. Interesuje nas blok, który ma nazwę i oba numery.
    candidates: list[KrsSearchCandidate] = []
    blocks = re.findall(r"<div[^>]+class=[\"'][^\"']*result[^\"']*[\"'][^>]*>(.*?)</div>\s*</div>", resp.text, re.I | re.S)
    if not blocks:
        blocks = re.split(r"result__title", resp.text, flags=re.I)

    for block in blocks[:10]:
        text = _remove_tags(block)
        if _name_score(raw_name, text) < 0.72:
            continue
        krs_match = re.search(r"\bKRS\s*[: ]\s*(000\d{7})\b", text, re.I)
        nip_match = re.search(r"\bNIP\s*[: ]\s*(\d{10})\b", text, re.I)
        if not krs_match:
            continue
        nip = normalize_nip(nip_match.group(1) if nip_match else "")
        if nip and not is_valid_nip(nip):
            # Nie odrzucamy kandydata całkowicie, bo NIP potwierdzimy z Open API,
            # ale nie zapisujemy podejrzanego NIP-u.
            nip = ""
        candidates.append(KrsSearchCandidate(
            name=clean_name,
            krs=normalize_krs(krs_match.group(1)),
            nip=nip,
            source="DuckDuckGo",
            score=_name_score(raw_name, text),
        ))

    unique: dict[str, KrsSearchCandidate] = {}
    for c in candidates:
        if c.krs and (c.krs not in unique or c.score > unique[c.krs].score):
            unique[c.krs] = c
    return sorted(unique.values(), key=lambda c: c.score, reverse=True)


def find_krs_and_nip_by_name(raw_name: str, existing_krs: str = "") -> tuple[str, str, str]:
    """
    Główna procedura wyszukiwania.
    Zwraca: (krs, nip, message)
    """
    if not requests:
        return "", "", "Brak biblioteki requests. Zainstaluj: pip install requests"

    clean_name = clean_company_name(raw_name)
    if len(clean_name) < 3 and not existing_krs:
        return "", "", "Nazwa za krótka."

    # Jeśli KRS już jest w tabeli, nie szukamy po Internecie – pobieramy NIP z Open API.
    if existing_krs:
        krs = normalize_krs(existing_krs)
        data, rejestr, msg = fetch_krs_json(krs)
        if data:
            basic = extract_basic_from_krs_json(data)
            return basic.get("krs") or krs, basic.get("nip") or "", f"✅ Dane potwierdzone w Open API KRS ({rejestr})."
        return krs, "", f"⚠️ Nie udało się potwierdzić KRS w Open API: {msg}"

    candidates = search_krs_pobierz(raw_name)
    if not candidates:
        candidates = search_duckduckgo_precise(raw_name)

    if not candidates:
        return "", "", f"❌ Nie znaleziono wiarygodnego dopasowania dla: {clean_name}"

    # Bierzemy najlepszego kandydata, ale zawsze potwierdzamy przez Open API KRS.
    best = candidates[0]
    if best.score < 0.72:
        return "", "", f"❌ Zbyt słabe dopasowanie ({best.score:.2f}) dla: {clean_name}"

    data, rejestr, api_msg = fetch_krs_json(best.krs)
    if data:
        basic = extract_basic_from_krs_json(data)
        official_name = basic.get("name", "")
        verify_score = _name_score(raw_name, official_name or best.name)
        if verify_score < 0.70:
            return "", "", (
                "❌ Kandydat odrzucony po weryfikacji Open API. "
                f"Szukano: '{clean_name}', API zwróciło: '{official_name}', score={verify_score:.2f}"
            )
        krs = basic.get("krs") or best.krs
        nip = basic.get("nip") or best.nip
        return krs, nip, f"✅ Dopasowano przez {best.source}, potwierdzono Open API KRS ({rejestr})."

    # Jeśli Open API chwilowo padło, zwracamy tylko mocny wynik, bez podejrzanego NIP-u.
    nip = best.nip if best.nip and is_valid_nip(best.nip) else ""
    return best.krs, nip, f"⚠️ Dopasowano przez {best.source}, ale bez potwierdzenia Open API: {api_msg}"


# -----------------------------------------------------------------------------
# Generowanie lokalnego PDF z JSON Open API
# -----------------------------------------------------------------------------
def _html_escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def build_krs_report_html(data: dict[str, Any], rejestr: str, source_url: str) -> str:
    basic = extract_basic_from_krs_json(data)
    pretty_json = json.dumps(data, ensure_ascii=False, indent=2)
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    return f"""
<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, sans-serif; font-size: 9pt; color: #111; }}
h1 {{ font-size: 16pt; margin-bottom: 4pt; }}
h2 {{ font-size: 12pt; margin-top: 14pt; border-bottom: 1px solid #999; }}
.warn {{ background: #fff3cd; border: 1px solid #e0b100; padding: 8pt; margin: 8pt 0; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 8pt; }}
td, th {{ border: 1px solid #bbb; padding: 4pt; vertical-align: top; }}
th {{ background: #f1f1f1; width: 28%; text-align: left; }}
pre {{ font-family: "DejaVu Sans Mono", "Courier New", monospace; font-size: 7pt; white-space: pre-wrap; }}
.small {{ color: #555; font-size: 8pt; }}
</style>
</head>
<body>
<h1>Raport KRS z Open API Ministerstwa Sprawiedliwości</h1>
<div class="warn">
<b>Uwaga:</b> ten PDF został wygenerowany lokalnie przez program na podstawie oficjalnej odpowiedzi JSON
z Open API KRS. Nie jest to oryginalny urzędowy PDF odpisu z identyfikatorem wydruku MS.
</div>
<table>
<tr><th>Nazwa</th><td>{_html_escape(basic.get('name'))}</td></tr>
<tr><th>KRS</th><td>{_html_escape(basic.get('krs'))}</td></tr>
<tr><th>NIP</th><td>{_html_escape(basic.get('nip'))}</td></tr>
<tr><th>REGON</th><td>{_html_escape(basic.get('regon'))}</td></tr>
<tr><th>Rejestr</th><td>{_html_escape(rejestr or basic.get('rejestr'))}</td></tr>
<tr><th>Data odpisu wg API</th><td>{_html_escape(basic.get('data'))}</td></tr>
<tr><th>Wygenerowano lokalnie</th><td>{_html_escape(now)}</td></tr>
<tr><th>Źródło JSON</th><td>{_html_escape(source_url)}</td></tr>
</table>
<h2>Pełna odpowiedź JSON Open API KRS</h2>
<pre>{_html_escape(pretty_json)}</pre>
</body>
</html>
"""


def save_html_as_pdf_qt(html_text: str, file_path: Path) -> None:
    """Generuje PDF przez Qt/PySide6, bez dodatkowych bibliotek."""
    from PySide6.QtGui import QTextDocument, QPdfWriter, QPageSize, QPageLayout

    writer = QPdfWriter(str(file_path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)

    doc = QTextDocument()
    doc.setHtml(html_text)

    # PySide6 zależnie od wersji może eksportować metodę jako print_ albo print.
    print_method = getattr(doc, "print_", None) or getattr(doc, "print", None)
    if not print_method:
        raise RuntimeError("Ta wersja PySide6 nie udostępnia QTextDocument.print_.")
    print_method(writer)


def save_krs_json_report_pdf(data: dict[str, Any], rejestr: str, pdf_path: Path, json_path: Path) -> None:
    source_url = f"{API_KRS_BASE}/OdpisAktualny/{normalize_krs(extract_basic_from_krs_json(data).get('krs'))}?rejestr={rejestr}&format=json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    html_text = build_krs_report_html(data, rejestr, source_url)
    save_html_as_pdf_qt(html_text, pdf_path)


# -----------------------------------------------------------------------------
# Wątki robocze
# -----------------------------------------------------------------------------
class AutoFindDataWorker(QThread):
    """Wątek szukający numeru KRS oraz NIP."""

    finished = Signal(int, str, str, str)  # row_idx, krs, nip, message

    def __init__(self, row_idx: int, raw_name: str, existing_krs: str = ""):
        super().__init__()
        self.row_idx = row_idx
        self.raw_name = raw_name
        self.existing_krs = existing_krs

    def run(self) -> None:
        try:
            krs, nip, msg = find_krs_and_nip_by_name(self.raw_name, self.existing_krs)
            self.finished.emit(self.row_idx, krs, nip, msg)
        except Exception as exc:
            logger.exception("AutoFindDataWorker failed")
            self.finished.emit(self.row_idx, "", "", f"⚠️ Błąd wyszukiwania: {exc}")


# -----------------------------------------------------------------------------
# Pobieranie oryginalnego PDF przez realną przeglądarkę
# -----------------------------------------------------------------------------
def _pw_first_visible(locator_candidates: list[Any], timeout_ms: int = 8000) -> Any:
    """Zwraca pierwszy widoczny locator Playwright z listy kandydatów."""
    last_exc: Optional[Exception] = None
    for loc in locator_candidates:
        try:
            # W Playwright Python `first` jest właściwością, nie metodą.
            first = getattr(loc, "first", loc)
            first.wait_for(state="visible", timeout=timeout_ms)
            return first
        except Exception as exc:  # noqa: BLE001 - różne wyjątki Playwright
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError("Brak kandydatów locatorów.")


def _pw_try_click_cookie_buttons(page: Any) -> None:
    for pattern in (r"Akcept", r"Zgadzam", r"Rozumiem", r"OK"):
        try:
            page.get_by_role("button", name=re.compile(pattern, re.I)).first.click(timeout=1500)
            return
        except Exception:
            pass


def _pw_label_is_checked(page: Any, label: Any) -> bool:
    """Sprawdza stan checkboxa PrimeNG po klasie labela albo po input#for."""
    try:
        return bool(label.evaluate(
            """
            (label) => {
                const cls = (label.className || '').toString();
                if (cls.includes('p-checkbox-label-active')) return true;
                const id = label.getAttribute('for');
                const input = id ? document.getElementById(id) : null;
                if (input && typeof input.checked === 'boolean') return input.checked;
                const box = label.closest('.p-checkbox, p-checkbox, .field-checkbox, div')?.querySelector?.('input[type="checkbox"]');
                if (box && typeof box.checked === 'boolean') return box.checked;
                const aria = label.getAttribute('aria-checked') || label.closest('[aria-checked]')?.getAttribute('aria-checked');
                return aria === 'true';
            }
            """
        ))
    except Exception:
        try:
            cls = label.get_attribute("class") or ""
            return "p-checkbox-label-active" in cls
        except Exception:
            return False


def _pw_ensure_register_label_checked(page: Any, label_regex: str) -> None:
    """Zaznacza konkretny checkbox rejestru, ale nie odznacza go gdy już jest aktywny."""
    candidates = [
        page.locator(
            "xpath=//h3[contains(normalize-space(.), 'Określ rodzaj rejestru')]"
            f"/following::label[contains(normalize-space(.), '{label_regex}')][1]"
        ),
        page.locator(f"xpath=//label[contains(normalize-space(.), '{label_regex}')][1]"),
        page.get_by_text(re.compile(label_regex, re.I)),
    ]
    label = _pw_first_visible(candidates, timeout_ms=10000)
    label.scroll_into_view_if_needed(timeout=3000)
    if not _pw_label_is_checked(page, label):
        label.click(timeout=5000)
        page.wait_for_timeout(250)


def _pw_ensure_both_registers_selected(page: Any) -> None:
    """
    Na stronie MS oba checkboxy w sekcji 'Określ rodzaj rejestru' muszą być zaznaczone:
    - Przedsiębiorcy
    - Stowarzyszenia, inne organizacje społeczne i zawodowe, fundacje, ZOZ
    """
    _pw_ensure_register_label_checked(page, "Przedsiębiorcy")
    _pw_ensure_register_label_checked(page, "Stowarzyszenia")


def _pw_fill_krs(page: Any, krs_number: str, type_delay_ms: int = 20) -> None:
    """Wypełnia pole Numer KRS możliwie odpornie na zmiany klas Angulara."""
    lower = "abcdefghijklmnopqrstuvwxyz"
    upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    candidates = [
        page.get_by_label(re.compile(r"Numer\s*KRS", re.I)),
        page.locator("input[formcontrolname='numerKRS']"),
        page.locator("input[formcontrolname='krs']"),
        page.locator(f"xpath=//input[contains(translate(@id,'{upper}','{lower}'),'krs')]") ,
        page.locator(f"xpath=//input[contains(translate(@name,'{upper}','{lower}'),'krs')]") ,
        page.locator(f"xpath=//input[contains(translate(@formcontrolname,'{upper}','{lower}'),'krs')]") ,
        page.locator("xpath=//*[contains(normalize-space(.), 'Numer KRS')]/following::input[1]"),
    ]
    field = _pw_first_visible(candidates, timeout_ms=10000)
    field.scroll_into_view_if_needed(timeout=3000)
    field.click(timeout=3000)
    try:
        field.fill("", timeout=3000)
    except Exception:
        # Gdy input jest maskowany, Ctrl+A + Backspace bywa pewniejsze.
        field.press("Control+A")
        field.press("Backspace")
    field.type(krs_number, delay=type_delay_ms)


def _pw_click_search(page: Any) -> None:
    candidates = [
        page.get_by_role("button", name=re.compile(r"^\s*Szukaj\s*$", re.I)),
        page.locator("button:has-text('Szukaj')"),
        page.locator("xpath=//button[contains(normalize-space(.), 'Szukaj')]") ,
    ]
    button = _pw_first_visible(candidates, timeout_ms=10000)
    button.scroll_into_view_if_needed(timeout=3000)
    button.click(timeout=5000)


def _pw_click_details(page: Any) -> bool:
    candidates = [
        page.get_by_role("button", name=re.compile(r"Wyświetl\s+szczegóły", re.I)),
        page.get_by_role("link", name=re.compile(r"Wyświetl\s+szczegóły", re.I)),
        page.locator("button:has-text('Wyświetl szczegóły')"),
        page.locator("a:has-text('Wyświetl szczegóły')"),
        page.locator("xpath=//*[self::button or self::a][contains(normalize-space(.), 'Wyświetl szczegóły')]") ,
    ]
    try:
        button = _pw_first_visible(candidates, timeout_ms=45000)
    except Exception:
        return False
    button.scroll_into_view_if_needed(timeout=5000)
    button.click(timeout=10000)
    return True


def _pw_minimize_browser_window(page: Any, log_func=print) -> None:
    """Minimalizuje normalne okno przeglądarki. Najpierw CDP, potem fallback pywinauto."""
    try:
        session = page.context.new_cdp_session(page)
        info = session.send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        if window_id:
            session.send("Browser.setWindowBounds", {
                "windowId": window_id,
                "bounds": {"windowState": "minimized"},
            })
            log_func("🌙 Okno przeglądarki zminimalizowane — pobieranie trwa w tle.")
            return
    except Exception as exc:
        log_func(f"ℹ️ Minimalizacja przez CDP nie zadziałała: {exc}")

    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        pattern = re.compile(r"krs|wyszukiwarka-krs|google chrome|microsoft edge|msedge|chromium|opera|firefox", re.I)
        for window in desktop.windows():
            try:
                if window.is_visible() and pattern.search(window.window_text() or ""):
                    window.minimize()
                    log_func("🌙 Okno przeglądarki zminimalizowane przez Windows — pobieranie trwa w tle.")
                    return
            except Exception:
                continue
        log_func("⚠️ Nie znaleziono okna przeglądarki do minimalizacji.")
    except Exception as exc:
        log_func(f"ℹ️ Nie udało się automatycznie zminimalizować okna: {exc}")


def _pw_find_current_pdf_button(page: Any) -> Any:
    """
    Znajduje przycisk 'Pobierz PDF' w sekcji 'Informacje aktualne'.
    To odpowiada fragmentowi DOM podanemu przez użytkownika.
    """
    candidates = [
        page.locator(
            "xpath=//h3[contains(normalize-space(.), 'Informacje aktualne')]"
            "/following::button[contains(normalize-space(.), 'Pobierz PDF')][1]"
        ),
        page.locator("button:has-text('Pobierz PDF')"),
        page.get_by_role("button", name=re.compile(r"Pobierz\s+PDF", re.I)),
    ]
    button = _pw_first_visible(candidates, timeout_ms=60000)
    button.scroll_into_view_if_needed(timeout=5000)
    return button


def download_official_pdf_via_playwright(
    krs_number: str,
    output_path: Path,
    log_func=print,
    speed_mode: str = "normal",
    background: bool = False,
    browser_mode: str = "auto",
) -> tuple[bool, str]:
    """
    Pobiera prawdziwy PDF z wyszukiwarka-krs.ms.gov.pl przez sterowanie widoczną
    przeglądarką. To nie używa Open API JSON – klika te same przyciski, które klika
    użytkownik: wyszukaj KRS -> Wyświetl szczegóły -> Informacje aktualne -> Pobierz PDF.

    Wymagane jednorazowo:
        pip install playwright
        python -m playwright install chromium

    Jeżeli strona pokaże zabezpieczenie/captcha/komunikat Imperva, przeglądarka jest
    widoczna i użytkownik może to potwierdzić ręcznie; program poczeka.
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception:
        return False, (
            "Brak biblioteki Playwright. Zainstaluj w środowisku programu:\n"
            "pip install playwright\npython -m playwright install chromium"
        )

    krs_number = normalize_krs(krs_number)
    if not krs_number:
        return False, "Niepoprawny numer KRS."

    speed = _playwright_speed_settings(speed_mode)

    profile_dir = Path(__file__).parent.parent / "dane" / "ms_krs_browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    with _PLAYWRIGHT_DOWNLOAD_LOCK:
        if background:
            log_func("🌙 Uruchamiam MS KRS w tle jako NORMALNE okno przeglądarki, ale zminimalizowane.")
            log_func("ℹ️ To nie jest tryb headless — działa jak poprzednio, tylko okno jest minimalizowane.")
            log_func("ℹ️ Jeśli MS pokaże zabezpieczenie, przywróć okno z paska zadań albo wyłącz 'w tle' i potwierdź ręcznie.")
        else:
            log_func("🌐 Uruchamiam widoczną przeglądarkę MS KRS. Nie zamykaj jej podczas pobierania.")
            log_func("ℹ️ Jeśli pojawi się zabezpieczenie strony, potwierdź je ręcznie – program poczeka.")
        log_func(f"⚙️ Prędkość działania: {speed.get('label', 'Normalna')}")

        with sync_playwright() as p:
            launch_kwargs = dict(
                # UWAGA: nie używamy headless=True, bo MS/Imperva często blokuje taki tryb.
                # Tryb „w tle” oznacza teraz normalną przeglądarkę, tylko zminimalizowaną.
                headless=False,
                accept_downloads=True,
                locale="pl-PL",
                timezone_id="Europe/Warsaw",
                viewport={"width": 1600, "height": 1000},
                slow_mo=int(speed.get("slow_mo_ms", 0)),
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-minimized" if background else "--start-maximized",
                ],
            )

            context = None
            last_launch_error: Optional[Exception] = None
            browser_mode = browser_mode if browser_mode in ("auto", "chrome", "msedge", "opera", "firefox") else "auto"
            if browser_mode == "firefox":
                # Nie używamy zwykłego firefox.exe, bo Playwright nie steruje stabilnie
                # normalną instalacją Firefoksa. Używamy przeglądarki Firefox z Playwright.
                kwargs = dict(launch_kwargs)
                kwargs.pop("args", None)
                log_func("🌐 Uruchamiam Firefox Playwright. Jeśli go brakuje: python -m playwright install firefox")
                context = p.firefox.launch_persistent_context(str(profile_dir), **kwargs)
            elif browser_mode == "opera":
                opera_path = _find_browser_executable("opera")
                if not opera_path:
                    return False, "Nie znaleziono Opera. Zainstaluj Operę albo wybierz inną przeglądarkę."
                kwargs = dict(launch_kwargs)
                kwargs["executable_path"] = opera_path
                log_func(f"🌐 Uruchamiam Operę: {opera_path}")
                context = p.chromium.launch_persistent_context(str(profile_dir), **kwargs)
            else:
                channels = {"auto": ("chrome", "msedge", None), "chrome": ("chrome",), "msedge": ("msedge",)}.get(browser_mode, ("chrome", "msedge", None))
                for channel in channels:
                    try:
                        kwargs = dict(launch_kwargs)
                        if channel:
                            kwargs["channel"] = channel
                        context = p.chromium.launch_persistent_context(str(profile_dir), **kwargs)
                        break
                    except Exception as exc:
                        last_launch_error = exc
                        context = None

            if context is None:
                return False, (
                    "Nie mogę uruchomić przeglądarki Playwright. "
                    f"Szczegóły: {last_launch_error}. Spróbuj: python -m playwright install chromium"
                )

            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(int(speed.get("default_timeout_ms", 30000)))
                context.set_extra_http_headers({"Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7"})
                if background:
                    _pw_minimize_browser_window(page, log_func)

                # Wyszukujemy raz z DWOMA zaznaczonymi rejestrami, zgodnie z wymaganiem strony MS.
                for rejestr in ("P+S",):
                    log_func(f"🔎 Szukam KRS {krs_number} na stronie MS, oba rejestry zaznaczone...")
                    page.goto(MS_KRS_HOME, wait_until="domcontentloaded", timeout=90000)
                    _pw_try_click_cookie_buttons(page)

                    # Jeżeli strona jest zabezpieczona, dajemy użytkownikowi czas na ręczne potwierdzenie.
                    try:
                        wait_for_form_ms = 60000 if background else 120000
                        page.wait_for_selector("input, button", timeout=wait_for_form_ms)
                    except PlaywrightTimeoutError:
                        if background:
                            return False, (
                                "Nie widzę formularza MS w zminimalizowanym oknie. "
                                "Prawdopodobnie strona pokazała zabezpieczenie. Przywróć okno z paska zadań albo wyłącz tryb w tle."
                            )
                        log_func("⚠️ Nie widzę formularza po 120 s. Sprawdź ręcznie okno przeglądarki.")

                    _pw_ensure_both_registers_selected(page)
                    _pw_fill_krs(page, krs_number, type_delay_ms=int(speed.get("type_delay_ms", 20)))
                    _pw_click_search(page)

                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    page.wait_for_timeout(int(speed.get("after_search_wait_ms", 1500)))

                    if not _pw_click_details(page):
                        log_func(f"ℹ️ Rejestr {rejestr}: nie znaleziono przycisku 'Wyświetl szczegóły'.")
                        continue

                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    page.wait_for_timeout(int(speed.get("after_details_wait_ms", 1000)))

                    pdf_button = _pw_find_current_pdf_button(page)
                    pdf_responses: list[Any] = []

                    def remember_pdf_response(response: Any) -> None:
                        try:
                            ct = (response.headers.get("content-type") or "").lower()
                            url = response.url.lower()
                            if "pdf" in ct or "pdf" in url or "odpis" in url or "wydruk" in url:
                                pdf_responses.append(response)
                        except Exception:
                            pass

                    page.on("response", remember_pdf_response)

                    log_func("📥 Klikam 'Informacje aktualne → Pobierz PDF'...")
                    try:
                        with page.expect_download(timeout=60000) as download_info:
                            pdf_button.click(timeout=10000)
                        download = download_info.value
                        download.save_as(str(output_path))
                        if output_path.exists() and output_path.stat().st_size > 1000:
                            with open(output_path, "rb") as f:
                                if f.read(5) == b"%PDF-":
                                    return True, f"Pobrano oryginalny PDF ze strony MS, rejestr {rejestr}."
                        log_func("⚠️ Pobranie zakończone, ale plik nie wygląda jak PDF. Próbuję z odpowiedzi sieciowej.")
                    except PlaywrightTimeoutError:
                        log_func("ℹ️ Nie było klasycznego zdarzenia download. Sprawdzam odpowiedzi sieciowe PDF/blob...")
                    except Exception as exc:
                        log_func(f"⚠️ Kliknięcie/pobranie PDF zgłosiło błąd: {exc}")

                    page.wait_for_timeout(int(speed.get("after_pdf_click_wait_ms", 3000)))
                    for response in pdf_responses:
                        try:
                            body = response.body()
                            if body and body[:5] == b"%PDF-":
                                output_path.write_bytes(body)
                                return True, f"Pobrano oryginalny PDF z odpowiedzi sieciowej MS, rejestr {rejestr}."
                        except Exception:
                            pass

                    log_func(f"ℹ️ Rejestr {rejestr}: nie udało się zapisać PDF po kliknięciu.")

                return False, "Nie udało się pobrać PDF przez stronę MS dla rejestru P ani S."
            finally:
                try:
                    context.close()
                except Exception:
                    pass


class KrsDownloadWorker(QThread):
    """
    Wątek pobierający dane KRS.

    Najpierw próbuje pobrać PDF z nieudokumentowanego endpointu wyszukiwarki MS.
    Jeśli endpoint zwraca 400/403 albo nie daje PDF-a, pobiera oficjalny JSON z Open API
    i generuje lokalny PDF-techniczny.
    """

    finished = Signal(int, bool, str, str)  # row_idx, success, message, file_path
    log_msg = Signal(str)

    def __init__(
        self,
        row_idx: int,
        krs_number: str,
        output_dir: Path,
        speed_mode: str = "normal",
        background: bool = False,
        browser_mode: str = "auto",
    ):
        super().__init__()
        self.row_idx = row_idx
        self.krs_number = normalize_krs(krs_number)
        self.output_dir = output_dir
        self.speed_mode = speed_mode if speed_mode in PLAYWRIGHT_SPEED_SETTINGS else "normal"
        self.background = background
        self.browser_mode = browser_mode if browser_mode in ("auto", "chrome", "msedge", "opera", "firefox") else "auto"

    def _try_direct_pdf_download(self, session: "requests.Session", file_path: Path) -> tuple[bool, str]:
        """
        Best-effort: prosty endpoint PDF. Obecnie często nie działa, ale zostawiamy próbę,
        bo w niektórych środowiskach MS może go jeszcze obsługiwać.
        """
        try:
            session.get(MS_KRS_HOME, timeout=10)
        except Exception:
            # To tylko ciasteczka dla ewentualnego endpointu PDF; jeśli padnie, lecimy dalej.
            pass

        for rejestr in ("P", "S"):
            url = f"{MS_KRS_PDF_BASE}/OdpisAktualny/{self.krs_number}?rejestr={rejestr}&format=pdf"
            self.log_msg.emit(f"📥 Próba pobrania oryginalnego PDF MS, rejestr '{rejestr}'...")
            try:
                response = session.get(url, timeout=20)
            except Exception as exc:
                self.log_msg.emit(f"⚠️ PDF MS rejestr {rejestr}: błąd sieci: {exc}")
                continue

            content_type = response.headers.get("content-type", "")
            if response.status_code == 200 and response.content[:5] == b"%PDF-":
                file_path.write_bytes(response.content)
                return True, f"Pobrano oryginalny PDF MS z rejestru '{rejestr}'."

            if response.status_code in (400, 403, 404):
                self.log_msg.emit(f"ℹ️ PDF MS rejestr {rejestr}: HTTP {response.status_code} ({content_type}).")
            else:
                self.log_msg.emit(f"ℹ️ PDF MS rejestr {rejestr}: HTTP {response.status_code}, content-type={content_type}.")

        return False, "Bezpośredni PDF MS niedostępny."

    def run(self) -> None:
        if not requests:
            self.finished.emit(self.row_idx, False, "Brak biblioteki requests. Zainstaluj: pip install requests", "")
            return

        if not self.krs_number or len(self.krs_number) != 10:
            self.finished.emit(self.row_idx, False, "Niepoprawny numer KRS.", "")
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = self.output_dir / f"KRS_{self.krs_number}.pdf"
        json_path = self.output_dir / f"KRS_{self.krs_number}.json"

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/pdf, application/json, text/plain, */*",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": MS_KRS_HOME,
            "Connection": "keep-alive",
        })

        self.log_msg.emit(f"⏳ Pobieram KRS: {self.krs_number}...")

        # 1. Najważniejsze: prawdziwy PDF przez widoczną przeglądarkę i kliknięcie strony MS.
        # To odpowiada ręcznej ścieżce: wyszukaj KRS → Wyświetl szczegóły → Informacje aktualne → Pobierz PDF.
        try:
            ok, msg = download_official_pdf_via_playwright(
                self.krs_number,
                pdf_path,
                self.log_msg.emit,
                speed_mode=self.speed_mode,
                background=self.background,
                browser_mode=self.browser_mode,
            )
            if ok:
                self.log_msg.emit("✅ SUKCES! Oryginalny PDF ze strony MS zapisany.")
                self.finished.emit(self.row_idx, True, msg, str(pdf_path))
                return
            self.log_msg.emit(f"ℹ️ Playwright/strona MS: {msg}")
        except Exception as exc:
            logger.exception("Playwright PDF download failed")
            self.log_msg.emit(f"⚠️ Pobieranie przez przeglądarkę zakończone błędem: {exc}")

        # 2. Próba pobrania oryginalnego PDF-u przez prosty endpoint, jeśli akurat działa.
        try:
            ok, msg = self._try_direct_pdf_download(session, pdf_path)
            if ok:
                self.log_msg.emit("✅ SUKCES! Oryginalny PDF zapisany.")
                self.finished.emit(self.row_idx, True, msg, str(pdf_path))
                return
            self.log_msg.emit(f"ℹ️ {msg}")
        except Exception as exc:
            self.log_msg.emit(f"⚠️ Próba PDF MS endpoint zakończona błędem: {exc}")

        # 3. Nie tworzymy już lokalnego „zamiennika” PDF z JSON, bo użytkownik potrzebuje
        # prawdziwego urzędowego PDF pobranego ze strony MS. Jeśli się nie udało, pokazujemy błąd
        # i zostawiamy przycisk „Pobierz PDF” do ponownej próby.
        self.log_msg.emit("❌ Nie pobrano oryginalnego PDF MS. Nie tworzę lokalnego PDF z JSON, żeby nie podmieniać dokumentu na niewłaściwy.")
        self.finished.emit(
            self.row_idx,
            False,
            "Nie udało się pobrać oryginalnego PDF ze strony MS. Spróbuj ponownie albo wyłącz tryb w tle i potwierdź zabezpieczenie ręcznie.",
            "",
        )


# -----------------------------------------------------------------------------
# Widget
# -----------------------------------------------------------------------------
class KrsDownloaderWidget(QWidget):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.project_path = ""
        self.krs_dir: Optional[Path] = None
        self.company_owners: list[dict[str, Any]] = []
        self.all_owners: list[dict[str, Any]] = []

        self.search_workers: list[AutoFindDataWorker] = []
        self.download_workers: list[KrsDownloadWorker] = []

        self._build_ui()
        self.log_to_console("System gotowy. Wybierz projekt, a wczytam firmy z zakładki Wypisy.")

    def log_to_console(self, text: str) -> None:
        self.console.append(text)
        logger.info(text)

    def set_project(self, project: dict) -> None:
        self.project_path = project.get("path", "")
        self.krs_dir = Path(self.project_path) / "KRS_Odpisy" if self.project_path else None
        self._refresh_table()

    def set_owners(self, owners: list) -> None:
        self.all_owners = owners or []
        self._apply_owner_source_filter()

    def _apply_owner_source_filter(self) -> None:
        include_company = self.config.get('krs_load_company', True)
        include_spolka = self.config.get('krs_load_spolka', True)
        include_institution = self.config.get('krs_load_institution', True)
        include_church = self.config.get('krs_load_church', False)
        self.company_owners = [
            o for o in self.all_owners
            if (include_company and o.get('is_company'))
            or (include_spolka and o.get('is_spolka'))
            or (include_institution and o.get('is_institution'))
            or (include_church and o.get('is_church'))
        ]
        self._refresh_table()

    def _open_krs_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('Ustawienia KRS')
        layout = QVBoxLayout(dlg)
        cb_company = QCheckBox('Ładuj Firmy')
        cb_company.setChecked(bool(self.config.get('krs_load_company', True)))
        cb_spolka = QCheckBox('Ładuj Spółki')
        cb_spolka.setChecked(bool(self.config.get('krs_load_spolka', True)))
        cb_inst = QCheckBox('Ładuj Instytucje')
        cb_inst.setChecked(bool(self.config.get('krs_load_institution', True)))
        cb_church = QCheckBox('Ładuj Parafie')
        cb_church.setChecked(bool(self.config.get('krs_load_church', False)))
        for cb in (cb_company, cb_spolka, cb_inst, cb_church):
            layout.addWidget(cb)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.config['krs_load_company'] = cb_company.isChecked()
            self.config['krs_load_spolka'] = cb_spolka.isChecked()
            self.config['krs_load_institution'] = cb_inst.isChecked()
            self.config['krs_load_church'] = cb_church.isChecked()
            for attr, val in [('chk_krs_company', cb_company.isChecked()), ('chk_krs_spolka', cb_spolka.isChecked()), ('chk_krs_institution', cb_inst.isChecked()), ('chk_krs_church', cb_church.isChecked())]:
                w = getattr(self, attr, None)
                if w is not None:
                    w.blockSignals(True); w.setChecked(val); w.blockSignals(False)
            self._apply_owner_source_filter()

    def _on_source_filter_changed(self, *_args) -> None:
        for attr, key in [
            ('chk_krs_company', 'krs_load_company'),
            ('chk_krs_spolka', 'krs_load_spolka'),
            ('chk_krs_institution', 'krs_load_institution'),
            ('chk_krs_church', 'krs_load_church'),
        ]:
            cb = getattr(self, attr, None)
            if cb is not None:
                self.config[key] = cb.isChecked()
        self._apply_owner_source_filter()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEWA: tabela
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        lbl_header = QLabel("🏢 Lista Firm / Spółek (edytuj klikając dwa razy na nazwę, NIP lub KRS)")
        lbl_header.setStyleSheet("font-size:15px; font-weight:700;")
        left_layout.addWidget(lbl_header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Nazwa Firmy (EDYTOWALNA)", "NIP", "KRS", "Status", "Odpis / raport", "Szukaj ręcznie"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.cellChanged.connect(self._on_cell_edited)
        left_layout.addWidget(self.table)

        row_btns = QHBoxLayout()
        btn_auto_find = QPushButton("🔍 Automatycznie szukaj brakujących NIP / KRS")
        btn_auto_find.setStyleSheet("background-color: #9b5de5; color: white; padding: 8px; font-weight:bold;")
        btn_auto_find.clicked.connect(self._auto_find_all_data)
        row_btns.addWidget(btn_auto_find)

        btn_reset_selected = QPushButton("♻️ Resetuj wybrany odpis")
        btn_reset_selected.setStyleSheet("background-color: #f39c12; color: white; padding: 8px; font-weight:bold;")
        btn_reset_selected.clicked.connect(self._reset_selected_krs_download)
        row_btns.addWidget(btn_reset_selected)

        btn_krs_settings = QPushButton("⚙️ Ustawienia")
        btn_krs_settings.setStyleSheet("background-color: #2b5797; color: white; padding: 8px; font-weight:bold;")
        btn_krs_settings.clicked.connect(self._open_krs_settings_dialog)
        row_btns.addWidget(btn_krs_settings)

        row_btns.addWidget(QLabel("⚙️ Prędkość MS:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItem("Szybka", "fast")
        self.speed_combo.addItem("Normalna", "normal")
        self.speed_combo.addItem("Wolna / stabilna", "slow")
        initial_speed = str(self.config.get("krs_playwright_speed", "normal"))
        speed_index = self.speed_combo.findData(initial_speed if initial_speed in PLAYWRIGHT_SPEED_SETTINGS else "normal")
        self.speed_combo.setCurrentIndex(max(0, speed_index))
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        row_btns.addWidget(self.speed_combo)

        row_btns.addWidget(QLabel("Przeglądarka:"))
        self.browser_combo = QComboBox()
        self.browser_combo.addItem("Domyślna z programu", "auto")
        self.browser_combo.addItem("Chrome", "chrome")
        self.browser_combo.addItem("Edge", "msedge")
        self.browser_combo.addItem("Opera", "opera")
        self.browser_combo.addItem("Firefox", "firefox")
        browser_index = self.browser_combo.findData(str(self.config.get("krs_browser", self.config.get("default_browser", "auto"))))
        self.browser_combo.setCurrentIndex(max(0, browser_index))
        self.browser_combo.currentIndexChanged.connect(self._on_browser_changed)
        row_btns.addWidget(self.browser_combo)

        self.background_checkbox = QCheckBox("Działaj w tle (zminimalizowane okno)")
        self.background_checkbox.setToolTip(
            "Gdy zaznaczone, program uruchamia normalną przeglądarkę, ale od razu ją minimalizuje. "
            "To nie jest headless, więc działa tak jak poprzednio. Jeśli MS pokaże zabezpieczenie, "
            "przywróć okno z paska zadań albo odznacz tę opcję."
        )
        self.background_checkbox.setChecked(bool(self.config.get("krs_playwright_background", True)))
        self.background_checkbox.stateChanged.connect(self._on_background_changed)
        row_btns.addWidget(self.background_checkbox)

        btn_open_folder = QPushButton("📂 Otwórz folder pobranych KRS")
        btn_open_folder.clicked.connect(self._open_krs_folder)
        row_btns.addWidget(btn_open_folder)
        left_layout.addLayout(row_btns)

        splitter.addWidget(left_widget)

        # PRAWA: ręczne linki
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        man_group = QGroupBox("🌐 Otwórz oryginalne strony")
        man_layout = QVBoxLayout(man_group)

        lbl_info = QLabel(
            "Jeśli automatyka nie znajdzie firmy lub potrzebujesz urzędowego PDF-u z identyfikatorem MS, "
            "otwórz wyszukiwarkę ręcznie."
        )
        lbl_info.setWordWrap(True)
        man_layout.addWidget(lbl_info)

        btn_ms = QPushButton("🏛️ Oficjalna wyszukiwarka eKRS/MS")
        btn_ms.setStyleSheet("padding: 8px;")
        btn_ms.clicked.connect(lambda checked=False: webbrowser.open(MS_KRS_HOME))
        man_layout.addWidget(btn_ms)

        btn_krs_pobierz = QPushButton("🌐 KRS-Pobierz – wyszukiwarka pomocnicza")
        btn_krs_pobierz.setStyleSheet("padding: 8px; background-color: #27ae60; color: white;")
        btn_krs_pobierz.clicked.connect(lambda checked=False: webbrowser.open("https://krs-pobierz.pl/"))
        man_layout.addWidget(btn_krs_pobierz)

        right_layout.addWidget(man_group)
        right_layout.addStretch()
        splitter.addWidget(right_widget)
        splitter.setSizes([850, 250])
        main_layout.addWidget(splitter)

        # DÓŁ: konsola logów
        console_group = QGroupBox("📝 Diagnostyka na żywo")
        console_layout = QVBoxLayout(console_group)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(170)
        self.console.setStyleSheet("background-color: #000; color: #0f0; font-family: monospace;")
        console_layout.addWidget(self.console)
        main_layout.addWidget(console_group)

    def _refresh_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        for owner in self.company_owners:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name = owner.get("name_plural") or owner.get("full_name") or owner.get("last_name") or ""
            nip = str(owner.get("nip", "") or "").strip()
            krs = str(owner.get("krs", "") or "").strip()

            file_exists = False
            if self.krs_dir and krs:
                padded_krs = normalize_krs(krs)
                if padded_krs and (self.krs_dir / f"KRS_{padded_krs}.pdf").exists():
                    file_exists = True

            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(nip))

            it_krs = QTableWidgetItem(krs)
            if not krs:
                it_krs.setBackground(QColor(60, 0, 0))
            self.table.setItem(row, 2, it_krs)

            item_status = QTableWidgetItem("✅ Plik" if file_exists else "❌ Brak pliku")
            item_status.setForeground(QColor("#2ecc71") if file_exists else QColor("#e74c3c"))
            item_status.setFlags(item_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, item_status)

            btn_down = QPushButton("📄 Otwórz PDF" if file_exists else "📥 Pobierz PDF")
            btn_down.setStyleSheet(
                "background-color: #2980b9; color: white;" if file_exists
                else "background-color: #27ae60; color: white;"
            )
            btn_down.clicked.connect(lambda checked=False, r=row: self._handle_download_row(r))
            self.table.setCellWidget(row, 4, btn_down)

            btn_web = QPushButton("Szukaj ręcznie")
            btn_web.clicked.connect(lambda checked=False, r=row: self._handle_manual_search(r))
            self.table.setCellWidget(row, 5, btn_web)

        self.table.blockSignals(False)

    def _on_browser_changed(self, *_args) -> None:
        """Zapisuje wybór przeglądarki KRS w konfiguracji."""
        mode = self._get_browser_mode()
        self.config["krs_browser"] = mode
        labels = {
            "auto": "Domyślna z programu",
            "chrome": "Chrome",
            "msedge": "Edge",
            "opera": "Opera",
            "firefox": "Firefox",
        }
        if hasattr(self, "log_to_console"):
            self.log_to_console(f"🌐 Ustawiono przeglądarkę KRS: {labels.get(mode, mode)}")

    def _get_browser_mode(self) -> str:
        combo = getattr(self, "browser_combo", None)
        if combo is None:
            mode = str(self.config.get("krs_browser", self.config.get("default_browser", "auto")))
        else:
            mode = str(combo.currentData() or "auto")
        return mode if mode in ("auto", "chrome", "msedge", "opera", "firefox") else "auto"

    def _on_speed_changed(self, *_args) -> None:
        speed_mode = self._get_speed_mode()
        self.config["krs_playwright_speed"] = speed_mode
        label = PLAYWRIGHT_SPEED_SETTINGS.get(speed_mode, PLAYWRIGHT_SPEED_SETTINGS["normal"])["label"]
        self.log_to_console(f"⚙️ Ustawiono prędkość pobierania MS: {label}")

    def _get_speed_mode(self) -> str:
        combo = getattr(self, "speed_combo", None)
        if combo is None:
            return str(self.config.get("krs_playwright_speed", "normal"))
        mode = combo.currentData()
        return mode if mode in PLAYWRIGHT_SPEED_SETTINGS else "normal"

    def _on_background_changed(self, *_args) -> None:
        background = self._get_background_mode()
        self.config["krs_playwright_background"] = background
        self.log_to_console("🌙 Tryb w tle: WŁĄCZONY — normalne okno będzie minimalizowane" if background else "🪟 Tryb w tle: WYŁĄCZONY — przeglądarka będzie widoczna")

    def _get_background_mode(self) -> bool:
        checkbox = getattr(self, "background_checkbox", None)
        if checkbox is None:
            return bool(self.config.get("krs_playwright_background", True))
        return checkbox.isChecked()

    def _set_row_download_missing(self, row: int) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        item_status = QTableWidgetItem("❌ Brak pliku")
        item_status.setForeground(QColor("#e74c3c"))
        item_status.setFlags(item_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 3, item_status)
        btn = self.table.cellWidget(row, 4)
        if btn:
            btn.setText("📥 Pobierz PDF")
            btn.setStyleSheet("background-color: #27ae60; color: white;")

    def _set_row_download_exists(self, row: int) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        item_status = QTableWidgetItem("✅ Plik")
        item_status.setForeground(QColor("#2ecc71"))
        item_status.setFlags(item_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 3, item_status)
        btn = self.table.cellWidget(row, 4)
        if btn:
            btn.setText("📄 Otwórz PDF")
            btn.setStyleSheet("background-color: #2980b9; color: white;")

    def _reset_selected_krs_download(self) -> None:
        """Usuwa zapisany PDF/JSON dla wybranego wiersza i przywraca przycisk 'Pobierz PDF'."""
        if not self.krs_dir:
            QMessageBox.warning(self, "Błąd", "Brak aktywnego projektu.")
            return

        selected_rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        if not selected_rows:
            selected_rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not selected_rows:
            current = self.table.currentRow()
            selected_rows = [current] if current >= 0 else []

        if not selected_rows:
            QMessageBox.information(self, "Reset odpisu", "Zaznacz wiersz, który chcesz zresetować.")
            return

        if len(selected_rows) == 1:
            question = "Usunąć zapisany PDF/JSON dla wybranego wiersza i pokazać przycisk 'Pobierz PDF'?"
        else:
            question = f"Usunąć zapisane PDF/JSON dla {len(selected_rows)} wybranych wierszy i pokazać przyciski 'Pobierz PDF'?"
        if QMessageBox.question(self, "Reset odpisu KRS", question) != QMessageBox.StandardButton.Yes:
            return

        removed = 0
        for row in selected_rows:
            krs_item = self.table.item(row, 2)
            krs = normalize_krs(krs_item.text() if krs_item else "")
            if not krs:
                self._set_row_download_missing(row)
                continue
            for suffix in (".pdf", ".json"):
                path = self.krs_dir / f"KRS_{krs}{suffix}"
                try:
                    if path.exists():
                        path.unlink()
                        removed += 1
                except Exception as exc:
                    self.log_to_console(f"⚠️ Nie mogę usunąć {path.name}: {exc}")
            if (self.krs_dir / f"KRS_{krs}.pdf").exists():
                self._set_row_download_exists(row)
            else:
                self._set_row_download_missing(row)

        self.log_to_console(f"♻️ Reset zakończony. Usunięto plików: {removed}. Przycisk ustawiony na 'Pobierz PDF' tam, gdzie usunięto PDF.")

    def _on_cell_edited(self, row: int, col: int) -> None:
        if row >= len(self.company_owners):
            return
        item = self.table.item(row, col)
        if not item:
            return

        new_val = item.text().strip()
        owner = self.company_owners[row]

        if col == 0:
            owner["name_plural"] = new_val
            owner["last_name"] = new_val
            self.log_to_console(f"✏️ Zmieniono nazwę na: {new_val}")
        elif col == 1:
            owner["nip"] = new_val
        elif col == 2:
            owner["krs"] = new_val
            item.setBackground(QColor(0, 0, 0, 0) if new_val else QColor(60, 0, 0))

    def _auto_find_all_data(self) -> None:
        self.log_to_console("Uruchamiam precyzyjne szukanie KRS/NIP...")
        started = 0

        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            nip_item = self.table.item(row, 1)
            krs_item = self.table.item(row, 2)
            name = name_item.text().strip() if name_item else ""
            nip = nip_item.text().strip() if nip_item else ""
            krs = krs_item.text().strip() if krs_item else ""

            if name and (not krs or not nip):
                cleaned = clean_company_name(name)
                self.log_to_console(f"🔎 Szukam / potwierdzam: {cleaned}")
                worker = AutoFindDataWorker(row, name, existing_krs=krs)
                worker.finished.connect(self._on_auto_find_finished)
                worker.finished.connect(lambda *_args, w=worker: self._cleanup_search_worker(w))
                worker.finished.connect(worker.deleteLater)
                self.search_workers.append(worker)
                worker.start()
                started += 1

        if not started:
            self.log_to_console("ℹ️ Nie ma brakujących danych do wyszukania.")

    def _cleanup_search_worker(self, worker: AutoFindDataWorker) -> None:
        try:
            self.search_workers.remove(worker)
        except ValueError:
            pass

    def _on_auto_find_finished(self, row_idx: int, krs: str, nip: str, msg: str) -> None:
        self.table.blockSignals(True)
        try:
            if row_idx >= self.table.rowCount() or row_idx >= len(self.company_owners):
                return

            if krs or nip:
                if krs:
                    it_krs = QTableWidgetItem(krs)
                    it_krs.setBackground(QColor(0, 60, 0))
                    self.table.setItem(row_idx, 2, it_krs)
                    self.company_owners[row_idx]["krs"] = krs

                if nip and not (self.table.item(row_idx, 1) and self.table.item(row_idx, 1).text().strip()):
                    self.table.setItem(row_idx, 1, QTableWidgetItem(nip))
                    self.company_owners[row_idx]["nip"] = nip

                self.log_to_console(f"✅ Wiersz {row_idx + 1}: KRS={krs or '-'} | NIP={nip or '-'} | {msg}")
            else:
                self.log_to_console(f"ℹ️ Wiersz {row_idx + 1}: {msg}")
        finally:
            self.table.blockSignals(False)

    def _handle_download_row(self, row: int) -> None:
        krs_item = self.table.item(row, 2)
        krs = krs_item.text().strip() if krs_item else ""

        if not krs or len(_only_digits(krs)) < 5:
            self.log_to_console("❌ Brak wpisanego albo zbyt krótkiego KRS.")
            QMessageBox.warning(self, "Brak KRS", "Wpisz numer KRS w tabelę, aby pobrać dane/PDF.")
            return

        if not self.krs_dir:
            QMessageBox.warning(self, "Błąd", "Brak aktywnego projektu.")
            return

        padded_krs = normalize_krs(krs)
        file_path = self.krs_dir / f"KRS_{padded_krs}.pdf"

        if file_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path)))
            return

        status_item = self.table.item(row, 3)
        if status_item:
            status_item.setText("⏳ Trwa pobieranie...")
            status_item.setForeground(QColor("#f1c40f"))

        worker = KrsDownloadWorker(
            row,
            krs,
            self.krs_dir,
            speed_mode=self._get_speed_mode(),
            background=self._get_background_mode(),
            browser_mode=self._get_browser_mode(),
        )
        worker.log_msg.connect(self.log_to_console)
        worker.finished.connect(self._on_download_finished)
        worker.finished.connect(lambda *_args, w=worker: self._cleanup_download_worker(w))
        worker.finished.connect(worker.deleteLater)
        self.download_workers.append(worker)
        worker.start()

    def _cleanup_download_worker(self, worker: KrsDownloadWorker) -> None:
        try:
            self.download_workers.remove(worker)
        except ValueError:
            pass

    def _on_download_finished(self, row_idx: int, success: bool, msg: str, file_path: str) -> None:
        if row_idx >= self.table.rowCount():
            return

        if success:
            item_status = QTableWidgetItem("✅ Pobrano / utworzono")
            item_status.setForeground(QColor("#2ecc71"))
            item_status.setFlags(item_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 3, item_status)

            btn = self.table.cellWidget(row_idx, 4)
            if btn:
                btn.setText("📄 Otwórz PDF")
                btn.setStyleSheet("background-color: #2980b9; color: white;")
            self.log_to_console(f"✅ {msg}")
        else:
            item_status = QTableWidgetItem("❌ Błąd / spróbuj ponownie")
            item_status.setForeground(QColor("#e74c3c"))
            item_status.setFlags(item_status.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 3, item_status)
            btn = self.table.cellWidget(row_idx, 4)
            if btn:
                btn.setText("📥 Pobierz PDF")
                btn.setStyleSheet("background-color: #27ae60; color: white;")
            self.log_to_console(f"❌ {msg}")

    def _handle_manual_search(self, row: int) -> None:
        name_item = self.table.item(row, 0)
        name = name_item.text().strip() if name_item else ""
        if not name:
            QMessageBox.warning(self, "Błąd", "Brak nazwy w tabeli.")
            return

        cleaned_name = clean_company_name(name)
        krs_pobierz_url = f"https://krs-pobierz.pl/szukaj?q={quote_plus(cleaned_name)}"
        google_url = f"https://www.google.com/search?q={quote_plus(cleaned_name + ' KRS NIP')}"

        try:
            import pyperclip
            pyperclip.copy(cleaned_name)
        except Exception:
            pass

        self.log_to_console(f"Otwieram wyszukiwanie ręczne dla: '{cleaned_name}'")
        webbrowser.open(krs_pobierz_url)
        webbrowser.open(google_url)

    def _open_krs_folder(self) -> None:
        if not self.krs_dir:
            return
        self.krs_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.krs_dir)))
