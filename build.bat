@echo off
chcp 65001 >nul
echo ヘックス・アリーナ exe作成を開始します...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Pythonが見つかりません。https://www.python.org/ からPython 3.11をインストールしてください（Add python.exe to PATHにチェック）。
  pause
  exit /b 1
)
for /f "delims=" %%i in ('python -c "import panda3d, os; print(os.path.join(os.path.dirname(panda3d.__file__), 'libpandagl.dll'))"') do set PANDAGL=%%i
python -m PyInstaller --noconfirm --onefile --windowed --name HexArena --add-data "assets;assets" --add-data "unit_data.json;." --add-binary "%PANDAGL%;panda3d" main.py
echo.
echo 完成しました：dist\HexArena.exe
pause
