# colab-skill

English | [日本語](README.ja.md)

An Agent Skill for Claude (web / mobile) and ChatGPT Work to operate **Google Colab** via the official [Google Colab CLI](https://github.com/googlecolab/google-colab-cli). Run scripts and notebooks on GPU/TPU runtimes, transfer files, and fetch execution logs directly from your chats.

Since cloud AI sandboxes cannot open a browser for interactive OAuth consent, this skill supports three ways to authenticate:

1. **Bundled token (Recommended)**: Package `auth/token.json` inside the skill zip. Upload once, and it works seamlessly across all chat sessions.
2. **Attached to chat**: Upload your token file directly into a specific conversation for one-off use.
3. **Remote OAuth flow**: Generate an authorization URL and paste back the one-time code (useful when you don't have a token file handy).

## Repository layout

```
skills/colab-skill/             # The skill directory to zip and upload
  SKILL.md                      # Agent instructions and command reference
  scripts/prepare_auth.py       # Validates and sets up credentials (never logs secrets)
  scripts/remote_login.py       # Two-step remote OAuth (URL -> code) designed for multi-turn chats
  scripts/install_cli.sh        # Installs Colab CLI and patches known upstream dependency issues
  auth/token.json.example       # Template for token.json (git-ignored)
```

## Method 1: Install without credentials (Remote OAuth)

Create a zip archive containing the `colab-skill` folder without any sensitive credentials:

```sh
cd skills
zip -r ../colab-skill.zip colab-skill -x 'colab-skill/auth/*.json'
# -> colab-skill.zip
```

> **Note:** Any standard archive utility works (e.g. *Send to → Compressed folder* on Windows) as long as `auth/` contains only `token.json.example`.

Upload `colab-skill.zip` as a custom skill in Claude or ChatGPT. On first use, the agent will guide you through the remote OAuth flow by providing a sign-in URL and asking for the one-time code.

## Method 2: Install with a bundled credential (Private package, Recommended)

1. **Generate a Colab CLI token** on your local machine (Linux, macOS, or WSL):

   ```sh
   uv tool install google-colab-cli
   colab --auth=oauth2 sessions   # Opens a browser to sign in once
   ```

   The credentials will be stored at `~/.config/colab-cli/token.json`.

   > **No local machine? (Mobile only):**
   > Use Method 1 once via the remote OAuth flow, then ask the agent: *"Export Colab credentials for bundling"*. It will provide the file as a chat download.

2. **Build your private package**
   Copy the token into the skill folder and create a private zip archive:

   ```sh
   cp ~/.config/colab-cli/token.json skills/colab-skill/auth/token.json
   cd skills
   zip -r ../colab-skill.private.zip colab-skill
   # -> colab-skill.private.zip
   ```

3. **Upload to your personal account**
   Upload the private zip to *your personal* Claude or ChatGPT account.

   At the start of each task, the agent automatically configures the token with restricted permissions (`0600`) in `~/.config/colab-cli/`, allowing you to run Colab workloads immediately without prompts.

## Security notes

- **Refresh token sensitivity**: The bundled file contains a long-lived refresh token. Anyone with access to it can execute workloads under your Google account until revoked. Never share, publish, or commit packages containing your active token.
- **Team / Organization visibility**: Uploading custom skills to shared enterprise or team workspaces may make them accessible to other members. Ensure proper visibility settings before uploading private packages.
- **Chat history**: If you exported your token through chat, the file remains in your conversation history. Delete the chat thread after downloading if you do not want it stored on the platform.
- **Git hygiene**: `.gitignore` is pre-configured to ignore `skills/*/auth/*.json` and `*.zip` archives. Still, run `git status` prior to committing to ensure no credentials are staged.
- **Revoking access**: If a token is ever compromised, immediately revoke access under your Google Account (**Security → Third-party apps & services**) and recreate your private package.

## Requirements

- Python 3.9+ (pre-installed in standard sandbox environments)
- Google Colab CLI (automatically installed by the agent in the sandbox if missing)

## License

[MIT](LICENSE)
