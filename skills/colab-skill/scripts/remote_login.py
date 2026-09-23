#!/usr/bin/env python3
"""Two-step version of the Colab CLI remote copy-paste OAuth flow.

The CLI itself prints the URL and then blocks on input() in the same process.
Hosted sandboxes may not keep that process alive until the user replies, so
this helper splits the flow while reusing the CLI's own OAuth client, scopes
and redirect page:

  remote_login.py gen                     print the authorization URL
  remote_login.py exchange < code.txt     exchange the code (read from stdin)

The PKCE verifier is kept in a 0600 file under ~/.config/colab-cli/ between
the two steps, so the pasted code alone cannot be redeemed elsewhere.
The resulting token is written where the CLI expects it. Secrets are never
printed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def reexec_with_cli_python() -> None:
    """colab_cli lives in the uv tool venv; re-run this script with that Python."""
    candidates = []
    colab = shutil.which("colab")
    if colab:  # the entry-point script's shebang names the venv Python
        with open(colab, "rb") as handle:
            first = handle.readline().decode(errors="ignore").strip()
        if first.startswith("#!"):
            candidates.append(Path(first[2:].split()[0]))
    if shutil.which("uv"):
        tool_dir = subprocess.run(["uv", "tool", "dir"], capture_output=True, text=True).stdout.strip()
        if tool_dir:
            candidates.append(Path(tool_dir) / "google-colab-cli" / "bin" / "python")
    candidates.append(Path.home() / ".local/share/uv/tools/google-colab-cli/bin/python")
    if os.environ.get("COLAB_REMOTE_LOGIN_REEXEC"):
        candidates = []  # already re-executed once; avoid a loop
    os.environ["COLAB_REMOTE_LOGIN_REEXEC"] = "1"
    for python in candidates:
        # venv interpreters are symlinks, so compare unresolved paths.
        if python.is_file():
            os.execv(str(python), [str(python), os.path.abspath(__file__), *sys.argv[1:]])
    sys.exit("google-colab-cli is not installed. Run: uv tool install google-colab-cli")


try:
    from importlib import resources

    from colab_cli.auth import PUBLIC_SCOPES, REMOTE_REDIRECT_URI, TOKEN_CONFIG_PATH
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    reexec_with_cli_python()

PENDING = Path(TOKEN_CONFIG_PATH).with_name(".pending-oauth.json")


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o600)


def make_flow() -> InstalledAppFlow:
    config = json.loads(resources.files("colab_cli").joinpath("oauth_config.json").read_text())
    flow = InstalledAppFlow.from_client_config(config, PUBLIC_SCOPES)
    flow.redirect_uri = REMOTE_REDIRECT_URI
    return flow


def gen() -> int:
    flow = make_flow()
    url, _ = flow.authorization_url(prompt="consent", token_usage="remote")
    write_private(PENDING, json.dumps({"code_verifier": flow.code_verifier}))
    print(url)
    return 0


def exchange() -> int:
    if not PENDING.is_file():
        print("No pending login. Run 'gen' first.", file=sys.stderr)
        return 3
    code = sys.stdin.readline().strip()
    if not code:
        print("No authorization code on stdin.", file=sys.stderr)
        return 2
    flow = make_flow()
    flow.code_verifier = json.loads(PENDING.read_text())["code_verifier"]
    try:
        flow.fetch_token(code=code)
    except Exception as exc:  # oauthlib raises several types; never echo the code
        print(f"Code exchange failed ({type(exc).__name__}). Run 'gen' again for a new URL.", file=sys.stderr)
        return 4
    write_private(Path(TOKEN_CONFIG_PATH), flow.credentials.to_json())
    PENDING.unlink()
    print(f"Saved Colab CLI token at {TOKEN_CONFIG_PATH}; secret values were not displayed.")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "gen":
        raise SystemExit(gen())
    if command == "exchange":
        raise SystemExit(exchange())
    print(__doc__, file=sys.stderr)
    raise SystemExit(2)
