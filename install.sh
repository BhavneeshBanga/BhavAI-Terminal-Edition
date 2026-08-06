#!/usr/bin/env bash
# ============================================================
# BhavAI installer (macOS / Linux)
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<user>/bhavai/main/install.sh | bash
# ============================================================
set -euo pipefail

# --- EDIT THIS: your GitHub repo ---
REPO_URL="https://github.com/BhavneeshBanga/bhavai-terminal-edition.git"
INSTALL_DIR="${HOME}/.local/share/bhavai"

info() { printf "\033[36m[bhavai]\033[0m %s\n" "$1"; }
ok()   { printf "\033[32m[bhavai]\033[0m %s\n" "$1"; }
err()  { printf "\033[31m[bhavai]\033[0m %s\n" "$1" >&2; }

# 1. Check python
info "Checking Python..."
PYTHON_BIN=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    PYTHON_BIN="$cand"
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  err "Python 3.10+ not found. Install it and re-run this script."
  exit 1
fi
info "Found $($PYTHON_BIN --version)"

# 2. Check git
if ! command -v git >/dev/null 2>&1; then
  err "git not found. Install it and re-run this script."
  exit 1
fi

# 3. Clone or update
if [ -d "$INSTALL_DIR" ]; then
  info "Existing install found, updating..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  info "Cloning bhavai into $INSTALL_DIR ..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

# 4. Install
if command -v pipx >/dev/null 2>&1; then
  info "Installing with pipx..."
  pipx install "$INSTALL_DIR" --force
else
  info "pipx not found, installing with pip --user..."
  "$PYTHON_BIN" -m pip install --user --upgrade "$INSTALL_DIR"
fi

# 5. Verify
if command -v bhav >/dev/null 2>&1; then
  ok "bhavai installed successfully! Run 'bhav' to start."
else
  ok "Install finished. If 'bhav' is not found, add this to your PATH:"
  echo "   $($PYTHON_BIN -m site --user-base)/bin"
  echo "Then restart your terminal or 'source ~/.bashrc' (or ~/.zshrc)."
fi

# 6. API key reminder
if [ -z "${SARVAM_API_KEY:-}" ]; then
  echo ""
  info "Set your Sarvam API key before first use:"
  echo '   export SARVAM_API_KEY="your-key-here"   # add to ~/.bashrc or ~/.zshrc'
fi