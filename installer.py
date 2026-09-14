import os
import sys
import time
import shutil
import subprocess
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar,
    QFileDialog, QFrame, QMessageBox, QTextEdit, QRadioButton, QButtonGroup
)

from core.windows_integration import (
    create_windows_shortcut, set_run_on_startup,
    register_windows_uninstaller, register_explorer_context_menu,
    get_default_install_dir, get_desktop_dir, get_start_menu_programs_dir,
    APP_NAME, APP_VERSION, APP_PUBLISHER, APP_ID
)


def kill_running_instances(timeout_sec: float = 3.0):
    """
    Forcefully terminates any existing background or foreground running instances
    of OmniSearchStudio.exe so that file copying and updating never fails or requires
    opening Windows Task Manager manually.
    """
    if sys.platform != "win32":
        return

    # 1. First attempt: taskkill /f /im OmniSearchStudio.exe
    try:
        subprocess.run(["taskkill", "/f", "/im", "OmniSearchStudio.exe"], capture_output=True)
    except Exception:
        pass

    # 2. Second attempt: PowerShell Stop-Process targeting any instance
    try:
        ps_cmd = 'Get-Process OmniSearchStudio -ErrorAction SilentlyContinue | Stop-Process -Force'
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], capture_output=True)
    except Exception:
        pass

    # 3. Give Windows filesystem handle releaser a brief moment
    time.sleep(0.4)


class InstallWorker(QThread):
    """Background worker that performs process cleanup, file copy, shortcut creation, and registry setup."""
    progress = Signal(int, str)
    finished_success = Signal(str)
    failed = Signal(str)

    def __init__(self, source_dir: str, target_dir: str, create_desktop: bool, create_start: bool, autostart: bool, explorer_context: bool = True):
        super().__init__()
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.create_desktop = create_desktop
        self.create_start = create_start
        self.autostart = autostart
        self.explorer_context = explorer_context

    def run(self):
        try:
            self.progress.emit(5, "Closing previously running OmniSearch Studio instances...")
            kill_running_instances()

            self.progress.emit(12, "Preparing installation directory...")
            os.makedirs(self.target_dir, exist_ok=True)

            # Copy files from source to target
            self.progress.emit(25, "Deploying application binaries and assets...")
            
            # Check if source has OmniSearchStudio.exe or main.py tree
            items_to_copy = [
                "OmniSearchStudio.exe", "main.py", "logo.ico", "logo.png",
                "core", "ui", "run.bat"
            ]

            total_items = len(items_to_copy)
            for idx, item in enumerate(items_to_copy):
                src = os.path.join(self.source_dir, item)
                dst = os.path.join(self.target_dir, item)
                if os.path.exists(src):
                    # Retry logic for destination if locked
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            if os.path.isdir(src):
                                if os.path.exists(dst):
                                    shutil.rmtree(dst, ignore_errors=True)
                                shutil.copytree(src, dst)
                            else:
                                if os.path.exists(dst):
                                    try:
                                        os.remove(dst)
                                    except Exception:
                                        kill_running_instances()
                                shutil.copy2(src, dst)
                            break
                        except Exception as copy_err:
                            if attempt == max_retries - 1:
                                raise copy_err
                            kill_running_instances()
                            time.sleep(0.5)

                pct = 25 + int(45 * (idx + 1) / total_items)
                self.progress.emit(pct, f"Installing {item}...")

            # If there is a dist/ folder with the compiled exe, copy that too
            dist_exe = os.path.join(self.source_dir, "dist", "OmniSearchStudio.exe")
            target_exe = os.path.join(self.target_dir, "OmniSearchStudio.exe")
            if os.path.exists(dist_exe) and not os.path.exists(target_exe):
                shutil.copy2(dist_exe, target_exe)

            # Check target executable
            if not os.path.exists(target_exe):
                target_exe = os.path.join(self.target_dir, "main.py")

            # ── Create Uninstaller Script ─────────────────────────────────────
            self.progress.emit(75, "Generating uninstaller...")
            uninstall_bat_path = os.path.join(self.target_dir, "uninstall.bat")
            desktop_lnk = os.path.join(get_desktop_dir(), f"{APP_NAME}.lnk")
            start_dir = os.path.join(get_start_menu_programs_dir(), APP_NAME)

            uninstall_content = f"""@echo off
title Uninstalling {APP_NAME}...
echo Closing {APP_NAME} if running...
taskkill /f /im OmniSearchStudio.exe >nul 2>&1
echo Removing Shortcuts...
if exist "{desktop_lnk}" del /f /q "{desktop_lnk}" >nul 2>&1
if exist "{start_dir}" rd /s /q "{start_dir}" >nul 2>&1
echo Removing Registry Entries...
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "{APP_ID}" /f >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_ID}" /f >nul 2>&1
reg delete "HKCU\\Software\\Classes\\Directory\\shell\\OmniSearchStudio" /f >nul 2>&1
reg delete "HKCU\\Software\\Classes\\Directory\\Background\\shell\\OmniSearchStudio" /f >nul 2>&1
reg delete "HKCU\\Software\\Classes\\Drive\\shell\\OmniSearchStudio" /f >nul 2>&1
echo Removing Installation Files...
cd /d "%TEMP%"
start "" cmd /c "timeout /t 1 /nobreak >nul & rd /s /q \\"{self.target_dir}\\" & exit"
echo {APP_NAME} has been completely uninstalled.
timeout /t 2 >nul
exit
"""
            with open(uninstall_bat_path, "w", encoding="utf-8") as f:
                f.write(uninstall_content)

            # Register with Windows Installed Apps
            self.progress.emit(85, "Registering with Windows Installed Apps...")
            register_windows_uninstaller(
                install_dir=self.target_dir,
                main_exe_path=target_exe,
                uninstall_cmd=f'cmd.exe /c "{uninstall_bat_path}"',
                version=APP_VERSION
            )

            # ── Create Shortcuts ──────────────────────────────────────────────
            self.progress.emit(90, "Creating Desktop & Start Menu shortcuts...")
            ico_path = os.path.join(self.target_dir, "logo.ico")

            is_exe = target_exe.endswith(".exe")
            exec_target = target_exe
            exec_args = ""
            if not is_exe:
                python_exe = sys.executable
                pythonw = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
                if os.path.exists(pythonw):
                    python_exe = pythonw
                exec_target = python_exe
                exec_args = f'"{target_exe}"'

            if self.create_desktop:
                create_windows_shortcut(
                    shortcut_path=desktop_lnk,
                    target_path=exec_target,
                    arguments=exec_args,
                    working_dir=self.target_dir,
                    icon_location=ico_path if os.path.exists(ico_path) else exec_target
                )

            if self.create_start:
                start_lnk = os.path.join(start_dir, f"{APP_NAME}.lnk")
                create_windows_shortcut(
                    shortcut_path=start_lnk,
                    target_path=exec_target,
                    arguments=exec_args,
                    working_dir=self.target_dir,
                    icon_location=ico_path if os.path.exists(ico_path) else exec_target
                )

            # ── Configure Autostart ───────────────────────────────────────────
            if self.autostart:
                self.progress.emit(95, "Configuring Windows Startup...")
                set_run_on_startup(True, target_exe=target_exe)

            # ── Configure Explorer Right-Click Context Menu ──────────────────
            if self.explorer_context:
                self.progress.emit(98, "Registering Windows Explorer Context Menu...")
                register_explorer_context_menu(target_exe=target_exe)

            self.progress.emit(100, "Installation complete!")
            self.finished_success.emit(target_exe)
        except Exception as e:
            self.failed.emit(str(e))


class LicensePage(QWizardPage):
    """Professional End-User License Agreement page requiring user acceptance to proceed."""
    def __init__(self):
        super().__init__()
        self.setTitle("End-User License Agreement")
        self.setSubTitle(f"Please read the following license agreement carefully before continuing.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        lbl_prompt = QLabel("Please review the license terms before installing OmniSearch Studio:")
        lbl_prompt.setStyleSheet("font-size: 12px; color: #cbd5e1;")
        layout.addWidget(lbl_prompt)

        self.txt_license = QTextEdit()
        self.txt_license.setReadOnly(True)
        self.txt_license.setStyleSheet(
            "background-color: #06090e; color: #cbd5e1; border: 1px solid #1e293b; "
            "border-radius: 6px; font-family: 'Consolas', 'Segoe UI', monospace; font-size: 11px; padding: 8px;"
        )

        license_text = f"""OMNISEARCH STUDIO END-USER LICENSE AGREEMENT (EULA)
========================================================================
Version: {APP_VERSION} Pro
Publisher: {APP_PUBLISHER}
Application: {APP_NAME}

1. GRANT OF LICENSE
OmniSearch Studio is granted to you as a high-performance personal and 
enterprise productivity search engine. You are permitted to install, execute, 
and configure this software on any compatible Windows operating system.

2. PRIVACY & LOCAL PROCESSING GUARANTEE
OmniSearch Studio operates 100% LOCALLY on your system. 
- All file indices, document caches, and metadata remain strictly on your local disk.
- Zero telemetry, zero external transmission of document text, and zero telemetry tracking.
- Your sensitive documents (PDF, DOCX, XLSX, PPTX, CAD, and Source Code) are never uploaded to any cloud server.

3. HARDWARE & DISK RESOURCE USAGE
OmniSearch Studio is optimized for lightning-fast search speeds. In-depth content 
search operates in background threads without blocking your system or freezing Windows.

4. UPDATES & RUNNING INSTANCE HANDLING
Setup automatically detects and safely terminates previous running background or 
taskbar instances of OmniSearch Studio during updates to ensure flawless binary replacement.

5. DISCLAIMER OF WARRANTIES
This software is provided "AS IS" without warranty of any kind, express or implied. 
In no event shall the author or publisher be liable for any special, incidental, 
indirect, or consequential damages resulting from the use of this software.

========================================================================
Crafted with pride by Ranjan. All Rights Reserved.
"""
        self.txt_license.setPlainText(license_text)
        layout.addWidget(self.txt_license, 1)

        # Radio button acceptance
        self.rb_agree = QRadioButton("I accept the terms in the License Agreement")
        self.rb_agree.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px;")
        self.rb_agree.toggled.connect(self.completeChanged)

        self.rb_disagree = QRadioButton("I do not accept the terms in the License Agreement")
        self.rb_disagree.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.rb_disagree.setChecked(True)
        self.rb_disagree.toggled.connect(self.completeChanged)

        layout.addWidget(self.rb_agree)
        layout.addWidget(self.rb_disagree)

    def isComplete(self) -> bool:
        return self.rb_agree.isChecked()


class SetupWizard(QWizard):
    """Modern dark-themed Windows Setup Wizard for OmniSearch Studio."""

    def __init__(self, source_dir: str):
        super().__init__()
        self.source_dir = os.path.abspath(source_dir)
        self.installed_exe: str = ""

        # Automatically kill any running instance upfront right when the installer opens!
        kill_running_instances()

        self.setWindowTitle(f"{APP_NAME} Setup — Windows Installer")
        self.setFixedSize(620, 480)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

        logo_path = os.path.join(self.source_dir, "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.setStyleSheet("""
            QWizard {
                background-color: #0b0f19;
                color: #f8fafc;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QWizardPage {
                background-color: #0b0f19;
            }
            QLabel {
                color: #e2e8f0;
            }
            QLineEdit {
                background-color: #0a0e17;
                border: 1px solid #1e293b;
                border-radius: 5px;
                padding: 6px 10px;
                color: #f8fafc;
                font-size: 12px;
            }
            QRadioButton {
                color: #e2e8f0;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #475569;
                border-radius: 8px;
                background-color: #1e293b;
            }
            QRadioButton::indicator:checked {
                background-color: #0284c7;
                border: 2px solid #38bdf8;
            }
            QCheckBox {
                color: #f1f5f9;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #475569;
                border-radius: 4px;
                background-color: #1e293b;
            }
            QCheckBox::indicator:checked {
                background-color: #0284c7;
                border-color: #38bdf8;
            }
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 5px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #0d131f;
                color: #475569;
                border-color: #1e293b;
            }
            QProgressBar {
                background-color: #111827;
                border: 1px solid #1e293b;
                border-radius: 5px;
                text-align: center;
                color: #f8fafc;
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 4px;
            }
        """)

        # Add Wizard Pages in professional order
        self.page_welcome = self._create_welcome_page()
        self.page_license = LicensePage()
        self.page_directory = self._create_directory_page()
        self.page_options = self._create_options_page()
        self.page_install = self._create_install_page()
        self.page_finish = self._create_finish_page()

        self.addPage(self.page_welcome)
        self.addPage(self.page_license)
        self.addPage(self.page_directory)
        self.addPage(self.page_options)
        self.addPage(self.page_install)
        self.addPage(self.page_finish)


    def _create_welcome_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Welcome to OmniSearch Studio Setup")
        page.setSubTitle(f"This wizard will install {APP_NAME} v{APP_VERSION} Pro • Crafted by Ranjan")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        lbl_desc = QLabel(
            f"<b>{APP_NAME} v{APP_VERSION} Pro</b> is an ultra-fast desktop search engine that indexes millions "
            f"of files in milliseconds with in-depth document content search.<br><br>"
            f"<b>Included Features:</b>"
            f"<ul>"
            f"<li>⚡ <b>Quick Launcher (Ctrl + Space)</b>: Instant floating Spotlight-style search bar anywhere in Windows</li>"
            f"<li>⚡ Sub-millisecond instant search with live typing results</li>"
            f"<li>📄 Full-Text Content Search inside PDF, Word (.docx), Excel (.xlsx), PPTX, & Code</li>"
            f"<li>🔌 External Hard Drive, Pen Drive, and Network NAS Share support</li>"
            f"<li>🖼️ Rich visual previews with native page navigation and sheet switching</li>"
            f"<li>🔍 Duplicate File Detective, Storage Space Visualizer, & Batch Renamer</li>"
            f"</ul>"
            f"Click <b>Next</b> to continue."
        )
        lbl_desc.setStyleSheet("font-size: 13px; line-height: 1.6; color: #cbd5e1;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)
        layout.addStretch()
        return page

    def _create_directory_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Choose Install Location")
        page.setSubTitle(f"Select the folder where {APP_NAME} will be installed.")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        lbl_info = QLabel("Setup will install files into the following directory:")
        lbl_info.setStyleSheet("font-size: 13px; color: #e2e8f0;")
        layout.addWidget(lbl_info)

        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(8)

        self.txt_target_dir = QLineEdit(get_default_install_dir())
        dir_layout.addWidget(self.txt_target_dir, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(btn_browse)

        layout.addLayout(dir_layout)

        lbl_note = QLabel(
            "💡 Recommended: Installs into your personal application directory without needing "
            "administrator elevation, ensuring seamless updates and full Start Menu integration."
        )
        lbl_note.setStyleSheet("color: #64748b; font-size: 11px;")
        lbl_note.setWordWrap(True)
        layout.addWidget(lbl_note)

        layout.addStretch()
        return page

    def _browse_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Install Directory", self.txt_target_dir.text())
        if folder:
            self.txt_target_dir.setText(folder)

    def _create_options_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Select Additional Tasks")
        page.setSubTitle("Choose which shortcuts and startup preferences to configure.")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        lbl_hdr = QLabel("Additional shortcuts:")
        lbl_hdr.setStyleSheet("font-weight: bold; font-size: 13px; color: #f8fafc;")
        layout.addWidget(lbl_hdr)

        self.chk_opt_desktop = QCheckBox("Create a Desktop shortcut")
        self.chk_opt_desktop.setChecked(True)
        layout.addWidget(self.chk_opt_desktop)

        self.chk_opt_start = QCheckBox("Create a Start Menu shortcut")
        self.chk_opt_start.setChecked(True)
        layout.addWidget(self.chk_opt_start)

        layout.addSpacing(10)

        lbl_boot = QLabel("System startup:")
        lbl_boot.setStyleSheet("font-weight: bold; font-size: 13px; color: #f8fafc;")
        layout.addWidget(lbl_boot)

        self.chk_opt_autostart = QCheckBox("Start OmniSearch Studio minimized in system tray when Windows boots")
        self.chk_opt_autostart.setChecked(True)
        layout.addWidget(self.chk_opt_autostart)

        layout.addSpacing(10)

        lbl_shell = QLabel("Windows Explorer Integration:")
        lbl_shell.setStyleSheet("font-weight: bold; font-size: 13px; color: #f8fafc;")
        layout.addWidget(lbl_shell)

        self.chk_opt_explorer = QCheckBox("Add 'Search with OmniSearch Studio...' to folder right-click context menu")
        self.chk_opt_explorer.setChecked(True)
        layout.addWidget(self.chk_opt_explorer)

        layout.addStretch()
        return page

    def _create_install_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Installing OmniSearch Studio")
        page.setSubTitle(f"Please wait while setup installs {APP_NAME} v{APP_VERSION} on your computer.")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 24, 20, 24)
        layout.setSpacing(16)

        self.lbl_status = QLabel("Extracting and copying files...")
        self.lbl_status.setStyleSheet("font-size: 13px; color: #94a3b8;")
        layout.addWidget(self.lbl_status)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        layout.addWidget(self.prog_bar)

        layout.addStretch()
        return page

    def _create_finish_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Installation Completed")
        page.setSubTitle(f"{APP_NAME} has been successfully installed on your computer.")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        lbl_success = QLabel(
            f"🎉 <b>Setup is finished!</b><br><br>"
            f"Shortcuts have been placed on your Desktop and Start Menu.<br>"
            f"Press <b>Double-Press Ctrl</b> (or <b>Ctrl + Space</b>) anytime anywhere in Windows to open the instant floating Quick Search HUD!"
        )
        lbl_success.setStyleSheet("font-size: 13px; line-height: 1.6; color: #cbd5e1;")
        lbl_success.setWordWrap(True)
        layout.addWidget(lbl_success)

        self.chk_launch_now = QCheckBox(f"Launch {APP_NAME} now")
        self.chk_launch_now.setChecked(True)
        layout.addWidget(self.chk_launch_now)

        layout.addStretch()
        return page

    def initializePage(self, page_id: int):
        super().initializePage(page_id)
        if self.page(page_id) == self.page_install:
            self.button(QWizard.WizardButton.BackButton).setEnabled(False)
            self.button(QWizard.WizardButton.NextButton).setEnabled(False)
            self._start_installation()

    def _start_installation(self):
        target = self.txt_target_dir.text().strip()
        self.worker = InstallWorker(
            source_dir=self.source_dir,
            target_dir=target,
            create_desktop=self.chk_opt_desktop.isChecked(),
            create_start=self.chk_opt_start.isChecked(),
            autostart=self.chk_opt_autostart.isChecked(),
            explorer_context=self.chk_opt_explorer.isChecked()
        )
        self.worker.progress.connect(self._on_install_progress)
        self.worker.finished_success.connect(self._on_install_success)
        self.worker.failed.connect(self._on_install_failed)
        self.worker.start()

    def _on_install_progress(self, pct: int, msg: str):
        self.prog_bar.setValue(pct)
        self.lbl_status.setText(msg)

    def _on_install_success(self, target_exe: str):
        self.installed_exe = target_exe
        self.button(QWizard.WizardButton.NextButton).setEnabled(True)
        self.next()

    def _on_install_failed(self, err: str):
        QMessageBox.critical(self, "Installation Error", f"An error occurred during installation:\n{err}")
        self.button(QWizard.WizardButton.BackButton).setEnabled(True)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OmniSearch Studio Setup")

    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    wizard = SetupWizard(source_dir=base_dir)
    wizard.show()

    res = app.exec()
    if wizard.installed_exe and wizard.chk_launch_now.isChecked():
        try:
            subprocess.Popen([wizard.installed_exe])
        except Exception:
            pass
    sys.exit(res)


if __name__ == "__main__":
    main()
