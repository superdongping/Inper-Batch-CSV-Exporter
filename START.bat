@echo off
cd /d "%~dp0"
if exist "Inper Batch CSV Exporter.exe" (
  start "" "Inper Batch CSV Exporter.exe"
) else (
  python inper_exporter_gui.py
  if errorlevel 1 pause
)
