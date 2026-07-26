@echo off
:: ============================================================
:: stop.bat — One-click stopper for AI Requirement Engineering Platform
::
:: WHAT THIS DOES:
::   1. Checks Docker is available
::   2. Runs docker compose down (WITHOUT -v flag — your database data is SAFE)
::   3. Confirms all services are stopped
::
:: IMPORTANT: Your database data is NOT deleted.
::   To delete data (factory reset), you would need to run:
::   docker compose down -v  (we never do this automatically)
::
:: HOW TO USE: Just double-click this file.
:: ============================================================

title AI Requirement Engineering Platform — Stopping...
color 0E

echo.
echo  ============================================================
echo   AI Requirement Engineering Platform — Stopping
echo  ============================================================
echo.
echo  [1/2] Checking Docker is available...

docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    color 0C
    echo.
    echo  ERROR: Docker Desktop is not running.
    echo  The app may already be stopped.
    echo.
    pause
    exit /b 1
)

:: Move to the project folder
cd /d "%~dp0"

echo  [2/2] Stopping all services...
echo.
echo  NOTE: Your database and uploaded files are NOT deleted.
echo.

:: docker compose down stops containers but keeps volumes (your data stays safe)
docker compose down

if %ERRORLEVEL% neq 0 (
    color 0C
    echo.
    echo  ERROR: Something went wrong while stopping.
    echo  You can also stop manually from Docker Desktop.
    echo.
    pause
    exit /b 1
)

color 0A
echo.
echo  ============================================================
echo   All services stopped successfully.
echo   Your database data is safe and preserved.
echo.
echo   To start again, double-click start.bat
echo  ============================================================
echo.

timeout /t 4 /nobreak >nul
exit /b 0
