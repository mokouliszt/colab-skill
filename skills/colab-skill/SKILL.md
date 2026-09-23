---
name: colab-skill
description: Operate the user's Google Colab from hosted or headless AI sandboxes (Claude, ChatGPT and similar) using the official Colab CLI. Use whenever the user asks to do anything on Colab or on a cloud GPU/TPU through Colab: run Python scripts or notebooks, train or run models, install packages, upload or download files, check sessions or compute units, or stop runtimes. Authenticates with a credential bundled in the skill's auth/ folder, a credential file attached to the task, or the CLI's remote OAuth flow.
---

# Colab Skill

Use Google's `google-colab-cli` from a hosted or headless agent environment. Prefer the CLI over browser automation. The official CLI repository also ships a `colab-operator` skill; this skill adds sandbox-specific credential handling and user interaction rules.

All paths below are relative to this skill's directory. The skill directory may be read-only; never edit files inside it.

## Authentication

First run `python3 scripts/prepare_auth.py --status`. It lists the bundled credential and any credential already in the private config directory (paths and formats only). Then use the first source that applies:

1. **Existing private credential.** If `~/.config/colab-cli/token.json` (or `adc-credentials.json`) is already present and valid, use it as is.
2. **Credential bundled in the skill.** If the status shows a bundled file in `auth/`, run `python3 scripts/prepare_auth.py` with no argument. It validates the JSON and copies it to `~/.config/colab-cli/` with owner-only permissions. Running it again is harmless when the credential is unchanged.
3. **Credential attached to the task.** For a user-provided `token.json`, `auth.json` or `application_default_credentials.json` uploaded with the task, run `python3 scripts/prepare_auth.py <uploaded-file>`.
4. **Remote OAuth flow.** If no credential exists, run `python3 scripts/remote_login.py gen`. It uses the Colab CLI's own OAuth client, scopes and code-display page, prints an authorization URL, and keeps the PKCE verifier in a private file. Give the user the URL and ask them to sign in and paste back the authorization code shown by Google's page. Then pass the code on stdin only: `printf '%s\n' '<code>' | python3 scripts/remote_login.py exchange`. The token is saved at `~/.config/colab-cli/token.json`. Codes expire within minutes; on failure run `gen` again. Do not ask the user to paste credential JSON into chat. (The CLI's built-in prompt, triggered by any `colab --auth=oauth2` command without a token, works too, but only if the process survives until the user replies.)

`prepare_auth.py` exit codes: `0` prepared or unchanged, `2` invalid file, `3` nothing bundled, `4` a different credential already exists. On `4`, keep the existing credential unless it fails authentication or the user asked to switch accounts; then rerun with `--replace`.

Command format by credential type:

- Colab CLI OAuth cache (`token.json`): `colab --auth=oauth2 ...`. Prefer this format.
- Google ADC `authorized_user`: set `GOOGLE_APPLICATION_CREDENTIALS` to the path the helper printed and use `colab --auth=adc ...`. Use ADC only when the file was deliberately created for Colab CLI and its scopes have been checked.

If a Colab command fails with an authentication error (`invalid_grant`, `401`, revoked or expired token), move to the next source down the list, using `--replace` when installing it. When the bundled credential is the one that failed, tell the user it has been revoked or expired and that they need to rebuild their private skill package with a fresh credential.

Google's OAuth Device Authorization flow is not a compatible fallback for Colab CLI: Google limits that flow to a small scope set (OpenID/email/profile, Drive file/appdata, and YouTube), while the Colab CLI requests Colab-related authorization scopes. Google recommends the desktop OAuth flow for CLI tools, including headless CLIs. Do not implement a custom device flow by silently dropping scopes.

When collecting the one-time code, use a structured user-input tool only if it allows a free-form answer with **only “中止” as a preset choice**. If the tool requires additional preset answers, use a plain free-form prompt instead. Never offer the authorization code as a preset option.

### Credential handling rules

- Never print, `cat`, summarize, or quote any credential file, including the bundled one, or echo the authorization code back. Refer to credentials only by path and format.
- Never copy `auth/` contents or `~/.config/colab-cli/` into deliverables, logs, notebooks, or Colab sessions.
- **Export for bundling only on explicit request.** If the user asks to obtain their credential so they can bundle it into the skill (typical after the remote OAuth flow on mobile), run `python3 scripts/prepare_auth.py --export-to <user-download-dir>` (for example `/mnt/user-data/outputs` on Claude or `/mnt/data` on ChatGPT), deliver that file, and remind the user it contains a refresh token that stays usable until revoked.
- If the user wants to share this skill with other people, warn that a package with a bundled credential gives them access to the user's Google account for Colab; they should share a package without the credential.

## Operating Colab

Handle any Colab request the user makes (run code, train or infer on a GPU, process files, install packages, inspect or clean up sessions) by mapping it to CLI commands. Before the first non-trivial operation in a task, run `colab skill` once: it prints Google's official command guide matching the installed CLI version. Follow it for command details, but this skill's Authentication section overrides its authentication advice (use `--auth=oauth2` with the flows above; ignore its "prefer ADC" and browser-consent notes).

### Setup

1. Run `bash scripts/install_cli.sh` (then `export PATH="$HOME/.local/bin:$PATH"`). It installs `google-colab-cli` if missing and repairs a known upstream packaging bug: CLI 0.7.2 pins `jupyter-kernel-client==0.8`, which makes every `run`/`exec` fail with `AttributeError: ... 'JupyterSubprotocol'`. The script is idempotent; rerun it if that error appears.
2. Always pass `--auth=oauth2` (or `--auth=adc`) **before** the subcommand. The CLI's default provider has changed between releases.
3. Run `colab --auth=oauth2 sessions` first: it verifies authentication and shows sessions left running from earlier tasks. Reuse a matching session instead of allocating another one.

### Command map

| User intent | Command (prefix every one with `colab --auth=oauth2`) |
|---|---|
| Run one script and release the VM | `run [--gpu T4] script.py [args...]` (script stdout on stdout, CLI chatter on stderr, exit code propagated) |
| Start a working session | `new -s <name> [--gpu T4\|L4\|G4\|A100\|H100 \| --tpu v5e1\|v6e1] [--high-mem]` |
| Run code in a session | `exec -s <name> -f script.py` or pipe code on stdin; add `--timeout <sec>` for anything longer than 30 s (the default); `--env KEY=VALUE` for variables; `--output-image path.png` for plots |
| Run a notebook | `exec -s <name> -f nb.ipynb` → results in `nb_output.ipynb` next to the input |
| Shell commands on the VM | `echo "cmd" \| console -s <name>` (output contains terminal control bytes; filter with `grep -a`) or `exec` with `subprocess` |
| Install packages | `install -s <name> pkg1 pkg2` or `install -s <name> -r requirements.txt` |
| Move files | `upload -s <name> local /content/remote`, `download -s <name> /content/remote local`, `ls -s <name> [path]`, `rm -s <name> path` |
| Inspect | `sessions`, `status -s <name>`, `usage`, `log -s <name> [-n 20]` |
| Save history | `log -s <name> -o history.ipynb` (`.md`, `.txt`, `.jsonl` by suffix) |
| Open in the browser | `url -s <name>` and give the URL to the user |
| Recover | `restart-kernel -s <name>` for a wedged kernel; on "session not found" check `sessions` and create a new one |
| Release | `stop -s <name>` |

Key behavior:

- A session is a live Jupyter kernel on a billed VM. Variables and imports persist across `exec` calls in the same session until `stop` or `restart-kernel`, so build state incrementally.
- The working directory on the VM is `/content`; use absolute `/content/...` paths.
- Always name sessions with `-s`. Accelerator availability depends on the account; if `new` fails with an accelerator, report it and fall back to `--gpu T4` or CPU. An unrecognized `--gpu` value silently falls back to A100, so pass only the listed values.
- Ask before allocating `A100`, `H100` or a TPU unless the user named it, and mention that it consumes compute units faster.
- Never run `repl`, `console`, `auth` or `drivemount` interactively; they wait for a TTY. `repl`/`console` are fine with piped stdin. `auth` and `drivemount` need a human, so for Google Drive or GCS data prefer uploading files, or ask the user to use the browser session from `url`.

### Finishing

1. Stop every session created for the task, including after an error, unless the user asked to keep it. Report any session still running.
2. Deliver results: download outputs into the sandbox, then hand them to the user through the platform's file delivery (for example `/mnt/user-data/outputs` on Claude or `/mnt/data` on ChatGPT).
3. Never expose tokens, credential JSON or authorization codes in logs, notebooks or deliverables.

## Sandbox Limits

- The Google Colab CLI supports Linux and macOS; the official repository currently does not support Windows.
- A browser-based OAuth consent flow cannot be completed by the sandbox itself. Use a bundled or supplied credential, or the supported remote copy-paste flow.
- A sandbox that starts clean on each task loses `~/.config/colab-cli/`; the bundled credential is reinstalled from `auth/` each time.
- Keep file and notebook code cells free of secrets. Avoid interactive commands that wait for a terminal user, including `colab auth` and `colab drivemount`, unless the user explicitly needs them and the agent can safely relay their prompt.

## Official References

- Google Colab CLI and its `colab-operator` skill: https://github.com/googlecolab/google-colab-cli
- Google Colab CLI authentication design: https://github.com/googlecolab/google-colab-cli/blob/main/docs/04_automation_and_utility.md
- Google OAuth for limited-input devices and its allowed scopes: https://developers.google.com/identity/protocols/oauth2/limited-input-device
