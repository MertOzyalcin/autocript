@echo off
setlocal
cd /d "%~dp0"

rem Konsol dili tek yerde belirlenir: sistem arayuz dili Turkce ise tr, degilse en.
rem AUTOCRIPT_KONSOL_DIL onceden ayarliysa o korunur; PowerShell betigi ve Python da bunu okur.
if defined AUTOCRIPT_KONSOL_DIL goto dil_hazir
for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "[Globalization.CultureInfo]::CurrentUICulture.TwoLetterISOLanguageName"`) do set "AUTOCRIPT_KONSOL_DIL=%%L"
:dil_hazir
if /i not "%AUTOCRIPT_KONSOL_DIL%"=="tr" set "AUTOCRIPT_KONSOL_DIL=en"

rem Akilli Uygulama Denetimi (Smart App Control) imzasiz araclari engeller. Durum yonetici izni olmadan okunur.
rem 0x1 acik: kurulum baslamaz. 0x2 degerlendirme: uyari verilir. Deger yoksa ya da okunamazsa sessizce devam.
set "SAC_DURUM="
for /f "tokens=1,3" %%A in ('%SystemRoot%\System32\reg.exe query HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy /v VerifiedAndReputablePolicyState 2^>nul') do if /i "%%A"=="VerifiedAndReputablePolicyState" set "SAC_DURUM=%%B"
if "%SAC_DURUM%"=="0x1" goto sac_acik
if "%SAC_DURUM%"=="0x2" call :sac_degerlendirme

rem Her sey bu klasorun icinde kalir: PATH, kayit defteri ve kullanici profiline yazilmaz.
set "UV_CACHE_DIR=%~dp0tools\uv-cache"
set "UV_PYTHON_INSTALL_DIR=%~dp0tools\python"
set "UV_PROJECT_ENVIRONMENT=%~dp0tools\venv"
set "UV_PYTHON_PREFERENCE=only-managed"
rem pyproject.toml'daki python-downloads = never, acik kurulumu da engeller; manual izin verir.
set "UV_PYTHON_DOWNLOADS=manual"
rem Antivirus HTTPS taramasi icin: uv sistem sertifika deposunu kullanir.
set "UV_SYSTEM_CERTS=1"

if not exist "%~dp0tools\uv\uv.exe" (
    if /i "%AUTOCRIPT_KONSOL_DIL%"=="tr" (echo uv indiriliyor...) else (echo Downloading uv...)
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dagitim\uv-indir.ps1"
    if errorlevel 1 goto hata
)
if not exist "%~dp0tools\uv\uv.exe" goto hata

"%~dp0tools\uv\uv.exe" python install 3.14 --no-registry --no-bin
if errorlevel 1 (
    if exist "%~dp0tools\venv\Scripts\python.exe" (
        if /i "%AUTOCRIPT_KONSOL_DIL%"=="tr" (echo Uyari: Python guncellenemedi, mevcut kurulumla devam ediliyor.) else (echo Warning: Python could not be updated, continuing with the existing installation.)
    ) else (
        goto hata
    )
)

rem Konusmasiz bolum dedektoru (numpy, onnxruntime) yalnizca .env icinde NONSPEECH_DETECTOR=silero ise kurulur.
set "VADGRUP="
if exist "%~dp0.env" findstr /r /i /c:"^NONSPEECH_DETECTOR=silero" "%~dp0.env" >nul 2>nul && set "VADGRUP=--group vad"
"%~dp0tools\uv\uv.exe" sync --frozen --no-dev %VADGRUP% --python 3.14
if errorlevel 1 (
    if exist "%~dp0tools\venv\Scripts\python.exe" (
        if /i "%AUTOCRIPT_KONSOL_DIL%"=="tr" (echo Uyari: paketler guncellenemedi, mevcut kurulumla devam ediliyor.) else (echo Warning: packages could not be updated, continuing with the existing installation.)
    ) else (
        goto hata
    )
)

"%~dp0tools\venv\Scripts\python.exe" -m autocript %*
if errorlevel 1 goto hata
exit /b 0

:hata
echo.
if /i "%AUTOCRIPT_KONSOL_DIL%"=="tr" (echo Bir sorun oldu. Yukaridaki mesaji okuyun.) else (echo Something went wrong. Read the message above.)
pause
exit /b 1

:sac_acik
echo.
if /i "%AUTOCRIPT_KONSOL_DIL%"=="tr" (echo Akilli Uygulama Denetimi bu bilgisayarda acik.) else (echo Smart App Control is on for this computer.)
call :sac_bilgi
pause
exit /b 1

:sac_degerlendirme
echo.
if /i "%AUTOCRIPT_KONSOL_DIL%"=="tr" (echo Uyari: Akilli Uygulama Denetimi degerlendirme modunda.) else (echo Warning: Smart App Control is in evaluation mode.)
call :sac_bilgi
exit /b 0

:sac_bilgi
if /i not "%AUTOCRIPT_KONSOL_DIL%"=="tr" goto sac_bilgi_en
echo Denetim aciksa imzasiz araclari (Python, ffmpeg vb.) engeller ve uygulama
echo bu bilgisayarda calismaz. Isteyen su bolumden kapatabilir:
echo Windows Guvenligi ^> Uygulama ve tarayici denetimi ^> Akilli Uygulama Denetimi
echo Karar sizindir.
echo.
exit /b 0
:sac_bilgi_en
echo When it is on, it blocks unsigned tools (Python, ffmpeg and others) and the
echo app does not run on this computer. If you wish, you can turn it off here:
echo Windows Security ^> App ^& browser control ^> Smart App Control
echo The choice is yours.
echo.
exit /b 0
