"""
build_installer.py — Builds OmniSearch Studio into:
  1. dist/OmniSearchStudio.exe (Application Executable)
  2. dist/OmniSearchStudio_Setup.exe (Windows Setup Installer Wizard)
"""
import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")


def run_pyinstaller(args, description="Building Executable"):
    print("\n" + "=" * 60)
    print(description)
    print("=" * 60)
    cmd = [sys.executable, "-m", "PyInstaller"] + args
    print("Command:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode != 0:
        print(f"[ERROR] PyInstaller failed with code {res.returncode}")
        sys.exit(res.returncode)


def build():
    ico_path = os.path.join(BASE_DIR, "logo.ico")
    png_path = os.path.join(BASE_DIR, "logo.png")

    os.makedirs(DIST_DIR, exist_ok=True)
    os.makedirs(BUILD_DIR, exist_ok=True)

    # ── 1. Build Main Application (OmniSearchStudio.exe) ──────────────────────
    app_args = [
        "--name=OmniSearchStudio",
        "--windowed",
        "--noconsole",
        "--onefile",
        "--clean",
        f"--distpath={DIST_DIR}",
        f"--workpath={os.path.join(BUILD_DIR, 'app')}",
        f"--add-data={png_path};.",
        f"--add-data={ico_path};.",
        "--hidden-import=PySide6",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=pypdfium2",
        "--hidden-import=winreg",
        "--hidden-import=ctypes",
        "--hidden-import=core",
        "--hidden-import=core.models",
        "--hidden-import=core.scanner",
        "--hidden-import=core.indexer",
        "--hidden-import=core.preview_loader",
        "--hidden-import=core.network_manager",
        "--hidden-import=core.duplicates",
        "--hidden-import=core.watcher",
        "--hidden-import=core.windows_integration",
        "--hidden-import=core.content_search",
        "--hidden-import=core.app_launcher",
        "--hidden-import=core.hotkey_manager",
        "--hidden-import=core.updater",
        "--hidden-import=ui",
        "--hidden-import=ui.main_window",
        "--hidden-import=ui.search_table_model",
        "--hidden-import=ui.preview_panel",
        "--hidden-import=ui.about_dialog",
        "--hidden-import=ui.update_dialog",
        "--hidden-import=ui.drives_dialog",
        "--hidden-import=ui.integration_dialog",
        "--hidden-import=ui.duplicates_dialog",
        "--hidden-import=ui.large_files_dialog",
        "--hidden-import=ui.batch_rename_dialog",
        "--hidden-import=ui.quick_launcher",
        "--hidden-import=ui.styles",
    ]
    if os.path.exists(ico_path):
        app_args.append(f"--icon={ico_path}")

    app_args.append(os.path.join(BASE_DIR, "main.py"))

    run_pyinstaller(app_args, "Step 1: Compiling Main Application (OmniSearchStudio.exe)")

    # ── 2. Build Setup Installer (OmniSearchStudio_Setup.exe) ─────────────────
    installer_args = [
        "--name=OmniSearchStudio_Setup",
        "--windowed",
        "--noconsole",
        "--onefile",
        "--clean",
        f"--distpath={DIST_DIR}",
        f"--workpath={os.path.join(BUILD_DIR, 'installer')}",
        f"--add-data={png_path};.",
        f"--add-data={ico_path};.",
        f"--add-data={os.path.join(DIST_DIR, 'OmniSearchStudio.exe')};.",
        "--hidden-import=PySide6",
        "--hidden-import=winreg",
        "--hidden-import=ctypes",
        "--hidden-import=core.windows_integration",
        "--hidden-import=core.updater",
    ]
    if os.path.exists(ico_path):
        installer_args.append(f"--icon={ico_path}")

    installer_args.append(os.path.join(BASE_DIR, "installer.py"))

    run_pyinstaller(installer_args, "Step 2: Compiling Windows Setup Installer Wizard (OmniSearchStudio_Setup.exe)")

    print("\n" + "=" * 60)
    print(" BUILD SUCCESSFUL!")
    print("=" * 60)
    main_exe = os.path.join(DIST_DIR, "OmniSearchStudio.exe")
    setup_exe = os.path.join(DIST_DIR, "OmniSearchStudio_Setup.exe")

    if os.path.exists(main_exe):
        size_mb = os.path.getsize(main_exe) / (1024 * 1024)
        print(f"1. Application: {main_exe} ({size_mb:.1f} MB)")

    if os.path.exists(setup_exe):
        size_mb = os.path.getsize(setup_exe) / (1024 * 1024)
        print(f"2. Windows Installer: {setup_exe} ({size_mb:.1f} MB)")

    print("\nTo install OmniSearch Studio with Desktop shortcut, Start Menu shortcut, and Windows startup:")
    print(f"Run: {setup_exe}")

    # ── 3. Automatically Create Versioned ZIP Backup & Copy to github/ ───────
    try:
        import zipfile
        from core.windows_integration import APP_VERSION
        zip_name = f"OmniSearchStudio-v{APP_VERSION}.zip"
        zip_path = os.path.join(DIST_DIR, zip_name)
        print(f"\nCreating Versioned Backup ZIP: {zip_name}...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(main_exe):
                zf.write(main_exe, arcname="OmniSearchStudio.exe")
            if os.path.exists(setup_exe):
                zf.write(setup_exe, arcname="OmniSearchStudio_Setup.exe")
        zip_mb = os.path.getsize(zip_path) / (1024 * 1024)
        print(f"3. Backup Archive: {zip_path} ({zip_mb:.1f} MB)")

        # Mirror releases to github/releases/
        github_releases_dir = os.path.join(BASE_DIR, "github", "releases")
        os.makedirs(github_releases_dir, exist_ok=True)
        for f in [main_exe, setup_exe, zip_path]:
            if os.path.exists(f):
                shutil.copy2(f, os.path.join(github_releases_dir, os.path.basename(f)))
        print(f"4. Successfully mirrored all release files to: {github_releases_dir}")
    except Exception as e:
        print(f"[Warning] Failed to generate versioned zip / copy to github: {e}")


if __name__ == "__main__":
    build()
