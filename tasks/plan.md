# Implementation Plan: pharo-dev-spaces

## Overview

`docs/ideas/pharo-dev-spaces.md` の方針（固定スロット ＋ ロックファイル型スナップショット）を CLI として実装する。

1. plain → dev-base の準備
2. 固定スロット（slot1..3、ポート 8087〜8089）の使い捨て起動と Claude Code の接続
3. `origin/develop` からの daily snapshot ビルド（full / incremental）

## Architecture Decisions

- **Python 単一 CLI `pds`（uv 管理、pytest）**: AGENTS.md の「新機能はユニットテストでカバー」を満たしやすいので、shell ではなく Python にする。サブコマンドは one-pager のコマンド名に対応させる（`pds setup-plain`、`pds prepare-dev-base`、`pds slot reset|up|down|claude N`、`pds add-project`、`pds build-snapshot [--full]`）。
- **Pharo の実行は1つの関数に集約する**: `run_pharo(image, st_script, port, timeout)` が `plain-pharo/pharo <image> st --quit <script>` を `PHARO_SIS_PORT` 付きでサブプロセス実行する。prepare / build / テスト実行のすべてがこれを使う（DRY）。headless でハングした場合に備えて timeout を必須にする。
- **Smalltalk 側の処理は `.st` テンプレートとして分離する**（`pds/st/*.st`）。Python からはパスなどの変数を埋め込むだけにし、ロジックを Python の文字列に埋め込まない。
- **Pharo との結果の受け渡しは JSON ファイルで行う**: テスト結果などは `.st` が JSON ファイルに書き出し、Python が読む。標準出力のパースには頼らない。
- **アーカイブは `tar.gz`（Python の `tarfile`）にする**: `zstd` が未インストールのため、外部依存を増やさない（one-pager の `.tar.zst` から変更）。
- **iceberg の後始末は共通関数にする**: `remove_iceberg_cache(dir)` を prepare-dev-base と full ビルドの両方から使う。
- **テストは2層に分ける**: Pharo 不要のユニットテスト（既定で実行）と、`plain-pharo` を実際に起動する統合テスト（`-m pharo` で明示的に実行）。
- **dev-base には SIS と AgenticBrowser だけを入れる**: SIS は `PharoSmalltalkInteropServer` @ `github://mumez/PharoSmalltalkInteropServer:main/src`、AgenticBrowser は `AgenticBrowser` @ `github://mumez/pharo-agentic-browser:main/src`（group `'all'`）。プロジェクトの外部依存は full ビルドの Baseline が解決する。
- **git 管理を始める**: 現在は git リポジトリではない。Task 1 で `git init` し、`plain-pharo/`、`dev-base/`、`slots/`、`snapshots/current/`、`archives/` は ignore する（`snapshots/*.json` はコミット対象）。

## Dependency Graph

```
T1 骨格 + setup-plain + run_pharo
 ├── T2 prepare-dev-base ──┬── T3 slot reset/up/down ── T4 slot claude
 │                         │
 │                         └── T7 build-snapshot --full ── T8 incremental ── T9 Baseline 変化検知
 ├── T5 add-project（Pharo 不要） ─────────────┘ (T8)
 └── T6 ソース取得（Pharo 不要） ─────────┘ (T7)
```

T5 と T6 は Pharo に依存しないので、T2〜T4 と並行して進められる。

## Task List

### Phase 1: 土台とスロット（最もリスクの高い起動まわりから）
- [x] Task 1: CLI の骨格、`setup-plain`、`run_pharo`
- [ ] Task 2:（AgenticBrowser のロードが BLOCKED。SIS のみで暫定運用） `prepare-dev-base`
- [x] Task 3: `slot reset / up / down`

### Checkpoint A
- [x] ユニットテストが通る
- [x] slot1〜3 を同時に起動し、それぞれのポートの SIS が別イメージとして応答する
- [x] 前提「sources のシンボリックリンク」と「`#port` が永続化されない」を確認済み
- [ ] 人間によるレビュー

### Phase 2: Claude 接続とスナップショットの部品
- [x] Task 4: `slot claude`（mcp.json の生成とマージ）
- [x] Task 5: `add-project`（Baseline の解析 → projects.json の雛形）
- [x] Task 6: ソース取得（fetch → SHA → git archive）

### Checkpoint B
- [ ] `pds slot claude 2` で起動した Claude Code から、slot2 のイメージだけを操作できる
- [ ] Historia の projects.json エントリを `add-project` で生成できる
- [ ] 人間によるレビュー

### Phase 3: スナップショットビルド
- [x] Task 7: `build-snapshot --full`（end-to-end：テスト → 確定 → manifest → archive）
- [x] Task 8: `build-snapshot`（incremental）
- [ ] Task 9: incremental で Baseline の変化を検知して中断

### Checkpoint C（完了）
- [ ] Historia で full → incremental → slot reset → slot up の一連の流れが通る
- [ ] Key Assumptions のうち、ロード順・メソッド削除・所要時間を確認して one-pager に反映済み
- [ ] README-ja.md を実装に合わせて更新
- [ ] 人間によるレビュー

## Risks and Mitigations

| リスク | 影響 | 対策 |
|---|---|---|
| headless の `st` 実行中にエラーやデバッガが出てハングする | 高 | `run_pharo` で timeout を必須にする。`.st` 側は `on: Error do:` で JSON にエラーを書き、`Smalltalk exitFailure` で終了する |
| SIS のポートがイメージに永続化され、環境変数が効かない | 中 | Task 2 の検証で `SisSettings` の `#port` 未設定を確認する。設定されていたら prepare 時にクリアする |
| incremental で TonelReader の記述順ロードが失敗する（新しいスーパークラスなど） | 中 | 失敗時は `current` を更新しない。`--full` を案内する |
| full ビルドが外部依存の取得（GitHub）で失敗、または時間がかかる | 中 | ネットワークエラーとして明示的に報告する。`current` は更新しない |
| `current` の差し替え中に中断され、壊れた状態になる | 低 | 新しいディレクトリに作ってから rename で入れ替える |

## Open Questions

- AgenticBrowser の Metacello の指定（baseline 名、リポジトリ URL、ブランチ）
　　-　 AgenticBrowser,　github://mumez/pharo-agentic-browser:main/src, groupは 'all'
- CLI 名を `pds` で良いか
  - OK
- full ビルドで「プロジェクトの外部依存」は Baseline が解決するので、`prepare-dev-base` は SIS + AgenticBrowser だけで良いか（one-pager には「+ プロジェクトの外部依存」とある）
  - OK
