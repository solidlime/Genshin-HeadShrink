@echo off
chcp 65001 >nul
REM launch_blender.bat -- HeadShrink addon install + Blender GUI launcher
REM
REM Usage:
REM   launch_blender.bat          (GUI launch)
REM   launch_blender.bat /h       (headless: addon check only, no GUI)
REM   launch_blender.bat /i       (install only: addon install + enable, exit)
REM
REM Once installed, "HeadShrink" persists in Edit > Preferences > Add-ons
REM as User category. Subsequent Blender launches show N-panel "HeadShrink" tab.

setlocal
set BLENDER=D:\Application\blender\blender.exe
set PROJECT=%~dp0
set ADDON_SRC=%PROJECT%scripts\headshrink_addon.py
set ADDON_DEST_DIR=%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons
set ADDON_DEST=%ADDON_DEST_DIR%\headshrink.py

set MODE=gui
if /i "%~1"=="/h" set MODE=headless
if /i "%~1"=="/i" set MODE=install
if /i "%~1"=="--headless" set MODE=headless
if /i "%~1"=="--install" set MODE=install

if not exist "%BLENDER%" (
    echo [ERROR] Blender not found: %BLENDER%
    echo         Edit BLENDER line in this file or set the env var.
    pause
    exit /b 1
)
if not exist "%ADDON_SRC%" (
    echo [ERROR] Addon not found: %ADDON_SRC%
    pause
    exit /b 1
)

echo ============================================
echo  HeadShrink Blender Launcher
echo  Project: %PROJECT%
echo  Blender: %BLENDER%
echo  Mode:    %MODE%
echo ============================================

REM Step 1: link addon into Blender's user scripts/addons dir (symlink, fallback to copy)
echo [1/3] Installing addon (symlink)...
if not exist "%ADDON_DEST_DIR%" (
    mkdir "%ADDON_DEST_DIR%"
    if errorlevel 1 (
        echo [ERROR] mkdir failed: %ADDON_DEST_DIR%
        pause
        exit /b 1
    )
)
if exist "%ADDON_DEST%" (
    del "%ADDON_DEST%" >nul 2>&1
    rmdir "%ADDON_DEST%" >nul 2>&1
)
mklink "%ADDON_DEST%" "%ADDON_SRC%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] mklink failed - run as Administrator or enable Developer Mode
    echo         Symlink: %ADDON_DEST% -> %ADDON_SRC%
    echo         Right-click launch_blender.bat ^> Run as administrator
    pause
    exit /b 1
)
echo       Installed (symlink): %ADDON_DEST% -> %ADDON_SRC%

REM Step 2: enable addon + save userpref (one-time)
echo [2/3] Enabling addon in Blender user prefs...
"%BLENDER%" --background --python-exit-code 1 --python-expr "import addon_utils, bpy; addon_utils.enable('headshrink'); bpy.ops.wm.save_userpref(); print('[HS] enabled + saved')" 2>nul
if errorlevel 1 (
    echo [WARN] auto-enable failed; enable manually in Preferences - Add-ons.
) else (
    echo       Enabled + userpref saved.
)

REM Step 3: launch Blender
if /i "%MODE%"=="install" (
    echo [3/3] Install complete. Blender not launched.
    exit /b 0
)

echo [3/3] Launching Blender GUI...
"%BLENDER%"
if errorlevel 1 (
    echo [ERROR] Blender exited with error.
    pause
    exit /b 1
)
