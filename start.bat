@echo off
:: ============================================================
:: start.bat — One-click launcher for AI Requirement Engineering Platform
:: 
:: WHAT THIS DOES:
::   1. Checks that Docker Desktop is running
::   2. Starts all 6 services with docker compose up -d
::   3. Waits for the API health check to pass
::   4. Opens http://localhost:3000 in your default browser
::
:: HOW TO USE: Just double-click this file.
:: ============================================================

title AI Requirement Engineering Platform — Starting...
color 0A

echo.
echo  ============================================================
echo   AI Requirement Engineering Platform
echo   Ezitech ^| AI-017
echo  ============================================================
echo.
echo  [1/4] Checking Docker Desktop is running...

:: Check if docker is available on PATH
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    color 0C
    echo.
    echo  ============================================================
    echo   ERROR: Docker Desktop is not running!
    echo  ============================================================
    echo.
    echo  Please do the following:
    echo    1. Open Docker Desktop from your Start Menu
    echo    2. Wait for the whale icon in the taskbar to stop animating
    echo    3. Then double-click start.bat again
    echo.
    pause
    exit /b 1
)

echo  Docker Desktop is running. OK
echo.
echo  [2/4] Starting all services (database, AI backend, frontend)...
echo  This may take 30-60 seconds on first run...
echo.

:: Move to the project folder (where docker-compose.yml lives)
cd /d "%~dp0"

:: Start all services in detached mode (-d = runs in background, no terminal lock)
docker compose up -d

if %ERRORLEVEL% neq 0 (
    color 0C
    echo.
    echo  ERROR: Failed to start services.
    echo  Please check that docker-compose.yml exists in this folder.
    echo.
    pause
    exit /b 1
)

echo.
echo  [3/4] Waiting for API to be ready...

:: Poll the /health endpoint every 3 seconds, up to 10 attempts (30 seconds total)
set ATTEMPTS=0
set MAX_ATTEMPTS=10

:HEALTH_CHECK
set /a ATTEMPTS+=1
if %ATTEMPTS% gtr %MAX_ATTEMPTS% (
    echo.
    echo  WARNING: API did not respond in time, but services are starting.
    echo  Try opening http://localhost:3000 in 30 seconds.
    goto OPEN_BROWSER
)

:: Use curl to check the health endpoint (curl is built into Windows 10/11)
curl -s -o nul -w "%%{http_code}" http://localhost:8000/health 2>nul | findstr "200" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo  API is healthy! OK
    goto OPEN_BROWSER
)

echo  Waiting... (attempt %ATTEMPTS%/%MAX_ATTEMPTS%)
timeout /t 3 /nobreak >nul
goto HEALTH_CHECK

:OPEN_BROWSER
echo.
echo  [4/4] Opening browser...
start http://localhost:3000

echo.
echo  ============================================================
echo   Done! App is running at http://localhost:3000
echo.
echo   API Docs:    http://localhost:8000/api/docs
echo   Health:      http://localhost:8000/health
echo.
echo   To STOP the app, double-click stop.bat
echo  ============================================================
echo.

:: Keep window open for 5 seconds then close
timeout /t 5 /nobreak >nul
exit /b 0
