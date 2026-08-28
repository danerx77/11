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
    "Kwidzyń": "Kwidzynie",
    "Kwidzyn": "Kwidzynie",
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

    # Nazwy nieregularne, przymiotnikowe i wielowyrazowe.
    # Reguły poniżej obsługują regularne końcówki, ale te formy wymagają
    # odmiany więcej niż jednego członu lub nieregularnej wymiany głosek.
    "Bielsko-Biała": "Bielsku-Białej",
    "Bielsko-Biala": "Bielsku-Białej",
    "Czechowice-Dziedzice": "Czechowicach-Dziedzicach",
    "Dąbrowa Górnicza": "Dąbrowie Górniczej",
    "Dabrowa Gornicza": "Dąbrowie Górniczej",
    "Dąbrowa Tarnowska": "Dąbrowie Tarnowskiej",
    "Dabrowa Tarnowska": "Dąbrowie Tarnowskiej",
    "Gniezno": "Gnieźnie",
    "Jastrzębie-Zdrój": "Jastrzębiu-Zdroju",
    "Jastrzebie-Zdroj": "Jastrzębiu-Zdroju",
    "Jelenia Góra": "Jeleniej Górze",
    "Jelenia Gora": "Jeleniej Górze",
    "Koło": "Kole",
    "Kolo": "Kole",
    "Krokowa": "Krokowej",
    "Limanowa": "Limanowej",
    "Mińsk Mazowiecki": "Mińsku Mazowieckim",
    "Minsk Mazowiecki": "Mińsku Mazowieckim",
    "Nowa Ruda": "Nowej Rudzie",
    "Nowa Wieś": "Nowej Wsi",
    "Nowy Sącz": "Nowym Sączu",
    "Nowy Sacz": "Nowym Sączu",
    "Nowy Targ": "Nowym Targu",
    "Ostrów Wielkopolski": "Ostrowie Wielkopolskim",
    "Ostrow Wielkopolski": "Ostrowie Wielkopolskim",
    "Piła": "Pile",
    "Pila": "Pile",
    "Piekary Śląskie": "Piekarach Śląskich",
    "Piekary Slaskie": "Piekarach Śląskich",
    "Ruda Śląska": "Rudzie Śląskiej",
    "Ruda Slaska": "Rudzie Śląskiej",
    "Siemianowice Śląskie": "Siemianowicach Śląskich",
    "Siemianowice Slaskie": "Siemianowicach Śląskich",
    "Tarnowskie Góry": "Tarnowskich Górach",
    "Tarnowskie Gory": "Tarnowskich Górach",
    "Wisła": "Wiśle",
    "Wisla": "Wiśle",
    "Zabrze": "Zabrzu",
    "Zakopane": "Zakopanem",
    "Zawiercie": "Zawierciu",
    "Chodzież": "Chodzieży",
    "Chodziez": "Chodzieży",
}

CITY_DECLENSIONS_LOOKUP = {
    _lookup_key(city): declined for city, declined in CITY_DECLENSIONS.items()
}


def parse_city_declension_overrides(value) -> dict:
    """Odczytuje własne formy miejscownika z konfiguracji lub pola ustawień.

    Obsługiwany jest słownik konfiguracji oraz prosty zapis po jednej pozycji
    w wierszu, np. ``Nowa Wieś = Nowej Wsi``. Można też użyć separatora
    ``→`` albo ``=>``. Puste i niepełne wiersze są pomijane.
    """
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, str):
        items = []
        for raw_line in value.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            for separator in ("=>", "→", "="):
                if separator in line:
                    city, declined = line.split(separator, 1)
                    items.append((city, declined))
                    break
    else:
        return {}

    result = {}
    for city, declined in items:
        city_text = str(city or "").strip()
        declined_text = str(declined or "").strip()
        if city_text and declined_text:
            result[city_text] = declined_text
    return result


def format_city_declension_overrides(value) -> str:
    """Zwraca własne formy w czytelnym, edytowalnym zapisie tekstowym."""
    overrides = parse_city_declension_overrides(value)
    return "\n".join(
        f"{city} = {declined}"
        for city, declined in sorted(
            overrides.items(), key=lambda item: _lookup_key(item[0])
        )
    )


def _match_city_case(source: str, declined: str) -> str:
    """Zachowuje zapis małymi lub wielkimi literami użyty w danych wejściowych."""
    if source.isupper():
        return declined.upper()
    if source.islower():
        return declined.lower()
    return declined


def _replace_city_ending(city: str, suffix: str, replacement: str) -> str:
    """Zamienia końcówkę słowa, zachowując wielkość liter końcówki wejściowej."""
    source_ending = city[-len(suffix):]
    if source_ending.isupper():
        replacement = replacement.upper()
    elif source_ending.islower():
        replacement = replacement.lower()
    return city[:-len(suffix)] + replacement


# Kolejność ma znaczenie: najpierw końcówki szczególne i dłuższe, potem
# ogólne. Reguły obejmują najczęstsze typy polskich nazw miejscowości.
_REGULAR_CITY_LOCATIVE_ENDINGS = (
    # Nazwy w liczbie mnogiej: Sierakowice, Kartuzy, Czaple, Trąbki.
    ("owice", "owicach"),
    ("ewice", "ewicach"),
    ("ice", "icach"),
    ("yce", "ycach"),
    ("any", "anach"),
    ("ony", "onach"),
    ("yny", "ynach"),
    ("y", "ach"),
    ("i", "ach"),
    ("e", "ach"),

    # Nazwy nijakie: Żukowo, Luzino, Kielno, Wicko, Brzesko.
    ("owo", "owie"),
    ("ewo", "ewie"),
    ("ino", "inie"),
    ("yno", "ynie"),
    ("ano", "anie"),
    ("ono", "onie"),
    ("sko", "sku"),
    ("cko", "cku"),
    ("ko", "ku"),
    ("no", "nie"),
    ("o", "ie"),

    # Nazwy żeńskie: Stężyca, Kobylnica, Gdynia, Wieliczka, Czerska.
    ("dzka", "dzkiej"),
    ("cka", "ckiej"),
    ("ska", "skiej"),
    ("owa", "owie"),
    ("awa", "awie"),
    ("yna", "ynie"),
    ("ina", "inie"),
    ("ona", "onie"),
    ("ena", "enie"),
    ("ana", "anie"),
    ("ica", "icy"),
    ("yca", "ycy"),
    ("cha", "sze"),
    ("ża", "ży"),
    ("ga", "dze"),
    ("ka", "ce"),
    ("ta", "cie"),
    ("da", "dzie"),
    ("ba", "bie"),
    ("pa", "pie"),
    ("ma", "mie"),
    ("wa", "wie"),
    ("ra", "rze"),
    ("la", "li"),
    ("ia", "i"),
    ("a", "ie"),

    # Nazwy męskie: Czersk, Tczew, Przywidz, Karsin, Żywiec.
    ("iec", "cu"),
    ("ek", "ku"),
    ("ec", "cu"),
    ("in", "inie"),
    ("yn", "ynie"),
    ("eń", "eniu"),
    ("ań", "aniu"),
    ("oń", "oniu"),
    ("ń", "niu"),
    ("ów", "owie"),
    ("ow", "owie"),
    ("ew", "ewie"),
    ("sk", "sku"),
    ("ck", "cku"),
    ("zk", "zku"),
    ("dz", "dzu"),
    ("cz", "czu"),
    ("sz", "szu"),
    ("rz", "rzu"),
    ("ież", "ieży"),
    ("ieś", "si"),
    ("ż", "żu"),
    ("ś", "si"),
    ("ź", "zi"),
    ("ch", "chu"),
    ("k", "ku"),
    ("g", "gu"),
    ("j", "ju"),
    ("d", "dzie"),
    ("z", "zie"),
    ("c", "cu"),
    ("t", "cie"),
    ("r", "rze"),
    ("l", "lu"),
    ("m", "mie"),
    ("n", "nie"),
    ("p", "pie"),
    ("b", "bie"),
    ("w", "wie"),
    ("f", "fie"),
    ("h", "hu"),
    ("s", "sie"),
)

# Częste samodzielne przymiotniki występujące jako człony nazw złożonych.
# Nie stosujemy ogólnej reguły dla każdej nazwy na -a/-y, bo mogłaby błędnie
# potraktować rzeczownik (np. Dąbrowa) jak przymiotnik.
_CITY_ADJECTIVE_FORMS = {
    "biała": "Białej",
    "biala": "Białej",
    "biały": "Białym",
    "bialy": "Białym",
    "czarna": "Czarnej",
    "czarny": "Czarnym",
    "długa": "Długiej",
    "dluga": "Długiej",
    "długi": "Długim",
    "dlugi": "Długim",
    "dobra": "Dobrej",
    "dobry": "Dobrym",
    "dolna": "Dolnej",
    "dolny": "Dolnym",
    "górna": "Górnej",
    "gorna": "Górnej",
    "górny": "Górnym",
    "gorny": "Górnym",
    "jelenia": "Jeleniej",
    "mała": "Małej",
    "mala": "Małej",
    "mały": "Małym",
    "maly": "Małym",
    "mokra": "Mokrej",
    "mokry": "Mokrym",
    "niska": "Niskiej",
    "niski": "Niskim",
    "nowa": "Nowej",
    "nowe": "Nowym",
    "nowy": "Nowym",
    "sucha": "Suchej",
    "suchy": "Suchym",
    "stara": "Starej",
    "stare": "Starym",
    "stary": "Starym",
    "wielka": "Wielkiej",
    "wielkie": "Wielkim",
    "wielki": "Wielkim",
    "wysoka": "Wysokiej",
    "wysoki": "Wysokim",
    "zielona": "Zielonej",
    "zielony": "Zielonym",
}

# Jednoznaczne końcówki przymiotnikowe. Formy na -e są niejednoznaczne
# (np. liczba mnoga lub rodzaj nijaki), dlatego dla nich pozostają słownik
# nazw pełnych oraz własne wyjątki użytkownika.
_CITY_ADJECTIVE_ENDINGS = (
    ("dzkie", "dzkich"),
    ("ckie", "ckich"),
    ("skie", "skich"),
    ("dzki", "dzkim"),
    ("cki", "ckim"),
    ("ski", "skim"),
    ("dzka", "dzkiej"),
    ("cka", "ckiej"),
    ("ska", "skiej"),
    ("cza", "czej"),
    ("czy", "czym"),
    ("nna", "nnej"),
)


def _decline_city_adjective(word: str):
    """Zwraca miejscownik rozpoznanego członu przymiotnikowego lub ``None``."""
    lower_word = word.casefold()
    explicit_form = _CITY_ADJECTIVE_FORMS.get(lower_word)
    if explicit_form is not None:
        return _match_city_case(word, explicit_form)

    for suffix, replacement in _CITY_ADJECTIVE_ENDINGS:
        if lower_word.endswith(suffix):
            return _replace_city_ending(word, suffix, replacement)
    return None


# Częste rzeczownikowe człony, w których miejscownik wymaga zmiany wewnątrz
# wyrazu, a nie tylko podmiany końcówki.
_CITY_WORD_LOCATIVE_FORMS = {
    "dwór": "Dworze",
    "dwor": "Dworze",
    "kalwaria": "Kalwarii",
    "miasto": "Mieście",
    "zdrój": "Zdroju",
    "zdroj": "Zdroju",
}

# Przyimki i spójniki występujące w nazwach złożonych (np. Kostrzyn nad Odrą)
# nie są samodzielnymi miejscowościami i nie mogą przejść przez reguły końcówek.
_CITY_NAME_UNINFLECTED_WORDS = {
    "do",
    "i",
    "im",
    "na",
    "nad",
    "od",
    "oraz",
    "pod",
    "przy",
    "w",
    "we",
    "z",
    "za",
    "ze",
}


def _decline_city_word(word: str) -> str:
    """Odmienia jeden alfabetyczny człon nazwy zgodnie z regularną końcówką."""
    lower_word = word.casefold()
    if lower_word in _CITY_NAME_UNINFLECTED_WORDS or lower_word.endswith(("ą", "ę")):
        return word

    exact_form = _CITY_WORD_LOCATIVE_FORMS.get(lower_word)
    if exact_form is not None:
        return _match_city_case(word, exact_form)

    for suffix, replacement in _REGULAR_CITY_LOCATIVE_ENDINGS:
        if lower_word.endswith(suffix):
            return _replace_city_ending(word, suffix, replacement)

    # Ostatnia bezpieczna próba dla rzadkiej, nieobjętej końcówki spółgłoskowej.
    # Nie dotyczy znaków innych niż litery, więc np. numery i kody pozostają takie
    # jak w danych wejściowych.
    if word and word[-1].isalpha():
        return word + ("IE" if word.isupper() else "ie")
    return word


def _decline_regular_city(city: str) -> str:
    """Odmienia człony nieznanej nazwy prostej, złożonej lub z łącznikiem.

    Przymiotnikowe człony, takie jak ``Mazowiecki`` i ``Śląska``, mają osobne
    reguły. Pozostałe wyrazy przechodzą przez reguły rzeczownikowe. Nietypowe
    wielowyrazowe nazwy nadal można doprecyzować trwałym wyjątkiem w ustawieniach.
    """
    parts = []
    index = 0
    while index < len(city):
        if not city[index].isalpha():
            parts.append(city[index])
            index += 1
            continue

        word_end = index
        while word_end < len(city) and city[word_end].isalpha():
            word_end += 1
        word = city[index:word_end]
        parts.append(_decline_city_adjective(word) or _decline_city_word(word))
        index = word_end

    return "".join(parts)


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


def decline_city(city: str, overrides=None) -> str:
    """Odmienia nazwę miejscowości przez miejscownik.

    Najpierw używa wpisanej przez użytkownika formy, potem słownika nazw
    nieregularnych, a na końcu reguł dla regularnych końcówek. Dzięki temu
    wartości tagów obsługują nie tylko nazwy na ``-owo``, ale też m.in.
    ``-ice``, ``-y/-i/-e``, ``-a``, ``-ino/-yno``, ``-ko/-no`` i nazwy
    męskie zakończone spółgłoską.

    ``overrides`` może być słownikiem ``nazwa -> miejscownik`` albo tekstem
    w formacie ``Nazwa = Forma``. Pozwala wskazać poprawną formę każdej
    nieregularnej lub wielowyrazowej miejscowości bez zmiany danych źródłowych.
    """
    if not city:
        return city

    normalized = str(city).strip()
    if not normalized:
        return normalized

    # Kod pocztowy nie jest częścią nazwy; zachowujemy go, ale odmieniamy
    # następującą po nim miejscowość.
    postal_prefix = ""
    if (
        len(normalized) > 6
        and normalized[2:3] == "-"
        and normalized[:2].isdigit()
        and normalized[3:6].isdigit()
        and normalized[6:7].isspace()
    ):
        postal_prefix = normalized[:7]
        normalized = normalized[7:].strip()

    # Własny słownik ma pierwszeństwo przed wbudowanymi formami.
    custom_forms = {
        _lookup_key(source): declined
        for source, declined in parse_city_declension_overrides(overrides).items()
    }
    custom_declined = custom_forms.get(_lookup_key(normalized))
    if custom_declined is not None:
        return postal_prefix + _match_city_case(normalized, custom_declined)

    # Słownik miejscowości (niezależnie od wielkości liter wejścia) musi być
    # sprawdzany przed nazwami powiatów: np. Pruszcz Gdański to miejscowość,
    # mimo że ostatni człon ma końcówkę przymiotnikową.
    declined_city = CITY_DECLENSIONS_LOOKUP.get(_lookup_key(normalized))
    if declined_city is not None:
        return postal_prefix + _match_city_case(normalized, declined_city)

    # Samodzielna nazwa powiatu/przymiotnik nie jest miejscowością. Dla nazw
    # złożonych przechodzimy dalej, aby przynajmniej odmienić ostatni człon.
    if " " not in normalized and "-" not in normalized and normalized.casefold().endswith(
        ("ski", "cka", "dzka", "skie", "ckie", "dzkie")
    ):
        return postal_prefix + normalized

    return postal_prefix + _decline_regular_city(normalized)


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
