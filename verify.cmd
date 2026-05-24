@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\verify-local.ps1" %*
