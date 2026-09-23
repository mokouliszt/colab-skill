#!/usr/bin/env bash
# Install (or repair) google-colab-cli and make sure `colab run/exec` can work.
#
# google-colab-cli 0.7.2 pins jupyter-kernel-client==0.8, but its runtime code
# needs JupyterSubprotocol, which first appeared in jupyter-kernel-client 0.9.0.
# When the installed kernel client lacks it, reinstall with an override.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

command -v uv >/dev/null 2>&1 || pip install -q uv --break-system-packages 2>/dev/null || pip install -q uv
command -v colab >/dev/null 2>&1 || uv tool install -q google-colab-cli

cli_python() { head -1 "$(readlink -f "$(command -v colab)")" | sed 's/^#!//; s/ .*//'; }
has_subprotocol() { "$(cli_python)" -c "import jupyter_kernel_client as j, sys; sys.exit(0 if hasattr(j, 'JupyterSubprotocol') else 1)" 2>/dev/null; }

if ! has_subprotocol; then
  overrides="$(mktemp)"
  echo "jupyter-kernel-client==0.9.0" > "$overrides"
  uv tool install -q --force google-colab-cli --overrides "$overrides"
  rm -f "$overrides"
  has_subprotocol || { echo "colab CLI installed, but its kernel client is still incompatible." >&2; exit 1; }
  echo "Applied jupyter-kernel-client 0.9.0 override."
fi
colab version | tail -1
echo "PATH needs: $HOME/.local/bin"
