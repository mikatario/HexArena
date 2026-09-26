@echo off
chcp 65001 >nul
echo ヘックス・アリーナ exe作成を開始します...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Pythonが見つかりません。https://www.python.org/ からPython 3.11をインストールしてください（Add python.exe to PATHにチェック）。
  pause
  exit /b 1
)
python -m PyInstaller --noconfirm --onefile --windowed --name HexArena --add-data "assets;assets" main.py
echo.
echo 完成しました：dist\HexArena.exe
pause
