# colab-skill

[English](README.md) | 日本語

Claude（Web / モバイル）や ChatGPT Work のサンドボックス環境から、公式の [Google Colab CLI](https://github.com/googlecolab/google-colab-cli) 経由で **Google Colab** を操作できるようにする Agent Skill です。GPU / TPU ランタイムでのスクリプト・ノートブック実行、ファイルのやりとり、実行ログの取得などをチャットから行えます。

AI のサンドボックス環境からはブラウザによる対面ログインができないため、以下の3通りの認証方法に対応しています。

1. **トークン同梱（推奨）**: `auth/token.json` を含めた zip を作成。一度アップロードすれば、以降すべてのチャットでそのまま使えます。
2. **チャットで都度添付**: トークンファイルをチャットに直接アップロード（同梱せずに単発で使いたい場合）。
3. **リモート OAuth 認証**: 認証 URL を開き、表示されたワンタイムコードをチャットに貼り付けて認証（手元にトークンファイルがない場合）。

## リポジトリ構成

```
skills/colab-skill/             # スキル本体（このフォルダを zip 化してアップロード）
  SKILL.md                      # スキルのプロンプト定義
  scripts/prepare_auth.py       # 認証ファイルの検証・配置（トークン漏洩防止対策済み）
  scripts/remote_login.py       # 複数ターンにまたがって動作するリモート OAuth 実装
  scripts/install_cli.sh        # Colab CLI の導入と既知の依存パッケージ不具合のワークアラウンド
  auth/token.json.example       # token.json の配置テンプレート（git 除外対象）
```

## 使い方 1: トークンなしで導入（リモート OAuth を利用）

トークンを含めず、`colab-skill` フォルダを zip に圧縮します。

```sh
cd skills
zip -r ../colab-skill.zip colab-skill -x 'colab-skill/auth/*.json'
# -> colab-skill.zip
```

> **Note:** Windows の標準機能（右クリック → *送る → 圧縮 (zip 形式) フォルダー*）など、どのアーカイブツールを使っても構いません（`auth/` 配下に `token.json.example` だけが含まれている状態にしてください）。

作成した zip を Claude または ChatGPT にスキルとして登録します。初回実行時にエージェントが認証 URL を提示してくれるので、ブラウザでログインして表示されたワンタイムコードを貼り付けてください。

## 使い方 2: トークン同梱で導入（自分専用パッケージ・推奨）

1. **Colab CLI のトークンを取得する**（PC: Linux / macOS / WSL 環境）:

   ```sh
   uv tool install google-colab-cli
   colab --auth=oauth2 sessions   # ブラウザが開くので一度ログイン
   ```

   トークンが `~/.config/colab-cli/token.json` に保存されます。

   > **PC 環境がない場合（スマホのみ等）:**
   > まず上記「使い方 1」のリモート OAuth で一度認証を通した後、チャット上で「Colabの認証情報を同梱用にエクスポートして」と指示してください。トークンファイルをダウンロードできます。

2. **プライベート用パッケージを作成する**
   取得したトークンをスキル内に配置して zip 化します。

   ```sh
   cp ~/.config/colab-cli/token.json skills/colab-skill/auth/token.json
   cd skills
   zip -r ../colab-skill.private.zip colab-skill
   # -> colab-skill.private.zip
   ```

3. **自分専用のアカウントにアップロードする**
   生成された zip を、**個人の** Claude / ChatGPT アカウントにスキルとして登録します。

   タスク実行時にエージェントが自動でパーミッション（`0600`）を設定してトークンを配置するため、以降は認証の手間なくすぐに Colab を操作できます。

## セキュリティに関する注意点

- **リフレッシュトークンの取り扱い**: 同梱するファイルにはリフレッシュトークンが含まれます。トークンがあれば誰でもあなたのアカウントで Colab を実行できてしまうため、トークン入りの zip は絶対に他人へ共有・公開したり、公開リポジトリにコミットしたりしないでください。
- **組織・チームアカウントでの公開範囲**: Team や Enterprise などの共有ワークスペースにスキルをアップロードすると、組織内のメンバーにトークンが見えてしまう恐れがあります。アップロード先の公開範囲を事前に確認してください。
- **チャット履歴への残留**: チャット経由でトークンをダウンロード（エクスポート）した場合、その会話履歴にファイルが残ります。不要になったら該当のチャットスレッドを削除することをおすすめします。
- **Git コミット前の確認**: `.gitignore` で `auth/*.json` や `*.zip` を除外設定していますが、念のためコミット前に `git status` で認証ファイルが含まれていないことを確認してください。
- **トークンが漏洩した場合**: 万が一トークンが流出した場合は、Google アカウントの [セキュリティ → サードパーティ製のアプリとサービスへのアクセス権](https://myaccount.google.com/connections) から該当の連携を解除（失効）し、パッケージを作り直してください。

## 動作要件

- Python 3.9 以上（サンドボックス内の補助スクリプト実行用）
- Google Colab CLI（サンドボックス内に未インストールの場合は、エージェントが自動でセットアップします）

## ライセンス

[MIT](LICENSE)
