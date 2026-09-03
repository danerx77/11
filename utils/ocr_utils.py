"""
ocr_utils.py – Narzędzia OCR (EasyOCR + Tesseract)
"""
import os
import re
from pathlib import Path


def _easyocr_reader_options() -> dict:
    """Zwraca opcje modelu dla przenośnego wydania PyInstaller.

    build_windows.ps1 pakuje wcześniej przygotowane modele do katalogu aplikacji.
    Nie pozwalamy wtedy EasyOCR pobierać brakujących plików do potencjalnie
    tylko-do-odczytu katalogu programu; przy niekompletnej paczce nastąpi
    kontrolowane przejście do awaryjnego OCR Tesseract.
    """
    bundled_model_dir = os.environ.get("ENERGODOK_EASYOCR_MODEL_DIR", "").strip()
    if not bundled_model_dir:
        # Zgodność ze starszym wydaniem programu.
        bundled_model_dir = os.environ.get(
            "PYSILDE6_EASYOCR_MODEL_DIR", ""
        ).strip()
    if bundled_model_dir:
        return {
            "model_storage_directory": bundled_model_dir,
            "download_enabled": False,
        }
    return {}


def run_ocr_on_image(image_path: str = None, image_array=None, lang: str = 'pl') -> str:
    try:
        import easyocr
        reader = easyocr.Reader(
            ['pl', 'en'],
            gpu=False,
            verbose=False,
            **_easyocr_reader_options(),
        )
        if image_array is not None:
            results = reader.readtext(image_array, detail=0, paragraph=True)
        else:
            results = reader.readtext(image_path, detail=0, paragraph=True)
        return '\n'.join(results)
    except Exception as e:
        print(f"[OCR] EasyOCR error: {e}")
        return run_tesseract_fallback(image_path, image_array, lang)

def run_tesseract_fallback(image_path: str = None, image_array=None, lang: str = 'pol') -> str:
    try:
        import pytesseract
        from PIL import Image
        if image_array is not None:
            from PIL import Image as PILImage
            img = PILImage.fromarray(image_array)
        else:
            img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=lang)
        return text
    except Exception as e:
        print(f"[OCR] Tesseract error: {e}")
        return ''

def ocr_screen_region(x: int, y: int, width: int, height: int) -> str:
    try:
        import mss
        import numpy as np
        with mss.mss() as sct:
            monitor = {"top": y, "left": x, "width": width, "height": height}
            screenshot = sct.grab(monitor)
            img_array = np.frombuffer(screenshot.bgra, dtype=np.uint8)
            img_array = img_array.reshape((screenshot.height, screenshot.width, 4))
            img_rgb = img_array[:, :, [2, 1, 0]]
        return run_ocr_on_image(image_array=img_rgb)
    except Exception as e:
        print(f"[OCR] Screen capture error: {e}")
        return ''

def parse_wypis_from_image(image_path: str) -> tuple[list, str]:
    """
    Wywoływana przez ImportWorker dla plików JPG/PNG. 
    Ze względu na duże błędy w OCR EGiB (rozbite linie), 
    dokonujemy rygorystycznego sklejania i ignorowania śmieci.
    Następnie wysyłamy do oryginalnego parsera z `pdf_utils.py` dla 100% zgodności.
    """
    raw_text = run_ocr_on_image(image_path=image_path)
    
    # 1. Czyszczenie i sklejanie typowych błędów OCR w EGiB
    text = raw_text
    text = re.sub(r'(?i)(znak)\s*\n\s*(sprawy:?)', r'\1 \2', text)
    text = re.sub(r'(?i)(jednostka)\s*\n\s*(ewidencyjna:?)', r'\1 \2', text)
    text = re.sub(r'(?i)(obręb)\s*\n\s*(ewidencyjny:?)', r'\1 \2', text)
    text = re.sub(r'(?i)(dane\s+osoby)\s*\n\s*(fizycznej)', r'\1 \2', text)
    text = re.sub(r'(?i)(strona)\s*\n\s*(\d+\s*z\s*\d+)', r'\1 \2', text)
    
    lines = text.split('\n')
    cleaned = []
    
    global_meta = {'voivodeship': '', 'county': '', 'municipality': '', 'precinct': '', 'precinct_number': ''}
    
    for line in lines:
        l = line.strip()
        l_low = l.lower()
        if not l: continue
        
        # Wyciąganie metadanych w taki sam sposób jak pdf_utils
        if 'województwo:' in l_low or 'powiat:' in l_low:
            wm = re.search(r'wojew[oó]dztwo:\s*([^\s]+)', l_low)
            pm = re.search(r'powiat:\s*([^\s]+)', l_low)
            if wm: global_meta['voivodeship'] = wm.group(1).title()
            if pm: global_meta['county'] = pm.group(1).title()
            continue
            
        if 'jednostka ewidencyjna:' in l_low:
            jm = re.search(r'jednostka ewidencyjna:[^\n]*,\s*([^\n]+)', l) or re.search(r'jednostka ewidencyjna:\s*([^\n,]+)', l)
            if jm: 
                muni = jm.group(1).strip()
                global_meta['municipality'] = muni.split('-')[0].strip() if '-' in muni else muni
            continue
            
        if 'obręb ewidencyjny:' in l_low:
            om = re.search(r'obr[eę]b ewidencyjny:[^\n]*,\s*([^\n]+)', l) or re.search(r'obr[eę]b ewidencyjny:\s*([^\n,]+)', l)
            om_num = re.search(r'obr[eę]b ewidencyjny:\s*0*(\d+)', l)
            if om: global_meta['precinct'] = om.group(1).strip()
            if om_num: global_meta['precinct_number'] = om_num.group(1).strip()
            continue

        # Ignorowanie śmieci przed złączeniem dla `pdf_utils`
        if l_low.startswith('znak sprawy'): continue
        if l_low.startswith('sprawy:'): continue
        if 'starosta' in l_low: continue
        if 'starosty' in l_low: continue
        if 'informacja z operatu' in l_low: continue
        if 'sporządzono dnia' in l_low: continue
        if 'wydruk z systemu' in l_low: continue
        if 'strona ' in l_low and ' z ' in l_low: continue
        if l_low == 'osoby:': continue
        if l_low.startswith('nr jednostki rejestrowej'): continue
        if l_low.startswith('działki ewidencyjne'): continue
        
        # ZOSTAWIAMY WAŻNE RZECZY: 1/1, formy władania, itp., by `pdf_utils` mogło zadziałać
        cleaned.append(l)

    cleaned_text = '\n'.join(cleaned)
    
    # Przekazujemy ładny, wyczyszczony z bełkotu tekst do potężnego analizatora z `pdf_utils.py`
    from utils.pdf_utils import _extract_parcels_from_text, _split_into_owner_blocks, _parse_owner_block, _merge_same_owners
    
    chunk_parcels = _extract_parcels_from_text(cleaned_text)
    for p in chunk_parcels:
        for k, v in global_meta.items():
            if k not in p: p[k] = v

    owners = []
    for block in _split_into_owner_blocks(cleaned_text):
        parsed_list = _parse_owner_block(block, chunk_parcels)
        for owner in parsed_list:
            for k, v in global_meta.items():
                if k not in owner or not owner[k]: owner[k] = v
            owners.append(owner)

    _merge_same_owners(owners)
    
    return owners, raw_text

def parse_ocr_land_data(text: str) -> dict:
    """
    Wyodrębnia obręb i numer działki z tekstu OCR ze Snip Tool.
    """
    result = {
        'precinct': '', 'parcel': '', 'municipality': '', 'county': '',
        'voivodeship': '', 'area_ha': '', 'kw': '',
    }
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        low = line.lower()
        if 'obr' in low and ('ewid' in low or 'enc' in low):
            after_colon = line.split(':')[-1].strip()
            if after_colon and len(after_colon) > 1: result['precinct'] = re.sub(r'^\d{4},?\s*', '', after_colon).strip()
            elif i + 1 < len(lines): result['precinct'] = re.sub(r'^\d{4},?\s*', '', lines[i + 1]).strip()

        elif 'numer dzia' in low or 'nr dzia' in low or 'dzia\u0142ki' in low:
            after_colon = line.split(':')[-1].strip()
            if after_colon:
                m = re.search(r'\b(\d+(?:/\d+)?)\b', after_colon)
                if m: result['parcel'] = m.group(1)
            elif i + 1 < len(lines):
                m = re.search(r'\b(\d+(?:/\d+)?)\b', lines[i + 1])
                if m: result['parcel'] = m.group(1)

        elif re.match(r'^\d+/\d+$', line) or re.match(r'^\d+$', line):
            if not result['parcel']: result['parcel'] = line

    return result