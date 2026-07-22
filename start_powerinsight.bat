@echo off & cd /d "%~dp0" & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_powerinsight.ps1" || (echo. & echo PowerInsight failed to start. & pause)
