#!/usr/bin/env bash
set -euo pipefail

POSTAL_USER="${1:-${SUDO_USER:-$USER}}"
ROOT="/opt/postal-creator"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo ./deploy/server/bootstrap.sh <linux-user>"
  exit 1
fi

if ! id "$POSTAL_USER" >/dev/null 2>&1; then
  echo "User '$POSTAL_USER' does not exist."
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git curl ffmpeg samba python3 python3-venv python3-pip rsync

mkdir -p \
  "$ROOT/app" \
  "$ROOT/config" \
  "$ROOT/data/input" \
  "$ROOT/data/output" \
  "$ROOT/data/cache" \
  "$ROOT/data/covers" \
  "$ROOT/data/state" \
  "$ROOT/recordings" \
  "$ROOT/secrets" \
  "$ROOT/logs"

chown -R "$POSTAL_USER":"$POSTAL_USER" "$ROOT"
chmod 700 "$ROOT/secrets"
chmod 775 "$ROOT/recordings"

SMB_BEGIN="# BEGIN POSTAL CREATOR OS"
SMB_END="# END POSTAL CREATOR OS"
SMB_BLOCK=$(cat <<EOF
$SMB_BEGIN
[postal-ingest]
   path = $ROOT/recordings
   browseable = yes
   read only = no
   guest ok = no
   valid users = $POSTAL_USER
   force user = $POSTAL_USER
   create mask = 0664
   directory mask = 0775
$SMB_END
EOF
)

python3 - "$SMB_BEGIN" "$SMB_END" "$SMB_BLOCK" <<'PY'
from pathlib import Path
import sys

path = Path('/etc/samba/smb.conf')
begin, end, block = sys.argv[1:4]
text = path.read_text(encoding='utf-8')
if begin in text and end in text:
    before = text.split(begin, 1)[0].rstrip()
    after = text.split(end, 1)[1].lstrip()
    text = before + '\n\n' + block + '\n\n' + after
else:
    text = text.rstrip() + '\n\n' + block + '\n'
path.write_text(text, encoding='utf-8')
PY

testparm -s >/dev/null
systemctl enable --now smbd
systemctl restart smbd

cat <<EOF

Postal Creator OS server folders are ready.

Next:
  1. Set the SMB password:
       sudo smbpasswd -a $POSTAL_USER
  2. From Windows open:
       \\\\SERVER-IP\\postal-ingest
  3. Confirm uploads land in:
       $ROOT/recordings

Nothing in this script touches RENTAL-01, social credentials, or Cloudflare.
EOF
