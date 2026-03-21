#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./install.sh [--dir ~/LoRa-Ultimate-Copy] [--repo-url https://github.com/the-tech-pro/LoRa-Ultimate-Copy.git] [--branch main]

Bootstrap installer for the eChook LoRa project.

What it does:
  - installs git if needed
  - clones or updates the repo
  - launches the interactive setup wizard

This file is intended for the pre-clone one-liner flow, for example:
  curl -fsSL https://raw.githubusercontent.com/the-tech-pro/LoRa-Ultimate-Copy/main/install.sh | bash
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_value() {
  local flag="$1"
  local value="${2:-}"
  [[ -n "$value" ]] || die "$flag requires a value"
}

repo_url="https://github.com/the-tech-pro/LoRa-Ultimate-Copy.git"
branch="main"
install_dir="${INSTALL_DIR:-$HOME/LoRa-Ultimate-Copy}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      require_value "$1" "${2:-}"
      install_dir="$2"
      shift 2
      ;;
    --repo-url)
      require_value "$1" "${2:-}"
      repo_url="$2"
      shift 2
      ;;
    --branch)
      require_value "$1" "${2:-}"
      branch="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

echo "eChook LoRa bootstrap installer"
echo "Repository: ${repo_url}"
echo "Branch: ${branch}"
echo "Install directory: ${install_dir}"
echo

if ! command -v git >/dev/null 2>&1; then
  echo "Installing git"
  sudo apt update
  sudo apt install -y git ca-certificates
fi

if [[ -d "${install_dir}/.git" ]]; then
  echo "Existing repo found, updating it"
  current_remote="$(git -C "$install_dir" remote get-url origin 2>/dev/null || true)"
  [[ -n "$current_remote" ]] || die "Existing git repo at ${install_dir} has no origin remote"
  [[ "$current_remote" == "$repo_url" ]] || die "Existing repo at ${install_dir} points to ${current_remote}, expected ${repo_url}"
  git -C "$install_dir" fetch origin "$branch"
  git -C "$install_dir" checkout "$branch"
  git -C "$install_dir" pull --ff-only origin "$branch"
elif [[ -e "$install_dir" ]]; then
  die "Install directory ${install_dir} already exists and is not a git checkout"
else
  echo "Cloning repo"
  git clone --branch "$branch" "$repo_url" "$install_dir"
fi

cd "$install_dir"

echo
echo "Repository ready at ${install_dir}"
echo "Launching interactive setup wizard..."

if [[ ! -t 0 ]]; then
  if [[ -r /dev/tty ]]; then
    exec bash ./scripts/setup.sh </dev/tty >/dev/tty 2>&1
  fi

  echo "No interactive terminal is available for the setup wizard."
  echo "Run it manually with:"
  echo "  cd ${install_dir}"
  echo "  bash ./scripts/setup.sh"
  exit 0
fi

exec bash ./scripts/setup.sh
