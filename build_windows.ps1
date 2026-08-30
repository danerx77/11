#requires -Version 5.1
<#
.SYNOPSIS
    Builds the Windows onedir release in dist\Pysilde6.

.DESCRIPTION
    Run this file on 64-bit Windows from an activated Python virtual environment.
    The script deliberately uses ASCII only and has a UTF-8 BOM so that it also
    parses correctly in legacy Windows PowerShell 5.1.

.EXAMPLE
    Set-ExecutionPolicy -Scope Process Bypass
    .\build_windows.ps1 -Console
#>

[CmdletBinding()]
param(
    # "python" uses an activated venv. Use -PythonExe py for the Python launcher.
    [string]$PythonExe = "python",

    # First build: show a console to make startup errors visible.
    [switch]$Console,

    # Do not bundle Playwright browsers. KW/KRS Playwright features will not be portable.
    [switch]$SkipBrowserBundle,

    # Do not bundle EasyOCR/Tesseract Python dependencies and EasyOCR models.
    [switch]$SkipOcr,

    # Keep previous build files instead of deleting build and dist\Pysilde6 first.
    [switch]$KeepBuildFiles,

    # Skip compileall and unit tests before PyInstaller starts.
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if ($env:OS -ne "Windows_NT") {
    throw "This script must be run on Windows."
}

if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    throw "Python command '$PythonExe' was not found. Activate the venv or use -PythonExe py."
}

function Test-PythonModule {
    param([Parameter(Mandatory = $true)][string]$ModuleName)

    $probe = "import importlib.util, sys; raise SystemExit(0 if importlib.util.find_spec(sys.argv[1]) else 1)"
    & $PythonExe -c $probe $ModuleName
    return ($LASTEXITCODE -eq 0)
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
    # EasyOCR loads several of these modules dynamically at OCR runtime.
    $requiredModules += @(
        "easyocr", "pytesseract", "torch", "torchvision", "cv2", "scipy",
        "skimage", "bidi", "yaml", "shapely", "pyclipper", "ninja"
    )
}

$missingModules = @(
    $requiredModules | Where-Object { -not (Test-PythonModule $_) }
)
if ($missingModules.Count -gt 0) {
    throw ("Missing Python modules: " + ($missingModules -join ", ") + "`nRun: $PythonExe -m pip install -r requirements-windows.txt")
}

$PlaywrightBrowsersPath = $null
if (-not $SkipBrowserBundle) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is not available for this user."
    }

    $PlaywrightBrowsersPath = Join-Path $env:LOCALAPPDATA "ms-playwright"
    if (-not (Test-Path -LiteralPath $PlaywrightBrowsersPath -PathType Container)) {
        throw ("Playwright browsers were not found in: $PlaywrightBrowsersPath`n" +
               "Run: $PythonExe -m playwright install chromium firefox")
    }

    $browserNames = @(
        Get-ChildItem -LiteralPath $PlaywrightBrowsersPath -Directory |
        ForEach-Object { $_.Name }
    )
    if ((-not ($browserNames -match "^chromium-")) -or (-not ($browserNames -match "^firefox-"))) {
        Write-Warning "Chromium and/or Firefox is missing. Run: $PythonExe -m playwright install chromium firefox"
    }
}

$EasyOcrModulePath = $null
if (-not $SkipOcr) {
    # This follows EasyOCR's standard cache resolution order.
    if (-not [string]::IsNullOrWhiteSpace($env:EASYOCR_MODULE_PATH)) {
        $EasyOcrModulePath = $env:EASYOCR_MODULE_PATH
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:MODULE_PATH)) {
        $EasyOcrModulePath = $env:MODULE_PATH
    }
    else {
        $EasyOcrModulePath = Join-Path $env:USERPROFILE ".EasyOCR"
    }

    $EasyOcrModelsPath = Join-Path $EasyOcrModulePath "model"
    Write-Host "Checking EasyOCR models for Polish and English..." -ForegroundColor Cyan
    Write-Host "The first full build may download several hundred MB of OCR models." -ForegroundColor DarkYellow
    & $PythonExe -c "import easyocr; easyocr.Reader(['pl', 'en'], gpu=False, verbose=False)"
    if ($LASTEXITCODE -ne 0) {
        throw "EasyOCR model preparation failed. Check the Internet connection or use -SkipOcr."
    }

    $modelFiles = @(
        Get-ChildItem -LiteralPath $EasyOcrModelsPath -File -ErrorAction SilentlyContinue
    )
    if ($modelFiles.Count -eq 0) {
        throw "EasyOCR did not create models in: $EasyOcrModelsPath"
    }
}

if ((-not $SkipOcr) -and (-not (Get-Command "tesseract.exe" -ErrorAction SilentlyContinue))) {
    Write-Warning "tesseract.exe was not found. The packaged pytesseract wrapper needs a separate Tesseract OCR installation with the pol language on the target PC."
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
    Write-Host "[1/3] Running compileall..." -ForegroundColor Cyan
    & $PythonExe -m compileall -q main.py modules utils tests
    if ($LASTEXITCODE -ne 0) {
        throw "compileall failed. Build stopped."
    }

    Write-Host "[2/3] Running unit tests..." -ForegroundColor Cyan
    & $PythonExe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Unit tests failed. Build stopped."
    }
}
else {
    Write-Warning "compileall and unit tests were skipped (-SkipTests)."
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
    # On Windows, PyInstaller add-data uses source;destination.
    $pyInstallerArgs += @(
        "--add-data",
        "$PlaywrightBrowsersPath;ms-playwright"
    )
}

if (-not $SkipOcr) {
    $pyInstallerArgs += @(
        "--add-data",
        "$EasyOcrModulePath;easyocr-data"
    )
}

$pyInstallerArgs += "main.py"

Write-Host "[3/3] Building $AppName.exe..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$exePath = Join-Path $OutputDir "$AppName.exe"
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Expected EXE was not created: $exePath"
}

if (-not $SkipBrowserBundle) {
    # PyInstaller 5 commonly uses the EXE folder, PyInstaller 6 commonly uses _internal.
    $bundledBrowserCandidates = @(
        (Join-Path $OutputDir "ms-playwright"),
        (Join-Path $OutputDir "_internal\ms-playwright")
    )
    $bundledBrowsers = @(
        $bundledBrowserCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Container }
    ) | Select-Object -First 1
    if (-not $bundledBrowsers) {
        throw "The ms-playwright directory was not bundled."
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
        throw "The EasyOCR model directory was not bundled."
    }
}

Write-Host ""
Write-Host "Build complete: $exePath" -ForegroundColor Green
Write-Host "Copy or ZIP the entire folder: $OutputDir" -ForegroundColor Yellow
Write-Host "Do not copy only the EXE. The folder contains Qt, Python modules and Playwright browsers." -ForegroundColor Yellow
