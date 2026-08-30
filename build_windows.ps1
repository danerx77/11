#requires -Version 5.1
<#
.SYNOPSIS
    Buduje przenośny katalog Windows dist\Pysilde6 dla aplikacji.

.EXAMPLE
    Set-ExecutionPolicy -Scope Process Bypass
    .\build_windows.ps1

.EXAMPLE
    .\build_windows.ps1 -Console

.NOTES
    Skrypt należy uruchomić na Windows, w aktywnym środowisku wirtualnym
    zawierającym zależności z requirements-windows.txt. Nie buduje pliku .exe
    na Linuxie ani macOS.
#>

[CmdletBinding()]
param(
    # "python" użyje aktywnego virtualenv. Dla launchera Pythona użyj: -PythonExe py
    [string]$PythonExe = "python",

    # Pierwsze wydanie warto zrobić z konsolą, aby było widać ewentualne błędy.
    [switch]$Console,

    # Nie dołącza przeglądarek Playwright. Wtedy funkcje KW/KRS wymagające
    # Playwright nie będą gotowe od razu po skopiowaniu programu na inny komputer.
    [switch]$SkipBrowserBundle,

    # Pomija ciężkie zależności OCR. Pozostałe funkcje programu nadal będą
    # budowane, ale OCR EasyOCR/Tesseract nie będzie kompletny.
    [switch]$SkipOcr,

    # Nie usuwa poprzednich katalogów build i dist\Pysilde6 przed budowaniem.
    [switch]$KeepBuildFiles,

    # Pomija compileall i testy jednostkowe przed budowaniem.
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if ($env:OS -ne "Windows_NT") {
    throw "Ten skrypt buduje Windows .exe i musi zostać uruchomiony w Windows."
}

if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    throw "Nie znaleziono interpretera '$PythonExe'. Aktywuj virtualenv albo podaj -PythonExe py."
}

function Test-PythonModule {
    param([Parameter(Mandatory = $true)][string]$ModuleName)

    $probe = @'
import importlib.util
import sys
try:
    found = importlib.util.find_spec(sys.argv[1]) is not None
except (ImportError, AttributeError, ValueError):
    found = False
raise SystemExit(0 if found else 1)
'@
    & $PythonExe -c $probe $ModuleName
    return $LASTEXITCODE -eq 0
}

$requiredModules = @(
    "PyInstaller",
    "PySide6",
    "playwright",
    "selenium",
    "pywinauto",
    "requests",
    "bs4",
    "lxml",
    "docx",
    "docxcompose",
    "openpyxl",
    "fitz",
    "PIL",
    "mss",
    "numpy",
    "pyperclip",
    "win32com.client",
    "win32con",
    "win32print"
)

if (-not $SkipOcr) {
    # EasyOCR importuje część tych bibliotek dopiero w trakcie odczytu obrazu.
    # Sprawdzamy je jawnie, żeby PyInstaller nie stworzył pozornie kompletnego EXE.
    $requiredModules += @(
        "easyocr", "pytesseract", "torch", "torchvision", "cv2", "scipy",
        "skimage", "bidi", "yaml", "shapely", "pyclipper", "ninja"
    )
}

$missingModules = @(
    $requiredModules | Where-Object { -not (Test-PythonModule $_) }
)
if ($missingModules.Count -gt 0) {
    $missingText = $missingModules -join ", "
    throw "Brakuje modułów: $missingText`nUruchom: $PythonExe -m pip install -r requirements-windows.txt"
}

if (-not $SkipBrowserBundle) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "Nie można odczytać LOCALAPPDATA. Uruchom PowerShell jako zalogowany użytkownik."
    }

    $PlaywrightBrowsersPath = Join-Path $env:LOCALAPPDATA "ms-playwright"
    if (-not (Test-Path -LiteralPath $PlaywrightBrowsersPath -PathType Container)) {
        throw @"
Nie znaleziono przeglądarek Playwright w:
$PlaywrightBrowsersPath

Najpierw uruchom:
$PythonExe -m playwright install chromium firefox
"@
    }

    $browserNames = @(
        Get-ChildItem -LiteralPath $PlaywrightBrowsersPath -Directory |
        ForEach-Object { $_.Name }
    )
    if ((-not ($browserNames -match "^chromium-")) -or (-not ($browserNames -match "^firefox-"))) {
        Write-Warning "W folderze ms-playwright nie znaleziono Chromium i Firefox. Dla funkcji KW/KRS uruchom: $PythonExe -m playwright install chromium firefox"
    }
}

$EasyOcrModulePath = $null
if (-not $SkipOcr) {
    # EasyOCR domyślnie używa EASYOCR_MODULE_PATH, MODULE_PATH albo
    # %USERPROFILE%\.EasyOCR. Zachowujemy tę samą kolejność, aby dołączyć cache
    # faktycznie używany przez interpreter budujący.
    if (-not [string]::IsNullOrWhiteSpace($env:EASYOCR_MODULE_PATH)) {
        $EasyOcrModulePath = $env:EASYOCR_MODULE_PATH
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:MODULE_PATH)) {
        $EasyOcrModulePath = $env:MODULE_PATH
    }
    else {
        $EasyOcrModulePath = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".EasyOCR"
    }

    $EasyOcrModelsPath = Join-Path $EasyOcrModulePath "model"
    # Reader sprawdza kompletność i sumy kontrolne modeli. W razie potrzeby
    # pobierze brakujący model dla języków używanych przez utils/ocr_utils.py.
    Write-Host "Weryfikuję modele EasyOCR dla polskiego i angielskiego..." -ForegroundColor Cyan
    Write-Host "Przy pierwszym pełnym buildzie może zostać pobrane kilkaset MB modeli." -ForegroundColor DarkYellow
    & $PythonExe -c "import easyocr; easyocr.Reader(['pl', 'en'], gpu=False, verbose=False)"
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udało się pobrać/przygotować modeli EasyOCR. Sprawdź Internet albo uruchom budowanie z -SkipOcr."
    }
    $modelFiles = @(
        Get-ChildItem -LiteralPath $EasyOcrModelsPath -File -ErrorAction SilentlyContinue
    )
    if ($modelFiles.Count -eq 0) {
        throw "Nie znaleziono modeli EasyOCR w $EasyOcrModelsPath po ich przygotowaniu."
    }
}

if ((-not $SkipOcr) -and (-not (Get-Command "tesseract.exe" -ErrorAction SilentlyContinue))) {
    Write-Warning "Nie znaleziono tesseract.exe. Pakiet pytesseract jest dołączony, ale awaryjny OCR Tesseract wymaga osobnej instalacji Tesseract OCR na komputerze docelowym."
}

$AppName = "Pysilde6"
$DistRoot = Join-Path $ProjectRoot "dist"
$OutputDir = Join-Path $DistRoot $AppName
$BuildDir = Join-Path $ProjectRoot "build"
$SpecDir = Join-Path $BuildDir "spec"

if (-not $KeepBuildFiles) {
    Remove-Item -LiteralPath $OutputDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $SpecDir -Force | Out-Null

if (-not $SkipTests) {
    Write-Host "[1/3] Sprawdzam składnię..." -ForegroundColor Cyan
    & $PythonExe -m compileall -q main.py modules utils tests
    if ($LASTEXITCODE -ne 0) {
        throw "compileall zakończył się błędem. Budowanie przerwane."
    }

    Write-Host "[2/3] Uruchamiam testy..." -ForegroundColor Cyan
    & $PythonExe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Testy zakończyły się błędem. Budowanie przerwane."
    }
}
else {
    Write-Warning "Pominięto compileall i testy (-SkipTests)."
}

$collectAllPackages = @(
    "PySide6",
    "playwright",
    "selenium",
    "pywinauto",
    "requests",
    "bs4",
    "lxml",
    "docx",
    "docxcompose",
    "openpyxl",
    "fitz",
    "PIL",
    "mss",
    "numpy",
    "pyperclip"
)
if (-not $SkipOcr) {
    # Są to moduły ładowane przez EasyOCR częściowo dynamicznie.
    $collectAllPackages += @(
        "easyocr", "pytesseract", "torch", "torchvision", "cv2", "scipy",
        "skimage", "bidi", "yaml", "shapely", "pyclipper", "ninja"
    )
}

$pyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name", $AppName,
    "--exclude-module", "PyQt5",
    "--hidden-import", "win32com.client",
    "--hidden-import", "win32con",
    "--hidden-import", "win32print",
    "--hidden-import", "pythoncom",
    "--hidden-import", "pywintypes",
    "--distpath", $DistRoot,
    "--workpath", $BuildDir,
    "--specpath", $SpecDir
)

if ($Console) {
    $pyInstallerArgs += "--console"
}
else {
    $pyInstallerArgs += "--noconsole"
}

foreach ($packageName in $collectAllPackages) {
    $pyInstallerArgs += @("--collect-all", $packageName)
}

if (-not $SkipBrowserBundle) {
    # Windowsowy separator add-data ma postać: źródło;folder_w_programie.
    # main.py wyszukuje ten folder obok Pysilde6.exe.
    $pyInstallerArgs += @(
        "--add-data",
        "$PlaywrightBrowsersPath;ms-playwright"
    )
}

if (-not $SkipOcr) {
    # main.py wskazuje easyocr-data/model przed pierwszym OCR.
    $pyInstallerArgs += @(
        "--add-data",
        "$EasyOcrModulePath;easyocr-data"
    )
}

$pyInstallerArgs += "main.py"

Write-Host "[3/3] Buduję $AppName.exe..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller zakończył się błędem: $LASTEXITCODE"
}

$exePath = Join-Path $OutputDir "$AppName.exe"
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Budowanie zakończyło się bez oczekiwanego pliku: $exePath"
}

if (-not $SkipBrowserBundle) {
    # PyInstaller 5 umieszcza dane zwykle obok EXE, a PyInstaller 6 często
    # przenosi je do _internal. Obie lokalizacje są obsługiwane przez main.py.
    $bundledBrowserCandidates = @(
        (Join-Path $OutputDir "ms-playwright"),
        (Join-Path $OutputDir "_internal\ms-playwright")
    )
    $bundledBrowsers = @(
        $bundledBrowserCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Container }
    ) | Select-Object -First 1
    if (-not $bundledBrowsers) {
        throw "Nie dołączono folderu ms-playwright do $OutputDir ani $OutputDir\_internal"
    }
}

if (-not $SkipOcr) {
    $bundledEasyOcrCandidates = @(
        (Join-Path $OutputDir "easyocr-data"),
        (Join-Path $OutputDir "_internal\easyocr-data")
    )
    $bundledEasyOcr = @(
        $bundledEasyOcrCandidates |
        Where-Object { Test-Path -LiteralPath (Join-Path $_ "model") -PathType Container }
    ) | Select-Object -First 1
    if (-not $bundledEasyOcr) {
        throw "Nie dołączono katalogu modeli EasyOCR do $OutputDir ani $OutputDir\_internal"
    }
}

Write-Host ""
Write-Host "Gotowe: $exePath" -ForegroundColor Green
Write-Host "Na inny komputer kopiuj lub spakuj cały folder: $OutputDir" -ForegroundColor Yellow
Write-Host "Nie kopiuj samego pliku .exe — katalog zawiera biblioteki, Qt i przeglądarki Playwright." -ForegroundColor Yellow
