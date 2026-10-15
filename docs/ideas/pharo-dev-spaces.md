# pharo-dev-spaces

## Problem Statement

Claude Code の各セッションが、互いに干渉しない使い捨ての Pharo イメージを即座に得られ、1日の成果（各リポジトリの develop ブランチ）を「テスト済みの翌日の派生元イメージ」に確実に畳み込めるようにするには？

## Recommended Direction

**固定スロット ＋ ロックファイル型スナップショット**。

並行数は 2〜3 なので、動的割り当ては行わず `slots/slot1..3`（SIS ポート 8087〜8089、8086 は単独利用用に空ける）を固定で持つ。スロットは `snapshots/current` のイメージをディレクトリごとコピーして作る使い捨て環境。VM は `plain-pharo/` のものを共有し（`plain-pharo/pharo <abs>/Pharo.image` で起動可能）、sources はシンボリックリンクで共有する。ディレクトリを分けるので `pharo-local/` もスロットごとに分離され、片付けは `rm -rf` で済む。agentfs / git worktree はイメージ分離には不要（ソース分離は別問題）。

MCP のポート切り替えは smalltalk-dev プラグインを変更せず、`claude --strict-mcp-config --mcp-config slots/slotN/mcp.json` で行う。`--strict-mcp-config` によってプラグイン由来の `smalltalk-interop`（8086 固定）も無効になることを検証済み（2026-10-12、Claude Code 2.1.296）。Pharo 側は `PHARO_SIS_PORT` を環境変数で渡して headless 起動するだけで、SIS が起動時に自動で listen する（`SisServer class >> startUp:` と `SisSettings >> port` で確認済み）。

スナップショットの実体は git 管理する JSON マニフェスト（派生元 + ビルドモード + 各リポジトリの `origin/develop` の SHA + テスト結果）で、イメージは再生成可能なキャッシュとして `archives/` に tar で積む（git 管理外）。

ビルドは2つのモードに分ける。どちらも Baseline 経由（Metacello `tonel://<展開先>/<srcDir>`）でロードし、違いは元イメージだけである。パッケージのロード順、プラットフォーム別の指定（`for: #pharo do:`）、`includes:` は Metacello に任せる（以前は Baseline を Python でパースしていたが、Stick の `includes:` に対応できなかったため 2026-10-15 にやめた）。
- **full（初回・作り直し）**: dev-base を元にロードする。リネームや削除の残骸も残らない。
- **incremental（毎日、既定）**: 前日の `current` を元にロードする。展開先は毎回新しい一時ディレクトリなので、古いソースがキャッシュされて「最新化されない」問題は起きない。

### レイアウト

```
pharo-dev-spaces/
  plain-pharo/                 # VM + plain image（VM は全スロットで共有）
  dev-base/                    # plain + SIS + AgenticBrowser（依存ライブラリもここで入れる）
  projects.json                # スナップショット対象（手動登録、リポジトリ順 = ロード順）
  mcp_others.json              # スロットの mcp.json にマージする、smalltalk-dev 以外の MCP サーバー
  snapshots/
    current/                   # 最新スナップショットのイメージ（スロットの派生元）
    2026-10-12.json            # git 管理: base, 各 repo の develop SHA, テスト結果
  archives/2026-10-12.tar.zst  # git 管理外
  slots/slot{1,2,3}/           # Pharo.image/.changes, sources へのリンク, mcp.json, pid
```

### コマンド（MVP）

| コマンド | 動作 |
|---|---|
| `setup_plain --version 140` | `curl https://get.pharo.org/64/140+vm \| bash` で plain-pharo/ を作る |
| `prepare_dev_base` | plain をコピーし、Metacello で SIS + AgenticBrowser（+ プロジェクトの外部依存）をロードし、save & quit した後に `pharo-local/iceberg` を削除する（full ビルドと共通の後始末） |
| `slot N reset` | `snapshots/current`（無ければ dev-base）を `slots/slotN/` にコピー |
| `slot N up` / `slot N down` | `PHARO_SIS_PORT=808(6+N)` で headless 起動 / 停止（pid 管理） |
| `slot N status` / `list-slots` | スロット（`list-slots` は全スロット）のポート、イメージの有無、起動状態、pid を JSON で出力する。`running` が false のスロットが空き |
| `slot N claude` | smalltalk-dev 用の設定（ポート 808(6+N)）と `mcp_others.json` をマージして mcp.json を生成し、`claude --strict-mcp-config --mcp-config slots/slotN/mcp.json` |
| `add_project <repoPath>` | `.project` の `srcDirectory` と `BaselineOfXxx` の名前から、`projects.json` のエントリの雛形を出力する |
| `build_snapshot [--full]` | 下記 |

### projects.json（案）

```json
[
  { "repository": "~/git/myapp", "baseline": "MyApp", "srcDir": "src", "groups": ["default"] }
]
```

配列の順序（リポジトリ順）がそのままロード順になる。

### build_snapshot の流れ

| 手順 | incremental（既定） | `--full` |
|---|---|---|
| 1. 元イメージ | `snapshots/current` をビルド用ディレクトリにコピー | `dev-base` をコピー |
| 2. ソース取得（共通） | 各リポジトリで `git fetch` → `origin/develop` の SHA を取得 → `git archive <sha> <srcDir>` で一時ディレクトリに展開（作業中の worktree やブランチには触れず、Iceberg も関与しない） | 同左 |
| 3. ロード（共通） | 各リポジトリを記述順に Metacello `tonel://<展開先>/<srcDir>` + `baseline:` + `groups` でロード（本体はキャッシュされないが、`github://` などの外部依存は Iceberg 経由で `pharo-local/iceberg` にキャッシュされる） | 同左 |
| 4. テスト（共通） | `srcDir` 直下のパッケージ（`BaselineOf*` を除く）のうち、イメージにロードされたもののテストを実行 | 同左 |
| 5. 確定（共通） | 全テスト成功なら save & quit。ここでビルド用ディレクトリの `pharo-local/iceberg` を削除する。その後、`current` を差し替え、JSON（mode、base、SHA、結果）を書き、tar を `archives/` に置く。失敗時は `current` を更新しない | 同左 |

- ビルド中は `PHARO_SIS_PORT` を専用ポートに設定し、8086 との衝突を避ける
- 依存の追加やパッケージ構成の変更は incremental でも Metacello が反映する。パッケージやクラスの削除・リネームは反映されないので、当面は手動で `--full` を実行する運用とする（イメージ側で事前にリネームする方式は将来の検討事項）

## Key Assumptions to Validate

- [x] **`--full` で Metacello の `tonel://` / `gitlocal://` を使ってローカルのソースからロードできる。** Historia で確認済み（2026-10-13）。外部依存（Stick、RediStick）は Iceberg 経由でロードされ `pharo-local/iceberg` にキャッシュが残るため、full ビルドの後始末で削除する。削除しても、Metacello の GUI に「local repository missing」と表示されるだけで無害
- [x] **Baseline を Metacello `tonel://` で再ロードしたとき、パッケージ内で追加・削除されたメソッドがイメージに反映される。** 2026-10-15 確認済み（`tests/test_snapshot.py` の統合テスト）（クラスの削除やリネームは `--full` で対処する前提）
- [ ] **incremental を続けても、`--full` と同じテスト結果になる。** 定期的に `--full` を実行して照合する
- [x] **コピーしたイメージを別ディレクトリから起動しても、sources のシンボリックリンクで正常に動く。** 2026-10-13 確認済み（`tests/test_slot.py` の統合テスト）
- [x] **SIS のポートが永続化された設定で上書きされない。** 2026-10-13 確認済み（Metacello でロードしたイメージを保存した後でも、`PHARO_SIS_PORT` が効く）。`apply_settings` で `#port` を保存しないよう注意する
- [x] **全パッケージを毎回再ロードしても許容時間内に収まる。** Historia（9パッケージ、46テスト）で、incremental 16.5秒 / full 21秒（2026-10-13、incremental が TonelReader だった時点）。対象が増えたら再計測する

## MVP Scope

**含む**: 上記のコマンド（shell + 必要に応じて最小限の python）、`projects.json`、`add_project`、`mcp_others.json` のマージ、スナップショット JSON、ビルド用の `.st` スクリプト（Metacello でのロード、テスト）。

**含まない**: 下記の Not Doing。

## Not Doing (and Why)

- **agentfs / git worktree によるイメージ分離**：ディレクトリコピーで足りる。60MB×3 では CoW の利点がない
- **Docker 方式**：並行開発には重く、OpenCode 用である
- **動的なポート / スロット割り当て**：並行数 2〜3 なら固定で十分
- **smalltalk-dev プラグインの改修**：Claude 専用にしたくない。`--strict-mcp-config` で回避できる
- **Baseline の Python でのパース**：プラットフォーム別の指定や `includes:` まで再現するのは複雑すぎる。ロードは Metacello に任せる
- **incremental でのパッケージ・クラスの削除やリネームへの自動追従**：`--full` で対処する
- **Metacello の登録や `MCRepositoryGroup` の後始末**：一時ディレクトリを指す `tonel://` が残るが無害
- **変更パッケージの差分判定**：計測して遅かったら導入する
- **イメージ側でクラスを事前にリネーム / 削除してからのロード**：実装が複雑になるので、当面は `--full` で代替する
- **スキル化（エージェントの自律構築）**：CLI が固まってから。MCP のポートはセッションの途中で変えられないため、「スロットを先に用意し、その後 claude を起動する」順序が前提になる
- **macOS 対応・汎用化**：当面は自分専用（WSL/Linux）

## Open Questions

- `develop` はローカルのブランチと `origin/develop` のどちらを正とするか（他マシンでの push を含めるなら、`git fetch` してから `origin/develop` を使う）
  - origin/develop
- `projects.json` にはリポジトリ単位で `srcDir` だけを書き、配下の全パッケージを自動検出するか、パッケージを明示的に列挙するか（DRY 的には自動検出 + 除外リストを推奨）
  - srcDirと除外が便利だがロード順に不安がある
  - 必ず記述順にロードする仕様になっていると依存の問題もシンプルになる
    - その場合BaselineOfXxxから、projects.jsonのひな形を作成するツールがあると良い
      - https://github.com/mumez/smalltalk-dev-plugin/blob/develop/skills/st-import/SKILL.md
  - 通常は多少順番が違っても一時的にクラスがUndefinedになるだけで問題はないが、存在しないスーパークラスを指定したクラスの定義はロードに失敗する
  - 前日のcurrentからのロードの場合は問題になりにくい (すでにクラスがあるので)
  - dev-baseから初回のsnapshotを作り直す場合はBaseline経由がシンプルかも (その後は st-import と同じ仕組みで良い)
    -　Baselineで作成した場合は pharo-local/iceberg も削除しておくのが安全
- テスト対象は「ロードした全パッケージ」で良いか（時間がかかる / 不安定なテストを除外する仕組みが要るか）
  - 全パッケージが対象で良い
- スロットの mcp.json に含める、smalltalk-dev 以外の MCP サーバー（zvec_grep、chrome-devtools など）の一覧
  - mcp_others.json など、別ファイルをもとにマージできると良い
- パッケージのリネーム/削除、クラスのリネーム/削除について
  - リネーム/削除があった場合、旧スナップショットイメージには旧パッケージやクラスが残っているため単純ロードでは追加になってしまう
    - パッケージについては空なので無害ではある
    - クラスは事前に消す方が良い
      - https://github.com/mumez/smalltalk-dev-plugin/blob/develop/skills/smalltalk-developer/references/best-practices.md#rename-in-the-smalltalk-image-before-importing
    - 実装が複雑になるので、まずは手動でdev-baseから作り直す運用も許容する　(その場合もbuild_snapshotのオプション指定で簡単に作成できると良い。元イメージが前日のcurrentから、dev-baseになり、BaselineOfXXXによるビルドになる)
