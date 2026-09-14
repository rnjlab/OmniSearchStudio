# OmniSearch Studio — GitHub Setup & Publishing Guide

This directory contains everything required to publish, distribute, and auto-update **OmniSearch Studio** via GitHub.

## 📁 Directory Structure
```
github/
├── .github/
│   └── workflows/
│       └── build-release.yml       # Automated GitHub Actions release workflow
├── releases/                       # Ready-to-upload binaries
│   ├── OmniSearchStudio.exe        # Standalone portable application (v1.4.0)
│   ├── OmniSearchStudio_Setup.exe  # Windows Setup Installer Wizard (v1.4.0)
│   └── OmniSearchStudio-v1.4.0.zip # Complete release package
├── version.json                    # API manifest for live online updater
├── RELEASE_v1.4.0.md               # Markdown release notes with features
└── GITHUB_SETUP_GUIDE.md           # This setup manual
```

---

## 🚀 How to Publish a New Release on GitHub

### 1. Initialize & Push Repository to GitHub
```bash
cd d:\Antigravity\MyCreations\OmniSearchStudio
git init
git add .
git commit -m "OmniSearch Studio v1.4.0 with Auto-Updater and Telemetry"
git branch -M main
git remote add origin https://github.com/<your-username>/OmniSearchStudio.git
git push -u origin main
```

### 2. Create the GitHub Release
1. Go to your GitHub repository -> **Releases** -> **Draft a new release**.
2. Tag version: `v1.4.0`.
3. Release title: `OmniSearch Studio v1.4.0 — Ultra-Fast Search Engine`.
4. Copy description from `github/RELEASE_v1.4.0.md`.
5. Upload the following binary assets from `github/releases/`:
   - `OmniSearchStudio_Setup.exe` (Windows Installer)
   - `OmniSearchStudio.exe` (Portable)
   - `OmniSearchStudio-v1.4.0.zip` (Backup archive)
   - `version.json` (For online update tracking)
6. Click **Publish Release**.

---

## 🔄 How the In-App Online Updater Works
- When the user launches OmniSearch Studio or clicks **Tools > 🔄 Check for Updates...**:
  1. The app queries the GitHub Releases API (`https://api.github.com/repos/<owner>/<repo>/releases/latest`).
  2. Parses the latest tag (e.g. `v1.4.1`) and compares it using semver logic against `1.4.0`.
  3. If an update is detected, an interactive dialog displays the changelog, download size, and an **Install Update** button.
  4. Clicking **Install Update** streams the installer with a real-time progress bar and launches the wizard seamlessly.

---

## 📊 How Popularity & Usage Tracking Works
- **100% Free & Open-Source**: Uses an anonymous SHA-256 machine hash (`machine_guid` or fallback hash) sent via standard HTTP GET to count daily active users.
- **Privacy Guaranteed**: No IP logging, no filenames, no paths, and no search queries are ever collected.
- **GitHub Badges**: Displays live download count and release badges on your README:
  ```markdown
  [![Downloads](https://img.shields.io/github/downloads/<user>/OmniSearchStudio/total.svg)](https://github.com/<user>/OmniSearchStudio/releases)
  [![Latest Release](https://img.shields.io/github/v/release/<user>/OmniSearchStudio)](https://github.com/<user>/OmniSearchStudio/releases/latest)
  ```
