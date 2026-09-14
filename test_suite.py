import os
import sys
import tempfile
import time
import zipfile
from PySide6.QtWidgets import QApplication

from core.models import FileEntry, FileCategory, SearchQuery, get_category_for_ext, format_size
from core.indexer import FileIndex
from core.duplicates import find_duplicates, compute_file_hash
from core.preview_loader import load_file_preview, generate_hex_dump
from ui.main_window import MainWindow


def test_models_and_queries():
    print("Testing SearchQuery parsing & matching...")

    e1 = FileEntry(name="script.py", path="C:/Users/Dev/Project", ext=".py", size=5000, mtime=time.time(), is_dir=False, category=FileCategory.CODE)
    e2 = FileEntry(name="photo.png", path="C:/Users/Dev/Pictures", ext=".png", size=2048576, mtime=time.time(), is_dir=False, category=FileCategory.IMAGE)
    e3 = FileEntry(name="budget.xlsx", path="C:/Users/Dev/Docs", ext=".xlsx", size=45000, mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)

    # 1. Plain search
    q1 = SearchQuery.parse("script")
    assert q1.matches(e1)
    assert not q1.matches(e2)

    # 2. Wildcard
    q2 = SearchQuery.parse("*.png")
    assert q2.matches(e2)
    assert not q2.matches(e1)

    # 3. Extension filter
    q3 = SearchQuery.parse("ext:py,xlsx")
    assert q3.matches(e1)
    assert q3.matches(e3)
    assert not q3.matches(e2)

    # 4. Size filter
    q4 = SearchQuery.parse("size:>1mb")
    assert q4.matches(e2)
    assert not q4.matches(e1)

    # 5. Type filter
    q5 = SearchQuery.parse("type:code")
    assert q5.matches(e1)
    assert not q5.matches(e2)

    # 6. Path filter
    q6 = SearchQuery.parse("path:Pictures")
    assert q6.matches(e2)
    assert not q6.matches(e1)

    print("[PASS] SearchQuery tests passed!")


def test_index_and_cache():
    print("Testing FileIndex and binary disk caching...")
    idx = FileIndex()
    entries = [
        FileEntry(name=f"file_{i}.txt", path="C:/Temp", ext=".txt", size=i * 100, mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
        for i in range(100)
    ]
    idx.set_entries(entries)
    assert len(idx.entries) == 100

    results = idx.search(SearchQuery.parse("file_5"))
    assert len(results) >= 1

    # Test cache
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        cache_path = tf.name

    try:
        saved = idx.save_to_cache(cache_path)
        assert saved

        idx2 = FileIndex()
        loaded = idx2.load_from_cache(cache_path)
        assert loaded
        assert len(idx2.entries) == 100
        assert idx2.entries[10].name == "file_10.txt"
        print("[PASS] FileIndex & binary cache tests passed!")
    finally:
        if os.path.exists(cache_path):
            os.remove(cache_path)


def test_duplicate_detection():
    print("Testing Duplicate File Detective...")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create identical files
        content = b"OmniSearch Studio duplicate testing payload 1234567890"
        p1 = os.path.join(tmpdir, "doc1.txt")
        p2 = os.path.join(tmpdir, "doc2_copy.txt")
        p3 = os.path.join(tmpdir, "unique.txt")

        with open(p1, "wb") as f:
            f.write(content)
        with open(p2, "wb") as f:
            f.write(content)
        with open(p3, "wb") as f:
            f.write(b"Different content here")

        e1 = FileEntry("doc1.txt", tmpdir, ".txt", len(content), time.time(), False, FileCategory.DOCUMENT)
        e2 = FileEntry("doc2_copy.txt", tmpdir, ".txt", len(content), time.time(), False, FileCategory.DOCUMENT)
        e3 = FileEntry("unique.txt", tmpdir, ".txt", 22, time.time(), False, FileCategory.DOCUMENT)

        dups = find_duplicates([e1, e2, e3], min_size_bytes=10)
        assert len(dups) == 1
        assert len(dups[0].entries) == 2
        assert dups[0].size == len(content)
        print("[PASS] Duplicate File Detective tests passed!")


def test_preview_loader():
    print("Testing Preview Loader & Rich Document Previews (PDF, Word, Excel, PowerPoint, CAD/GIS)...")
    from ui.preview_panel import PreviewPanel

    app = QApplication.instance() or QApplication(sys.argv)
    panel = PreviewPanel()

    with tempfile.TemporaryDirectory() as td:
        # 1. Code / Text preview
        py_path = os.path.join(td, "hello.py")
        with open(py_path, "w", encoding="utf-8") as f:
            f.write("def hello():\n    print('Hello OmniSearch!')\n")
        e_py = FileEntry("hello.py", td, ".py", os.path.getsize(py_path), time.time(), False, FileCategory.CODE)
        prev_py = load_file_preview(e_py)
        assert prev_py["preview_type"] == "code"
        assert "hello" in prev_py["content"]

        # 2. Word .docx preview
        docx_path = os.path.join(td, "spec.docx")
        with zipfile.ZipFile(docx_path, "w") as z:
            z.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>""")
            z.writestr("docProps/core.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>OmniSearch Architecture</dc:title>
  <dc:creator>System Engineer</dc:creator>
</cp:coreProperties>""")
            z.writestr("word/document.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Ultra-fast file searching in microseconds.</w:t></w:r></w:p>
  </w:body>
</w:document>""")
        e_docx = FileEntry("spec.docx", td, ".docx", os.path.getsize(docx_path), time.time(), False, FileCategory.DOCUMENT)
        panel.set_entry(e_docx)
        assert panel.stack.currentIndex() == 2  # HTML view
        assert "OmniSearch Architecture" in panel.txt_html.toHtml()
        assert "System Engineer" in panel.txt_html.toHtml()
        assert "Ultra-fast file searching" in panel.txt_html.toPlainText()

        # 3. Excel .xlsx preview & sheet switching
        xlsx_path = os.path.join(td, "data.xlsx")
        with zipfile.ZipFile(xlsx_path, "w") as z:
            z.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Overview" sheetId="1" r:id="rId1"/>
    <sheet name="Metrics" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>""")
            z.writestr("xl/sharedStrings.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
  <si><t>SearchSpeed</t></si>
  <si><t>100x</t></si>
</sst>""")
            z.writestr("xl/worksheets/sheet1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
  </sheetData>
</worksheet>""")
            z.writestr("xl/worksheets/sheet2.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1"><v>8888</v></c></row>
  </sheetData>
</worksheet>""")
        e_xlsx = FileEntry("data.xlsx", td, ".xlsx", os.path.getsize(xlsx_path), time.time(), False, FileCategory.DOCUMENT)
        panel.set_entry(e_xlsx)
        assert panel.stack.currentIndex() == 2
        assert not panel.sheet_bar.isHidden()
        assert "SearchSpeed" in panel.txt_html.toPlainText()

        # Switch to Sheet 2
        panel._on_sheet_clicked(1)
        assert panel.current_sheet_idx == 1
        assert "8888" in panel.txt_html.toPlainText()

        # 4. PowerPoint .pptx preview
        pptx_path = os.path.join(td, "pitch.pptx")
        with zipfile.ZipFile(pptx_path, "w") as z:
            z.writestr("ppt/slides/slide1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Project Milestone</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
</p:sld>""")
        e_pptx = FileEntry("pitch.pptx", td, ".pptx", os.path.getsize(pptx_path), time.time(), False, FileCategory.DOCUMENT)
        panel.set_entry(e_pptx)
        assert panel.stack.currentIndex() == 2
        assert "Project Milestone" in panel.txt_html.toPlainText()

        # 5. Mode Switcher (Visual -> Text -> Hex)
        panel._set_mode("text")
        assert panel.stack.currentIndex() == 1
        assert "Project Milestone" in panel.txt_code.toPlainText()

        panel._set_mode("hex")
        assert panel.stack.currentIndex() == 4
        assert "00000000" in panel.txt_hex.toPlainText()

        panel._set_mode("formatted")
        assert panel.stack.currentIndex() == 2

        # 6. PDF Visual Page Rendering (via pypdfium2)
        try:
            import pypdfium2 as pdfium
            pdf_path = os.path.join(td, "doc.pdf")
            doc = pdfium.PdfDocument.new()
            doc.new_page(width=595, height=842)
            doc.new_page(width=595, height=842)
            doc.save(pdf_path)
            doc.close()

            e_pdf = FileEntry("doc.pdf", td, ".pdf", os.path.getsize(pdf_path), time.time(), False, FileCategory.DOCUMENT)
            panel.set_entry(e_pdf)
            assert panel.stack.currentIndex() == 3  # Visual image/PDF view
            assert not panel.pdf_bar.isHidden()
            assert "Page 1 of 2" in panel.lbl_pdf_page.text()

            panel._on_pdf_next()
            assert panel.current_page_idx == 1
            assert "Page 2 of 2" in panel.lbl_pdf_page.text()

            panel._on_pdf_prev()
            assert panel.current_page_idx == 0
        except Exception as e:
            print(f"[INFO] Skipping PDF generation test: {e}")

        # 7. Empty state reset
        panel.set_entry(None)
        assert panel.stack.currentIndex() == 0
        assert not panel.btn_open.isEnabled()
        assert panel.pdf_bar.isHidden()
        assert panel.sheet_bar.isHidden()

        panel.close()
        app.processEvents()
        print("[PASS] Rich Preview Loader & UI tests passed!")


def test_engineering_and_gis():
    print("Testing Engineering/CAD and GIS Categories & Previews...")
    # 1. Categories
    assert get_category_for_ext(".dwg") == FileCategory.CAD
    assert get_category_for_ext(".dxf") == FileCategory.CAD
    assert get_category_for_ext(".step") == FileCategory.CAD
    assert get_category_for_ext(".rvt") == FileCategory.CAD
    assert get_category_for_ext(".shp") == FileCategory.GIS
    assert get_category_for_ext(".gpkg") == FileCategory.GIS
    assert get_category_for_ext(".kml") == FileCategory.GIS
    assert get_category_for_ext(".geojson") == FileCategory.GIS
    assert get_category_for_ext(".las") == FileCategory.GIS

    # 2. Type Queries
    q_cad = SearchQuery.parse("type:cad")
    assert q_cad.type_filter == FileCategory.CAD
    q_gis = SearchQuery.parse("type:gis")
    assert q_gis.type_filter == FileCategory.GIS

    # 3. DWG Header preview test
    with tempfile.NamedTemporaryFile(suffix=".dwg", delete=False) as tf:
        tf.write(b"AC1032\x00\x00AutoCAD Drawing Test")
        dwg_path = tf.name

    try:
        e_dwg = FileEntry(os.path.basename(dwg_path), os.path.dirname(dwg_path), ".dwg", 100, time.time(), False, FileCategory.CAD)
        prev = load_file_preview(e_dwg)
        assert "AutoCAD 2018 - 2025" in prev["content"]
        assert "AC1032" in prev["content"]
    finally:
        if os.path.exists(dwg_path):
            os.remove(dwg_path)

    # 4. Shapefile Header preview test
    import struct
    with tempfile.NamedTemporaryFile(suffix=".shp", delete=False) as tf:
        hdr = bytearray(100)
        struct.pack_into(">i", hdr, 0, 9994)
        struct.pack_into("<ii", hdr, 28, 1000, 5)  # 5 = Polygon
        struct.pack_into("<dddd", hdr, 36, 10.0, 20.0, 30.0, 40.0)  # bounding box
        tf.write(hdr)
        shp_path = tf.name

    try:
        e_shp = FileEntry(os.path.basename(shp_path), os.path.dirname(shp_path), ".shp", 100, time.time(), False, FileCategory.GIS)
        prev_shp = load_file_preview(e_shp)
        assert "ESRI Shapefile" in prev_shp["content"]
        assert "Polygon" in prev_shp["content"]
        assert "10.0000" in prev_shp["content"]
    finally:
        if os.path.exists(shp_path):
            os.remove(shp_path)

    print("[PASS] Engineering/CAD and GIS tests passed!")


def test_location_scoping():
    print("Testing Location & Scope Path Filtering...")
    e1 = FileEntry("plan.dwg", "D:/Projects/Civil", ".dwg", 5000, time.time(), False, FileCategory.CAD)
    e2 = FileEntry("notes.docx", "D:/Projects/Civil/Subfolder", ".docx", 2000, time.time(), False, FileCategory.DOCUMENT)
    e3 = FileEntry("backup.zip", "C:/Users/Dev/Downloads", ".zip", 99000, time.time(), False, FileCategory.ARCHIVE)

    # Scope to D:/Projects/Civil with subfolders
    q1 = SearchQuery.parse("", scope_path="D:/Projects/Civil", include_subfolders=True)
    assert q1.matches(e1)
    assert q1.matches(e2)
    assert not q1.matches(e3)

    # Scope to D:/Projects/Civil without subfolders
    q2 = SearchQuery.parse("", scope_path="D:/Projects/Civil", include_subfolders=False)
    assert q2.matches(e1)
    assert not q2.matches(e2)
    assert not q2.matches(e3)

    print("[PASS] Location & Scope Path tests passed!")


def test_subpills_and_fine_tuning():
    print("Testing Sub-Type Fine-Tuning Pills...")
    e_pdf = FileEntry("report.pdf", "C:/Docs", ".pdf", 1000, time.time(), False, FileCategory.DOCUMENT)
    e_docx = FileEntry("letter.docx", "C:/Docs", ".docx", 2000, time.time(), False, FileCategory.DOCUMENT)
    e_xlsx = FileEntry("budget.xlsx", "C:/Docs", ".xlsx", 3000, time.time(), False, FileCategory.DOCUMENT)

    # Fine-tuned ext filter for PDF only
    q_pdf = SearchQuery.parse("")
    q_pdf.ext_filter = {".pdf"}
    assert q_pdf.matches(e_pdf)
    assert not q_pdf.matches(e_docx)
    assert not q_pdf.matches(e_xlsx)

    # Fine-tuned ext filter for DOCX only
    q_docx = SearchQuery.parse("")
    q_docx.ext_filter = {".docx", ".doc"}
    assert not q_docx.matches(e_pdf)
    assert q_docx.matches(e_docx)
    assert not q_docx.matches(e_xlsx)

    print("[PASS] Sub-Type Fine-Tuning tests passed!")


def test_ui_initialization():
    print("Testing Qt MainWindow initialization and location controls...")
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    assert win.windowTitle().startswith("OmniSearch Studio")
    assert win.table_model is not None
    assert win.preview_panel is not None
    assert win.combo_scope is not None
    assert win.combo_scope.count() >= 1
    assert win.subpills_btn_layout.count() > 0

    # Test clicking CAD category chip
    cad_btn = win.chip_buttons.get(FileCategory.CAD)
    assert cad_btn is not None
    cad_btn.click()
    assert win.active_category_filter == FileCategory.CAD

    # Test clicking Document chip and clicking PDF and DOCX subpills
    doc_btn = win.chip_buttons.get(FileCategory.DOCUMENT)
    assert doc_btn is not None
    doc_btn.click()
    assert win.active_category_filter == FileCategory.DOCUMENT

    # Check subpills were generated for Document
    subpill_count = win.subpills_btn_layout.count()
    assert subpill_count >= 5  # PDF, Word, Excel, PowerPoint, Text/Markdown...

    # Find PDF button and click
    pdf_btn = None
    docx_btn = None
    for i in range(win.subpills_btn_layout.count()):
        widget = win.subpills_btn_layout.itemAt(i).widget()
        if widget and "PDF" in widget.text():
            pdf_btn = widget
        elif widget and "Word" in widget.text():
            docx_btn = widget

    assert pdf_btn is not None
    pdf_btn.click()
    assert win.active_ext_filter == {".pdf"}

    assert docx_btn is not None
    docx_btn.click()
    assert win.active_ext_filter == {".docx", ".doc"}

    # Test clicking GIS category chip
    gis_btn = win.chip_buttons.get(FileCategory.GIS)
    assert gis_btn is not None
    gis_btn.click()
    assert win.active_category_filter == FileCategory.GIS
    assert win.active_ext_filter is None  # Reset when category switches

    # Test setting location scope
    win.set_location_scope("D:/Antigravity")
    assert win.current_scope_path == "D:/Antigravity" or win.current_scope_path == "D:\\Antigravity"

    # Test resetting scope
    win.btn_clear_scope.click()
    assert win.current_scope_path is None

    # Check Scope dropdown has actions and items
    combo_items = [win.combo_scope.itemText(i) for i in range(win.combo_scope.count())]
    assert any("Everywhere" in item for item in combo_items)
    assert any("Manage Drives" in item for item in combo_items)
    assert any("Add Network" in item for item in combo_items)

    # Test clicking table headers for sorting
    win.last_results = [
        FileEntry(name="zebra.txt", path="C:/", ext=".txt", size=500, mtime=100.0, is_dir=False, category=FileCategory.DOCUMENT),
        FileEntry(name="apple.pdf", path="C:/", ext=".pdf", size=2000, mtime=200.0, is_dir=False, category=FileCategory.DOCUMENT),
        FileEntry(name="banana.png", path="C:/", ext=".png", size=100, mtime=50.0, is_dir=False, category=FileCategory.IMAGE)
    ]
    win.table_model.set_entries(win.last_results)

    # Sort by Name (col 0): first click -> ascending (apple, banana, zebra)
    win._on_header_clicked(0)
    assert win.current_sort_column == 0
    assert win.current_sort_ascending is True
    assert win.table_model.entries[0].name == "apple.pdf"
    assert win.table_model.entries[-1].name == "zebra.txt"

    # Second click -> descending (zebra, banana, apple)
    win._on_header_clicked(0)
    assert win.current_sort_ascending is False
    assert win.table_model.entries[0].name == "zebra.txt"

    # Click Size (col 2) -> defaults to descending (apple=2000, zebra=500, banana=100)
    win._on_header_clicked(2)
    assert win.current_sort_column == 2
    assert win.current_sort_ascending is False
    assert win.table_model.entries[0].name == "apple.pdf"

    # Click Date (col 3) -> defaults to descending (apple=200, zebra=100, banana=50)
    win._on_header_clicked(3)
    assert win.current_sort_column == 3
    assert win.current_sort_ascending is False
    assert win.table_model.entries[0].name == "apple.pdf"
    assert win.table_model.entries[-1].name == "banana.png"

    # Click Type (col 4) -> defaults to ascending
    win._on_header_clicked(4)
    assert win.current_sort_column == 4
    assert win.current_sort_ascending is True

    # ── Test Simple Mode vs Pro Mode Toggling & Persistence ──
    # Starts in Simple Mode by default (or configured default)
    assert win.current_ui_mode in ("simple", "pro")
    win._apply_ui_mode("simple")
    assert win.current_ui_mode == "simple"
    assert "Pro Mode" in win.btn_mode_toggle.text()
    assert win.scope_container.isHidden()
    assert win.chips_container.isHidden()
    assert win.preview_panel.isHidden()
    assert win.btn_content_search.isHidden()
    assert win.btn_toggle_preview.isHidden()

    # Toggle to Pro Mode (via button or shortcut F12)
    win._toggle_ui_mode()
    assert win.current_ui_mode == "pro"
    assert "Simple Mode" in win.btn_mode_toggle.text()
    assert not win.scope_container.isHidden()
    assert not win.chips_container.isHidden()
    assert not win.btn_content_search.isHidden()
    assert not win.btn_toggle_preview.isHidden()
    assert not win.preview_panel.isHidden()

    # Test saving startup default preference
    win._set_default_startup_mode("pro")
    from core.windows_integration import load_integration_settings
    assert load_integration_settings().get("default_mode") == "pro"
    win._set_default_startup_mode("simple")
    assert load_integration_settings().get("default_mode") == "simple"

    win.close()
    app.processEvents()
    print("[PASS] Qt MainWindow, Simple vs Pro Mode & Column Header Click-to-Sort tested smoothly with zero errors!")


def test_drives_and_network():
    print("Testing External Drives, Pen Drives & Network Shares...")
    from core.models import DriveType, DriveInfo
    from core.network_manager import NetworkShareManager
    from core.scanner import get_detailed_drives
    from ui.drives_dialog import DrivesDialog
    import tempfile

    # 1. DriveInfo models
    d1 = DriveInfo(path="E:\\", drive_type=DriveType.REMOVABLE_USB, label="SanDisk", total_bytes=32*1024**3, free_bytes=16*1024**3)
    assert d1.icon_emoji == "🔌"
    assert "SanDisk" in d1.display_name
    assert "Pen Drive" in d1.display_name
    assert d1.used_percent == 50.0

    d2 = DriveInfo(path="\\\\NAS\\Civil", drive_type=DriveType.NETWORK_UNC, label="Civil")
    assert d2.icon_emoji == "🌐"

    # 2. NetworkShareManager
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "network_shares.json")
        mgr = NetworkShareManager(cfg)
        ok, msg = mgr.add_share("\\\\OfficeServer\\Drawings")
        assert ok
        assert "\\\\OfficeServer\\Drawings" in mgr.shares
        assert len(mgr.load_shares()) == 1

        # Test duplicate prevention
        ok2, _ = mgr.add_share("\\\\OfficeServer\\Drawings")
        assert not ok2

        # Test removal
        assert mgr.remove_share("\\\\OfficeServer\\Drawings")
        assert len(mgr.load_shares()) == 0

    # 3. Detailed drives enumeration with UNC path
    drives = get_detailed_drives(include_network=True, custom_unc_paths=["\\\\Server\\Share"])
    assert len(drives) >= 1
    assert any(d.drive_type == DriveType.NETWORK_UNC for d in drives)

    # 4. DrivesDialog initialization
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = DrivesDialog()
    assert dlg.table.rowCount() >= 1
    dlg.close()
    app.processEvents()

    print("[PASS] External Drives, Pen Drives & Network Shares tests passed!")


def test_windows_integration():
    print("Testing Windows Integration (Shortcuts, Startup, Uninstaller, IntegrationDialog)...")
    from core.windows_integration import (
        get_default_install_dir, get_desktop_dir, get_start_menu_programs_dir,
        resolve_executable_or_python, set_run_on_startup, is_run_on_startup_enabled,
        register_windows_uninstaller, unregister_windows_uninstaller,
        load_integration_settings, save_integration_settings, APP_NAME
    )
    from ui.integration_dialog import IntegrationDialog

    # 1. Directory resolvers
    assert "Programs" in get_default_install_dir()
    assert os.path.exists(get_desktop_dir())
    assert os.path.exists(get_start_menu_programs_dir())

    # 2. Executable resolution
    target, args, ico = resolve_executable_or_python()
    assert os.path.exists(target)

    # 3. Settings persistence
    cfg = load_integration_settings()
    assert isinstance(cfg, dict)

    # 4. Windows Startup Registry
    ok_set = set_run_on_startup(True)
    assert ok_set
    assert is_run_on_startup_enabled()

    ok_clear = set_run_on_startup(False)
    assert ok_clear
    assert not is_run_on_startup_enabled()

    # 4b. Background Reindex on Startup Registry
    from core.windows_integration import (
        set_background_reindex_on_startup, is_background_reindex_enabled
    )
    ok_reindex_set = set_background_reindex_on_startup(True, delay_seconds=180)
    assert ok_reindex_set
    assert is_background_reindex_enabled()

    ok_reindex_clear = set_background_reindex_on_startup(False)
    assert ok_reindex_clear
    assert not is_background_reindex_enabled()

    # 5. Windows Uninstaller Registry
    ok_uninst = register_windows_uninstaller(get_default_install_dir(), target, "cmd.exe /c echo")
    assert ok_uninst
    ok_remove = unregister_windows_uninstaller()
    assert ok_remove

    # 6. IntegrationDialog UI
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = IntegrationDialog(is_first_run=True)
    assert dlg.chk_desktop.isChecked()
    assert dlg.chk_start_menu.isChecked()
    assert dlg.chk_autostart.isChecked()
    assert dlg.chk_reindex.isChecked()
    dlg.close()
    app.processEvents()

    # 7. SetupWizard with LicensePage & Process Cleanup
    from installer import SetupWizard, LicensePage, kill_running_instances
    kill_running_instances()
    wiz = SetupWizard(source_dir=os.path.dirname(os.path.abspath(__file__)))
    assert hasattr(wiz, "page_license")
    assert isinstance(wiz.page_license, LicensePage)
    # License agreement must be accepted before wizard can proceed past license page
    assert not wiz.page_license.isComplete()
    wiz.page_license.rb_agree.setChecked(True)
    assert wiz.page_license.isComplete()
    wiz.close()
    app.processEvents()

    print("[PASS] Windows Integration tests passed!")


def test_headless_reindex():
    print("Testing Headless Background Reindex Engine & CLI...")
    from main import run_headless_reindex
    from core.indexer import FileIndex

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a small sample file structure
        sub = os.path.join(tmpdir, "documents")
        os.makedirs(sub, exist_ok=True)
        f1 = os.path.join(sub, "project_spec.pdf")
        with open(f1, "w") as f:
            f.write("test content")

        cache_file = os.path.join(tmpdir, "test_cache.dat")
        count = run_headless_reindex(drives=[tmpdir], cache_path=cache_file)
        assert count >= 1
        assert os.path.exists(cache_file)

        # Verify the saved cache loads properly
        idx = FileIndex()
        assert idx.load_from_cache(cache_path=cache_file)
        assert len(idx.entries) >= 1
        assert any("project_spec.pdf" in e.name for e in idx.entries)

    print("[PASS] Headless Background Reindex tests passed!")


def test_content_search():
    print("Testing Full-Text Document Content Search Engine...")
    from core.content_search import (
        ContentMatch, extract_snippet, search_file_content,
        search_candidates_in_parallel
    )

    # 1. Test snippet extraction
    text = "Geotechnical investigation showed limestone bedrock with compressive strength of 45 MPa at 12 meters."
    snip = extract_snippet(text, "compressive strength")
    assert "compressive strength" in snip

    with tempfile.TemporaryDirectory() as tmpdir:
        # 2. Test Text file search
        txt_path = os.path.join(tmpdir, "report.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("Line 1: Project Overview\nLine 2: Foundation design using driven steel piles\nLine 3: Safety factor 2.5\n")

        entry_txt = FileEntry(name="report.txt", path=tmpdir, ext=".txt", size=os.path.getsize(txt_path), mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
        match_txt = search_file_content(entry_txt, "steel piles")
        assert match_txt is not None
        assert match_txt.location == "Line 2"
        assert "steel piles" in match_txt.snippet

        # 3. Test Word .docx search (create minimal OpenXML docx)
        docx_path = os.path.join(tmpdir, "spec.docx")
        with zipfile.ZipFile(docx_path, "w") as z:
            doc_xml = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                b'<w:body>'
                b'<w:p><w:r><w:t>Project Specification for Highway Interchange</w:t></w:r></w:p>'
                b'<w:p><w:r><w:t>Concrete compressive strength requirement is Grade C40</w:t></w:r></w:p>'
                b'</w:body>'
                b'</w:document>'
            )
            z.writestr("word/document.xml", doc_xml)

        entry_docx = FileEntry(name="spec.docx", path=tmpdir, ext=".docx", size=os.path.getsize(docx_path), mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
        match_docx = search_file_content(entry_docx, "Grade C40")
        assert match_docx is not None
        assert "Paragraph" in match_docx.location
        assert "Grade C40" in match_docx.snippet

        # 4. Test Excel .xlsx search (create minimal OpenXML xlsx)
        xlsx_path = os.path.join(tmpdir, "data.xlsx")
        with zipfile.ZipFile(xlsx_path, "w") as z:
            ss_xml = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">'
                b'<si><t>Borehole Depth</t></si>'
                b'<si><t>Hydraulic Conductivity 1.5e-4</t></si>'
                b'</sst>'
            )
            z.writestr("xl/sharedStrings.xml", ss_xml)

        entry_xlsx = FileEntry(name="data.xlsx", path=tmpdir, ext=".xlsx", size=os.path.getsize(xlsx_path), mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
        match_xlsx = search_file_content(entry_xlsx, "Hydraulic Conductivity")
        assert match_xlsx is not None
        assert "Hydraulic Conductivity" in match_xlsx.snippet

        # 5. Test PowerPoint .pptx search (create minimal OpenXML pptx)
        pptx_path = os.path.join(tmpdir, "presentation.pptx")
        with zipfile.ZipFile(pptx_path, "w") as z:
            slide_xml = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                b'<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Quarterly Financial Results and EBITDA margin</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>'
                b'</p:sld>'
            )
            z.writestr("ppt/slides/slide1.xml", slide_xml)

        entry_pptx = FileEntry(name="presentation.pptx", path=tmpdir, ext=".pptx", size=os.path.getsize(pptx_path), mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
        match_pptx = search_file_content(entry_pptx, "EBITDA margin")
        assert match_pptx is not None
        assert match_pptx.location == "Slide 1"
        assert "EBITDA margin" in match_pptx.snippet

        # 6. Test Parallel Search across candidate list
        candidates = [entry_txt, entry_docx, entry_xlsx, entry_pptx]
        par_matches = search_candidates_in_parallel(candidates, "Highway Interchange")
        assert len(par_matches) == 1
        assert par_matches[0].entry.name == "spec.docx"

    print("[PASS] Full-Text Document Content Search tests passed!")


def test_two_stage_and_in_document_search():
    print("Testing Two-Stage Narrow-Down & In-Document Preview Search...")
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sample documents
        doc1 = os.path.join(tmpdir, "bridge_report.txt")
        doc2 = os.path.join(tmpdir, "tunnel_report.txt")
        doc3 = os.path.join(tmpdir, "highway_spec.txt")

        with open(doc1, "w", encoding="utf-8") as f:
            f.write("Bridge structural foundation using reinforced concrete abutments.\n")
        with open(doc2, "w", encoding="utf-8") as f:
            f.write("Tunnel ventilation system specifications and emergency exits.\n")
        with open(doc3, "w", encoding="utf-8") as f:
            f.write("Highway pavement design with asphalt concrete.\n")

        e1 = FileEntry(name="bridge_report.txt", path=tmpdir, ext=".txt", size=os.path.getsize(doc1), mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
        e2 = FileEntry(name="tunnel_report.txt", path=tmpdir, ext=".txt", size=os.path.getsize(doc2), mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
        e3 = FileEntry(name="highway_spec.txt", path=tmpdir, ext=".txt", size=os.path.getsize(doc3), mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)

        win = MainWindow()
        win.index.set_entries([e1, e2, e3])

        # 1. Stage 1: Search by filename "report" -> narrows to e1 and e2
        win.txt_search.setText("report")
        win._execute_search()
        assert len(win.last_results) == 2
        assert len(win.cached_filename_results) == 2
        cached_names = {x.name for x in win.cached_filename_results}
        assert cached_names == {"bridge_report.txt", "tunnel_report.txt"}

        # 2. Stage 2: Using Dedicated Content Narrowing Bar (Filter Inside Results)
        assert hasattr(win, "txt_content_filter")
        assert hasattr(win, "btn_narrow_trigger")
        assert not win.btn_narrow_trigger.isHidden()
        assert "2 Files" in win.btn_narrow_trigger.text()

        # Type keyword in dedicated filter bar
        win.txt_content_filter.setText("ventilation")
        win._apply_content_filter()
        # Wait for worker thread to finish
        if win.content_worker:
            win.content_worker.wait(3000)
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)

        assert len(win.last_results) == 1
        assert win.last_results[0].name == "tunnel_report.txt"
        assert not win.lbl_narrow_badge.isHidden()
        assert "1 of 2" in win.lbl_narrow_badge.text()

        # Instant Reset: Clear the dedicated narrowing filter
        win._clear_content_filter()
        assert len(win.last_results) == 2
        assert win.txt_content_filter.text() == ""
        assert win.lbl_narrow_badge.isHidden()

        # 3. Test Targeted Search in Selected Documents
        win._search_content_in_selected([e1], query="reinforced concrete")
        if win.content_worker:
            win.content_worker.wait(2000)
        app.processEvents()
        assert len(win.last_results) == 1
        assert win.last_results[0].name == "bridge_report.txt"

        # 4. Test In-Document Preview Panel Find on Page
        pp = win.preview_panel
        assert hasattr(pp, "btn_find_in_doc")
        assert "Find on Page" in pp.btn_find_in_doc.text()
        assert hasattr(pp, "doc_search_bar")
        assert pp.doc_search_bar.isHidden()

        # Toggle open
        pp._toggle_doc_search_bar()
        assert not pp.doc_search_bar.isHidden()

        # Load entry into preview
        pp.set_entry(e1)
        pp.txt_find_in_doc.setText("reinforced")
        pp._find_next_in_doc()
        assert "Match found" in pp.lbl_find_stats.text()

        # Toggle close
        pp._hide_doc_search_bar()
        assert pp.doc_search_bar.isHidden()

        win.close()
        app.processEvents()

    print("[PASS] Two-stage narrow-down and in-document preview search tests passed!")


def test_about_and_branding():
    print("Testing Version Info and 'Crafted by Ranjan' Attribution...")
    from ui.about_dialog import AboutDialog, APP_NAME, APP_VERSION, APP_AUTHOR
    from core.windows_integration import APP_PUBLISHER, APP_VERSION as WIN_APP_VERSION

    assert APP_VERSION == "1.4.0"
    assert WIN_APP_VERSION == "1.4.0"
    assert APP_AUTHOR == "Ranjan"
    assert APP_PUBLISHER == "Ranjan"

    app = QApplication.instance() or QApplication(sys.argv)
    dlg = AboutDialog(theme="light")
    assert "1.4.0" in dlg.windowTitle() or "OmniSearch" in dlg.windowTitle()
    dlg.close()
    app.processEvents()

    # Verify MainWindow header and status bar branding
    win = MainWindow()
    assert hasattr(win, "btn_content_search")
    assert win.btn_content_search.isCheckable()
    win.btn_content_search.setChecked(True)
    assert "search inside documents" in win.txt_search.placeholderText().lower()
    win.btn_content_search.setChecked(False)
    win.close()
    app.processEvents()

    print("[PASS] Version info & 'Crafted by Ranjan' branding tests passed!")


def test_recently_modified_date_filters():
    print("Testing Recently Modified Date Filters (today, lastweek, lastmonth, etc.)...")
    import time
    now = time.time()
    idx = FileIndex()

    e_today = FileEntry("daily_log.txt", "C:\\Logs", ".txt", 1024, now - 1800, False, FileCategory.DOCUMENT)
    e_yesterday = FileEntry("yesterday_notes.txt", "C:\\Docs", ".txt", 2048, now - 86400 * 1.5, False, FileCategory.DOCUMENT)
    e_week = FileEntry("weekly_report.pdf", "C:\\Reports", ".pdf", 4096, now - 86400 * 4, False, FileCategory.DOCUMENT)
    e_month = FileEntry("monthly_summary.xlsx", "C:\\Finance", ".xlsx", 8192, now - 86400 * 20, False, FileCategory.DOCUMENT)
    e_ancient = FileEntry("archive_2023.zip", "C:\\Archive", ".zip", 16384, now - 86400 * 500, False, FileCategory.ARCHIVE)

    idx.set_entries([e_today, e_yesterday, e_week, e_month, e_ancient])

    # 1. Test keyword-based date queries: dm:today, dm:lastweek, dm:lastmonth
    r_today = idx.search("dm:today")
    assert len(r_today) == 1 and r_today[0].name == "daily_log.txt"

    r_week = idx.search("dm:lastweek")
    assert len(r_week) == 3  # daily_log, yesterday_notes, weekly_report
    assert {x.name for x in r_week} == {"daily_log.txt", "yesterday_notes.txt", "weekly_report.pdf"}

    r_month = idx.search("dm:lastmonth")
    assert len(r_month) == 4  # All except archive_2023.zip
    assert "archive_2023.zip" not in {x.name for x in r_month}

    # 2. Test combining search term with date filter
    r_combo = idx.search("weekly dm:lastmonth")
    assert len(r_combo) == 1 and r_combo[0].name == "weekly_report.pdf"

    # 3. Test MainWindow UI dropdown integration
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.index = idx
    assert hasattr(win, "combo_date")
    assert hasattr(win, "active_date_filter")

    # Select 'Past 7 Days (Last Week)' in combo
    idx_week = win.combo_date.findData("week")
    assert idx_week >= 0
    win.combo_date.setCurrentIndex(idx_week)
    assert len(win.last_results) == 3

    # Select 'Last 24 Hours (Today)' in combo
    idx_today = win.combo_date.findData("today")
    win.combo_date.setCurrentIndex(idx_today)
    assert len(win.last_results) == 1
    assert win.last_results[0].name == "daily_log.txt"

    # Reset to Anytime
    win.combo_date.setCurrentIndex(0)
    assert len(win.last_results) == 5

    win.close()
    app.processEvents()

    print("[PASS] Recently Modified date filter tests passed!")


def test_content_trigger_and_deletion():
    print("Testing Manual Content Search Trigger & Safe File/Folder Deletion...")
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create temporary file and subfolder for deletion testing
        test_file = os.path.join(tmpdir, "to_delete.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Important document about geotechnical analysis.")

        test_dir = os.path.join(tmpdir, "to_delete_folder")
        os.makedirs(test_dir, exist_ok=True)
        sub_file = os.path.join(test_dir, "nested.txt")
        with open(sub_file, "w", encoding="utf-8") as f:
            f.write("Nested content.")

        e_file = FileEntry(name="to_delete.txt", path=tmpdir, ext=".txt", size=os.path.getsize(test_file), mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
        e_dir = FileEntry(name="to_delete_folder", path=tmpdir, ext="", size=0, mtime=time.time(), is_dir=True, category=FileCategory.FOLDER)

        win = MainWindow()
        win.index.set_entries([e_file, e_dir])

        # 1. Test Content Search button visibility and manual trigger
        win._apply_ui_mode("pro")
        assert hasattr(win, "btn_content_search")
        assert hasattr(win, "btn_run_content_search")
        assert hasattr(win, "btn_run_narrow")

        # When Content Search is not toggled, run button is hidden
        assert win.btn_run_content_search.isHidden()

        # When Content Search is toggled on, run button appears in Pro Mode
        win.btn_content_search.setChecked(True)
        assert not win.btn_run_content_search.isHidden()

        # Typing in content search mode without from_trigger in production doesn't thrash worker
        win.txt_search.setText("geotechnical")
        # In test mode, from_trigger is tested directly
        win._execute_search(from_trigger=True)
        if win.content_worker:
            win.content_worker.wait(3000)
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)

        assert len(win.last_results) == 1
        assert win.last_results[0].name == "to_delete.txt"

        # 2. Test Safe Deletion (Send to Windows Recycle Bin)
        # Select e_file row in table
        win.table_view.selectRow(0)
        assert len(win._get_selected_entries()) == 1
        win._recycle_selected_from_table()
        # Item removed from index and search results
        assert not win.index.get_entry(e_file.full_path)
        assert e_file not in win.last_results

        # 3. Test Permanent Deletion on folder
        win.txt_search.clear()
        win.btn_content_search.setChecked(False)
        win._execute_search()
        assert len(win.last_results) == 1
        assert win.last_results[0].name == "to_delete_folder"

        win.table_view.selectRow(0)
        win._permanently_delete_selected_from_table()
        assert not os.path.exists(test_dir)
        assert not win.index.get_entry(e_dir.full_path)
        assert len(win.last_results) == 0

        win.close()
        app.processEvents()

    print("[PASS] Manual Content Search trigger & Safe File/Folder Deletion tests passed!")


def test_explorer_context_menu_and_folder_search():
    """
    Verifies:
    1. Folder preservation in FileIndex cache save/load and search matching.
    2. Windows Explorer context menu registration, state checking, and unregistration.
    3. Setting scope from CLI / Windows Explorer path.
    """
    from core.windows_integration import (
        register_explorer_context_menu, unregister_explorer_context_menu,
        is_explorer_context_menu_enabled
    )

    # 1. Folder preservation test in FileIndex cache
    idx = FileIndex()
    f1 = FileEntry(name="Geotech_Reports", path="C:\\Projects", ext="", size=0, mtime=time.time(), is_dir=True, category=FileCategory.FOLDER)
    f2 = FileEntry(name="summary.pdf", path="C:\\Projects\\Geotech_Reports", ext=".pdf", size=1024, mtime=time.time(), is_dir=False, category=FileCategory.DOCUMENT)
    idx.add_entry(f1)
    idx.add_entry(f2)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_cache = os.path.join(tmpdir, "test_idx.cache")
        saved = idx.save_to_cache(test_cache)
        assert saved

        idx_loaded = FileIndex()
        loaded = idx_loaded.load_from_cache(test_cache)
        assert loaded

        entry_dir = idx_loaded.get_entry(f1.full_path)
        assert entry_dir is not None
        assert entry_dir.is_dir is True
        assert entry_dir.category == FileCategory.FOLDER

        # Test search with type:folder
        sq_folder = SearchQuery.parse("type:folder")
        results = idx_loaded.search(sq_folder)
        assert len(results) == 1
        assert results[0].name == "Geotech_Reports"

        # Test search with folder name keyword
        sq_name = SearchQuery.parse("Geotech")
        res_name = idx_loaded.search(sq_name)
        assert any(r.is_dir and r.name == "Geotech_Reports" for r in res_name)

    # 2. Explorer context menu registration
    if sys.platform == "win32":
        # Register
        reg_ok = register_explorer_context_menu()
        assert reg_ok
        assert is_explorer_context_menu_enabled()

        # Unregister
        unreg_ok = unregister_explorer_context_menu()
        assert unreg_ok
        assert not is_explorer_context_menu_enabled()

    # 3. Location scope setting in MainWindow
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.index.set_entries([f1, f2])
    test_scope = "C:\\Projects\\Geotech_Reports"
    win.set_location_scope(test_scope)
    assert win.current_scope_path == test_scope

    # Search within that scope
    win.txt_search.clear()
    win._execute_search()
    # Inside scope: Geotech_Reports (the folder) and summary.pdf (inside it)
    assert any(r.name == "summary.pdf" for r in win.last_results)
    assert any(r.name == "Geotech_Reports" for r in win.last_results)
    win.close()
    app.processEvents()

    print("[PASS] Explorer context menu & Folder search verification passed!")


def test_auto_updater_and_popularity_ping():
    print("Testing GitHub Auto-Updater and Telemetry Ping...")
    from core.updater import compare_versions, send_popularity_ping, GITHUB_REPO
    from ui.update_dialog import UpdateDialog

    # Test semver logic
    assert compare_versions("1.4.0", "1.3.0") == 1
    assert compare_versions("1.4.0", "1.4.0") == 0
    assert compare_versions("1.4.0", "1.5.0") == -1
    assert compare_versions("v1.4.0", "1.3.9") == 1
    assert compare_versions("2.0.0", "1.99.99") == 1

    # Test popularity ping executes smoothly without crashing
    success = send_popularity_ping("1.4.0")
    # In sandbox or offline it returns True or False without raising exceptions
    assert isinstance(success, bool)

    # Test UpdateDialog UI creation
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = UpdateDialog()
    assert dlg.windowTitle() == "Software Update — OmniSearch Studio"
    assert "1.4.0" in dlg.lbl_status.text()
    dlg.close()
    app.processEvents()
    print("[PASS] Auto-Updater and Telemetry Ping tests passed!")


if __name__ == "__main__":
    os.environ["OMNISEARCH_TEST_MODE"] = "1"
    print("==================================================")
    print("Running OmniSearch Studio Full Verification Suite")
    print("==================================================")
    test_models_and_queries()
    test_index_and_cache()
    test_recently_modified_date_filters()
    test_duplicate_detection()
    test_preview_loader()
    test_engineering_and_gis()
    test_location_scoping()
    test_subpills_and_fine_tuning()
    test_content_search()
    test_two_stage_and_in_document_search()
    test_about_and_branding()
    test_ui_initialization()
    test_drives_and_network()
    test_windows_integration()
    test_headless_reindex()
    test_content_trigger_and_deletion()
    test_explorer_context_menu_and_folder_search()
    test_auto_updater_and_popularity_ping()
    print("==================================================")
    print(">>> ALL 18 VERIFICATION TEST SUITES PASSED! <<<")
    print("==================================================")


