@echo off
REM ═══════════════════════════════════════════════════
REM  Spotify Mini Player — Windows .exe Build Script
REM  Çalıştır: build.bat
REM ═══════════════════════════════════════════════════

echo.
echo  [1/4] Gerekli paketler kuruluyor...
pip install pyqt6 requests pyinstaller pynput --quiet

echo.
echo  [2/4] Eski build temizleniyor...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
if exist *.spec  del *.spec

echo.
echo  [3/4] .exe derleniyor (1-2 dakika sürebilir)...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "SpotifyMiniPlayer" ^
  --hidden-import PyQt6.QtCore ^
  --hidden-import PyQt6.QtGui ^
  --hidden-import PyQt6.QtWidgets ^
  --hidden-import requests ^
  --hidden-import pynput ^
  --hidden-import pynput.keyboard ^
  --hidden-import pynput._util.win32 ^
  main.py

echo.
echo  [4/4] Temizlik...
if exist build rmdir /s /q build
if exist *.spec del *.spec

echo.
echo ═══════════════════════════════════════════════════
echo   HAZIR!  dist\SpotifyMiniPlayer.exe
echo ═══════════════════════════════════════════════════
echo.
pause
