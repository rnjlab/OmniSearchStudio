import sys
import os

# Ensure root directory in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PySide6.QtWidgets import QApplication
from core.indexer import FileIndex
from ui.quick_launcher import QuickLauncher
from core.hotkey_manager import GlobalHotkeyManager

def main():
    print("=" * 60)
    print("OmniSearch Studio — Quick Launcher HUD Standalone Runner")
    print("=" * 60)
    print("Loading file cache & app registry...")

    app = QApplication(sys.argv)
    index = FileIndex()
    index.load_from_cache()

    hud = QuickLauncher(index)

    def on_hotkey():
        print(">>> [HOTKEY TRIGGERED] Double-Press Ctrl / Hotkey pressed! Showing HUD...")
        hud.show_centered()

    hotkey_mgr = GlobalHotkeyManager(callback=on_hotkey)
    hotkey_mgr.start()

    print(f"Global listener active: {hotkey_mgr.active_hotkey_label}")
    print("-" * 60)
    print("HUD is now popping up centered on your screen.")
    print("You can also press Esc to hide, and Double-Press Ctrl anytime to show it!")
    print("-" * 60)

    # Immediately show the HUD so the user sees it right away on launch!
    hud.show_centered()

    try:
        sys.exit(app.exec())
    finally:
        hotkey_mgr.stop()

if __name__ == "__main__":
    main()
