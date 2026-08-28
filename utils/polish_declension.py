"""
polish_declension.py – Odmiana polskich nazw miejscowości.

UWAGA: 
- WOJEWÓDZTWA nie są odmieniane (zostają jak są)
- POWIATY: miejscowości są ZAMIENIANE na nazwy powiatów (city_to_powiat)
- MIEJSCOWOŚCI: odmieniane przez miejscownik (decline_city)
- ULICE: odmieniane przez miejscownik (decline_street)

ZAMIANA miejscowości na powiat:
- "Kościerzyna" → "kościerski"
- "Wejherowo" → "wejherowski"
- itp.
"""

import unicodedata


def _lookup_key(value: str) -> str:
    """Normalizuje wielkość liter oraz polskie znaki na potrzeby słowników."""
    decomposed = unicodedata.normalize("NFD", str(value).casefold())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    # Ł/ł nie rozkłada się do litery bazowej w Unicode NFD.
    return without_marks.translate(str.maketrans({"ł": "l"}))


# ============================================================================
# SŁOWNIK: MIEJSCOWOŚĆ → NAZWA POWIATU
# ============================================================================

CITY_TO_POWIAT = {
    # MIEJSCOWOŚĆ: "Nazwa powiatu (małymi literami)",
    
    # Pomorze
    "Kościerzyna": "kościerski",
    "Koscierzyna": "kościerski",
    "Wejherowo": "wejherowski",
    "Wejherów": "wejherowski",
    "Wejherow": "wejherowski",
    "Kartuzy": "kartuski",
    "Gdańsk": "gdański",
    "Gdynia": "gdyński",
    "Sopot": "sopocki",
    "Tczew": "tczewski",
    "Starogard Gdański": "starogardzki",
    "Starogard Gdański": "starogardzki",
    "Malbork": "malborski",
    "Sztum": "sztumski",
    "Kwidzyń": "kwidzyński",
    "Kwidzyn": "kwidzyński",
    "Słupsk": "słupski",
    "Slupsk": "słupski",
    "Lębork": "lęborski",
    "Lebork": "lęborski",
    "Człuchów": "człuchowski",
    "Czluchow": "człuchowski",
    "Chojnice": "chojnicki",
    "Puck": "pucki",
    "Bytów": "bytowski",
    "Bytow": "bytowski",
    "Lubań": "lubański",
    "Luban": "lubański",
    " Grybów": "gorlicki",
    "Gorlice": "gorlicki",
    "Bielsko-Biała": "bielski",
    "Bielsko-Biala": "bielski",
    "Żywiec": "żywiecki",
    "Zywiec": "żywiecki",
    "Cieszyn": "cieszyński",
    "Cieszyn": "cieszyński",
    "Jastrzębie-Zdrój": "jastrzębski",
    "Jastrzebie-Zdroj": "jastrzębski",
    "Pszczyna": "pszczyński",
    "Mysłowice": "mysłowicki",
    "Myslowice": "mysłowicki",
    "Będzin": "będziński",
    "Bedzin": "będziński",
    "Zawiercie": "zawierciański",
    "Mikołów": "mikołowski",
    "Mikolow": "mikołowski",
    "Ruda Śląska": "rudzki",
    "Ruda Slaska": "rudzki",
    "Siemianowice Śląskie": "siemianowicki",
    "Siemianowice Slaskie": "siemianowicki",
    "Piekary Śląskie": "piekarski",
    "Piekary Slaskie": "piekarski",
    "Tarnowskie Góry": "tarnogórski",
    "Tarnowskie Gory": "tarnogórski",
    "Świętochłowice": "świętochłowicki",
    "Swietochlowice": "świętochłowicki",
    "Pyskowice": "gliwicki",
    
    # Mazowsze
    "Płock": "płocki",
    "Plock": "płocki",
    "Ostrołęka": "ostrołęcki",
    "Ostroleka": "ostrołęcki",
    "Ciechanów": "ciechanowski",
    "Ciechanow": "ciechanowski",
    "Przasnysz": "przasnyski",
    "Maków Mazowiecki": "makowski",
    "Wyszków": "wyszkowski",
    "Wołomin": "wołomiński",
    "Wolomin": "wołomiński",
    "Legionowo": "legionowski",
    "Piaseczno": "piaseczyński",
    "Grójec": "grójecki",
    "Grojec": "grójecki",
    "Węgrów": "węgrowski",
    "Wegrów": "węgrowski",
    "Siedlce": "siedlecki",
    "Minsk Mazowiecki": "miński",
    "Mińsk Mazowiecki": "miński",
    "Łosice": "łosicki",
    "Sokołów Podlaski": "sokołowski",
    "Węgrów": "węgrowski",
    
    # Wielkopolska
    "Poznań": "poznański",
    "Poznan": "poznański",
    "Kalisz": "kaliski",
    "Konin": "koniński",
    "Leszno": "leszczyński",
    "Piła": "pilski",
    "Pila": "pilski",
    "Ostrów Wielkopolski": "ostrowski",
    "Ostrow Wielkopolski": "ostrowski",
    "Gniezno": "gnieźnieński",
    "Września": "wrzesiński",
    "Wrzesnia": "wrzesiński",
    "Śrem": "śremski",
    "Srem": "śremski",
    "Koło": "kolski",
    "Kolo": "kolski",
    "Turek": "turecki",
    "Krotoszyn": "krotoszyński",
    "Krotoszyn": "krotoszyński",
    "Ostrzeszów": "ostrzeszowski",
    "Ostrzeszow": "ostrzeszowski",
    "Kępno": "kępiński",
    "Kepno": "kępiński",
    "Wągrowiec": "wągrowiecki",
    "Wagrowiec": "wągrowiecki",
    "Chodzież": "chodzieski",
    "Chodziez": "chodzieski",
    "Szamotuły": "szamotulski",
    "Szamutuly": "szamotulski",
    "Wronki": "szamotulski",
    "Nowy Tomyśl": "nowotomyski",
    "Nowy Tomysl": "nowotomyski",
    "Grodzisk Wielkopolski": "grodziski",
    "Grodzisk Wielkopolski": "grodziski",
    "Kościan": "kościański",
    "Koscian": "kościański",
    "Środa Wielkopolska": "średzki",
    "Sroda Wielkopolska": "średzki",
    "Jarocin": "jarociński",
    "Pleszew": "pleszewski",
    
    # Małopolska
    "Kraków": "krakowski",
    "Krakow": "krakowski",
    "Tarnów": "tarnowski",
    "Tarnow": "tarnowski",
    "Nowy Sącz": "nowosądecki",
    "Nowy Sącz": "nowosądecki",
    "Oświęcim": "oświęcimski",
    "Oswiecim": "oświęcimski",
    "Chrzanów": "chrzanowski",
    "Chrzanow": "chrzanowski",
    "Olkusz": "olkuski",
    "Myślenice": "myślenicki",
    "Myslenice": "myślenicki",
    "Wadowice": "wadowicki",
    "Andrychów": "andrychowski",
    "Andrychow": "andrychowski",
    "Brzesko": "brzeski",
    "Bochnia": "bocheński",
    "Niepołomice": "wielicki",
    "Niepolomice": "wielicki",
    "Wieliczka": "wielicki",
    "Limanowa": "limanowski",
    "Nowy Targ": "nowotarski",
    "Nowy Targ": "nowotarski",
    "Podhale": "nowotarski",
    "Zakopane": "tatrzański",
    "Dąbrowa Tarnowska": "dąbrowski",
    "Dabrowa Tarnowska": "dąbrowski",
    "Müllerstadt": "dąbrowski",
    
    # Śląsk
    "Katowice": "katowicki",
    "Częstochowa": "częstochowski",
    "Czestochowa": "częstochowski",
    "Bytom": "bytomski",
    "Chorzów": "chorzowski",
    "Chorzow": "chorzowski",
    "Dąbrowa Górnicza": "dąbrowski",
    "Dabrowa Gornicza": "dąbrowski",
    "Zabrze": "zabrski",
    "Zory": "żorski",
    "Zory": "żorski",
    "Rybnik": "rybnicki",
    "Mysłowice": "mysłowicki",
    "Myslowice": "mysłowicki",
    "Siemianowice Śląskie": "siemianowicki",
    "Siemianowice Slaskie": "siemianowicki",
    "Piekary Śląskie": "piekarski",
    "Piekary Slaskie": "piekarski",
    "Tarnowskie Góry": "tarnogórski",
    "Tarnowskie Gory": "tarnogórski",
    "Świętochłowice": "świętochłowicki",
    "Swietochlowice": "świętochłowicki",
    "Pyskowice": "gliwicki",
    "Knurów": "gliwicki",
    "Knurów": "gliwicki",
    "Gliwice": "gliwicki",
    "Ruda Śląska": "rudzki",
    "Ruda Slaska": "rudzki",
    "Jastrzębie-Zdrój": "jastrzębski",
    "Jastrzebie-Zdroj": "jastrzębski",
    "Żory": "żorski",
    "Zory": "żorski",
    "Będzin": "będziński",
    "Bedzin": "będziński",
    "Zawiercie": "zawierciański",
    "Mikołów": "mikołowski",
    "Mikolow": "mikołowski",
    "Pszczyna": "pszczyński",
    "Bielsko-Biała": "bielski",
    "Bielsko-Biala": "bielski",
    "Czechowice-Dziedzice": "bielski",
    "Czechowice-Dziedzice": "bielski",
    "Skoczów": "cieszyński",
    "Ustroń": "cieszyński",
    "Wisła": "cieszyński",
    "WislA": "cieszyński",
    "Żywiec": "żywiecki",
    "Zywiec": "żywiecki",
    "Cieszyn": "cieszyński",
    "Cieszyn": "cieszyński",
    
    # Dolny Śląsk
    "Wrocław": "wrocławski",
    "Wroclaw": "wrocławski",
    "Wałbrzych": "wałbrzyski",
    "Walbrzych": "wałbrzyski",
    "Legnica": "legnicki",
    "Jelenia Góra": "jeleniogórski",
    "Jelenia Gora": "jeleniogórski",
    "Lubin": "lubiński",
    "Polkowice": "polkowicki",
    "Głogów": "głogowski",
    "Glogow": "głogowski",
    "Oleśnica": "oleśnicki",
    "Olesnica": "oleśnicki",
    "Trzebnica": "trzebnicki",
    "Świdnica": "świdnicki",
    "Swidnica": "świdnicki",
    "Dzierżoniów": "dzierżoniowski",
    "Dzierzoniów": "dzierżoniowski",
    "Kłodzko": "kłodzki",
    "Klodzko": "kłodzki",
    "Bielawa": "dzierżoniowski",
    "Nowa Ruda": "kłodzki",
    "Kraków": "krakowski",
}

# Słownik jest wpisany w zapisie tytułowym, ale dane z wypisów bywają
# zapisane małymi/wielkimi literami albo bez polskich znaków. Indeks
# znormalizowany zapewnia, że forma zapisu wejściowego nie blokuje odmiany.
CITY_TO_POWIAT_LOOKUP = {
    _lookup_key(city): county for city, county in CITY_TO_POWIAT.items()
}


# ============================================================================
# MIEJSCOWOŚCI - odmiana miejscownik (gdzie?)
# ============================================================================

CITY_DECLENSIONS = {
    # Trójmiasto
    "Gdańsk": "Gdańsku",
    "Gdynia": "Gdyni",
    "Sopot": "Sopocie",
    
    # Duże miasta
    "Warszawa": "Warszawie",
    "Kraków": "Krakowie",
    "Krakow": "Krakowie",
    "Wrocław": "Wrocławiu",
    "Wroclaw": "Wrocławiu",
    "Poznań": "Poznaniu",
    "Poznan": "Poznaniu",
    "Łódź": "Łodzi",
    "Lodz": "Łodzi",
    "Lublin": "Lublinie",
    "Szczecin": "Szczecinie",
    "Bydgoszcz": "Bydgoszczy",
    "Toruń": "Toruniu",
    "Torun": "Toruniu",
    "Kielce": "Kielcach",
    "Rzeszów": "Rzeszowie",
    "Rzeszow": "Rzeszowie",
    "Białystok": "Białymstoku",
    "Bialystok": "Białymstoku",
    "Olsztyn": "Olsztynie",
    "Katowice": "Katowicach",
    "Gorzów Wielkopolski": "Gorzowie Wielkopolskim",
    "Gorzow Wielkopolski": "Gorzowie Wielkopolskim",
    "Zielona Góra": "Zielonej Górze",
    "Zielona Gora": "Zielonej Górze",
    "Opole": "Opolu",
    
    # Pomorze
    "Kościerzyna": "Kościerzynie",
    "Koscierzyna": "Kościerzynie",
    "Wejherowo": "Wejherowie",
    "Wejherów": "Wejherowie",
    "Wejherow": "Wejherowie",
    "Kartuzy": "Kartuzach",
    "Pruszcz Gdański": "Pruszczu Gdańskim",
    "Pruszcz Gdanski": "Pruszczu Gdańskim",
    "Starogard Gdański": "Starogardzie Gdańskim",
    "Starogard Gdanski": "Starogardzie Gdańskim",
    "Tczew": "Tczewie",
    "Rumia": "Rumi",
    "Sztum": "Sztumie",
    "Malbork": "Malborku",
    "Kwidzyń": "Kwidzyniu",
    "Kwidzyn": "Kwidzyniu",
    "Słupsk": "Słupsku",
    "Slupsk": "Słupsku",
    "Grudziądz": "Grudziądzu",
    "Grudziadz": "Grudziądzu",
    "Kołobrzeg": "Kołobrzegu",
    "Kolobrzeg": "Kołobrzegu",
    "Chojnice": "Chojnicach",
    "Puck": "Pucku",
    "Władysławowo": "Władysławowie",
    "Wladyslawowo": "Władysławowie",
}

CITY_DECLENSIONS_LOOKUP = {
    _lookup_key(city): declined for city, declined in CITY_DECLENSIONS.items()
}


# ============================================================================
# ODMIANA ULIC
# ============================================================================

def decline_street(street: str) -> str:
    """Odmienia nazwę ulicy przez miejscownik."""
    if not street:
        return street
    
    original = street.strip()
    
    # Prefix ulica/ul./ul
    prefix = ""
    rest = original
    
    lower_orig = original.lower()
    if lower_orig.startswith("ulica "):
        prefix = "ulica "
        rest = original[6:]
    elif lower_orig.startswith("ul. "):
        prefix = "ul. "
        rest = original[4:]
    elif lower_orig.startswith("ul "):
        prefix = "ul "
        rest = original[3:]
    
    if not rest:
        return original
    
    rest = rest.split(",")[0].strip()
    rest = rest.split("(")[0].strip()

    # Nazwy już w dopełniaczu (np. "Słowackiego", "Poniatowskiego") zostaw bez zmian.
    if rest.lower().endswith("ego"):
        return original

    return prefix + _decline_female_name(rest)


def _decline_female_name(name: str) -> str:
    """Odmienia żeńskie nazwy własne (przymiotnikowe nazwy ulic)."""
    if not name:
        return name

    low = name.lower()

    if low.endswith("ia"):
        return name

    if low.endswith("a"):
        # Przymiotniki żeńskie: -ska/-cka/-dzka -> -skiej/-ckiej/-dzkiej
        if low.endswith("dzka"):
            return name[:-4] + "dzkiej"
        if low.endswith("cka"):
            return name[:-3] + "ckiej"
        if low.endswith("ska"):
            return name[:-3] + "skiej"

        base = name[:-1]
        # -ga -> -giej (Długa -> Długiej), -ka -> -kiej (Szeroka -> Szerokiej)
        if low.endswith("ga"):
            return base + "iej"
        if low.endswith("ka"):
            return base + "iej"

        # Pozostałe żeńskie: Nowa -> Nowej, Stara -> Starej
        return base + "ej"

    return name


# ============================================================================
# FUNKCJE GŁÓWNE
# ============================================================================

def city_to_powiat(city: str) -> str:
    """
    Zamienia nazwę miejscowości na nazwę powiatu.
    
    Args:
        city: Nazwa miejscowości, np. "Kościerzyna"
    
    Returns:
        Nazwa powiatu małymi literami, np. "kościerski"
        
    Jeśli nie ma w słowniku, zwraca oryginalną wartość.
    """
    if not city:
        return city
    
    normalized = city.strip()
    
    mapped_county = CITY_TO_POWIAT_LOOKUP.get(_lookup_key(normalized))
    if mapped_county is not None:
        return mapped_county
    
    # Jeśli już jest nazwą powiatu (kończy się na -ski/-cki/-dzki), zwróć jak jest
    if normalized.lower().endswith(("ski", "cka", "dzka", "skie", "ckie", "dzkie")):
        return normalized.lower()
    
    # Nie znaleziono - zwróć oryginalną wartość
    return normalized


def decline_city(city: str) -> str:
    """
    Odmienia nazwę miejscowości przez miejscownik.
    
    Args:
        city: Nazwa miejscowości, np. "Gdańsk"
    
    Returns:
        Odmieniona nazwa, np. "Gdańsku"
    """
    if not city:
        return city
    
    normalized = city.strip()
    
    # Sprawdź czy to nie jest przypadkiem nazwa powiatu
    if normalized.lower().endswith(("ski", "cka", "dzka", "skie", "ckie", "dzkie")):
        return normalized
    
    # Słownik miejscowości (niezależnie od wielkości liter wejścia).
    declined_city = CITY_DECLENSIONS_LOOKUP.get(_lookup_key(normalized))
    if declined_city is not None:
        if normalized.isupper():
            return declined_city.upper()
        if normalized.islower():
            return declined_city.lower()
        return declined_city
    
    # Produktywna odmiana nijakich nazw miejscowości na -owo:
    # Żukowo -> Żukowie, Grabowo -> Grabowie, a także zapis wielkimi literami.
    # Wcześniej takie nazwy nie znajdowały się w słowniku i wpadały w fallback
    # zwracający oryginalną wartość.
    if normalized.lower().endswith("owo"):
        ending = "IE" if normalized.isupper() else "ie"
        return normalized[:-1] + ending

    # Automatyczna odmiana dla żeńskich nazw na -a
    if normalized.lower().endswith("a") and not normalized.lower().endswith("ia"):
        base = normalized[:-1]
        
        if base.lower().endswith(("sk", "ck", "zk", "dz")):
            return base + "u"
        
        if base.lower().endswith(("ów", "ow")):
            if base.lower().endswith("ów"):
                return base + "ie"
            return base + "a"
        
        if base.lower().endswith("ica"):
            return base[:-2] + "y"
        
        return base + "ej"
    
    if normalized.lower().endswith(("in", "lin", "cin", "win", "ton")):
        return normalized + "ie"
    
    return normalized


# ============================================================================
# TAGI DLA DOKUMENTÓW
# ============================================================================

def create_declension_tags(city: str, street: str) -> dict:
    """Tworzy słownik z tagami dla szablonów dokumentów."""
    return {
        "<Miejscowosc dzialki odmiana>": decline_city(city) if city else city,
        "<Ulica odmiana>": decline_street(street) if street else street,
        "<Powiat zamiana>": city_to_powiat(city) if city else city,
    }
