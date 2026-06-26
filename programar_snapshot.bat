@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PYTHON=python"
set "TASK_NAME=SilvestorDailySnapshot"
set "SCHED_TIME=18:00"

echo ===========================================
echo  Programar Snapshot Diario - Silvestor
echo ===========================================
echo.
echo Este script crea una tarea en el Programador
echo de Tareas de Windows para ejecutar el snapshot
echo del portafolio automaticamente cada dia a las
echo %SCHED_TIME%.
echo.
echo La tarea ejecutara: %SCRIPT_DIR%snapshot.py
echo.

set /p CONFIRM="Proceder con la creacion de la tarea? (S/N): "
if /i not "!CONFIRM!"=="S" (
    echo Cancelado.
    pause
    exit /b 0
)

schtasks /create /tn "%TASK_NAME%" /tr "'%PYTHON%' '%SCRIPT_DIR%snapshot.py'" /sc daily /st %SCHED_TIME% /f /rl LIMITED

if !ERRORLEVEL! equ 0 (
    echo.
    echo [OK] Tarea "%TASK_NAME%" creada exitosamente.
    echo      Se ejecutara cada dia a las %SCHED_TIME%.
    echo.
    echo Para probarla manualmente:
    echo   python "%SCRIPT_DIR%snapshot.py"
    echo.
    echo Para ver el historial:
    echo   python "%SCRIPT_DIR%snapshot.py" history
    echo.
    echo Para eliminar la tarea:
    echo   schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo [ERROR] No se pudo crear la tarea.
    echo         Ejecuta este script como Administrador.
)

pause
