# Wykonane zmiany

Poniżej opis dziewięciu zgłoszonych punktów. Wszystko jest już w gałęzi
`arena/01a06823-11`. Testy: **153 przechodzą** (wcześniej było 48).

---

## 1. Ikona programu

Program ma teraz własną ikonę aplikacji, a nie tylko ikonkę na zakładce.

* `assets/pysilde6.ico` — rozmiary 16, 20, 24, 32, 40, 48, 64, 96, 128, 256 px
  (Windows sam dobiera właściwy do paska zadań, Alt+Tab i podglądu pliku).
* `tools/make_app_icon.py` — generator ikony. Korzysta wyłącznie z Pillow,
  które jest już w `requirements-windows.txt`. Aby wygenerować ponownie:
  `python tools/make_app_icon.py`.
* Ikona jest ustawiana w trzech miejscach:
  * `QApplication.setWindowIcon(...)` — pasek zadań i okna dialogowe,
  * `MainWindow.setWindowIcon(...)` — belka okna,
  * `--icon assets/pysilde6.ico` w PyInstallerze — sam plik EXE.
* Dodatkowo ustawiany jest `AppUserModelID`. Bez tego Windows pokazywałby na
  pasku zadań ikonę Pythona zamiast ikony programu.
* Aby użyć własnej grafiki, wystarczy podmienić `assets/pysilde6.ico` —
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
