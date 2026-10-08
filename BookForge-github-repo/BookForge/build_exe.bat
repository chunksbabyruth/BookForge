@echo off
REM Builds BookForge on your own PC. Needs Python 3.10+ from python.org.
py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --onedir --windowed --name BookForge --icon bookforge.ico --add-data "bookforge.ico;." --version-file version_info.txt --collect-data docx --collect-submodules reportlab.pdfbase BookForge.py
echo.
echo Done. The program is in dist\BookForge - run BookForge.exe inside it, or zip that folder to share it.
pause
