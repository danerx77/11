"""
gender_utils.py – Wykrywanie płci na podstawie imienia (heurystyki polskie)
oraz odmiana nazwisk (par małżeńskich).
"""

FEMALE_ENDINGS = ('a', 'ia', 'ea', 'ta', 'da', 'la', 'na', 'ra', 'sa', 'wa', 'ga', 'ma', 'ka', 'fa', 'za', 'ba', 'ca', 'pa', 'ha', 'ja')
MALE_EXCEPTIONS = {'Barnaba', 'Kuba', 'Kosma', 'Jarema', 'Zawisza', 'Bonawentura'}

def detect_gender(first_name: str) -> str:
    """Zwraca 'F' dla kobiety, 'M' dla mężczyzny."""
    if not first_name: return 'M'
    
    # Wyciągnij pierwsze imię, zignoruj białe znaki i zrób dużą pierwszą literę
    name = first_name.split()[0].strip().capitalize()
    
    if name in MALE_EXCEPTIONS: return 'M'
    
    lower = name.lower()
    for ending in FEMALE_ENDINGS:
        if lower.endswith(ending): return 'F'
    return 'M'

def _pluralize_ski(name_masc: str) -> str:
    """Tworzy liczbę mnogą dla polskich nazwisk zakończonych na ski/cki/dzki."""
    lower = name_masc.lower()
    if lower.endswith('cki'): return name_masc[:-3] + 'ccy'
    if lower.endswith('dzki'): return name_masc[:-4] + 'dzcy'
    if lower.endswith('ski'): return name_masc[:-3] + 'scy'
    return name_masc

def get_couple_last_name(n1: str, n2: str) -> str:
    """
    Zwraca odmienione nazwisko liczby mnogiej (np. Paradowscy), 
    jeśli małżeństwo ma zgodny temat nazwiska kończącego się na: ski/ska, cki/cka, dzki/dzka.
    Nie odmienia nazwisk wieloczłonowych (z myślnikiem).
    """
    if '-' in n1 or '-' in n2: 
        return ""
        
    n1_lower = n1.lower()
    n2_lower = n2.lower()
    
    masc = ""
    if n1_lower.endswith(('ski', 'cki', 'dzki')):
        masc = n1
    elif n2_lower.endswith(('ski', 'cki', 'dzki')):
        masc = n2
        
    if masc:
        # Jeśli różnią się tylko ostatnią literą (np. Kowalsk-i / Kowalsk-a)
        if n1_lower[:-1] == n2_lower[:-1]:
            return _pluralize_ski(masc)
            
    return ""

def get_ownership_phrase(is_couple: bool, first_name: str, parcels: list, is_sole_owner: bool) -> str:
    """Dobiera właściwą formę gramatyczną dla pisma przewodniego."""
    plural = len(parcels) > 1

    if is_couple:
        if is_sole_owner:
            return "których są Państwo właścicielami," if plural else "której są Państwo właścicielami,"
        else:
            return "których są Państwo współwłaścicielami," if plural else "której są Państwo współwłaścicielami,"
    else:
        g = detect_gender(first_name)
        if g == 'F':
            if is_sole_owner:
                return "których jest Pani właścicielką," if plural else "której jest Pani właścicielką,"
            else:
                return "których jest Pani współwłaścicielką," if plural else "której jest Pani współwłaścicielką,"
        else:
            if is_sole_owner:
                return "których jest Pan właścicielem," if plural else "której jest Pan właścicielem,"
            else:
                return "których jest Pan współwłaścicielem," if plural else "której jest Pan współwłaścicielem,"

def format_couple_salutation(owners: list) -> str:
    """Formatuje nagłówek dla pary lub pojedynczej osoby (bez Sz. P.)."""
    if not owners: return ""
    o1 = owners[0]
    
    if not o1.get('is_couple'):
        return f"{o1.get('first_name', '')} {o1.get('last_name', '')}".strip()
    
    return o1.get('full_name', '')

def format_salutation_line(owners: list) -> str:
    """Tworzy linię 'Sz. P.' z odpowiednim adresatem poniżej."""
    if not owners: return "Sz. P.\n"
    o = owners[0]
    
    if o.get('is_institution'):
        return f"{o.get('full_name', '')}"
        
    return f"Sz. P.\n{format_couple_salutation(owners)}"