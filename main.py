import sys
import os

# Add root folder to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import time
from core.indexer import FileIndex, DEFAULT_CACHE_PATH
from core.scanner import get_available_drives, scan_multiple_drives


def run_headless_reindex(drives=None, cache_path=DEFAULT_CACHE_PATH):
    """
    Executes a fast, silent, completely headless scan of all drives,
    building and writing the binary index cache to disk.
    Zero GUI or window created.
    """
    if drives is None:
        drives = get_available_drives(include_network=False)
    if not drives:
        return 0

    idx = FileIndex()
    scanned_entries = scan_multiple_drives(drives, batch_size=2000)
    idx.set_entries(scanned_entries)
    idx.save_to_cache(cache_path=cache_path)
    return len(scanned_entries)


def main():
    # ── Headless Background Reindex Modes ─────────────────────────────────────
    if "--reindex" in sys.argv or any(arg.startswith("--reindex") for arg in sys.argv):
        delay = 0
        for i, arg in enumerate(sys.argv):
            if arg == "--reindex-delayed" and i + 1 < len(sys.argv):
                try:
                    delay = int(sys.argv[i + 1])
                except ValueError:
                    delay = 180
            elif arg.startswith("--reindex-delayed="):
                try:
                    delay = int(arg.split("=", 1)[1])
                except ValueError:
                    delay = 180

        if delay > 0:
            time.sleep(delay)

        run_headless_reindex()
        sys.exit(0)

    # ── Normal Interactive GUI Mode ───────────────────────────────────────────
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from ui.main_window import MainWindow

    # Enable crisp high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("OmniSearch Studio")
    app.setApplicationVersion("1.4.0")
    app.setOrganizationName("Ranjan")
    app.setQuitOnLastWindowClosed(False)

    # Parse scope directory if passed via CLI (e.g. from Explorer context menu)
    initial_scope = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--scope" and i + 1 < len(sys.argv):
            initial_scope = sys.argv[i + 1]
            break
        elif arg.startswith("--scope="):
            initial_scope = arg.split("=", 1)[1]
            break
        elif os.path.isdir(arg) and not arg.startswith("-"):
            initial_scope = arg
            break

    # ── Single Instance Enforcement via QLocalSocket / QLocalServer ─────────
    # Prevents duplicate background orphan processes that would lock Ctrl+Space!
    server_name = "OmniSearchStudio_SingleInstance_IPC"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(500):
        # Already running! Notify existing instance to bring window to front and set scope
        if initial_scope:
            payload = f"SCOPE:{initial_scope}\n".encode("utf-8")
        else:
            payload = b"ACTIVATE\n"
        socket.write(payload)
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.close()
        sys.exit(0)

    # Create local IPC server to listen for future launch attempts
    local_server = QLocalServer()
    # Remove old socket file if orphaned from crash
    local_server.removeServer(server_name)
    local_server.listen(server_name)

    window = MainWindow()

    def handle_new_connection():
        client = local_server.nextPendingConnection()
        if client:
            client.waitForReadyRead(500)
            msg = bytes(client.readAll()).decode("utf-8", errors="ignore").strip()
            client.close()
            # If message starts with SCOPE:, update scope path immediately
            if msg.startswith("SCOPE:"):
                target_scope = msg[6:].strip()
                if target_scope and os.path.exists(target_scope):
                    window.set_location_scope(target_scope)
            # Bring existing window to front
            window._show_main_window()

    local_server.newConnection.connect(handle_new_connection)
    window.show()

    # Apply initial scope if passed on first launch
    if initial_scope and os.path.exists(initial_scope):
        window.set_location_scope(initial_scope)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

