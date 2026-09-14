import os
import sys

# Ensure root directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.app_launcher import AppRegistry, InstalledApp
from core.indexer import FileIndex
from core.models import FileEntry, FileCategory


def test_app_registry():
    print("Testing AppRegistry...")
    reg = AppRegistry()
    reg.refresh()
    assert len(reg.apps) > 0, "Should have discovered apps"

    # Search for calculator
    calc_results = reg.search("calc")
    assert any("calc" in a.name.lower() or "calc" in a.target_path.lower() for a in calc_results), "Should find Calculator"
    print(f"[PASS] Found {len(reg.apps)} applications. Calculator search passed.")

    # Search for notepad
    note_results = reg.search("note")
    assert any("note" in a.name.lower() for a in note_results), "Should find Notepad"
    print("[PASS] Notepad search passed.")


def test_quick_launcher_headless():
    print("Testing QuickLauncher UI integration...")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["OMNISEARCH_TEST_MODE"] = "1"

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    index = FileIndex()
    # Add dummy entries
    index.add_entry(FileEntry(name="Report_2026.pdf", path="C:\\Documents", ext=".pdf", size=1024, mtime=1700000000.0, is_dir=False, category=FileCategory.DOCUMENT))
    index.add_entry(FileEntry(name="Projects", path="C:\\Work", ext="", size=0, mtime=1700000000.0, is_dir=True, category=FileCategory.FOLDER))

    from ui.quick_launcher import QuickLauncher
    hud = QuickLauncher(index)

    # Test typing query
    hud._on_text_changed("calc")
    assert hud.results_list.count() > 0, "HUD should show app results for calc"
    print(f"[PASS] HUD found {hud.results_list.count()} results for 'calc'.")

    hud._on_text_changed("Report")
    assert hud.results_list.count() > 0, "HUD should show file results for 'Report'"
    print(f"[PASS] HUD found {hud.results_list.count()} results for 'Report'.")

    # Test open full studio signal
    signals_received = []
    hud.open_full_studio_requested.connect(lambda q: signals_received.append(q))
    hud.search_input.setText("test_query")
    hud._open_studio()
    assert signals_received == ["test_query"], "Should emit open_full_studio_requested with query"
    print("[PASS] Open Full Studio signal passed.")


if __name__ == "__main__":
    test_app_registry()
    test_quick_launcher_headless()
    print("\nALL QUICK LAUNCHER TESTS PASSED SUCCESSFULLY! [SUCCESS]")
