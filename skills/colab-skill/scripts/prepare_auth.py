#!/usr/bin/env python3
"""Install a Google Colab CLI OAuth cache or Google ADC user credential into a
private config directory. The credential can come from the skill bundle
(``<skill>/auth/``), from a file attached to the task, or already be present.

Secret values are never printed.

Exit codes:
  0  credential prepared (or already identical)
  2  invalid credential / I/O error
  3  no credential found (no argument given and nothing bundled)
  4  a different credential already exists; rerun with --replace if intended
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

TOKEN_URI = "https://oauth2.googleapis.com/token"
SKILL_DIR = Path(__file__).resolve().parent.parent
BUNDLED_DIR = SKILL_DIR / "auth"
# Searched in this order when no source is given. *.example files are never used.
BUNDLED_NAMES = (
    "token.json",
    "auth.json",
    "adc-credentials.json",
    "application_default_credentials.json",
)
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "colab-cli"
TARGET_NAMES = {"oauth2": "token.json", "adc": "adc-credentials.json"}


class CredentialConflict(Exception):
    pass


class CredentialNotFound(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and copy a Colab CLI OAuth cache or Google ADC authorized-user "
            "credential into a private local config directory. Without SOURCE, the "
            "credential bundled in the skill's auth/ directory is used. "
            "Secret values are never printed."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="Credential JSON file (default: the credential bundled in <skill>/auth/)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "oauth2", "adc"),
        default="auto",
        help="Credential format; auto detects Google ADC authorized_user files",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help=f"Private destination directory (default: {DEFAULT_CONFIG_DIR})",
    )
    parser.add_argument(
        "--bundled-dir",
        type=Path,
        default=BUNDLED_DIR,
        help=argparse.SUPPRESS,  # for tests
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing, different destination credential",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report which credentials exist (paths and formats only) and exit",
    )
    parser.add_argument(
        "--export-to",
        type=Path,
        metavar="DIR",
        help=(
            "Copy the prepared credential into DIR so the user can download it and "
            "build a private skill package. Use only on the user's explicit request."
        ),
    )
    return parser.parse_args()


def load_credentials(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as source_file:
            value = json.load(source_file)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read a valid credential JSON file: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError("Credential JSON must contain an object.")
    return value


def detect_mode(data: dict[str, Any], requested: str = "auto") -> str:
    """Validate the credential shape and return "oauth2" or "adc"."""
    detected = "adc" if data.get("type") == "authorized_user" else "oauth2"
    mode = detected if requested == "auto" else requested
    if mode == "adc" and data.get("type") != "authorized_user":
        raise ValueError("ADC mode supports only Google authorized_user credential files.")
    if mode == "oauth2" and data.get("type") == "authorized_user":
        raise ValueError("This is an ADC authorized_user file; use --mode adc.")
    if mode == "adc" and "token_uri" not in data:
        # gcloud-generated ADC files omit token_uri; Google's default applies.
        data = {**data, "token_uri": TOKEN_URI}
    required = ("client_id", "refresh_token", "token_uri")
    missing = [key for key in required if not isinstance(data.get(key), str) or not data[key]]
    if missing:
        raise ValueError("Credential JSON is missing required fields: " + ", ".join(missing))
    if data["token_uri"].rstrip("/") != TOKEN_URI:
        raise ValueError("Refusing a credential file with a non-Google OAuth token endpoint.")
    if mode == "oauth2" and not isinstance(data.get("client_secret"), str):
        raise ValueError("Colab CLI OAuth cache must include a client_secret field.")
    if "<" in data["refresh_token"]:
        raise ValueError("This looks like the placeholder example file, not a real credential.")
    return mode


def find_bundled(bundled_dir: Path) -> Path | None:
    for name in BUNDLED_NAMES:
        candidate = bundled_dir / name
        if candidate.is_file():
            return candidate
    return None


def secure_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError as exc:
        raise ValueError(f"Could not secure directory permissions: {path}") from exc


def write_private(data: dict[str, Any], target: Path) -> None:
    secure_dir(target.parent)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, prefix=".credential-", delete=False
        ) as temp_file:
            temporary_name = temp_file.name
            os.chmod(temporary_name, 0o600)
            json.dump(data, temp_file, ensure_ascii=False)
            temp_file.write("\n")
        os.replace(temporary_name, target)
        temporary_name = None
        os.chmod(target, 0o600)
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def same_grant(a: dict[str, Any] | None, b: dict[str, Any]) -> bool:
    return bool(a) and all(a.get(key) == b.get(key) for key in ("client_id", "refresh_token"))


def install(source: Path, requested_mode: str, config_dir: Path, replace: bool) -> tuple[str, Path, str]:
    """Returns (mode, target, action) where action is 'installed', 'replaced' or 'unchanged'."""
    data = load_credentials(source)
    mode = detect_mode(data, requested_mode)
    target = config_dir.expanduser().resolve() / TARGET_NAMES[mode]
    if source == target:
        os.chmod(target.parent, 0o700)
        os.chmod(target, 0o600)
        return mode, target, "unchanged"
    if target.exists():
        try:
            existing = load_credentials(target)
        except ValueError:
            existing = None
        if same_grant(existing, data):
            # The CLI rewrites token.json whenever it refreshes the access token,
            # so compare only the long-lived grant and keep the fresher file.
            os.chmod(target, 0o600)
            return mode, target, "unchanged"
        if not replace:
            raise CredentialConflict(
                f"A different credential already exists at {target}. Keep it, or rerun with "
                "--replace if it fails authentication or the user asked to switch accounts."
            )
        write_private(data, target)
        return mode, target, "replaced"
    write_private(data, target)
    return mode, target, "installed"


def describe(path: Path) -> str:
    try:
        return detect_mode(load_credentials(path))
    except ValueError as exc:
        return f"invalid ({exc})"


def status(config_dir: Path, bundled_dir: Path) -> int:
    bundled = find_bundled(bundled_dir)
    print(f"bundled: {bundled} [{describe(bundled)}]" if bundled else f"bundled: none in {bundled_dir}")
    config_dir = config_dir.expanduser()
    for mode, name in TARGET_NAMES.items():
        path = config_dir / name
        print(f"config {mode}: {path} [{describe(path)}]" if path.is_file() else f"config {mode}: none")
    return 0


def export(target: Path, export_dir: Path) -> Path:
    export_dir = export_dir.expanduser().resolve()
    export_dir.mkdir(parents=True, exist_ok=True)
    destination = export_dir / target.name
    write_private(load_credentials(target), destination)
    return destination


def main() -> int:
    args = parse_args()
    if args.status:
        return status(args.config_dir, args.bundled_dir)
    try:
        if args.source is not None:
            source = args.source.expanduser().resolve(strict=True)
            origin = "supplied file"
        else:
            found = find_bundled(args.bundled_dir)
            if found is None:
                raise CredentialNotFound(
                    f"No credential bundled in {args.bundled_dir}. Ask the user to attach one, "
                    "or use the Colab CLI remote OAuth flow."
                )
            source = found.resolve()
            origin = f"bundled {found.name}"
        mode, target, action = install(source, args.mode, args.config_dir, args.replace)
        exported = export(target, args.export_to) if args.export_to else None
    except CredentialNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except CredentialConflict as exc:
        print(str(exc), file=sys.stderr)
        return 4
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"{action.capitalize()} {mode} credentials from {origin} at {target}; secret values were not displayed.")
    if mode == "adc":
        print(f"For Colab commands, set GOOGLE_APPLICATION_CREDENTIALS={target} and use --auth=adc.")
    else:
        print("For Colab commands, use --auth=oauth2.")
    if exported is not None:
        print(f"Exported a copy to {exported}. It contains a refresh token; the user must keep it private.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
