# Wykonane zmiany

Poniżej opis dziewięciu zgłoszonych punktów. Wszystko jest już w gałęzi
`arena/01a06823-11`. Testy: **153 przechodzą** (wcześniej było 48).

---

## 1. Ikona programu

Program ma teraz własną ikonę aplikacji, a nie tylko ikonkę na zakładce.

* `assets/energodok.ico` — rozmiary 16, 20, 24, 32, 40, 48, 64, 96, 128, 256 px
  (Windows sam dobiera właściwy do paska zadań, Alt+Tab i podglądu pliku).
* `tools/make_app_icon.py` — generator ikony. Korzysta wyłącznie z Pillow,
  które jest już w `requirements-windows.txt`. Aby wygenerować ponownie:
  `python tools/make_app_icon.py`.
* Ikona jest ustawiana w trzech miejscach:
  * `QApplication.setWindowIcon(...)` — pasek zadań i okna dialogowe,
  * `MainWindow.setWindowIcon(...)` — belka okna,
  * `--icon assets/energodok.ico` w PyInstallerze — sam plik EXE.
* Dodatkowo ustawiany jest `AppUserModelID`. Bez tego Windows pokazywałby na
  pasku zadań ikonę Pythona zamiast ikony programu.
* Aby użyć własnej grafiki, wystarczy podmienić `assets/energodok.ico` —
  skrypt budujący nie nadpisuje istniejącego pliku.

## 2. Powrót nazwy `eKW` na `KW2`

Karta modułu nazywa się znowu **KW2**. Zapisany układ zakładek nie ginie:
nazwy `eKW`, `KW 2`, `📖 KW 2 — ręcznie` i `📖 KW 2 — ręczne przeglądanie` są
nadal rozpoznawane jako ta sama karta. Ikonka karty pokazuje teraz `KW2`.
Nazwa portalu Ministerstwa Sprawiedliwości („Otwórz portal eKW”) celowo
została, bo tak nazywa się sam serwis.

## 3. Nowy moduł „Wskaźnik”

Nowa zakładka `🔢 Wskaźnik` z listą działek i ich identyfikatorami
ewidencyjnymi (`221001_1.0001.12/3`).

* **Filtr listą działek** — w polu „Pokaż tylko działki” można wkleić
  `1/1, 1/2` (przecinki, spacje, średniki, nowe wiersze — dowolnie) i tabela
  pokazuje wyłącznie te działki. Program informuje, których działek z filtra
  nie ma na liście.
* **Import TXT/CSV i wklejanie** — plik lub wklejony tekst może mieć postać
  `1/2  221001_1.0001.1/2`, `1/2;221001_1.0001.1/2;Polki` albo sam
  identyfikator (numer działki zostanie z niego odczytany). Rozdzielać można
  tabulatorem, średnikiem, kreską pionową, znakiem `=` lub dwiema spacjami;
  wiersze z `#` są pomijane.
* **Rozszerzenia, o które prosiłeś**: pobranie działek z zakładki „Lista
  działek”, uzupełnienie danych z wypisów, wyszukiwarka w tabeli, filtr
  „tylko bez identyfikatora”, sortowanie (naturalne po numerze, po
  identyfikatorze, obrębie, gminie), ręczna edycja i dodawanie wierszy,
  wykrywanie powtórzonych identyfikatorów, kopiowanie widoku i samych
  identyfikatorów oraz eksport do CSV/TXT. Lista zapisuje się w projekcie
  (`wskaznik_state.json`).

## 4. Ustawienia — schematy nazw plików

Nowa sekcja **„Nazewnictwo plików — Oświadczenia i Pisma (PSM)”**.

* **Domyślnie nic się nie zmienia** — nazwy plików są dokładnie takie jak do
  tej pory.
* Dopisek numeru działki jest opcją: *nigdy* / *tylko gdy właściciel ma
  dokładnie jedną działkę* / *zawsze* / *do ustalonej liczby, potem „i inne”*.
* Dodatkowo konfigurowalne: gotowe warianty nazw, własny wzór z polami
  (`{nazwisko}`, `{typ}`, `{dzialki}`, `{projekt}`, `{data}`, `{obreb}`,
  `{gmina}`, `{miejscowosc}` i inne), sposób zapisu nazwiska (`J.Kowalski`,
  `Jan Kowalski`, `Kowalski Jan`, `Kowalski`), zamiana spacji na `_` lub `-`
  oraz usuwanie polskich znaków.
* Pod spodem jest **podgląd na żywo** obu nazw i przycisk „Przywróć
  dotychczasowe nazwy”.
* Ukośnik z numeru działki zamienia się w myślnik (`12/3` → `12-3`), bo
  Windows nie dopuszcza `/` w nazwie pliku.

## 5. Oświadczenia — lista postaci urządzeń

Wybór z listy **od razu** wpisuje treść do pola obok. Przyczyną błędu było
podpięcie się pod `currentTextChanged`, który nie zgłasza ponownego wyboru tej
samej pozycji, a lista była czyszczona przy każdym odświeżeniu przykładów.
Teraz używany jest sygnał `activated`, lista zachowuje wybraną pozycję po
odświeżeniu, a wiersz zachęty („— wybierz postać urządzenia —”) nie nadpisuje
tego, co wpisałeś ręcznie.

## 6. Druczki — plik daje się edytować

Druczki z Poczty Polskiej mają ustawione hasło właściciela i ograniczone
uprawnienia, które PyMuPDF przepisywał do pliku wynikowego. Teraz szablon jest
otwierany pustym hasłem, a wynik zapisywany jawnie bez szyfrowania i z pełnymi
uprawnieniami (edycja, kopiowanie, komentarze, druk). Plik dostaje też zwykłe
prawa zapisu. Jest na to test na faktycznie zabezpieczonym PDF.

## 7. Wypisy — kilka obrębów w jednym pliku

`Obręb ewidencyjny`, `Jednostka ewidencyjna`, `Powiat` i `Województwo` są
odczytywane **osobno dla każdej działki**, zamiast brania pierwszej wartości z
pliku. Każda działka dostaje wartości ze swojej sekcji dokumentu, a właściciel
z działkami w dwóch obrębach ma w polu Obręb obie nazwy (`Polki, Borkowo`).
Okno po imporcie pokazuje raport z liczbą różnych wartości i przypisaniem
obrębu do poszczególnych działek.

## 8. Historia — kolory i pełna historia

* Kolumna „Status Poczty Polskiej” jest kolorowana według kategorii zdarzenia:
  doręczona — zielony, w doręczeniu — jasnoniebieski, w transporcie —
  niebieski, nadana — żółty, awizowana — pomarańczowy, zwrot/problem —
  czerwony. Żaden status nie jest już szary. Przed tekstem jest ikonka.
* Nowy przycisk **„🕘 Pełna historia zdarzeń”** (działa też dwuklik na kolumnie
  statusu) otwiera okno z całą historią z Poczty Polskiej: numer kolejny, data
  i godzina, zdarzenie, placówka i przyczyna, z możliwością skopiowania
  historii i przejścia do emonitoringu.

## 9. Historia — kolejność i mapowanie statusu

* Zdarzenia są ułożone **od najwcześniejszego do najnowszego** — w oknie
  historii, w podpowiedzi i przy kopiowaniu. Zdarzenia bez daty trafiają na
  koniec.
* Status **„udostępniono podpis odbioru”** (oraz pokrewne sformułowania, np.
  „potwierdzenie odbioru”, „pokwitowanie odbioru”) liczy się teraz jako
  **doręczona / odebrana**.

---

# Poprawki po pierwszych testach

## 10. Kolejność zakładek

* **„↕️ Sortuj działki”** i **„🔢 Wskaźnik”** stoją teraz tuż przed
  **„⚙️ Ustawienia”**, na końcu paska.
* Jeżeli masz zapisany starszy układ kart, program **jednorazowo sam go
  poprawi** przy pierwszym uruchomieniu — nie trzeba nic przestawiać ręcznie.
  Twoja własna kolejność pozostałych zakładek zostaje nienaruszona.

## 11. Ikonka przy module KW2

* Rysowana ikonka na zakładce **KW2 została usunięta**. Karta nazywa się
  teraz **„📖 KW2”** — emotka w nazwie, dokładnie jak w pozostałych modułach.
* Stare zapisane układy z nazwami „eKW”, „KW 2” czy „KW2” nadal są
  rozpoznawane.

## 12. Czytelność w trybie nocnym

* Sekcja **„Nazewnictwo plików”** w Ustawieniach była na sztywno jasna i w
  trybie nocnym praktycznie nie dało się jej odczytać. Podgląd nazw,
  podpowiedź u góry i lista dostępnych pól **dopasowują się teraz do motywu** —
  jasny tekst na ciemnym tle w nocy, ciemny na jasnym w dzień.

## 13. Domyślny limit działek = 1

* Ustawienie **„limit działek”** (Oświadczenia i Pisma) ma teraz domyślnie
  **1** zamiast 3 — zarówno w Ustawieniach, jak i w samej logice nazw plików.

## 14. Opis odmiany miejscowości

* Pole wyboru nie powtarza już nazwy tagu. Czytasz po prostu:
  **„Odmieniaj tag <Miejscowość działki:> (np. Gdańsk → Gdańsku,
  Sopot → Sopocie)”**, a informacja o zapisie bez dwukropka i bez polskich
  znaków przeniosła się do dymka.

---

# Trzecia tura poprawek

## 15. Nowa nazwa programu — EnergoDok

* Pasek okna pokazuje teraz po prostu **„EnergoDok”** (wcześniej „Pysilde 6 –
  Zarządzanie Inwestycjami Elektroenergetycznymi”). Po wybraniu projektu:
  **„EnergoDok – [Projekt: OBI/123/2026]”**.
* Plik programu nazywa się **`EnergoDok.exe`** i powstaje w katalogu
  **`dist\EnergoDok`**. Ikona to `assets/energodok.ico` (litera **E** pasuje
  do nowej nazwy).
* Nazwa siedzi w **jednym miejscu** w kodzie (`APP_NAME` w `main.py`), więc
  przy kolejnej zmianie nie trzeba jej poprawiać w kilkunastu plikach.
* Program nadal wczyta ikonę ze starego wydania, jeśli gdzieś zostanie —
  nic się nie wysypie po aktualizacji.

## 16. Ramka „Zestawienie działek” w trybie nocnym

* Niebieska ramka z opisem na górze modułu **Wskaźnik** była na sztywno
  biało-kremowa i w trybie nocnym raziła w oczy. Teraz ma ciemne tło i jasny
  tekst, a w trybie dziennym wygląda jak dotąd.
* Ta sama poprawka objęła **wszystkie takie ramki w programie**, nie tylko
  jedną: opis w module **KW2**, ramkę reguł pism w **Ustawieniach** oraz
  podgląd druczka i grupy pól w **Druczkach** — one też świeciły na biało.

---

# Czwarta tura poprawek

## 17. Projekty — schematy nazwy folderu

* W **Ustawieniach** jest nowa sekcja **„Projekty — nazwa folderu nowego
  projektu”** z podglądem na żywo. Do wyboru 9 gotowych wariantów albo własny
  wzór z pól `{nazwa}`, `{symbol}`, `{miasto}`, `{termin}`.
* Osobno ustawiasz, **czym zastąpić ukośnik** w numerze projektu:
  `OBI.23.23220` (jak dotąd), `OBI-23-23220`, `OBI_23_23220`, ze spacją albo
  bez separatora.
* Dodatkowo: zapis terminu (5 wariantów, np. `04-12-2026`, `2026-12-04`) oraz
  zamiana spacji na myślnik lub podkreślnik.
* Ten sam schemat podpowiada się w oknie **„Nowy projekt”**, gdzie pod polem
  formatu widać **gotową nazwę folderu**, zanim klikniesz OK.
* Bez zmiany ustawień nazwa wygląda jak dotąd:
  **`Maki OBI.23.23220 04-12-2026`**.

## 18. Wypisy — jednostka ewidencyjna na trzy sposoby

W Ustawieniach, sekcja **„Wypisy — odczyt danych z dokumentu”**:

1. **Tak jak w wypisie** — `Maki - G`, `Maki - M` (ustawienie domyślne).
2. **Tylko miejscowość** — zawsze `Maki`.
3. **Miejscowość, ale zostaw „- M”** — gmina traci oznaczenie (`Maki`),
   miasto je zachowuje (`Maki - M`).

Gdy wypis podaje kilka jednostek po przecinku, każda jest formatowana osobno,
a powtórki są usuwane.

## 19. Wypisy — kropki w identyfikatorze działki

* Identyfikator rozdzielony spacjami jest teraz zapisywany prawidłowo:
  * `110101 2 0010 202` → **`110101_2.0010.202`**
  * `110101 2 0010 22 21` → **`110101_2.0010.22/21`**
* Poprawka działa w czterech miejscach, w których program czyta identyfikator
  z PDF, oraz w module **Wskaźnik**. Zapis już poprawny zostaje bez zmian.

## 20. Wypisy — nowa kolumna „Forma władania”

* Program odczytuje z wypisu formę władania i pokazuje ją w nowej kolumnie
  obok „Udziału”: *współwłasność*, *wspólność ustawowa*, *użytkowanie
  wieczyste*, *udział łączny*, *trwały zarząd* i podobne.
* Kolumnę można poprawić ręcznie, tak jak pozostałe.

## 21. Wskaźnik — „Pobierz z listy działek” z pełnymi danymi

* Wcześniej przycisk pobierał **same numery** działek, bo lista działek nie zna
  identyfikatorów — te są w Wypisach. Teraz jednym kliknięciem program
  **łączy oba źródła**: numery z listy działek, a identyfikator, obręb, gminę,
  powiat i województwo z wypisów.
* Po pobraniu widać podsumowanie: ile działek ma identyfikator, a ile nie —
  i co zrobić z brakami.

## 22. Oświadczenia i Pisma — jedno pole zamiast dwóch

* Dwa mylące pola („Pokaż tylko grupę” + „Wszystkie bez działek z grup”)
  zastąpiło **jedno**: **„Pokaż i generuj tylko wybraną grupę”**.
* Włączone przy wybranej grupie — widać **wyłącznie działki tej grupy**, także
  w kolumnie „Działki”. Działki z innych grup znikają z listy.
* Włączone przy „Wszystkie działki” — program ukrywa działki, które trafiły
  już do nazwanych grup.

## 23. Oświadczenia — „Generuj automatycznie wszystkie” tylko dla grupy

* Przycisk **⚡ GENERUJ AUTOMATYCZNIE WSZYSTKIE** respektuje teraz filtr grupy:
  generuje dokumenty **tylko dla działek z widocznej grupy**, a nie dla
  wszystkich grup naraz.
* Naprawiony błąd: **postać urządzeń ustawiona przy grupie nie trafiała do
  dokumentu**. Teraz opis z grupy ma pierwszeństwo przed tym, co akurat
  zostało w formularzu — osobno dla budowy i demontażu.
* Gdy w grupie nie ma żadnego właściciela, program mówi to wprost, zamiast
  generować cokolwiek.

## 24. Pisma — nazwa przycisku jak w Oświadczeniach

* **„GENERUJ WSZYSTKIE BEZ PTASZKA”** → **„⚡ GENERUJ AUTOMATYCZNIE
  WSZYSTKIE”**, tak samo jak w Oświadczeniach. Filtr grupy obowiązuje tu
  dokładnie tak samo.

---

# Piąta tura poprawek

## 25. Forma władania — teraz naprawdę czytana z PDF

* **Przyczyna błędu:** wypisy są drukowane **bez polskich znaków**
  (`udzial laczny`, `wspolnosc ustawowa`), a program szukał wyłącznie zapisu
  z ogonkami — więc nie znajdował nic i kolumna zostawała pusta.
* Rozpoznawanie działa teraz **niezależnie od ogonków i wielkości liter**,
  a wynik zawsze zapisuje się poprawną polszczyzną:
  `udzial laczny` → **udział łączny**, `wspolnosc ustawowa` →
  **wspólność ustawowa**, `WSPOLWLASNOSC` → **współwłasność**.
* Wypis potrafi rozbić opis na kilka wierszy (`udzial laczny` / `14/48` /
  `wspólwłasność`). Program czyta **cały blok** i skleja obie informacje:
  **„udział łączny, współwłasność”** — dokładnie jak na Twoim zrzucie.
* „Współwłasność” nie jest już mylona ze „własnością”.

## 26. Forma władania w szczegółach właściciela

* Pozycja **„Forma władania”** pojawia się w panelu szczegółów pod
  „Udziałem”.
* Pole jest też w oknie **dodawania i edycji właściciela**, więc można je
  poprawić ręcznie.

## 27. Nowy projekt — wybór separatora w numerze

* W oknie **„Nowy projekt”** doszło pole **„Ukośnik w numerze zamień na:”**
  z wyborem: kropka (jak dotąd), **myślnik**, **podkreślnik**, spacja albo bez
  separatora.
* Podgląd nazwy folderu zmienia się od razu, a utworzony folder ma dokładnie
  taką nazwę, jaka była w podglądzie.

## 28. Wskaźnik — eksport z wyborem kolumn

* Przycisk **„Eksportuj widok”** otwiera teraz okno wyboru zawartości pliku:
  * **Nr działki i identyfikator** (domyślnie),
  * **Same numery działek**,
  * **Same identyfikatory**,
  * **Wszystkie kolumny** — tak jak działało dotychczas,
  * albo własny wybór dowolnych kolumn.
* Dodatkowo: wybór znaku rozdzielającego (tabulator, średnik, przecinek,
  spacja, myślnik) i decyzja, czy dopisać wiersz z nazwami kolumn.
* Widać **podgląd**, jak będzie wyglądał plik, a wybór jest zapamiętywany na
  następny raz. Zapis działa zarówno do TXT, jak i CSV.

---

## Uwagi techniczne

* Cała nowa logika siedzi w `utils/` (`parcel_indicators.py`,
  `document_naming.py`, `wypis_metadata.py`, `shipment_tracking.py`), dzięki
  czemu jest pokryta testami bez uruchamiania okien.
* Nowe pliki testów: `test_parcel_indicators.py`, `test_document_naming.py`,
  `test_wypis_metadata.py`, `test_wypis_pdf_multi_meta.py`,
  `test_pdf_editable_output.py`, `test_tab_naming.py`, `test_app_icon.py`.
* Uruchomienie testów: `python -m unittest discover -s tests -v`.
* Skrypt `build_windows.ps1` pozostaje czystym ASCII z BOM (zgodność z
  Windows PowerShell 5.1) i sam wygeneruje ikonę, jeśli jej zabraknie.
