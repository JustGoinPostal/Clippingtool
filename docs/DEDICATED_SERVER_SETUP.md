# Postal Creator OS — Dedicated Server Setup

## Target architecture

- Proxmox host: `pve` at `192.168.0.34`
- New VM: `CREATOR-01`
- Network: existing private `10.10.10.0/24` behind Proxmox NAT
- Recommended VM IP: `10.10.10.20`
- Existing `RENTAL-01` remains isolated and untouched
- Streaming PC only streams/records and runs a lightweight handoff agent
- Creator OS, AutoClip, storage, analytics, bots, scheduling, and Cloudflare live on `CREATOR-01`
- Default recurring infrastructure cost target: $0 beyond services already owned
- No OpenAI API dependency by default

## Recommended VM resources

Start with:

- Ubuntu Server 26.04 LTS
- 4 vCPU
- 8 GB RAM
- 80 GB OS disk
- Separate media disk sized for VOD retention if available
- VirtIO NIC on `vmbr0`
- QEMU Guest Agent enabled

If the Proxmox host is short on RAM, use 4 GB initially. Media processing performance scales with available CPU/RAM/GPU, but the control plane does not require large resources.

## Directory layout

The bootstrap script creates:

```text
/opt/postal-creator/
  app/
  config/
  data/
    input/
    output/
    cache/
    covers/
    state/
  recordings/
  secrets/
  logs/
```

`recordings/` is the authenticated SMB landing share used by the streaming PC. AutoClip watches `data/input/`; a later ingest worker moves completed uploads from `recordings/` into the processing queue.

## Phase 1 — create CREATOR-01

Create a new Ubuntu Server VM in Proxmox. Do not reuse `RENTAL-01`.

Suggested settings:

- Name: `CREATOR-01`
- BIOS: SeaBIOS or OVMF; either is fine
- Machine: default
- Disk: SCSI / VirtIO SCSI
- CPU type: host
- Cores: 4
- Memory: 8192 MB
- Network model: VirtIO
- Bridge: `vmbr0`

Use static network settings matching the existing private network:

```text
Address: 10.10.10.20/24
Gateway: 10.10.10.1
DNS: 1.1.1.1, 8.8.8.8
```

Before assigning the address, verify it is unused from the Proxmox host:

```bash
ping -c 2 10.10.10.20
ip neigh show | grep 10.10.10.20
```

If both show no active host, use `.20`. Otherwise choose another unused address in the subnet and update the Creator OS config later.

After Ubuntu installs:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y qemu-guest-agent git curl ffmpeg samba python3 python3-venv python3-pip
sudo systemctl enable --now qemu-guest-agent
```

## Phase 2 — clone and bootstrap

```bash
sudo mkdir -p /opt/postal-creator/app
sudo chown -R "$USER":"$USER" /opt/postal-creator
cd /opt/postal-creator/app
git clone -b feature/server-first-v1 https://github.com/JustGoinPostal/Clippingtool.git .
chmod +x deploy/server/bootstrap.sh
sudo ./deploy/server/bootstrap.sh "$USER"
```

The bootstrap script creates local folders and an authenticated SMB share named `postal-ingest`.

Set the SMB password for the same Linux user:

```bash
sudo smbpasswd -a "$USER"
sudo systemctl restart smbd
```

## Phase 3 — test the share from Windows

From the streaming PC, open File Explorer and enter:

```text
\\10.10.10.20\postal-ingest
```

Sign in with the Linux username/password you configured with `smbpasswd`.

Create a small text file in the share. Confirm it appears on the server:

```bash
ls -lah /opt/postal-creator/recordings
```

## Phase 4 — streaming PC handoff agent

The Windows-side agent is in `streaming_agent/`.

Copy `config.example.json` to `config.json`, set the real OBS recording directory, and leave the server share as:

```text
\\10.10.10.20\postal-ingest
```

Run:

```powershell
py .\streaming_agent\postal_stream_agent.py
```

The agent does not touch files that are still growing. Once a recording has remained unchanged for the configured stability period, it copies it to the server using a `.partial` file and atomically renames it after the copy succeeds.

## Phase 5 — Cloudflare

Do not expose SMB to the internet.

Cloudflare is only for authenticated HTTP services such as the Creator dashboard and future ChatGPT bridge. The SMB share remains LAN-only.

Planned hostname:

```text
creator.postalops.com -> CREATOR-01 local dashboard
```

The existing Cloudflare Tunnel pattern used elsewhere on the network can be reused after the Creator dashboard is running.

## Phase 6 — next build stages

After the VM and automatic recording handoff are verified:

1. Run AutoClip natively on `CREATOR-01`.
2. Add an ingest worker that moves completed uploads into AutoClip automatically.
3. Add OBS/RuneLite telemetry relay from the streaming PC.
4. Add server-hosted Kick/Discord collectors and bots.
5. Add local analytics and automatic distribution.
6. Add the ChatGPT control bridge without making OpenAI API billing a dependency.

## Safety boundaries

- `RENTAL-01` is not modified.
- SMB stays on the LAN only.
- Source VOD deletion remains disabled until a retention policy is explicitly configured.
- Social credentials stay on `CREATOR-01`, not on the streaming PC when avoidable.
- Paid APIs remain opt-in and disabled by default.
