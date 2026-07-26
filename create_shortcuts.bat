@echo off
:: ============================================================
:: create_shortcuts.bat — Creates desktop shortcuts for Start and Stop
::
:: Run this ONCE. It will place two shortcuts on your Desktop:
::   "Start ReqAI Platform"
::   "Stop ReqAI Platform"
:: After that, use those Desktop shortcuts — you never need to
:: come back to this folder.
:: ============================================================

title Creating Desktop Shortcuts...
color 0B

echo.
echo  Creating desktop shortcuts for AI Requirement Engineering Platform...
echo.

:: Write a temporary PowerShell script to a temp file and run it
:: This avoids the ^ line-continuation issue in CMD-called PowerShell
set PS_SCRIPT=%TEMP%\create_reqai_shortcuts.ps1
set PROJECT_DIR=%~dp0
set DESKTOP=%USERPROFILE%\Desktop

:: Write the PowerShell script to a temp file
(
echo $ws = New-Object -ComObject WScript.Shell
echo.
echo # Start shortcut
echo $sc = $ws.CreateShortcut('%DESKTOP%\Start ReqAI Platform.lnk'^)
echo $sc.TargetPath      = '%PROJECT_DIR%start.bat'
echo $sc.WorkingDirectory = '%PROJECT_DIR%'
echo $sc.Description      = 'Start AI Requirement Engineering Platform'
echo $sc.IconLocation     = 'C:\Windows\System32\shell32.dll,175'
echo $sc.Save(^)
echo.
echo # Stop shortcut
echo $sc = $ws.CreateShortcut('%DESKTOP%\Stop ReqAI Platform.lnk'^)
echo $sc.TargetPath      = '%PROJECT_DIR%stop.bat'
echo $sc.WorkingDirectory = '%PROJECT_DIR%'
echo $sc.Description      = 'Stop AI Requirement Engineering Platform'
echo $sc.IconLocation     = 'C:\Windows\System32\shell32.dll,131'
echo $sc.Save(^)
) > "%PS_SCRIPT%"

:: Run the PowerShell script
powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

:: Clean up temp file
del "%PS_SCRIPT%" >nul 2>&1

:: Confirm results
if exist "%DESKTOP%\Start ReqAI Platform.lnk" (
    echo  [OK] Created: Desktop\Start ReqAI Platform
) else (
    echo  [WARN] Could not create Start shortcut. Use start.bat directly.
)

if exist "%DESKTOP%\Stop ReqAI Platform.lnk" (
    echo  [OK] Created: Desktop\Stop ReqAI Platform
) else (
    echo  [WARN] Could not create Stop shortcut. Use stop.bat directly.
)

echo.
echo  ============================================================
echo   DONE! Two shortcuts are now on your Desktop:
echo.
echo     Start ReqAI Platform  =  double-click to START the app
echo     Stop ReqAI Platform   =  double-click to STOP the app
echo.
echo   You can delete this create_shortcuts.bat file if you want.
echo  ============================================================
echo.
pause
