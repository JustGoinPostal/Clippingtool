# Postal AutoClip — Windows launcher

The preferred Windows workflow is the packaged launcher, not manual PowerShell commands.

## Normal use

1. Download the latest `PostalAutoClip-Windows` build artifact from the repository's **Build Windows Package** GitHub Actions run.
2. Extract `PostalAutoClip-Windows.zip` to a normal folder such as `C:\PostalAutoClip`.
3. Double-click `PostalAutoClip.exe`.
4. Choose your OBS recording folder with **Browse** and click **Save Folder**.
5. Click **Start AutoClip**.

On the first run, the launcher checks for Python 3.11/3.12 and FFmpeg. When either is missing, **Run Setup** uses Windows Package Manager (`winget`) to install it, creates AutoClip's private `.venv`, and installs the Python dependencies. Later launches reuse that environment.

## Launcher buttons

- **Browse / Save Folder** — choose the OBS recording directory AutoClip watches.
- **Run Setup** — install/check prerequisites and the local Python environment.
- **Start AutoClip** — start the local API/watcher and open the clip dashboard.
- **Stop** — stop the AutoClip process started by this launcher.
- **Open Clips** — open `http://127.0.0.1:8787`.
- **Analytics** — open `http://127.0.0.1:8787/static/analytics.html`.
- **Secrets Folder** — open the local credential directory.
- **Connect YouTube** — start the existing YouTube upload OAuth flow after the local server is running and `secrets/youtube_client_secret.json` exists.
- **Connect Analytics** — start the read-only YouTube analytics OAuth flow.

## Status panel

The launcher shows whether:

- the AutoClip server is running;
- the local Python/FFmpeg setup is ready;
- YouTube has an upload token;
- TikTok has a local token file;
- Instagram has a local token file;
- RuneLite events have been seen by the running local server.

## Privacy

The launcher uses the same local-first model as the rest of Postal AutoClip. Source recordings, generated clips, SQLite data, analytics history, and files under `secrets/` stay on the PC unless you explicitly queue media for a social platform.

## Developer build

The launcher is a small native WinForms front end under `launcher/`. The main Python application remains separate so Whisper/FFmpeg/ML dependencies do not have to be embedded into a giant fragile executable.

GitHub Actions publishes the launcher as a self-contained Windows x64 executable and bundles it with the Python application into `PostalAutoClip-Windows.zip`.
