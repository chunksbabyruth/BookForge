@echo off
REM Builds BookForge on your own PC. Needs Python 3.10+ from python.org.
py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --onedir --windowed --name BookForge --icon bookforge.ico --add-data "bookforge.ico;." --version-file version_info.txt --add-data "fonts;fonts" --collect-data docx --collect-data pyphen --collect-submodules reportlab.pdfbase --collect-submodules fontTools.ttLib.tables --collect-submodules fontTools.varLib BookForge.py
echo.
echo Done. The program is in dist\BookForge - run BookForge.exe inside it, or zip that folder to share it.
pause
