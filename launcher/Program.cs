using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace PostalAutoClipLauncher;

internal static class Program
{
    [STAThread]
    static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

public sealed class MainForm : Form
{
    readonly string root = AppContext.BaseDirectory;
    readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(2) };
    readonly Label serverState = new();
    readonly Label setupState = new();
    readonly Label ytState = new();
    readonly Label tiktokState = new();
    readonly Label igState = new();
    readonly Label rlState = new();
    readonly TextBox obsFolder = new();
    readonly TextBox logBox = new();
    readonly Button startButton = new();
    readonly Button stopButton = new();
    readonly System.Windows.Forms.Timer timer = new() { Interval = 3000 };
    Process? server;
    bool busy;

    string VenvPython => Path.Combine(root, ".venv", "Scripts", "python.exe");
    string ConfigPath => Path.Combine(root, "config.json");
    string ExampleConfigPath => Path.Combine(root, "config.example.json");
    string SecretsPath => Path.Combine(root, "secrets");

    public MainForm()
    {
        Text = "Postal AutoClip";
        Width = 980; Height = 720; MinimumSize = new Size(900, 640);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(10, 12, 16); ForeColor = Color.White;
        Font = new Font("Segoe UI", 10f);

        Controls.Add(new Label { Text = "POSTAL AUTOCLIP", Font = new Font("Segoe UI", 24, FontStyle.Bold), AutoSize = true, Left = 28, Top = 22 });
        Controls.Add(new Label { Text = "Local OSRS clipping, editing, publishing, and analytics", ForeColor = Color.Silver, AutoSize = true, Left = 31, Top = 65 });

        var left = new Panel { Left = 28, Top = 105, Width = 560, Height = 520, BackColor = Color.FromArgb(17, 21, 29) };
        var right = new Panel { Left = 610, Top = 105, Width = 330, Height = 520, BackColor = Color.FromArgb(17, 21, 29) };
        Controls.Add(left); Controls.Add(right);

        AddHeader(left, "CONTROL", 18); AddLabel(left, "OBS recording folder", 60);
        obsFolder.SetBounds(24, 87, 405, 32); StyleText(obsFolder); left.Controls.Add(obsFolder);
        left.Controls.Add(MakeButton("Browse", 438, 86, 95, 34, BrowseObs));
        left.Controls.Add(MakeButton("Save Folder", 24, 128, 120, 36, SaveObs));
        left.Controls.Add(MakeButton("Run Setup", 154, 128, 120, 36, async (_, _) => await RunSetupAsync()));

        startButton.Text = "START AUTOCLIP"; startButton.SetBounds(24, 184, 244, 58); StylePrimary(startButton); startButton.Click += async (_, _) => await StartServerAsync(); left.Controls.Add(startButton);
        stopButton.Text = "STOP"; stopButton.SetBounds(282, 184, 110, 58); StyleButton(stopButton); stopButton.Click += (_, _) => StopServer(); left.Controls.Add(stopButton);
        left.Controls.Add(MakeButton("Open Clips", 24, 255, 110, 40, (_, _) => OpenUrl("http://127.0.0.1:8787")));
        left.Controls.Add(MakeButton("Analytics", 144, 255, 110, 40, (_, _) => OpenUrl("http://127.0.0.1:8787/static/analytics.html")));
        left.Controls.Add(MakeButton("Accounts", 264, 255, 110, 40, async (_, _) => await OpenAccountsAsync()));
        left.Controls.Add(MakeButton("Secrets", 384, 255, 149, 40, (_, _) => OpenFolder(SecretsPath)));

        AddLabel(left, "Activity", 312);
        logBox.SetBounds(24, 338, 509, 154); logBox.Multiline = true; logBox.ReadOnly = true; logBox.ScrollBars = ScrollBars.Vertical; StyleText(logBox); left.Controls.Add(logBox);

        AddHeader(right, "STATUS", 18);
        AddStatus(right, "Server", serverState, 62); AddStatus(right, "Setup", setupState, 108); AddStatus(right, "YouTube", ytState, 154);
        AddStatus(right, "TikTok", tiktokState, 200); AddStatus(right, "Instagram", igState, 246); AddStatus(right, "RuneLite", rlState, 292);
        right.Controls.Add(MakeButton("Connect YouTube", 22, 350, 135, 38, async (_, _) => await PostLocalAsync("/api/publishing/youtube/connect")));
        right.Controls.Add(MakeButton("Connect Analytics", 168, 350, 140, 38, async (_, _) => await PostLocalAsync("/api/analytics/youtube/connect")));
        right.Controls.Add(MakeButton("TikTok / Instagram", 22, 400, 286, 38, async (_, _) => await OpenAccountsAsync()));
        right.Controls.Add(new Label { Left = 22, Top = 450, Width = 286, Height = 55, ForeColor = Color.Silver, Text = "Account app keys and OAuth tokens stay local. Use Accounts to connect TikTok and Instagram through your browser." });

        FormClosing += (_, _) => StopServer();
        Load += async (_, _) => { EnsureConfig(); LoadObsFolder(); await RefreshStatusAsync(); timer.Start(); };
        timer.Tick += async (_, _) => await RefreshStatusAsync();
    }

    void AddHeader(Control p, string t, int y) => p.Controls.Add(new Label { Text = t, Left = 22, Top = y, AutoSize = true, Font = new Font("Segoe UI", 12, FontStyle.Bold) });
    void AddLabel(Control p, string t, int y) => p.Controls.Add(new Label { Text = t, Left = 24, Top = y, AutoSize = true, ForeColor = Color.Gainsboro });
    void AddStatus(Control p, string name, Label value, int y) { p.Controls.Add(new Label { Text = name, Left = 22, Top = y, Width = 100, ForeColor = Color.Silver }); value.Left = 132; value.Top = y; value.Width = 170; value.Font = new Font("Segoe UI", 10, FontStyle.Bold); p.Controls.Add(value); }
    Button MakeButton(string text, int x, int y, int w, int h, EventHandler handler) { var b = new Button { Text = text }; b.SetBounds(x, y, w, h); StyleButton(b); b.Click += handler; return b; }
    void StyleButton(Button b) { b.FlatStyle = FlatStyle.Flat; b.FlatAppearance.BorderColor = Color.FromArgb(58, 68, 86); b.BackColor = Color.FromArgb(31, 38, 50); b.ForeColor = Color.White; }
    void StylePrimary(Button b) { StyleButton(b); b.BackColor = Color.FromArgb(230, 235, 248); b.ForeColor = Color.FromArgb(10, 12, 16); b.Font = new Font("Segoe UI", 11, FontStyle.Bold); }
    void StyleText(TextBox t) { t.BackColor = Color.FromArgb(11, 14, 19); t.ForeColor = Color.White; t.BorderStyle = BorderStyle.FixedSingle; }
    void SetState(Label label, string text, bool? ok = null) { label.Text = text; label.ForeColor = ok == true ? Color.LightGreen : ok == false ? Color.OrangeRed : Color.Khaki; }

    void EnsureConfig() { try { if (!File.Exists(ConfigPath) && File.Exists(ExampleConfigPath)) File.Copy(ExampleConfigPath, ConfigPath); } catch { } }
    void LoadObsFolder() { try { var node = JsonNode.Parse(File.ReadAllText(ConfigPath))?.AsObject(); obsFolder.Text = node?["watch_folder"]?.GetValue<string>() ?? "data/input"; } catch { obsFolder.Text = "data/input"; } }
    void BrowseObs(object? s, EventArgs e) { using var dlg = new FolderBrowserDialog { Description = "Choose your OBS recording folder", UseDescriptionForTitle = true }; if (dlg.ShowDialog() == DialogResult.OK) obsFolder.Text = dlg.SelectedPath; }
    void SaveObs(object? s, EventArgs e)
    {
        try { EnsureConfig(); var node = JsonNode.Parse(File.ReadAllText(ConfigPath))?.AsObject() ?? new JsonObject(); node["watch_folder"] = obsFolder.Text.Trim(); File.WriteAllText(ConfigPath, node.ToJsonString(new JsonSerializerOptions { WriteIndented = true })); Log("Saved OBS folder."); }
        catch (Exception ex) { MessageBox.Show(ex.Message, "Could not save folder"); }
    }

    async Task RunSetupAsync()
    {
        if (busy) return; busy = true; ToggleBusy(true); Log("Starting first-run setup...");
        try
        {
            EnsureConfig();
            if (FindPython() is null)
            {
                if (!CommandExists("winget")) throw new Exception("Windows Package Manager (winget) is required for automatic Python installation.");
                Log("Python 3.12 not found. Installing...");
                if (await RunVisibleAsync("winget", "install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements") != 0) throw new Exception("Python install did not complete successfully.");
                RefreshPath();
            }
            if (!CommandExists("ffmpeg"))
            {
                if (!CommandExists("winget")) throw new Exception("FFmpeg is missing and winget is unavailable.");
                Log("FFmpeg not found. Installing...");
                if (await RunVisibleAsync("winget", "install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements") != 0) throw new Exception("FFmpeg install did not complete successfully.");
                RefreshPath();
            }
            if (!File.Exists(VenvPython))
            {
                var py = FindPython() ?? throw new Exception("Python was installed but is not visible yet. Restart Postal AutoClip and press Run Setup again.");
                Log("Creating private Python environment..."); await RunCaptureAsync(py.file, $"{py.prefix}-m venv .venv");
            }
            Log("Installing/updating AutoClip dependencies...");
            await RunCaptureAsync(VenvPython, "-m pip install --upgrade pip wheel");
            await RunCaptureAsync(VenvPython, "-m pip install -e .");
            Log("Setup complete.");
        }
        catch (Exception ex) { Log("SETUP ERROR: " + ex.Message); MessageBox.Show(ex.Message, "Postal AutoClip setup"); }
        finally { busy = false; ToggleBusy(false); await RefreshStatusAsync(); }
    }

    async Task StartServerAsync()
    {
        if (await IsServerUp()) { OpenUrl("http://127.0.0.1:8787"); return; }
        if (!File.Exists(VenvPython)) await RunSetupAsync();
        if (!File.Exists(VenvPython)) return;
        SaveObs(null, EventArgs.Empty);
        try
        {
            var psi = new ProcessStartInfo(VenvPython, "-m uvicorn app.api:app --host 127.0.0.1 --port 8787") { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            server = new Process { StartInfo = psi, EnableRaisingEvents = true };
            server.OutputDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) Log(e.Data); };
            server.ErrorDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) Log(e.Data); };
            server.Exited += (_, _) => BeginInvoke(new Action(() => { Log("AutoClip server stopped."); _ = RefreshStatusAsync(); }));
            server.Start(); server.BeginOutputReadLine(); server.BeginErrorReadLine(); Log("Starting Postal AutoClip...");
            for (var i = 0; i < 25; i++) { if (await IsServerUp()) { OpenUrl("http://127.0.0.1:8787"); break; } await Task.Delay(500); }
            await RefreshStatusAsync();
        }
        catch (Exception ex) { Log("START ERROR: " + ex.Message); }
    }

    async Task OpenAccountsAsync()
    {
        if (!await IsServerUp()) await StartServerAsync();
        if (!await IsServerUp()) return;
        for (var i = 0; i < 10; i++)
        {
            try
            {
                using var r = await http.GetAsync("http://127.0.0.1:8790/status");
                if (r.IsSuccessStatusCode) { OpenUrl("http://127.0.0.1:8790"); return; }
            }
            catch { }
            await Task.Delay(250);
        }
        MessageBox.Show("The account manager did not start. Check the Activity log, then restart AutoClip.", "Postal AutoClip Accounts");
    }

    void StopServer() { try { if (server is { HasExited: false }) { server.Kill(true); server.WaitForExit(3000); } } catch { } server = null; _ = RefreshStatusAsync(); }

    async Task RefreshStatusAsync()
    {
        var up = await IsServerUp(); SetState(serverState, up ? "RUNNING" : "STOPPED", up);
        var ready = File.Exists(VenvPython) && CommandExists("ffmpeg"); SetState(setupState, ready ? "READY" : "SETUP NEEDED", ready);
        var yt = File.Exists(Path.Combine(SecretsPath, "youtube_token.json")); SetState(ytState, yt ? "CONNECTED" : "NOT CONNECTED", yt);
        var tt = File.Exists(Path.Combine(SecretsPath, "tiktok_token.json")); SetState(tiktokState, tt ? "CONNECTED" : "NOT CONNECTED", tt);
        var ig = File.Exists(Path.Combine(SecretsPath, "instagram_token.json")); SetState(igState, ig ? "CONNECTED" : "NOT CONNECTED", ig);
        if (up)
        {
            try { var r = await http.GetAsync("http://127.0.0.1:8787/api/game-events/recent?limit=1"); var txt = await r.Content.ReadAsStringAsync(); SetState(rlState, txt.Trim() != "[]" ? "EVENTS SEEN" : "WAITING", null); }
            catch { SetState(rlState, "WAITING", null); }
        }
        else SetState(rlState, "SERVER OFF", false);
    }

    async Task PostLocalAsync(string path)
    {
        if (!await IsServerUp()) { MessageBox.Show("Start AutoClip first."); return; }
        try { var r = await http.PostAsync("http://127.0.0.1:8787" + path, new StringContent("{}", Encoding.UTF8, "application/json")); Log(await r.Content.ReadAsStringAsync()); }
        catch (Exception ex) { Log(ex.Message); }
    }

    async Task<bool> IsServerUp() { try { var r = await http.GetAsync("http://127.0.0.1:8787/api/status"); return r.IsSuccessStatusCode; } catch { return false; } }
    (string file, string prefix)? FindPython() { foreach (var c in new[] { ("py", "-3.12 "), ("py", "-3.11 "), ("python", "") }) if (RunCheck(c.Item1, c.Item2 + "--version")) return (c.Item1, c.Item2); return null; }
    bool CommandExists(string cmd) => RunCheck("where", cmd);
    bool RunCheck(string file, string args)
    {
        try { using var p = Process.Start(new ProcessStartInfo(file, args) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true }); if (p is null) return false; if (!p.WaitForExit(4000)) { p.Kill(); return false; } return p.ExitCode == 0; }
        catch { return false; }
    }
    async Task<int> RunVisibleAsync(string file, string args) { using var p = Process.Start(new ProcessStartInfo(file, args) { WorkingDirectory = root, UseShellExecute = true }) ?? throw new Exception($"Could not start {file}"); await p.WaitForExitAsync(); return p.ExitCode; }
    async Task RunCaptureAsync(string file, string args)
    {
        var psi = new ProcessStartInfo(file, args) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        using var p = Process.Start(psi) ?? throw new Exception($"Could not start {file}");
        p.OutputDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) Log(e.Data); }; p.ErrorDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) Log(e.Data); };
        p.BeginOutputReadLine(); p.BeginErrorReadLine(); await p.WaitForExitAsync(); if (p.ExitCode != 0) throw new Exception($"Command failed: {file} {args}");
    }
    void RefreshPath() { var machine = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.Machine) ?? ""; var user = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.User) ?? ""; Environment.SetEnvironmentVariable("Path", machine + ";" + user); }
    void ToggleBusy(bool value) { startButton.Enabled = !value; stopButton.Enabled = !value; }
    void OpenUrl(string url) { try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); } catch { } }
    void OpenFolder(string path) { try { Directory.CreateDirectory(path); Process.Start(new ProcessStartInfo("explorer.exe", $"\"{path}\"") { UseShellExecute = true }); } catch { } }
    void Log(string text) { if (InvokeRequired) { BeginInvoke(new Action(() => Log(text))); return; } logBox.AppendText($"[{DateTime.Now:HH:mm:ss}] {text}{Environment.NewLine}"); logBox.SelectionStart = logBox.TextLength; logBox.ScrollToCaret(); }
}
