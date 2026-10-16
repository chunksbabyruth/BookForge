@echo off
REM Builds BookForge on your own PC. Needs Python 3.10+ from python.org.
py -m pip install -r requirements.txt
py -m PyInstaller --onedir --noconfirm --windowed --name BookForge --icon bookforge.ico --add-data "bookforge.ico;." --add-data "fonts;fonts" --version-file version_info.txt --collect-data docx --collect-data pyphen --collect-submodules reportlab.pdfbase --collect-submodules fontTools.ttLib.tables --collect-submodules fontTools.varLib --collect-all pypdfium2 --collect-all pypdfium2_raw BookForge.py
echo.
echo Done. The program is in dist\BookForge - run BookForge.exe inside it, or zip that folder to share it.
pause
