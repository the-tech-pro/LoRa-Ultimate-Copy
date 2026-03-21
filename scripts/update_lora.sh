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

service_exists() {
  local service="$1"

  if [[ -f "/etc/systemd/system/${service}.service" ]] || [[ -f "/lib/systemd/system/${service}.service" ]] || [[ -f "/usr/lib/systemd/system/${service}.service" ]]; then
    return 0
  fi

  systemctl cat "${service}.service" >/dev/null 2>&1
}

services=()
for service in lora-sender lora-receiver; do
  if service_exists "$service"; then
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
