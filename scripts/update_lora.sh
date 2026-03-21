#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if ! git diff --quiet --ignore-submodules -- || ! git diff --cached --quiet --ignore-submodules --; then
  echo "Tracked local changes detected in $repo_dir." >&2
  echo "Commit, stash, or remove them before running update_lora.sh." >&2
  exit 1
fi

echo "Updating repo in $repo_dir"
git pull --ff-only

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Creating virtualenv"
  python3 -m venv .venv
fi

echo "Installing Python dependencies"
".venv/bin/pip" install -r requirements.txt

services=()
for service in lora-sender lora-receiver; do
  if systemctl list-unit-files --type=service --all | grep -Fq "${service}.service"; then
    services+=("$service")
  fi
done

if [[ ${#services[@]} -gt 0 ]]; then
  echo "Restarting installed services: ${services[*]}"
  sudo systemctl restart "${services[@]}"
else
  echo "No lora systemd services found. Restart the Python app manually if needed."
fi

echo "Update complete"
