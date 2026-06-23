@echo off
title Sistema de Etiquetas - Iniciando...
color 0A

echo.
echo  ================================================
echo   SISTEMA DE ETIQUETAS - Iniciando servidores...
echo  ================================================
echo.

:: --- Verifica que Python esta disponible ---
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python no encontrado. Instala Python y vuelve a intentarlo.
    pause
    exit /b 1
)

:: --- Verifica que Node.js esta disponible ---
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Node.js no encontrado. Instala Node.js y vuelve a intentarlo.
    pause
    exit /b 1
)

echo  [1/2] Iniciando Backend (FastAPI - puerto 8000)...
start "Backend - FastAPI" cmd /k "cd /d "%~dp0backend" && color 0B && echo  Backend corriendo en http://localhost:8000 && echo. && python -m uvicorn main:app --reload --port 8000"

:: Espera 2 segundos para que el backend arranque primero
timeout /t 2 /nobreak >nul

echo  [2/2] Iniciando Frontend (Vite - puerto 5173)...
start "Frontend - Vite" cmd /k "cd /d "%~dp0" && color 0D && echo  Frontend corriendo en http://localhost:5173 && echo. && npm run dev"

:: Espera a que Vite arranque y abre el navegador
timeout /t 4 /nobreak >nul

echo.
echo  [OK] Servidores iniciados. Abriendo navegador...
start "" "http://localhost:5173"

echo.
echo  Puedes cerrar esta ventana. Los servidores siguen corriendo
echo  en sus propias ventanas de terminal.
echo.
pause
