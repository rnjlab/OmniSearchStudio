import sys
import os
import tempfile
import struct
import zipfile
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Ensure app can be imported
sys.path.insert(0, os.path.abspath("."))

from ui.main_window import MainWindow
from ui.preview_panel import PreviewPanel
from ui.search_table_model import SearchTableModel
from ui.about_dialog import AboutDialog
from ui.integration_dialog import IntegrationDialog
from ui.duplicates_dialog import DuplicatesDialog
from ui.large_files_dialog import LargeFilesDialog
from core.models import FileEntry, FileCategory
from core.preview_loader import (
    load_file_preview, get_theme_colors,
    extract_docx_preview, extract_xlsx_preview,
    extract_pptx_preview, extract_csv_preview,
    render_dwg_card_html, render_shapefile_card_html
)

def test_theme_system():
    print("--- Starting Theme System & Residual Artifacts Verification ---")
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Verify MainWindow Default Theme
    win = MainWindow()
    assert win.current_theme == "light", f"Expected default 'light', got '{win.current_theme}'"
    assert "Dark" in win.btn_theme.text(), f"Expected Dark toggle button text, got '{win.btn_theme.text()}'"
    print("[PASS] MainWindow defaults to 'light' with correct button label.")

    # 2. Verify Theme Toggling
    win._toggle_theme()
    assert win.current_theme == "dark", f"Expected 'dark' after toggle, got '{win.current_theme}'"
    assert "Light" in win.btn_theme.text(), f"Expected Light toggle button text, got '{win.btn_theme.text()}'"
    assert win.table_model.current_theme == "dark"
    assert win.preview_panel.current_theme == "dark"
    print("[PASS] MainWindow successfully toggles to 'dark'.")

    win._toggle_theme()
    assert win.current_theme == "light", f"Expected 'light' after toggle, got '{win.current_theme}'"
    assert "Dark" in win.btn_theme.text(), f"Expected Dark toggle button text, got '{win.btn_theme.text()}'"
    assert win.table_model.current_theme == "light"
    assert win.preview_panel.current_theme == "light"
    print("[PASS] MainWindow successfully toggles back to 'light'.")

    # 3. Verify SearchTableModel Theme-Aware Brushes
    model = SearchTableModel()
    sample_entry = FileEntry(
        name="test.txt",
        path="C:/test.txt",
        ext=".txt",
        size=1024,
        mtime=1700000000,
        is_dir=False,
        category=FileCategory.DOCUMENT
    )
    model.set_entries([sample_entry])

    model.set_theme("light")
    brush_path_light = model.data(model.index(0, 1), Qt.ItemDataRole.ForegroundRole)
    assert brush_path_light.color().name() == "#64748b", f"Expected #64748b, got {brush_path_light.color().name()}"
    brush_size_light = model.data(model.index(0, 2), Qt.ItemDataRole.ForegroundRole)
    assert brush_size_light.color().name() == "#0284c7", f"Expected #0284c7, got {brush_size_light.color().name()}"

    model.set_theme("dark")
    brush_path_dark = model.data(model.index(0, 1), Qt.ItemDataRole.ForegroundRole)
    assert brush_path_dark.color().name() == "#94a3b8", f"Expected #94a3b8, got {brush_path_dark.color().name()}"
    brush_size_dark = model.data(model.index(0, 2), Qt.ItemDataRole.ForegroundRole)
    assert brush_size_dark.color().name() == "#38bdf8", f"Expected #38bdf8, got {brush_size_dark.color().name()}"
    print("[PASS] SearchTableModel ForegroundRole adapts to active theme.")

    # 4. Verify PreviewPanel In-Doc Quick Search & Controls Apply Theme
    panel = win.preview_panel
    panel.apply_theme("light")
    assert panel.current_theme == "light"
    panel.apply_theme("dark")
    assert panel.current_theme == "dark"
    panel.apply_theme("light")
    print("[PASS] PreviewPanel apply_theme runs cleanly for both themes.")

    # 5. Test Dialogs initialization and theme adaptation
    about_light = AboutDialog(parent=win, theme="light")
    assert about_light.theme == "light"
    about_dark = AboutDialog(parent=win, theme="dark")
    assert about_dark.theme == "dark"

    integ_light = IntegrationDialog(parent=win, theme="light")
    assert integ_light.theme == "light"
    integ_dark = IntegrationDialog(parent=win, theme="dark")
    assert integ_dark.theme == "dark"

    dups = DuplicatesDialog([sample_entry], parent=win)
    assert dups.theme == "light"

    large = LargeFilesDialog([sample_entry], parent=win)
    assert large.theme == "light"
    print("[PASS] Dialogs dynamically detect and inherit the parent theme.")

    # 6. Test Document Previews with both Light and Dark modes
    with tempfile.TemporaryDirectory() as td:
        # 6a. CSV
        csv_file = os.path.join(td, "test.csv")
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("A,B,C\n1,2,3\n4,5,6\n")
        res_csv_light = extract_csv_preview(csv_file, theme="light")
        assert res_csv_light["preview_type"] == "html"
        assert "#ffffff" in res_csv_light["content"] or "#f8fafc" in res_csv_light["content"]
        assert "c[" not in res_csv_light["content"]

        res_csv_dark = extract_csv_preview(csv_file, theme="dark")
        assert res_csv_dark["preview_type"] == "html"
        assert "#1e293b" in res_csv_dark["content"] or "#0f172a" in res_csv_dark["content"]
        assert "c[" not in res_csv_dark["content"]
        print("[PASS] CSV Preview renders correctly for Light and Dark.")

        # 6b. DWG Card
        dwg_info = {"release": "AutoCAD 2024", "version_code": "AC1032"}
        dwg_entry = FileEntry("test.dwg", td, ".dwg", 1024, 1700000000, False, FileCategory.CAD)
        dwg_html_light = render_dwg_card_html(dwg_entry.full_path, dwg_info, dwg_entry, theme="light")
        assert "c[" not in dwg_html_light
        assert "#ffffff" in dwg_html_light or "#0f172a" in dwg_html_light

        dwg_html_dark = render_dwg_card_html(dwg_entry.full_path, dwg_info, dwg_entry, theme="dark")
        assert "c[" not in dwg_html_dark
        print("[PASS] DWG Card renders correctly for Light and Dark.")

        # 6c. Shapefile Card
        shp_info = {"shape_type": "Polygon", "bounds": "X: [0, 10]<br>Y: [0, 10]"}
        shp_entry = FileEntry("test.shp", td, ".shp", 2048, 1700000000, False, FileCategory.GIS)
        shp_html_light = render_shapefile_card_html(shp_entry.full_path, shp_info, shp_entry, theme="light")
        assert "c[" not in shp_html_light
        shp_html_dark = render_shapefile_card_html(shp_entry.full_path, shp_info, shp_entry, theme="dark")
        assert "c[" not in shp_html_dark
        print("[PASS] Shapefile Card renders correctly for Light and Dark.")

        # 6d. PPTX Mock
        pptx_file = os.path.join(td, "test.pptx")
        with zipfile.ZipFile(pptx_file, "w") as zf:
            zf.writestr(
                "ppt/slides/slide1.xml",
                b'<?xml version="1.0" encoding="UTF-8"?><p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Slide Title</a:t></a:r></a:p><a:p><a:r><a:t>Bullet 1</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
            )
        res_pptx_light = extract_pptx_preview(pptx_file, theme="light")
        assert res_pptx_light["preview_type"] == "html"
        assert "c[" not in res_pptx_light["content"]

        res_pptx_dark = extract_pptx_preview(pptx_file, theme="dark")
        assert res_pptx_dark["preview_type"] == "html"
        assert "c[" not in res_pptx_dark["content"]
        print("[PASS] PPTX Preview renders correctly for Light and Dark.")

        # 6e. XLSX Mock
        xlsx_file = os.path.join(td, "test.xlsx")
        with zipfile.ZipFile(xlsx_file, "w") as zf:
            zf.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Overview" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""")
            zf.writestr("xl/sharedStrings.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1">
  <si><t>Hello World</t></si>
</sst>""")
            zf.writestr("xl/worksheets/sheet1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c></row>
  </sheetData>
</worksheet>""")
        res_xlsx_light = extract_xlsx_preview(xlsx_file, theme="light")
        assert res_xlsx_light["preview_type"] == "spreadsheet"
        assert "c[" not in res_xlsx_light["content"]
        assert "Hello World" in res_xlsx_light["content"]

        res_xlsx_dark = extract_xlsx_preview(xlsx_file, theme="dark")
        assert res_xlsx_dark["preview_type"] == "spreadsheet"
        assert "c[" not in res_xlsx_dark["content"]
        assert "Hello World" in res_xlsx_dark["content"]
        print("[PASS] XLSX Preview renders correctly for Light and Dark.")

    print(">>> ALL THEME SYSTEM & RESIDUAL ARTIFACT TESTS PASSED! <<<")

if __name__ == "__main__":
    test_theme_system()
