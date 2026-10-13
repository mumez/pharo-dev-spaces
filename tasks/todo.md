# TODO: pharo-dev-spaces

設計と前提は `tasks/plan.md` と `docs/ideas/pharo-dev-spaces.md` を参照。

- ユニットテスト: `uv run pytest`
- 統合テスト（実際の Pharo を起動）: `uv run pytest -m pharo`

---

## Task 1: CLI の骨格、`setup-plain`、`run_pharo`

**Description:** `git init`、uv プロジェクト、`pds` CLI のサブコマンドの枠を作る。`pds setup-plain --version 140` で `plain-pharo/` を作り（get.pharo.org を呼び出す）、Pharo を timeout 付きで `PHARO_SIS_PORT` を渡して実行する共通関数 `run_pharo` を用意する。

**Acceptance criteria:**
- [x] `pds setup-plain --version 140` で `plain-pharo/` に image、VM、sources ができる。既に存在する場合は `--force` が無ければ中断する
- [x] `run_pharo` で `Transcript`（標準出力）に書くだけの `.st` を実行でき、終了コードと timeout が扱える
- [x] `.gitignore` で生成物を除外し、`snapshots/*.json` は追跡対象にする

**Verification:**
- [x] `uv run pytest`（コマンド組み立て、環境変数、timeout のユニットテスト）
- [x] `uv run pytest -m pharo`（`run_pharo` で `1+1` を JSON に書いて読む）

**Dependencies:** なし

**Files likely touched:** `pyproject.toml`、`pds/cli.py`、`pds/pharo.py`、`tests/test_pharo.py`、`.gitignore`

**Estimated scope:** M

---

## Task 2: `prepare-dev-base`

**Description:** `plain-pharo/` の image と changes を `dev-base/` にコピーし（sources はシンボリックリンク）、SIS（`PharoSmalltalkInteropServer`、`github://mumez/PharoSmalltalkInteropServer:main/src`）と AgenticBrowser（`AgenticBrowser`、`github://mumez/pharo-agentic-browser:main/src`、group `'all'`）を Metacello でロードして save & quit する。プロジェクトの外部依存はここでは入れない（full ビルドの Baseline が解決する）。その後 `remove_iceberg_cache` で `pharo-local/iceberg` を削除する。

**Acceptance criteria:**
- [ ] `pds prepare-dev-base` で `dev-base/Pharo.image` ができ、`pharo-local/iceberg` は残らない
- [ ] `PHARO_SIS_PORT=8099` で dev-base を起動すると SIS がそのポートで応答する（`#port` が永続化されていない）
- [ ] ロードに失敗したら非ゼロで終了し、`dev-base/` は作りかけの状態で残らない

**Verification:**
- [ ] `uv run pytest`（コピーやシンボリックリンクの作成、iceberg の削除のユニットテスト）
- [ ] 手動: `curl localhost:8099/list-packages` に `Sis-Core` が含まれる

**Dependencies:** Task 1

**Files likely touched:** `pds/dev_base.py`、`pds/image_dir.py`（コピー、リンク、iceberg 削除の共通処理）、`pds/st/prepare_dev_base.st`、`tests/test_image_dir.py`

**Estimated scope:** M

---

## Task 3: `slot reset / up / down`

**Description:** `slot reset N` で `snapshots/current`（無ければ `dev-base`）を `slots/slotN/` に作り直す。`slot up N` は `PHARO_SIS_PORT=8086+N` でバックグラウンド起動して pid を保存し、`slot down N` で停止する。

**Acceptance criteria:**
- [ ] N は 1〜3 のみ受け付け、ポートは 8086+N
- [ ] 起動中のスロットは reset を拒否する（先に down が必要）
- [ ] slot1〜3 を同時に起動でき、互いに独立している（片方で定義したクラスが、もう片方に存在しない）

**Verification:**
- [ ] `uv run pytest`（ポート計算、派生元の選択、pid の扱いのユニットテスト）
- [ ] `uv run pytest -m pharo`（2スロットを同時に起動し、SIS の eval で独立性を確認。`get-method-source` でソースが読めること＝sources リンクの前提も確認）

**Dependencies:** Task 2

**Files likely touched:** `pds/slot.py`、`pds/image_dir.py`、`tests/test_slot.py`

**Estimated scope:** M

---

### Checkpoint A
- [ ] `uv run pytest` と `uv run pytest -m pharo` が通る
- [ ] Key Assumptions の「sources のシンボリックリンク」と「`#port` が永続化されない」を one-pager でチェック済みにする
- [ ] 人間によるレビュー

---

## Task 4: `slot claude`

**Description:** smalltalk-interop（`SIS_PORT=8086+N`）と smalltalk-validator の定義に `mcp_others.json`（任意）をマージして `slots/slotN/mcp.json` を生成し、`claude --strict-mcp-config --mcp-config <file>` を exec する。

**Acceptance criteria:**
- [ ] `mcp_others.json` が無くても動く。同名のサーバーがある場合は smalltalk-dev 側を優先する
- [ ] スロットが起動していなければ警告する（起動はしない）
- [ ] 追加の引数は claude にそのまま渡す（`pds slot claude 2 -- --model opus` など）

**Verification:**
- [ ] `uv run pytest`（マージ結果と exec の引数のユニットテスト）
- [ ] 手動: `pds slot claude 2` で起動したセッションで eval `Smalltalk os environment at: 'PHARO_SIS_PORT'` が `8088` を返す

**Dependencies:** Task 3

**Files likely touched:** `pds/mcp_config.py`、`pds/slot.py`、`tests/test_mcp_config.py`

**Estimated scope:** S

---

## Task 5: `add-project`

**Description:** リポジトリの `.project`（`srcDirectory`）と `BaselineOf*.class.st` の `baseline:` を解析し、`package:` / `requires:` をトポロジカルソートして、projects.json のエントリ（BaselineOf を先頭に置く）を出力する。`--write` を付けると projects.json に追記する。

**Acceptance criteria:**
- [ ] `requires:` の順序制約を満たし、Baseline 外の依存（外部プロジェクト名）は無視する
- [ ] 循環依存はエラーにする
- [ ] `~/git/Historia` で妥当なエントリを出力する

**Verification:**
- [ ] `uv run pytest`（フィクスチャの BaselineOf を使ったパースとソートのテスト、循環依存のテスト）
- [ ] 手動: `pds add-project ~/git/Historia` の出力を確認する

**Dependencies:** Task 1

**Files likely touched:** `pds/baseline.py`、`pds/projects.py`、`tests/test_baseline.py`、`tests/fixtures/BaselineOfSample.class.st`

**Estimated scope:** M

---

## Task 6: ソース取得（fetch → SHA → git archive）

**Description:** projects.json の各リポジトリについて `git fetch` → `origin/develop` の SHA を取得し、`git archive <sha> <srcDir>` で一時ディレクトリに展開する。展開先とリポジトリごとの SHA を返す。

**Acceptance criteria:**
- [ ] 作業ツリーやカレントブランチを変更しない
- [ ] `origin/develop` が無い場合、fetch に失敗した場合は、リポジトリ名付きのエラーにする
- [ ] 戻り値に `{repository, sha, extractedSrcPath}` を含む

**Verification:**
- [ ] `uv run pytest`（tmp に bare リポジトリと clone を作り、develop を push したものを取得するテスト）

**Dependencies:** Task 1（Task 5 の projects.json の読み込みを共有）

**Files likely touched:** `pds/sources.py`、`pds/projects.py`、`tests/test_sources.py`

**Estimated scope:** S

---

### Checkpoint B
- [ ] `uv run pytest` が通る
- [ ] Claude Code から slot2 のイメージだけを操作できることを確認する
- [ ] Historia の projects.json を作成する
- [ ] 人間によるレビュー

---

## Task 7: `build-snapshot --full`

**Description:** dev-base を `snapshots/.build/` にコピーし、Task 6 で取得したソースを各リポジトリの記述順に Metacello `tonel://` + `baseline:` でロードする。全パッケージのテストを実行して結果を JSON で出力し、全テストが成功したら save & quit、iceberg の削除、`current` の rename 差し替え、`snapshots/YYYY-MM-DD.json`（mode、base、SHA、テスト集計）の書き出し、`archives/YYYY-MM-DD.tar.gz` の作成を行う。

**Acceptance criteria:**
- [ ] 成功時は `current`、manifest、archive が揃い、`current` に `pharo-local/iceberg` が無い
- [ ] ロードの失敗、またはテストが1件でも失敗した場合は `current` を変更せず、失敗したテストの一覧を表示して非ゼロで終了する
- [ ] ビルド中は専用ポート（8090）を使う

**Verification:**
- [ ] `uv run pytest`（manifest の生成、差し替え、失敗時に current が不変であることのユニットテスト。`run_pharo` はスタブ）
- [ ] 手動: Historia で `pds build-snapshot --full` を実行し、所要時間を記録する

**Dependencies:** Task 2、Task 6

**Files likely touched:** `pds/snapshot.py`、`pds/st/load_full.st`、`pds/st/run_tests.st`、`tests/test_snapshot.py`

**Estimated scope:** M

---

## Task 8: `build-snapshot`（incremental）

**Description:** `current` を元に、projects.json の packages の記述順で TonelReader による直接ロードを行う（SIS の `handleImportPackage:` と同じ方式）。テスト、確定、manifest、archive の処理は Task 7 と共通にする。

**Acceptance criteria:**
- [ ] `current` が無い場合は `--full` を案内して中断する
- [ ] manifest の mode が `incremental`、base が前回の manifest になる
- [ ] Historia で develop にメソッドの削除を入れた場合、incremental 後のイメージからそのメソッドが消えている（前提の検証）

**Verification:**
- [ ] `uv run pytest`（モードによる分岐のユニットテスト）
- [ ] 手動: Historia で incremental を実行し、所要時間を full と比較して記録する

**Dependencies:** Task 7

**Files likely touched:** `pds/snapshot.py`、`pds/st/load_incremental.st`、`tests/test_snapshot.py`

**Estimated scope:** S

---

## Task 9: incremental で Baseline の変化を検知する

**Description:** 前回の manifest の SHA と今回の SHA の間で `git diff --name-only` を取り、`BaselineOf*` 配下に変更があれば `--full` を案内して中断する。

**Acceptance criteria:**
- [ ] BaselineOf が変化していれば、ロード前に中断し、変化したリポジトリ名を表示する
- [ ] manifest に無いリポジトリ（新規追加）も `--full` を案内する

**Verification:**
- [ ] `uv run pytest`（tmp の git リポジトリで Baseline あり / なしの変更を作るテスト）

**Dependencies:** Task 8

**Files likely touched:** `pds/sources.py`、`pds/snapshot.py`、`tests/test_sources.py`

**Estimated scope:** S

---

### Checkpoint C（完了）
- [ ] `uv run pytest` と `uv run pytest -m pharo` が通る
- [ ] Historia で full → incremental → `slot reset 1` → `slot up 1` が通る
- [ ] Key Assumptions（ロード順、メソッド削除、所要時間）の結果を one-pager に反映する
- [ ] README-ja.md を実装に合わせて更新する
- [ ] 人間によるレビュー
