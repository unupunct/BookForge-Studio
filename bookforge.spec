# PyInstaller specification for BookForge Studio (one-folder, windowed).
# Build with scripts\build_windows.bat
from PyInstaller.utils.hooks import collect_data_files

datas = [("app/templates", "app/templates")]
datas += collect_data_files("reportlab")  # ReportLab's bundled Vera fonts (fallback only)

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=["docx", "lxml", "lxml.etree", "markdown_it", "pymupdf", "PIL"],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pandas", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml",
              "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BookForgeStudio", console=False,
          disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="BookForgeStudio")
