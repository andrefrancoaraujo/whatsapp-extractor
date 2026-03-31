@echo off
REM Build WhatsApp Extractor .exe for Windows
REM Run this on a Windows machine with Python installed

echo === WhatsApp Extractor Build ===
echo.

REM 1. Install dependencies
echo Installing dependencies...
pip install pyinstaller requests wa-crypt-tools pycryptodomex tkinterdnd2
echo.

REM 2. Download ADB platform-tools if not present
if not exist "adb\adb.exe" (
    echo Downloading ADB platform-tools...
    curl -L -o platform-tools.zip https://dl.google.com/android/repository/platform-tools-latest-windows.zip
    powershell -command "Expand-Archive -Path platform-tools.zip -DestinationPath temp_adb -Force"
    mkdir adb 2>nul
    copy temp_adb\platform-tools\adb.exe adb\
    copy temp_adb\platform-tools\AdbWinApi.dll adb\
    copy temp_adb\platform-tools\AdbWinUsbApi.dll adb\
    rmdir /s /q temp_adb
    del platform-tools.zip
    echo ADB downloaded.
) else (
    echo ADB already present.
)
echo.

REM 3. Build the .exe
echo Building .exe with PyInstaller...
cd extractor
pyinstaller --onefile --windowed ^
    --name WhatsAppExtractor ^
    --add-data "../adb;adb" ^
    --collect-all tkinterdnd2 ^
    --hidden-import wa_crypt_tools ^
    --hidden-import wa_crypt_tools.lib.key.keyfactory ^
    --hidden-import wa_crypt_tools.lib.db.dbfactory ^
    --additional-hooks-dir=. ^
    --icon NONE ^
    main.py
cd ..

REM 4. Copy to dist
mkdir dist 2>nul
copy extractor\dist\WhatsAppExtractor.exe dist\
echo.
echo === Build complete! ===
echo Output: dist\WhatsAppExtractor.exe
pause
