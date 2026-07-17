@echo off
setlocal

echo ============================================
echo   YT to MP3 Converter - Build script
echo ============================================
echo.

REM Check ffmpeg/ffprobe - disabled
REM if not exist "bin\ffmpeg.exe" (
REM     echo [ERROR] bin\ffmpeg.exe missing
REM     exit /b 1
REM )
REM if not exist "bin\ffprobe.exe" (
REM     echo [ERROR] bin\ffprobe.exe missing
REM     exit /b 1
REM )

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)

echo.
echo [2/3] Building app with PyInstaller...
python -m PyInstaller Youtube-Mp3-Converter.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    pause
    exit /b 1
)

echo.
echo [3/3] Building installer with Inno Setup...
where ISCC.exe >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ISCC.exe missing from PATH
    echo Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
) else (
    ISCC.exe installer.iss
    if errorlevel 1 (
        echo [ERROR] Inno Setup compile failed
        pause
        exit /b 1
    )
)

:done
echo.
echo ============================================
echo   Done!
echo   - App:       dist\YT-MP3-Converter\
echo   - Installer: installer_output\YT-MP3-Converter-Setup-*.exe
echo ============================================
pause
