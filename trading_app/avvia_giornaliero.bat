@echo off
REM ==============================================================
REM  Avvio automatico del controllo giornaliero (conto DEMO).
REM  Da collegare all'Utilita di pianificazione di Windows (vedi README).
REM  TWS deve essere aperto e collegato al conto demo.
REM ==============================================================
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m scripts.fase4_giornaliero --esegui
