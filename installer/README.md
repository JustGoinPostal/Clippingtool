# Postal AutoClip Windows beta installer

The beta installer is deliberately **per-user** and does not require administrator access for normal installation.

Program files:

`%LOCALAPPDATA%\Programs\Postal AutoClip`

Persistent creator state:

`%LOCALAPPDATA%\PostalAutoClip`

The uninstaller removes only the program files/shortcuts. It intentionally leaves creator data in place so an update/reinstall cannot erase the SQLite database, settings, account tokens, learning history, benchmark labels, logs, covers, or cached model files.

Large media is not forced onto the system drive. The first-run wizard lets the creator choose the OBS recording folder and rendered-clip folder on any local drive.

## Build locally

Install Python 3.12, FFmpeg and Inno Setup 6, then run from the repository root:

```powershell
.\build_windows_beta.ps1
```

The installer is written to `installer\output\PostalAutoClip-Beta-Setup.exe`.

## CI build

The `Build Windows Beta Installer` GitHub Actions workflow is manual (`workflow_dispatch`) so large installer artifacts are not generated and retained on every commit. Run it only when a beta package is actually needed.

## RuneLite companion

If `runelite-companion\build\libs\PostalAutoClipCompanion-*-all.jar` exists when the installer is built, it is bundled under the installed app's `RuneLite` directory. It is not silently injected into RuneLite. The production distribution path should be a reviewed RuneLite Plugin Hub install; sideloading remains a beta/developer path.
