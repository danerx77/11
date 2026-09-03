"""
pdf_utils.py – Narzędzia do przetwarzania PDF (wypisy i druczki).
"""
import re
import fitz  # PyMuPDF
from pathlib import Path

from utils.wypis_metadata import (
    META_FIELDS as _WYPIS_META_FIELDS,
    extract_wypis_metadata as _extract_wypis_metadata_text,
    merge_meta_into_parcels as _merge_wypis_meta_into_parcels,
)

def _get_font_path(font_name: str) -> str:
    fonts = {
        "Arial": "C:/Windows/Fonts/arial.ttf",
        "Calibri": "C:/Windows/Fonts/calibri.ttf",
        "Times New Roman": "C:/Windows/Fonts/times.ttf",
        "Tahoma": "C:/Windows/Fonts/tahoma.ttf"
    }
    path = fonts.get(font_name, "C:/Windows/Fonts/arial.ttf")
    if Path(path).exists(): return path
    return ""

def _split_zip_city(city_raw: str) -> tuple[str, str]:
    if not city_raw: return "", ""
    m = re.match(r'^(\d{2}-\d{3})\s+(.*)', city_raw.strip())
    if m: return m.group(1), m.group(2)
    return "", city_raw.strip()

def _clean_multipage_garbage(full_text: str) -> str:
    lines = full_text.split('\n')
    cleaned = []
    for line in lines:
        l_strip = line.strip()
        l_low = l_strip.lower()
        if l_low.startswith('znak sprawy:'): continue
        if re.match(r'^strona \d+ z \d+$', l_low): continue
        if 'informacja z operatu ewidencyjnego' in l_low: continue
        if l_low.startswith('sporządzono dnia:'): continue
        if l_low.startswith('nr jednostki rejestrowej:'): continue
        if l_low.startswith('osoby:'): continue
        if l_low in ['udział', 'forma władania', 'dane osoby fizycznej / instytucji', 'dane osoby fizycznej/instytucji']: continue
        cleaned.append(l_strip)
    return '\n'.join(cleaned)

def _abbreviate_company_name(name: str) -> str:
    name = re.sub(r'(?i)\bspółka z ograniczoną odpowiedzialnością spółka komandytowa\b', 'sp. z o.o. sp. k.', name)
    name = re.sub(r'(?i)\bspółka z ograniczoną odpowiedzialnością\b', 'sp. z o.o.', name)
    name = re.sub(r'(?i)\bspółka komandytowa\b', 'sp. k.', name)
    name = re.sub(r'(?i)\bspółka akcyjna\b', 'S.A.', name)
    name = re.sub(r'(?i)\bspółka jawna\b', 'sp. j.', name)
    name = re.sub(r'(?i)\bspółka cywilna\b', 'sp. c.', name)
    return name

def _extract_meta_simplified_wypis(text: str) -> dict:
    meta = {'voivodeship': '', 'county': '', 'municipality': '', 'precinct': '', 'precinct_number': ''}
    lines = [re.sub(r'\s+', ' ', l).strip() for l in str(text or '').split('\n') if l.strip()]
    low = [l.lower() for l in lines]
    labels = ['województwo', 'powiat', 'gmina', 'jednostka ewidencyjna', 'obręb']
    found_block = False
    for i in range(len(lines) - 9):
        if all(labels[j] in low[i+j] for j in range(5)):
            vals = lines[i+5:i+10]
            meta['voivodeship'] = vals[0].strip()
            meta['county'] = vals[1].strip()
            muni_val = vals[2].strip()
            if ',' in muni_val:
                muni_val = muni_val.split(',')[-1].strip()
            meta['municipality'] = muni_val
            v4 = vals[4]
            v4_clean = re.sub(r'(?i)^.*?Kancelaryjny.*?(?:EG[\.\d]+)?(?=Nr|\d)', '', v4).strip()
            m_obr = re.search(r'(?:Nr\s*)?0*(\d+)\s*[,\- ]+\s*(.+)', v4_clean, re.I)
            if m_obr:
                meta['precinct_number'] = m_obr.group(1).strip()
                meta['precinct'] = m_obr.group(2).strip()
            else:
                meta['precinct'] = v4_clean.strip()
            found_block = True
            break
    if not found_block:
        wm = re.search(r'\bWojew[oó]dztwo\b\s*:?\s*([^\n]+)', text, re.I)
        if wm and not meta['voivodeship']: 
            v = wm.group(1).strip()
            v = re.split(r'(?i)\b(Powiat|Gmina|Jednostka|Obręb)\b', v)[0].strip(' ,-')
            meta['voivodeship'] = v
        pm = re.search(r'\bPowiat\b\s*:?\s*([^\n]+)', text, re.I)
        if pm and not meta['county']: 
            v = pm.group(1).strip()
            v = re.split(r'(?i)\b(Gmina|Jednostka|Obręb|Województwo)\b', v)[0].strip(' ,-')
            if v.lower() not in ['owe w']: 
                meta['county'] = v
        jm = re.search(r'\b(?:Gmina|Jednostka ewidencyjna)\b\s*:?\s*([^\n]+)', text, re.I)
        if jm and not meta['municipality']: 
            v = jm.group(1).strip()
            v = re.split(r'(?i)\b(Obręb|Województwo|Powiat)\b', v)[0].strip(' ,-')
            if ',' in v: v = v.split(',')[-1].strip()
            meta['municipality'] = v.split('-')[0].strip() if '-' in v else v
        om = re.search(r'\bObr[eę]b\b(?: ewidencyjny)?\s*:?\s*([^\n]+)', text, re.I)
        if om and not meta['precinct']: 
            v = om.group(1).strip()
            v = re.split(r'(?i)Nr\s+Kancelaryjny', v)[0].strip(' ,-')
            m_num = re.search(r'(?:Nr\s*)?0*(\d+)\s*[,\- ]+\s*(.+)', v, re.I)
            if m_num:
                meta['precinct_number'] = m_num.group(1).strip()
                meta['precinct'] = m_num.group(2).strip()
            else:
                if v.isdigit(): meta['precinct_number'] = str(int(v))
                else: meta['precinct'] = v
    return meta

def _is_land_use_description(line: str) -> bool:
    low = str(line or '').lower().strip()
    bad = [
        'grunty przeznaczone', 'drogi', 'ter.zabud', 'tereny mieszkaniowe',
        'grunty orne', 'użytków', 'uzytkow', 'klas bonitacyjnych', 'opis',
        'oznacz', 'powierzchnia', 'numer księgi', 'identyfikator', 'razem powierzchnia',
        'tp', 'dr', 'bi', 'b', 'rvi'
    ]
    return low in bad or any(x in low for x in bad[:9])

def _extract_parcels_simplified_wypis(text: str) -> list[dict]:
    lines = [re.sub(r'\s+', ' ', l).strip() for l in str(text or '').split('\n') if l.strip()]
    parcels = []
    current = None
    kw_mem = ''
    for i, line in enumerate(lines):
        m_kw = re.search(r'KW\s*([A-Z]{2,4}\d?[A-Z]?\s*/\s*\d+\s*/\s*\d)', line, re.I) or re.search(r'([A-Z]{2,4}\d?[A-Z]?\s*/\s*\d+\s*/\s*\d)', line)
        if m_kw:
            kw_mem = re.sub(r'\s+', '', m_kw.group(1)).upper()
            if current: current['kw'] = kw_mem
        m_id = re.search(r'Identyfikator\s+dzia[łl]ki\s*:?\s*([0-9A-Za-z_.\-/]+)', line, re.I)
        if m_id and current:
            current['identifier'] = m_id.group(1).strip()
        if re.fullmatch(r'\d+(?:/\d+)?', line):
            look = ' '.join(lines[i+1:i+8]).lower()
            if not (re.search(r'\d+[\.,]\d{2,4}', look) or 'kw ' in look or 'identyfikator' in look):
                continue
            if current: parcels.append(current)
            current = {'number': line, 'area_ha': 0.0, 'kw': kw_mem, 'parcel_address': '', 'identifier': ''}
            if i + 1 < len(lines):
                nxt = lines[i+1].strip()
                if nxt and not _is_land_use_description(nxt) and not re.fullmatch(r'[A-Za-z]{1,4}', nxt) and not re.match(r'\d+[\.,]\d+', nxt):
                    current['parcel_address'] = nxt
            continue
        if current:
            m_area = re.search(r'^(\d{1,4}[\.,]\d{2,4})$', line)
            if m_area and current.get('area_ha', 0.0) == 0.0:
                try: current['area_ha'] = float(m_area.group(1).replace(',', '.'))
                except Exception: pass
    if current: parcels.append(current)
    out = {}
    for par in parcels:
        n = par['number']
        if n not in out: out[n] = par
        else:
            for k in ['kw', 'parcel_address', 'identifier']:
                if par.get(k) and not out[n].get(k): out[n][k] = par[k]
            if par.get('area_ha',0)>0 and out[n].get('area_ha',0)==0: out[n]['area_ha']=par['area_ha']
    return list(out.values())

def _extract_entities_simplified_wypis(text: str) -> list[dict]:
    lines = [re.sub(r'\s+', ' ', l).strip() for l in str(text or '').split('\n') if l.strip()]
    entities = []
    current = None
    in_owner_section = False
    stop_words = ['Oznaczenie działki', 'Bliższe określenie położenia', 'G R U N T Y', 'Razem powierzchnia']
    skip = ['W Ł A Ś C I E L E', 'właściciel :', 'użytkownik :', 'trwały zarząd :', 'udział:', 'oraz żona']
    for line in lines:
        if 'udział:' in line.lower():
            in_owner_section = True
            continue
        if any(w.lower() in line.lower() for w in stop_words):
            if entities: break
            continue
        if not in_owner_section: continue
        if any(line.lower().startswith(w.lower()) or line.lower()==w.lower() for w in skip): continue
        low = line.lower()
        if low.startswith(('zam:', 'siedziba:', 'korespondencja:')):
            addr = re.sub(r'^(zam:|siedziba:|korespondencja:)\s*', '', line, flags=re.I).strip()
            if current:
                if current.get('address') and current['address'] != addr:
                    current['address2'] = addr
                else:
                    current['address'] = addr
                    if low.startswith('siedziba:'): current['has_siedziba'] = True
            continue
        if re.search(r'^(Oznaczenie|Numer|Powierzchnia|Identyfikator|Data|Nr Kancelaryjny|UPROSZCZONY)', line, re.I): continue
        if re.search(r'\d{2}-\d{3}', line) or ' ul.' in low or low.startswith('ul.'): continue
        clean = re.sub(r'\(.*?\)', '', line).strip(' ,;:-')
        if not clean: continue
        current = {'raw_name': _abbreviate_company_name(clean), 'is_dead': False, 'address': '', 'address2': '', 'has_siedziba': False}
        entities.append(current)
    return entities

def _parse_simplified_wypis_page(text: str) -> list[dict]:
    if 'UPROSZCZONY WYPIS Z REJESTRU GRUNTÓW' not in text: return []
    meta = _extract_meta_simplified_wypis(text)
    # Uzupełniamy odczyt o wszystkie etykiety z całej strony. Uproszczony wypis
    # także bywa wystawiany dla działek z dwóch różnych obrębów.
    label_meta = _extract_wypis_metadata_text(text)
    for field in _WYPIS_META_FIELDS:
        if label_meta.get(field) and not str(meta.get(field, '') or '').strip():
            meta[field] = label_meta[field]
    parcels = _extract_parcels_simplified_wypis(text)
    if not parcels: return []
    _merge_wypis_meta_into_parcels(parcels, text, meta)
    for par in parcels:
        for k,v in meta.items(): par.setdefault(k, v)
    entities = _extract_entities_simplified_wypis(text)
    if not entities: return []
    owners = []
    for e in entities:
        raw = e['raw_name']; addr = e.get('address','')
        is_church = any(k in raw.upper() for k in ['PARAFIA', 'KOŚCIÓŁ', 'DIECEZJA', 'ARCHIDIECEZJA', 'PROWINCJA', 'EPISKOPAT', 'KURIA'])
        is_inst = any(k in raw.upper() for k in ['GMINA', 'SKARB PAŃSTWA', 'NADLEŚNICTWO', 'ZARZĄD', 'POWIAT', 'WOJEWÓDZTWO', 'URZĄD', 'MIASTO', 'PAŃSTWOWE', ' PKP'])
        is_spolka = any(k in raw.upper() for k in ['SPÓŁKA', 'SP. Z O.O.', ' S.A.', 'SPÓŁDZIELNIA', 'SPÓŁDZIELNI'])
        is_company = any(k in raw.upper() for k in ['PRZEDSIĘBIORSTWO', 'F.H.U']) or e.get('has_siedziba')
        ln, fn = raw, ''
        if not is_inst and not is_church and not is_company and not is_spolka:
            parts = raw.split()
            if len(parts)>=2:
                ln = parts[0]; fn = parts[1]; raw = f'{fn} {ln}'.strip()
        total_area = sum(par.get('area_ha',0) for par in parcels)
        kw_numbers = list(dict.fromkeys([par.get('kw','') for par in parcels if par.get('kw')]))
        street = ', '.join(dict.fromkeys([par.get('parcel_address','') for par in parcels if par.get('parcel_address')]))
        owners.append({
            'full_name':raw, 'name_plural':raw, 'name_separate':raw, 'first_name':fn, 'last_name':ln, 'last_name_plural':ln,
            'address':addr, 'address_2':e.get('address2',''), 'city':'', 'parcels':parcels, 'parcel_street':street,
            'total_area_ha':total_area, 'share':'1/1', 'kw_numbers':kw_numbers, 'is_couple':False, 'is_dead':False,
            'is_institution':is_inst, 'is_company':is_company, 'is_spolka':is_spolka, 'is_church':is_church,
            'status_sprawy':'Do zrobienia', **meta
        })
    return owners

def extract_wypis_metadata_file(pdf_path: str) -> dict:
    """Odczytuje nagłówek wypisu razem z listą wszystkich wartości.

    Jeden wypis może obejmować kilka obrębów, gmin, a nawet powiatów. Dlatego
    zwracamy zarówno tekst połączony (np. "Polki, Borkowo"), jak i pełne listy
    w kluczach ``*_values``, aby moduł Wypisy mógł przypisać właściwą wartość
    do konkretnej działki zamiast brać wyłącznie pierwszą znalezioną.
    """
    empty = {field: '' for field in _WYPIS_META_FIELDS}
    empty.update({f'{field}_values': [] for field in _WYPIS_META_FIELDS})
    empty['has_multiple'] = False

    try:
        doc = fitz.open(pdf_path)
        text = "\n".join(page.get_text() for page in doc).replace('\r\n', '\n').replace('\r', '\n')
        doc.close()
    except Exception:
        return empty

    meta = _extract_wypis_metadata_text(text)

    # Zapasowo korzystamy ze starszego odczytu bloku tabelarycznego, który
    # radzi sobie z wypisami uproszczonymi bez wyraźnych etykiet w liniach.
    legacy = _extract_meta_simplified_wypis(text)
    for field in _WYPIS_META_FIELDS:
        if not meta.get(field) and legacy.get(field):
            value = str(legacy.get(field) or '').strip()
            meta[field] = value
            if value:
                meta[f'{field}_values'] = [value]
    return meta

def extract_wypis_parcel_metadata_file(pdf_path: str) -> dict:
    """Zwraca metadane przypisane do konkretnych działek z pliku wypisu.

    Klucz to numer działki, wartość to słownik z polami województwo, powiat,
    jednostka ewidencyjna, obręb i numer obrębu. Dzięki temu wypis obejmujący
    kilka obrębów nie nadpisuje wszystkich działek pierwszą znalezioną nazwą.
    """
    from utils.wypis_metadata import parcel_meta_map

    try:
        doc = fitz.open(pdf_path)
        text = "\n".join(page.get_text() for page in doc).replace('\r\n', '\n').replace('\r', '\n')
        doc.close()
    except Exception:
        return {}
    return parcel_meta_map(text)


def parse_wypis_pdf(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    all_owners = []
    simplified_any = False
    for page in doc:
        page_text = page.get_text().replace('\r\n', '\n').replace('\r', '\n')
        parsed = _parse_simplified_wypis_page(page_text)
        if parsed:
            all_owners.extend(parsed)
            simplified_any = True
    if simplified_any:
        _merge_same_owners(all_owners)
        return all_owners
    full_text = "".join(page.get_text() for page in doc).replace('\r\n', '\n').replace('\r', '\n')
    full_text = _clean_multipage_garbage(full_text)
    chunks = re.split(r'(?=Wojew[oó]dztwo\b)', full_text, flags=re.I)
    for chunk in chunks:
        if not chunk.strip(): continue
        global_meta = {'voivodeship': '', 'county': '', 'municipality': '', 'precinct': '', 'precinct_number': ''}
        wm = re.search(r'\bWojew[oó]dztwo\b\s*:?\s*([^\n]+)', chunk, re.I)
        if wm: 
            v = wm.group(1).strip()
            v = re.split(r'(?i)\b(Powiat|Gmina|Jednostka|Obręb)\b', v)[0].strip(' ,-')
            global_meta['voivodeship'] = v
        pm = re.search(r'\bPowiat\b\s*:?\s*([^\n]+)', chunk, re.I)
        if pm: 
            v = pm.group(1).strip()
            v = re.split(r'(?i)\b(Gmina|Jednostka|Obręb|Województwo)\b', v)[0].strip(' ,-')
            if v.lower() not in ['owe w']: 
                global_meta['county'] = v
        jm = re.search(r'\b(?:Gmina|Jednostka ewidencyjna)\b\s*:?\s*([^\n]+)', chunk, re.I)
        if jm: 
            v = jm.group(1).strip()
            v = re.split(r'(?i)\b(Obręb|Województwo|Powiat)\b', v)[0].strip(' ,-')
            if ',' in v: v = v.split(',')[-1].strip()
            global_meta['municipality'] = v.split('-')[0].strip() if '-' in v else v
        om = re.search(r'\bObr[eę]b\b(?: ewidencyjny)?\s*:?\s*([^\n]+)', chunk, re.I)
        if om: 
            v = om.group(1).strip()
            v = re.split(r'(?i)Nr\s+Kancelaryjny', v)[0].strip(' ,-')
            m_num = re.search(r'(?:Nr\s*)?0*(\d+)\s*[,\- ]+\s*(.+)', v, re.I)
            if m_num:
                global_meta['precinct_number'] = m_num.group(1).strip()
                global_meta['precinct'] = m_num.group(2).strip()
            else:
                if v.isdigit(): global_meta['precinct_number'] = str(int(v))
                else: global_meta['precinct'] = v
        chunk_parcels = _extract_parcels_from_text(chunk)
        # Fragment może zawierać kilka obrębów lub gmin. Każdej działce
        # przypisujemy wartość z jej własnej sekcji, a global_meta służy tylko
        # jako wartość zapasowa dla działek spoza rozpoznanych sekcji.
        _merge_wypis_meta_into_parcels(chunk_parcels, chunk, global_meta)
        for p in chunk_parcels:
            for k, v in global_meta.items():
                if k not in p: p[k] = v

        # Właściciel dostaje zestawienie wszystkich wartości występujących przy
        # jego działkach, dzięki czemu pola Obręb/Powiat/Województwo nie gubią
        # drugiego i kolejnych obrębów z tego samego wypisu.
        def _owner_meta_from_parcels(owner_parcels: list) -> dict:
            collected = {field: [] for field in _WYPIS_META_FIELDS}
            for parcel in owner_parcels:
                if not isinstance(parcel, dict):
                    continue
                for field in _WYPIS_META_FIELDS:
                    value = str(parcel.get(field, '') or '').strip()
                    if value and value not in collected[field]:
                        collected[field].append(value)
            return {
                field: ', '.join(values)
                for field, values in collected.items()
                if values
            }

        for block in _split_into_owner_blocks(chunk):
            parsed_list = _parse_owner_block(block, chunk_parcels)
            for owner in parsed_list:
                owner_meta = _owner_meta_from_parcels(owner.get('parcels', []))
                for k, v in global_meta.items():
                    value = owner_meta.get(k) or v
                    if k not in owner or not owner[k]:
                        owner[k] = value
                all_owners.append(owner)
    _merge_same_owners(all_owners)
    return all_owners

def _split_into_owner_blocks(text: str) -> list[str]:
    pattern = re.compile(
        r'((?:wsp[oó]lno[sś][cć][^\n]*\n\s*)?\d+/\d+\s*\n\s*(?:własno[sś][sś]?ć|własno[sś][sś]?\s|współwłasno[sś][sś]?ć|u[żz]ytkowanie wieczyste|dzier[żz]awa|trwały zarz[ąa]d|wsp[oó]lno[sś][cć]))', 
        re.IGNORECASE
    )
    positions = [m.start() for m in pattern.finditer(text)]
    if not positions: return [text]
    return [text[pos:positions[i+1] if i+1 < len(positions) else len(text)] for i, pos in enumerate(positions)]

def _parse_owner_block(block: str, global_parcels: list) -> list[dict]:
    lines = [l.strip() for l in block.split('\n') if l.strip()]
    if not lines: return []
    share = "1/1"
    for line in lines[:5]:
        share_match = re.search(r'(\d+/\d+)', line)
        if share_match:
            share = share_match.group(1)
            break
    entities = []
    current_entity = None
    for line in lines:
        lower_line = line.lower()
        if re.match(r'^\d+/\d+$', line): continue
        if re.match(r'^(własno[sś]|współwłasno[sś]|wsp[oó]lno[sś]c|u[żz]ytkowanie|dzier[żz]awa|trwały zarz[ąa]d)', line, re.I): continue
        if "ustawowa" in lower_line: continue
        if "ewidencyjne:" in lower_line or "jednostka:" in lower_line or "działki" in lower_line or "uwaga:" in lower_line: 
            break 
        if lower_line.startswith('stały pobyt:'):
            if current_entity: current_entity['address'] = line[12:].strip()
            continue
        is_address_line = lower_line.startswith('adres:') or lower_line.startswith('siedziba:') or lower_line.startswith('koresp')
        if is_address_line:
            is_siedziba = lower_line.startswith('siedziba:')
            if lower_line.startswith('adres:'): addr_val = line[6:].strip()
            elif lower_line.startswith('siedziba:'): addr_val = line[9:].strip()
            else: addr_val = re.sub(r'^koresp\.?:?\s*', '', line, flags=re.I).strip()
            if current_entity:
                if is_siedziba: current_entity['has_siedziba'] = True
                if current_entity['address'] and current_entity['address'] != addr_val:
                    current_entity['address2'] = addr_val
                else: current_entity['address'] = addr_val
            continue
        if not re.match(r'^\d+(/\d+)?$', line) and not re.match(r'^\d+[.,]\d{4}$', line) and 'dane osoby' not in lower_line:
            is_dead = "osoba nie żyje" in lower_line
            clean_name = re.sub(r'\(.*?\)', '', line).replace('/osoba nie żyje/', '').strip()
            clean_name = clean_name.strip('/*,; "')
            clean_name = _abbreviate_company_name(clean_name)
            if clean_name:
                current_entity = {'raw_name': clean_name, 'is_dead': is_dead, 'address': '', 'address2': '', 'has_siedziba': False}
                entities.append(current_entity)
    if len(entities) > 1 and any(e.get('has_siedziba') for e in entities):
        entities = [e for e in entities if e.get('has_siedziba')]
    last_addr = ""
    for e in reversed(entities):
        if e['address']: last_addr = e['address']
        elif last_addr: e['address'] = last_addr
    last_addr = ""
    for e in entities:
        if e['address']: last_addr = e['address']
        elif last_addr: e['address'] = last_addr
    import copy
    parcels = copy.deepcopy(global_parcels)
    kw_numbers = list(set(p['kw'] for p in parcels if p.get('kw')))
    total_area = sum(p['area_ha'] for p in parcels)
    ulice_dz = []
    for p in parcels:
        if p.get('parcel_address') and p['parcel_address'] not in ulice_dz:
            ulice_dz.append(p['parcel_address'])
    parcel_street_str = ", ".join(ulice_dz)
    owners_output = []
    is_wspolnosc = any("wspólnos" in line.lower() or "wspólnoś" in line.lower() or "wspolnos" in line.lower() for line in lines)
    any_dead = any(e['is_dead'] for e in entities)
    is_couple = False
    from utils.gender_utils import get_couple_last_name
    if len(entities) == 2 and not any_dead and not any(e.get('has_siedziba') for e in entities):
        e1, e2 = entities[0], entities[1]
        parts1 = e1['raw_name'].split()
        parts2 = e2['raw_name'].split()
        n1 = parts1[0] if len(parts1) > 0 else ""
        n2 = parts2[0] if len(parts2) > 0 else ""
        if is_wspolnosc or n1 == n2 or get_couple_last_name(n1, n2):
            is_couple = True
    if is_couple:
        e1, e2 = entities[0], entities[1]
        parts1 = e1['raw_name'].split()
        parts2 = e2['raw_name'].split()
        n1 = parts1[0] if len(parts1) > 0 else ""; f1 = parts1[1] if len(parts1) > 1 else ""
        n2 = parts2[0] if len(parts2) > 0 else ""; f2 = parts2[1] if len(parts2) > 1 else ""
        if not f1: f1 = n1; n1 = ""
        if not f2: f2 = n2; n2 = ""
        if not n1: n1 = n2
        if not n2: n2 = n1
        from utils.gender_utils import detect_gender
        g1 = detect_gender(f1)
        g2 = detect_gender(f2)
        if g1 == 'M' and g2 == 'F':
            f1, f2 = f2, f1
            n1, n2 = n2, n1
        n_plural = get_couple_last_name(n1, n2)
        if n_plural: name_plural = f"{f1} i {f2} {n_plural}".strip()
        elif n1 == n2: name_plural = f"{f1} i {f2} {n1}".strip()
        else: name_plural = f"{f1} {n1} i {f2} {n2}".strip()
        name_separate = f"{f1} {n1} i {f2} {n2}".strip()
        addr1 = e1['address']; addr2 = e2['address']
        if addr1 == addr2: addr2 = ""
        owners_output.append({
            'full_name': name_plural, 'name_plural': name_plural, 'name_separate': name_separate,
            'first_name': f"{f1} i {f2}".strip(), 'last_name': n1,
            'last_name_plural': n_plural if n_plural else n1, 
            'address': addr1, 'address_2': addr2, 'city': '', 'parcels': parcels,
            'parcel_street': parcel_street_str, 'total_area_ha': total_area, 'share': share, 'kw_numbers': kw_numbers,
            'is_couple': True, 'is_dead': False, 'is_institution': False, 'is_company': False, 'is_spolka': False, 'is_church': False,
            'status_sprawy': 'Do zrobienia'
        })
    else:
        for e in entities:
            addr = e['address']
            raw = e['raw_name']
            is_church = any(k in raw.upper() for k in ['PARAFIA', 'KOŚCIÓŁ', 'DIECEZJA', 'ARCHIDIECEZJA', 'PROWINCJA', 'EPISKOPAT', 'KURIA'])
            is_inst = any(k in raw.upper() for k in ['GMINA', 'SKARB PAŃSTWA', 'NADLEŚNICTWO', 'ZARZĄD', 'POWIAT', 'WOJEWÓDZTWO', 'URZĄD', 'MIASTO', 'PAŃSTWOWE', ' PKP'])
            is_spolka = any(k in raw.upper() for k in ['SPÓŁKA', 'SP. Z O.O.', ' S.A.', 'SPÓŁDZIELNIA', 'SPÓŁDZIELNI'])
            is_company = any(k in raw.upper() for k in ['PRZEDSIĘBIORSTWO', 'F.H.U']) or e.get('has_siedziba')
            if is_church: is_inst = False; is_company = False; is_spolka = False
            elif is_spolka: is_inst = False; is_company = False
            elif is_company: is_inst = False
            ln, fn = raw, ""
            if not is_inst and not is_church and not is_company and not is_spolka:
                parts = raw.split()
                if len(parts) >= 2:
                    ln = parts[0]; fn = parts[1] 
                    raw = f"{fn} {ln}".strip()
            owners_output.append({
                'full_name': raw, 'name_plural': raw, 'name_separate': raw,
                'first_name': fn, 'last_name': ln, 'last_name_plural': ln, 
                'address': addr, 'address_2': e.get('address2', ''), 'city': '', 'parcels': parcels,
                'parcel_street': parcel_street_str, 'total_area_ha': total_area, 'share': share, 'kw_numbers': kw_numbers,
                'is_couple': False, 'is_dead': e['is_dead'], 
                'is_institution': is_inst, 'is_company': is_company, 'is_spolka': is_spolka, 'is_church': is_church,
                'status_sprawy': 'Do zrobienia'
            })
    return owners_output

def _extract_parcels_from_text(text: str) -> list[dict]:
    parcels = []
    lines = text.split('\n')
    current_parcel = None
    kw_mem = ""
    address_buffer = ""
    last_identifier = ""
    expect_identifier_line = False
    expect_parcel_location_line = False
    expect_parcel_number_line = False
    def _is_bad_parcel_location(value: str) -> bool:
        low = str(value or '').lower().strip()
        bad = [
            'grunty przeznaczone', 'przeznaczone pod budowę', 'budowę dróg',
            'drog publicznych', 'dróg publicznych', 'linii kolejowych', 'kolejowych',
            'określenie konturów', 'okreslenie konturow', 'konturów', 'konturow',
            'użytków gruntowych', 'uzytkow gruntowych', 'klas bonitacyjnych',
            'bonitacyjnych', 'opis', 'oznacz', 'użytek', 'uzytek', 'klasa',
            'tp', 'dr', 'ls', 'rvi'
        ]
        return any(x in low for x in bad)
    for line in lines:
        line = line.strip()
        if not line: continue
        low_line = line.lower()
        if re.search(r'^(oznaczenie\s+dzia[łl]ki|numer\s+dzia[łl]ki)\s*:?\s*$', line, re.I):
            expect_parcel_number_line = True
            continue
        if expect_parcel_number_line:
            candidate = line.strip(' ,;:')
            if re.match(r'^\d+(?:/\d+)+$', candidate) or re.match(r'^\d{1,6}$', candidate):
                if current_parcel and (current_parcel.get('area_ha', 0) > 0 or current_parcel.get('kw') or current_parcel.get('parcel_address') or current_parcel.get('identifier')):
                    parcels.append(current_parcel)
                current_parcel = {'number': candidate, 'area_ha': 0.0, 'kw': kw_mem, 'parcel_address': '', 'identifier': last_identifier}
                address_buffer = ""
            expect_parcel_number_line = False
            continue
        if re.fullmatch(r'\d{1,6}(?:/[A-Za-z\d]+)?', line):
            if current_parcel and (current_parcel.get('area_ha', 0) > 0 or current_parcel.get('kw') or current_parcel.get('parcel_address') or current_parcel.get('identifier')):
                parcels.append(current_parcel)
            current_parcel = {'number': line, 'area_ha': 0.0, 'kw': kw_mem, 'parcel_address': '', 'identifier': last_identifier}
            address_buffer = ""
            continue
        if expect_identifier_line:
            ident = line.strip(' ,;:')
            if ident:
                last_identifier = ident
                if current_parcel: current_parcel['identifier'] = ident
            expect_identifier_line = False
            continue
        m_id = re.search(r'Identyfikator\s+dzia[łl]ki\s*:?\s*([0-9A-Za-z_.\-/]+)?', line, re.I)
        if m_id:
            ident = (m_id.group(1) or '').strip()
            if ident:
                last_identifier = ident
                if current_parcel: current_parcel['identifier'] = ident
            else: expect_identifier_line = True
            continue
        if expect_parcel_location_line:
            val = line.strip(' ,;:')
            if current_parcel and val and not _is_bad_parcel_location(val) and not re.search(r'^(oznaczenie|numer|powierzchnia|identyfikator|określenie|opis)\b', low_line):
                current_parcel['parcel_address'] = val
            expect_parcel_location_line = False
            continue
        if 'bliższe określenie położenia' in low_line or 'blizsze okreslenie polozenia' in low_line:
            val = re.split(r':', line, maxsplit=1)
            if len(val) > 1 and val[1].strip() and current_parcel:
                candidate_loc = val[1].strip(' ,;:')
                if not _is_bad_parcel_location(candidate_loc):
                    current_parcel['parcel_address'] = candidate_loc
            else: expect_parcel_location_line = True
            continue
        m_kw = re.search(r'([A-Z]{2,4}\d?[A-Z]?\s*/\s*\d+\s*/\s*\d)', line)
        if m_kw: 
            kw_mem = re.sub(r'\s+', '', m_kw.group(1))
            if current_parcel: current_parcel['kw'] = kw_mem
        parts = line.split()
        if not parts: continue
        is_potential_parcel = False
        if re.match(r'^\d+/\d+$', parts[0]): is_potential_parcel = True
        line_clean = line
        teryt_match = re.search(r'\b(\d{2,6}[_\s\.-]+\d[_\s\.-]+\d{1,4}[_\s\.-]+(\d+(?:/[A-Za-z\d]+)?))\b', line_clean)
        if teryt_match:
            ident_val = teryt_match.group(1)
            parcel_num = teryt_match.group(2)
            if current_parcel:
                if current_parcel['number'] == parcel_num or current_parcel['number'] in ident_val:
                    current_parcel['identifier'] = ident_val
                else:
                    if current_parcel.get('area_ha', 0) > 0 or current_parcel.get('kw') or current_parcel.get('identifier'):
                        parcels.append(current_parcel)
                    current_parcel = {'number': parcel_num, 'area_ha': 0.0, 'kw': kw_mem, 'parcel_address': '', 'identifier': ident_val}
                    address_buffer = ""
            else:
                current_parcel = {'number': parcel_num, 'area_ha': 0.0, 'kw': kw_mem, 'parcel_address': '', 'identifier': ident_val}
                address_buffer = ""
            last_identifier = ident_val
            line_clean = line_clean.replace(ident_val, ' ').strip()
        if current_parcel:
            num_pattern = re.escape(current_parcel['number'])
            line_clean = re.sub(rf'^{num_pattern}\b', '', line_clean).strip()
            line_clean = re.sub(r'^[/\s]+', '', line_clean).strip()
        m_area = re.search(r'(?:^|\s)(\d{1,4}(?:[.,]|\s+)\d{2,4})(?:\s|[A-Za-z]|$)', line_clean)
        if is_potential_parcel and m_area and line_clean.startswith(m_area.group(1)):
            is_potential_parcel = False
        if is_potential_parcel:
            if current_parcel and (current_parcel.get('area_ha', 0) > 0 or current_parcel.get('kw') or current_parcel.get('parcel_address') or current_parcel.get('identifier')):
                parcels.append(current_parcel)
            if "własno" in line.lower() or "udział" in line.lower() or "wspólnosc" in line.lower() or "wspólno" in line.lower():
                continue
            current_parcel = {'number': parts[0], 'area_ha': 0.0, 'kw': kw_mem, 'parcel_address': '', 'identifier': last_identifier}
            address_buffer = ""
        if current_parcel and current_parcel['area_ha'] == 0.0:
            if m_area:
                area_raw = m_area.group(1)
                area_str = re.sub(r'[\s,]+', '.', area_raw)
                try: current_parcel['area_ha'] = float(area_str)
                except ValueError: pass
                before_area = line_clean[:m_area.start()].strip()
                if before_area and not _is_bad_parcel_location(before_area):
                    address_buffer += " " + before_area
                final_addr = address_buffer.strip(',; -')
                if final_addr and not current_parcel.get('parcel_address') and not _is_bad_parcel_location(final_addr):
                    current_parcel['parcel_address'] = final_addr
            else:
                lower = line_clean.lower()
                if lower and not re.match(r'^[\d\s\.,/:-]+$', lower):
                    skip = ['bliższe określenie położenia', 'blizsze okreslenie polozenia', 'identyfikator', 'powierzchnia', 'użytek', 'klasa', 'oznaczenie', 'numer działki', 'adres']
                    if not any(w in lower for w in skip) and not _is_bad_parcel_location(lower):
                        if "własno" not in lower and "udział" not in lower:
                            address_buffer += " " + line_clean
                            address_buffer = address_buffer.strip()
    if current_parcel and (current_parcel.get('area_ha', 0) > 0 or current_parcel.get('kw') or current_parcel.get('parcel_address') or current_parcel.get('identifier')): 
        parcels.append(current_parcel)
    for p in parcels:
        if p.get('parcel_address') and _is_bad_parcel_location(p.get('parcel_address')):
            p['parcel_address'] = ''
    unique_p = {}
    for p in parcels:
        if p['number'] in unique_p:
            if p['kw'] and not unique_p[p['number']]['kw']: unique_p[p['number']]['kw'] = p['kw']
            if p['area_ha'] > 0 and unique_p[p['number']]['area_ha'] == 0.0: unique_p[p['number']]['area_ha'] = p['area_ha']
            if p.get('parcel_address') and not unique_p[p['number']].get('parcel_address'): unique_p[p['number']]['parcel_address'] = p['parcel_address']
            if p.get('identifier') and not unique_p[p['number']].get('identifier'): unique_p[p['number']]['identifier'] = p['identifier']
        else: unique_p[p['number']] = p
    return list(unique_p.values())

def _merge_same_owners(owners: list):
    merged = {}
    for o in owners:
        key = (o.get('name_plural', o['full_name']).lower(), o['address'].lower())
        if key in merged:
            existing_keys = {(p['number'], p.get('municipality', ''), p.get('precinct', '')) for p in merged[key]['parcels']}
            for new_p in o['parcels']:
                p_key = (new_p['number'], new_p.get('municipality', ''), new_p.get('precinct', ''))
                if p_key not in existing_keys:
                    merged[key]['parcels'].append(new_p)
                    existing_keys.add(p_key)
            merged[key]['total_area_ha'] = sum(p['area_ha'] for p in merged[key]['parcels'])
        else: merged[key] = o
    owners.clear(); owners.extend(merged.values())

def parse_parcel_list_text(text: str) -> dict:
    result = {'demolition': [], 'construction': [], 'full': [], 'connection': [], 'by_precinct': {}}
    current_cat, current_prec = 'full', None
    for line in text.replace(',', '\n').replace(';', '\n').split('\n'):
        line = line.strip()
        if not line: continue
        low = line.lower()
        if 'demonta' in low: current_cat = 'demolition'; continue
        if 'budow' in low: current_cat = 'construction'; continue
        if 'przyłącz' in low or 'przylacz' in low: current_cat = 'connection'; continue
        if 'pe' in low and 'na' in low: current_cat = 'full'; continue
        if 'obr' in low:
            current_prec = line
            if current_prec not in result['by_precinct']: result['by_precinct'][current_prec] = {'demolition': [], 'construction': [], 'full': [], 'connection': []}
            continue
        for token in re.split(r'[\s,;]+', line):
            if re.match(r'^\d+(/\d+)?$', token.strip()):
                result[current_cat].append(token.strip())
                if current_prec: result['by_precinct'][current_prec][current_cat].append(token.strip())
    seen = set()
    result['full'] = [x for x in result['full'] if not (x in seen or seen.add(x))]
    return result

def parse_parcel_list_file(filepath: str) -> dict:
    path = Path(filepath); ext = path.suffix.lower()
    if ext == '.txt': return parse_parcel_list_text(path.read_text(encoding='utf-8', errors='replace'))
    elif ext in ('.doc', '.docx'): import docx as python_docx; return parse_parcel_list_text('\n'.join(p.text for p in python_docx.Document(filepath).paragraphs))
    elif ext in ('.xls', '.xlsx', '.xlsm'): import openpyxl; return parse_parcel_list_text('\n'.join([str(c) for r in openpyxl.load_workbook(filepath, read_only=True, data_only=True).active.iter_rows(values_only=True) for c in r if c]))
    return {'demolition': [], 'construction': [], 'full': [], 'connection': [], 'by_precinct': {}}

def extract_stamps_from_pdf(pdf_path: str, envelope_type: str = 'C5', stamp_profile: dict = None, max_stamps: int = 0) -> list[dict]:
    barcode_re = re.compile(r'\(00\)\d[\d ]+')
    if stamp_profile is None: stamp_profile = {'crop_left': 90, 'crop_right': 90, 'crop_up': 136, 'crop_down': 2} if envelope_type == 'C5' else {'crop_left': 0, 'crop_right': 0, 'crop_up': 0, 'crop_down': 0}
    cl, cr, cu, cd = stamp_profile.get('crop_left', 0), stamp_profile.get('crop_right', 0), stamp_profile.get('crop_up', 0), stamp_profile.get('crop_down', 0)
    doc = fitz.open(pdf_path); stamps, stamp_index = [], 0
    for page_num, page in enumerate(doc):
        if envelope_type == 'C5':
            barcode_blocks = [b for b in page.get_text("blocks") if b[6] == 0 and barcode_re.search(b[4])]
            barcode_blocks.sort(key=lambda b: (round(b[3] / 50) * 50, b[0]))
            for b in barcode_blocks:
                ax, ay = (b[0] + b[2]) / 2, b[3]
                sr = fitz.Rect(max(0, ax - cl), max(0, ay - cu), min(page.rect.width, ax + cr), min(page.rect.height, ay + cd))
                if sr.width > 10 and sr.height > 10:
                    stamps.append({'index': stamp_index, 'page': page_num, 'barcode': re.sub(r'\s+', '', b[4].strip()), 'rect': [sr.x0, sr.y0, sr.x1, sr.y1], 'used': False, 'used_by': '', 'pdf_path': pdf_path})
                    stamp_index += 1
                    if 0 < max_stamps <= len(stamps): doc.close(); return stamps
        else:
            image_rects = [r for img in page.get_images(full=True) for r in page.get_image_rects(img[0]) if r.width > 50 and r.height > 20]
            unique_rects, seen = [], set()
            for r in sorted(image_rects, key=lambda r: (round(r.y0 / 50) * 50, r.x0)):
                if (round(r.x0), round(r.y0)) not in seen:
                    seen.add((round(r.x0), round(r.y0)))
                    unique_rects.append(r)
            for r in unique_rects:
                sr = fitz.Rect(max(0, r.x0 + cl), max(0, r.y0 + cu), min(page.rect.width, r.x1 - cr), min(page.rect.height, r.y1 - cd))
                if sr.width > 10 and sr.height > 10:
                    stamps.append({'index': stamp_index, 'page': page_num, 'barcode': '', 'rect': [sr.x0, sr.y0, sr.x1, sr.y1], 'used': False, 'used_by': '', 'pdf_path': pdf_path})
                    stamp_index += 1
                    if 0 < max_stamps <= len(stamps): doc.close(); return stamps
    doc.close(); return stamps

def render_stamp_thumbnail(pdf_path: str, page_num: int, rect_list: list, size: int = 160) -> bytes:
    doc = fitz.open(pdf_path); clip = fitz.Rect(rect_list) & doc[page_num].rect
    if clip.is_empty or clip.width < 5 or clip.height < 5: doc.close(); return b''
    res = doc[page_num].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), clip=clip, alpha=False, colorspace=fitz.csRGB).tobytes("png")
    doc.close(); return res

def render_stamp_preview(pdf_path: str, envelope_type: str, profile: dict) -> bytes:
    stamps = extract_stamps_from_pdf(pdf_path, envelope_type, profile, max_stamps=1)
    if not stamps: return b''
    return render_stamp_thumbnail(pdf_path, stamps[0]['page'], stamps[0]['rect'], size=300)

def _detect_pdf_slots(doc, cols: int, rows: int) -> list[dict]:
    slots = []
    for page_idx, page in enumerate(doc):
        page_w, page_h = page.rect.width or 595, page.rect.height or 842
        zone_w, zone_h = page_w / max(1, cols), page_h / max(1, rows)
        page_slots = {}
        for r in page.search_for("NADAWCA:"):
            cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
            c = min(int(max(0, cx) // zone_w), cols - 1)
            row = min(int(max(0, cy) // zone_h), rows - 1)
            pos_idx = row * cols + c
            if pos_idx not in page_slots: page_slots[pos_idx] = ""
        for b in page.get_text("blocks"):
            m = re.search(r'\(00\)\s*\d[\d\s]+', b[4])
            if m:
                barcode = re.sub(r'\s+', '', m.group(0))
                cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                c = min(int(max(0, cx) // zone_w), cols - 1)
                row = min(int(max(0, cy) // zone_h), rows - 1)
                pos_idx = row * cols + c
                page_slots[pos_idx] = barcode
        for pos_idx, barcode in sorted(page_slots.items()):
            slots.append({'page_idx': page_idx, 'pos_idx': pos_idx, 'barcode': barcode})
    return slots

def get_druczek_capacity(pdf_path: str, cols: int = 2, rows: int = 2) -> int:
    try:
        doc = fitz.open(pdf_path)
        count = len(_detect_pdf_slots(doc, cols, rows))
        doc.close()
        return count
    except: return 0

def _get_positions_from_profile(profile: dict) -> list[dict]:
    cols, rows = profile.get('cols', 2), profile.get('rows', 2)
    dx, dy = profile.get('delta_x', 288), profile.get('delta_y', 405)
    positions = []
    for r in range(rows):
        for c in range(cols): positions.append({'bx': c * dx, 'by': r * dy})
    return positions

def _draw_field(page, text, pfx, pos, font_name, profile, color=(0,0,0), show_boxes=False):
    if not text and not show_boxes: return
    x = pos['bx'] + float(profile.get(f'{pfx}_x', 0))
    y = pos['by'] + float(profile.get(f'{pfx}_y', 0))
    w = float(profile.get(f'{pfx}_w', 150))
    h = float(profile.get(f'{pfx}_h', 30))
    if w < 20: w = 150
    if h < 15: h = 30
    sz = float(profile.get(f'{pfx}_size', 10))
    al = int(profile.get(f'{pfx}_align', 0))
    lh = float(profile.get(f'{pfx}_lh', 1.2))
    rect = fitz.Rect(x, y, x+w, y+h)
    if show_boxes: page.draw_rect(rect, color=(1, 0, 0), width=1.5, fill=(1, 0.8, 0.8), fill_opacity=0.4, dashes="[2 2] 0")
    if text:
        rc = page.insert_textbox(rect, str(text), fontsize=sz, fontname=font_name, color=color, align=al, lineheight=lh)
        if rc < 0 and show_boxes: page.insert_text((x, y + sz), f"{text} (Powiększ Ramkę!)", fontsize=max(6, sz-3), fontname=font_name, color=(1,0,0))

def _clean_bc(bc: str) -> str:
    c = re.sub(r'\D', '', bc)
    if c.startswith('00'): c = c[2:]
    return c

def _all_pdf_permissions() -> int:
    """Zwraca komplet uprawnień PDF (druk, edycja, kopiowanie, komentarze...)."""
    names = (
        'PDF_PERM_PRINT', 'PDF_PERM_MODIFY', 'PDF_PERM_COPY',
        'PDF_PERM_ANNOTATE', 'PDF_PERM_FORM', 'PDF_PERM_ACCESSIBILITY',
        'PDF_PERM_ASSEMBLE', 'PDF_PERM_PRINT_HQ',
    )
    permissions = 0
    for name in names:
        value = getattr(fitz, name, None)
        if isinstance(value, int):
            permissions |= value
    return permissions or -1


def _save_editable_pdf(doc, output_path: str):
    """Zapisuje PDF bez blokad, żeby dało się go edytować w innych programach.

    Druczki pobrane z Poczty Polskiej mają ustawione hasło właściciela
    i ograniczenia uprawnień. PyMuPDF domyślnie przepisuje te ograniczenia do
    pliku wynikowego, przez co gotowy druczek otwierał się tylko do odczytu.
    Zapisujemy więc jawnie bez szyfrowania i z pełnymi uprawnieniami.
    """
    save_attempts = (
        dict(
            garbage=4,
            deflate=True,
            clean=True,
            encryption=getattr(fitz, 'PDF_ENCRYPT_NONE', 0),
            permissions=_all_pdf_permissions(),
            owner_pw='',
            user_pw='',
        ),
        dict(
            garbage=4,
            deflate=True,
            clean=True,
            encryption=getattr(fitz, 'PDF_ENCRYPT_NONE', 0),
        ),
        dict(garbage=4, deflate=True),
        {},
    )
    last_error = None
    for kwargs in save_attempts:
        try:
            doc.save(output_path, **kwargs)
            return
        except Exception as exc:  # pragma: no cover - zależne od wersji PyMuPDF
            last_error = exc
    raise last_error if last_error else RuntimeError('Nie udało się zapisać PDF')


def fill_neoznacze_pdf(template_path: str, output_path: str, shipments: list, sender_info: dict, profile: dict = None) -> tuple[bool, int]:
    try:
        doc = fitz.open(template_path)
        # Druczki z Poczty bywają zabezpieczone hasłem właściciela. Pustym
        # hasłem zdejmujemy blokadę, dzięki czemu wynik nie dziedziczy
        # ograniczeń uniemożliwiających późniejszą edycję.
        if getattr(doc, 'is_encrypted', False):
            try:
                doc.authenticate('')
            except Exception:
                pass
        if profile is None: profile = {}
        positions = _get_positions_from_profile(profile)
        available_slots = _detect_pdf_slots(doc, profile.get('cols', 2), profile.get('rows', 2))
        matched_assignments = []
        used_slots = set()
        for ship in shipments:
            if not ship:
                matched_assignments.append((ship, -1))
                continue
            target_slot = -1
            ship_bc = _clean_bc(ship.get('stamp_barcode', ''))
            if ship_bc and len(ship_bc) > 5:
                for i, slot in enumerate(available_slots):
                    slot_bc = _clean_bc(slot['barcode'])
                    if i not in used_slots and slot_bc and ship_bc in slot_bc:
                        target_slot = i; break
            if target_slot != -1:
                matched_assignments.append((ship, target_slot))
                used_slots.add(target_slot)
            else: matched_assignments.append((ship, -1)) 
        final_assignments = []
        for ship, target_slot in matched_assignments:
            if target_slot == -1:
                for i in range(len(available_slots)):
                    if i not in used_slots: target_slot = i; used_slots.add(i); break
            if target_slot != -1: final_assignments.append((ship, available_slots[target_slot]))
            else: break 
        sf = _get_font_path(profile.get('s_font', 'Arial'))
        af = _get_font_path(profile.get('a_font', 'Arial'))
        s_n, s_s = sender_info.get('name', ''), sender_info.get('street', '')
        s_z, s_c = _split_zip_city(sender_info.get('city', ''))
        for ship, slot in final_assignments:
            if not ship: continue 
            page = doc[slot['page_idx']]
            pos = positions[slot['pos_idx']]
            s_fname, a_fname = f"plfs_{slot['page_idx']}", f"plfa_{slot['page_idx']}"
            if sf: page.insert_font(fontname=s_fname, fontfile=sf)
            else: s_fname = "helv"
            if af: page.insert_font(fontname=a_fname, fontfile=af)
            else: a_fname = "helv"
            _draw_field(page, s_n, 'sn', pos, s_fname, profile)
            _draw_field(page, s_s, 'ss', pos, s_fname, profile)
            _draw_field(page, s_z, 'sz', pos, s_fname, profile)
            _draw_field(page, s_c, 'sc', pos, s_fname, profile)
            a_z, a_c = _split_zip_city(ship.get('addressee_city', ''))
            _draw_field(page, ship.get('addressee', ''), 'an', pos, a_fname, profile)
            _draw_field(page, ship.get('addressee_street', ''), 'as', pos, a_fname, profile)
            _draw_field(page, a_z, 'az', pos, a_fname, profile)
            _draw_field(page, a_c, 'ac', pos, a_fname, profile)
        _save_editable_pdf(doc, output_path)
        doc.close()
        return True, len([s for s, slot in final_assignments if s])
    except Exception as e:
        print(f"[fill_neoznacze_pdf] Error: {e}")
        return False, 0

def render_druczek_preview(template_path: str, profile: dict, sender_info: dict) -> bytes:
    try:
        doc = fitz.open(template_path)
        page = doc[0]
        sf = _get_font_path(profile.get('s_font', 'Arial'))
        af = _get_font_path(profile.get('a_font', 'Arial'))
        s_fname, a_fname = "plfont_s", "plfont_a"
        if sf: page.insert_font(fontname=s_fname, fontfile=sf)
        else: s_fname = "helv"
        if af: page.insert_font(fontname=a_fname, fontfile=af)
        else: a_fname = "helv"
        positions = _get_positions_from_profile(profile)
        s_n = sender_info.get('name') or 'NADAWCA TESTOWY'
        s_s = sender_info.get('street') or 'ul. Przykładowa 12'
        s_z, s_c = _split_zip_city(sender_info.get('city') or '00-000 Miasto')
        if not s_z: s_z = "00-000"; s_c = "Miasto"
        a_n, a_s, a_z, a_c = "Jan Kowalski", "ul. Testowa 99/2", "11-111", "Miejscowość"
        for pos in positions:
            _draw_field(page, s_n, 'sn', pos, s_fname, profile, color=(1,0,0), show_boxes=True)
            _draw_field(page, s_s, 'ss', pos, s_fname, profile, color=(1,0,0), show_boxes=True)
            _draw_field(page, s_z, 'sz', pos, s_fname, profile, color=(1,0,0), show_boxes=True)
            _draw_field(page, s_c, 'sc', pos, s_fname, profile, color=(1,0,0), show_boxes=True)
            _draw_field(page, a_n, 'an', pos, a_fname, profile, color=(1,0,0), show_boxes=True)
            _draw_field(page, a_s, 'as', pos, a_fname, profile, color=(1,0,0), show_boxes=True)
            _draw_field(page, a_z, 'az', pos, a_fname, profile, color=(1,0,0), show_boxes=True)
            _draw_field(page, a_c, 'ac', pos, a_fname, profile, color=(1,0,0), show_boxes=True)
        res = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False, colorspace=fitz.csRGB).tobytes("png")
        doc.close()
        return res
    except: return b''