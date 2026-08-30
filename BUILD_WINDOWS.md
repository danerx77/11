# Budowanie wersji Windows (`.exe`)

Program należy budować **na Windowsie 64-bit**, używając 64-bitowego Pythona
**3.11** (zalecany dla zgodności PySide6, EasyOCR i PyInstaller). PyInstaller
nie tworzy poprawnego pliku Windows `.exe` z Linuxa lub macOS.

> Na drugi komputer kopiuje się cały katalog `dist\Pysilde6`, a nie sam plik
> `Pysilde6.exe`. W katalogu są biblioteki Qt, moduły Pythona i przeglądarki
> Playwright. Rozpakuj go w **zapisywalnym** miejscu, np. w Dokumentach lub na
> dysku danych — nie w `C:\Program Files`, ponieważ program zapisuje globalne
> ustawienia w sąsiednim katalogu `dane`.

## Najprostsza, zalecana metoda

`build_windows.ps1` jest zapisany jako UTF-8 z BOM i celowo zawiera wyłącznie
znaki ASCII. Dzięki temu działa także w starszym **Windows PowerShell 5.1**,
który potrafi błędnie odczytać polskie znaki z pliku UTF-8 bez BOM. Pobierz
aktualną wersję skryptu zamiast używać wcześniejszej kopii.

Otwórz **PowerShell** w katalogu projektu i wykonaj:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-windows.txt
python -m playwright install chromium firefox
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1 -Console
```

Jeśli `py -3.11` nie jest dostępne, zainstaluj 64-bitowy Python 3.11 albo użyj
właściwego interpretera w poleceniu tworzenia środowiska.

Pierwszą kompilację zrób z przełącznikiem `-Console`. Gdy program uruchomi się
prawidłowo z katalogu `dist\Pysilde6`, zbuduj wersję bez konsoli:

```powershell
.\build_windows.ps1
```

Skrypt przed kompilacją:

1. sprawdza, czy potrzebne biblioteki są zainstalowane;
2. uruchamia `compileall` i testy jednostkowe;
3. pakuje PySide6, Playwright, Selenium, Word/Excel/PDF/OCR i pozostałe
   używane moduły;
4. dołącza folder `%LOCALAPPDATA%\ms-playwright` oraz cache modeli EasyOCR
   dla `pl` i `en`; przy pierwszym pełnym buildzie modele mogą pobrać kilkaset MB;
5. wykrywa układ danych PyInstaller 5/6 (katalog główny albo `_internal`) i
   sprawdza, czy powstał `dist\Pysilde6\Pysilde6.exe`.

Jeśli nie chcesz dołączać OCR, można świadomie użyć `-SkipOcr`. Jeżeli nie
chcesz dołączać przeglądarek Playwright, istnieje `-SkipBrowserBundle`, ale
wtedy funkcje KW/KRS oparte na Playwright **nie będą gotowe na drugim komputerze**.
Pełna paczka (Qt, dwie przeglądarki Playwright, Torch i modele OCR) będzie
celowo duża; nie usuwaj z niej ręcznie katalogów `_internal`, `ms-playwright`
lub `easyocr-data`.

## Poprawiony wariant jednorazowej komendy PyInstaller

Poniższa wersja poprawia składnię PowerShell z pytania: znak `` ` `` musi być
ostatnim znakiem w wierszu, a na końcu podaje się zwykłe `main.py`, bez linku
Markdown. Poniższy wariant używa launchera `py`, więc zależności muszą być
zainstalowane przez `py -m pip` w tym samym interpreterze. Jeśli aktywowałeś
`.venv` według pierwszej instrukcji, zamień każde `py` poniżej na `python`.

```powershell
# Wymagane przed komendą: pip install -r requirements-windows.txt
# oraz: py -m playwright install chromium firefox
# Pierwsze wykonanie przygotowuje modele OCR do późniejszego spakowania.
py -c "import easyocr; easyocr.Reader(['pl', 'en'], gpu=False, verbose=False)"

py -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --noconsole `
  --name Pysilde6 `
  --exclude-module PyQt5 `
  --collect-all PySide6 `
  --collect-all playwright `
  --collect-all selenium `
  --collect-all pywinauto `
  --collect-all requests `
  --collect-all bs4 `
  --collect-all lxml `
  --collect-all docx `
  --collect-all docxcompose `
  --collect-all openpyxl `
  --collect-all fitz `
  --collect-all PIL `
  --collect-all easyocr `
  --collect-all pytesseract `
  --collect-all mss `
  --collect-all numpy `
  --collect-all pyperclip `
  --collect-all torch `
  --collect-all torchvision `
  --collect-all cv2 `
  --collect-all scipy `
  --collect-all skimage `
  --collect-all bidi `
  --collect-all yaml `
  --collect-all shapely `
  --collect-all pyclipper `
  --collect-all ninja `
  --hidden-import win32com.client `
  --hidden-import win32con `
  --hidden-import win32print `
  --hidden-import pythoncom `
  --hidden-import pywintypes `
  --add-data "$env:LOCALAPPDATA\ms-playwright;ms-playwright" `
  --add-data "$env:USERPROFILE\.EasyOCR;easyocr-data" `
  main.py
```

Zalecany jest jednak skrypt `build_windows.ps1`, ponieważ przerywa budowanie,
gdy brakuje biblioteki, przeglądarek albo modeli OCR. Powyższa ręczna komenda
zakłada standardowy cache `%USERPROFILE%\.EasyOCR`; gdy ustawiono własne
`EASYOCR_MODULE_PATH`, użyj tego folderu zamiast niego.

## Co musi być dostępne na drugim komputerze

W paczce są biblioteki programu oraz przeglądarki Playwright. Pewne funkcje
zależą jednak od programów lub danych systemowych, których PyInstaller nie
powinien ukrycie zastępować:

| Funkcja | Wymaganie na komputerze docelowym |
| --- | --- |
| Zwykła praca programu, PDF, listy Excel oraz generowanie DOCX | cały katalog `dist\Pysilde6` |
| KW i KRS przez Playwright | folder `ms-playwright` dołączony przez skrypt; dostęp do Internetu |
| **KW 2** przez Selenium | zainstalowany zwykły Google Chrome / Chrome zgodny z Selenium; dostęp do Internetu |
| Łączenie/dobieranie dokumentów oraz druk/konwersja DOCX przez automatykę | Microsoft Word, gdy wybierany jest ten tryb; łączenie ma też wariant bez Worda |
| Eksport Tytułów prawnych do szablonu Excel przez COM | Microsoft Excel — sama biblioteka `openpyxl` nie zastępuje programu Excel dla tego eksportu |
| Awaryjny OCR Tesseract | osobno zainstalowany Tesseract OCR z językiem polskim (`pol`) |
| OCR EasyOCR | pełne wydanie skryptu zawiera wcześniej przygotowane modele `pl`/`en`; nie używaj `-SkipOcr`, jeśli OCR ma działać offline |

Nie kopiuj automatycznie starego `dane\app_config.json`, jeśli zawiera ścieżki
z poprzedniego komputera. Lepiej skopiować potrzebne foldery szablonów
(Przykłady, Tytuły Prawne, Znaczki) i wskazać ich lokalizację w **Ustawieniach**
na nowym komputerze.

## Test paczki przed przekazaniem

1. Spakuj **cały** katalog `dist\Pysilde6` do ZIP.
2. Rozpakuj go w nowym folderze, najlepiej na czystej maszynie wirtualnej lub
   innym komputerze — nie uruchamiaj programu z katalogu źródłowego.
3. Uruchom `Pysilde6.exe`.
4. Sprawdź podstawy: utworzenie projektu, wczytanie danych, sortowanie działek,
   duplikaty, generowanie przykładowego dokumentu/koperty, eksport PDF/Excel,
   Historię oraz zapisywanie ustawień po ponownym uruchomieniu.
5. Sprawdź osobno funkcje internetowe: status Poczty Polskiej, KRS i KW.
6. Jeśli korzystasz z OCR lub KW 2, sprawdź odpowiednio OCR/Tesseract oraz
   uruchomienie widocznego Chrome.

Jeśli wersja z `-Console` pokaże błąd, zachowaj treść komunikatu — będzie
znacznie łatwiejszy do zdiagnozowania niż błąd w wydaniu `--noconsole`.
