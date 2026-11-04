# slot でリモートブランチを上書きロードする

## 目的

snapshot を土台に、指定したリポジトリだけを `origin/<branch>` で上書きした slot を作り、`build-snapshot` と同じ範囲のテストを実行する。slot 1 で RepoA の `feature/xxx` をレビューする、という使い方をこれで行う。

```bash
uv run pds slot 1 reset --ref RepoA:feature/xxx
uv run pds slot 1 up
```

## コマンド

`pds slot N reset` に次のオプションを足す。`up` と `gui` は起動のままにする。

| オプション | 意味 |
|---|---|
| `--ref NAME:BRANCH` | 繰り返し指定できる。snapshot をコピーしたあと、そのリポジトリを `origin/BRANCH` で上書きロードする。渡した集合が slot の保存済み ref 全体になる |
| `--load` | `slots/slotN/refs.json` に保存済みの ref で、同じ上書きを行う |
| `--test` / `--no-test` | 上書きのあと、プロジェクトのテストを実行する。省略したときは実行する |
| `--clear-refs` | 保存済み ref を捨て、snapshot（無ければ dev-base）のクリーンなコピーに戻す |

`--ref` を付けた時点で上書きする。`--ref` と `--load` を同時に付けたときは、`--ref` の集合を使う。

### 組み合わせ

| コマンド | イメージ | `refs.json` | テスト |
|---|---|---|---|
| `reset` | 今どおりのコピー | 残す | しない |
| `reset --no-test` | 今どおりのコピー | 残す | しない |
| `reset --ref RepoA:feature/xxx` | 上書き | この 1 件に置き換える | する |
| `reset --ref RepoA:feature/xxx --ref RepoB:feature/yyy` | 両方を上書き | この 2 件に置き換える | する |
| `reset --ref RepoA:feature/xxx --test` | 上書き | 置き換える | する |
| `reset --ref RepoA:feature/xxx --no-test` | 上書き | 置き換える | しない |
| `reset --load` | 保存済み ref で上書き | 内容は維持する | する |
| `reset --load --no-test` | 保存済み ref で上書き | 内容は維持する | しない |
| `reset --clear-refs` | クリーンなコピー | 削除する。最初から無ければ成功のまま | しない |

次は実行前に拒否する。イメージも `refs.json` も変えない。stdout には JSON を出さず、stderr に `pds: ...` を出して終了コード 1 にする。

- slot が起動中。メッセージは今の reset と同じく、`down` を案内する。
- `--test` を、`--ref` も `--load` も無いコマンドに付けた。
- `--clear-refs` を `--ref` または `--load` と同時に付けた。
- `--load` のときに `refs.json` が無い。
- `--ref` が `NAME:BRANCH` ではない、`NAME` か `BRANCH` が空、同じリポジトリを二度指定した。
- `NAME` が `st-projects.json` の 0 件または複数件に当たる。
- `refs.json` の形が下記のスキーマと違う、または `repository` が `st-projects.json` に無い。

`--test` の省略と、明示した `--test` は実装で区別する。argparse では `BooleanOptionalAction` のデフォルトを `None` にし、`None` と `--test`（`True`）は上書き時にテストを実行する。`--no-test` は実行しない。`None` のまま上書きしない reset は、今までどおりテストしない。

## 上書きの中身

土台は `snapshots/current` だけにする。イメージが無いときは置き換えを行わず、終了コードの節にある `loaded: false` の JSON で返し、`pds build-snapshot --full` を案内する。引数なしの `reset` は、今どおり snapshot が無ければ dev-base をコピーする。

手順は incremental な `build-snapshot` のロードと同じ仕組みに乗せる。

1. `st-projects.json` の該当リポジトリだけを `git fetch origin <branch>` し、`origin/<branch>` の `srcDir` を archive する。作業ツリーは checkout しない。
2. `snapshots/current` を slot へコピーする。
3. そのリポジトリだけを、既存の `load_baselines.st` で Metacello `get` + `load` する。baseline、`srcDir`、groups は `st-projects.json` のまま使う。
4. 指定しなかったリポジトリは再 fetch も再ロードもしない。イメージには、snapshot を作ったときのコードが残る。各リポジトリの snapshot 元ブランチは、`st-projects.json` の `branch`（省略時は `develop`）である。
5. Pharo は 1 回だけ起動する。スクリプトは対象リポジトリのロードに続けて、テストするときだけ `run_tests.st` を実行する。タイムアウトと SIS ポートは `build-snapshot` と同じ（3600 秒、8096）にする。このポートが使用中のときも、イメージは置き換えない。
6. プロセスの save は、そのスクリプトの終了時に行う。スクリプトが終了し、テストするときは結果ファイルもある、というときだけ iceberg のキャッシュを消してから staging を slot に昇格する。

`BRANCH` は origin 上のブランチ名とする。`--ref` でも `refs.json` の `ref` でも、`origin/` 付きのときはその接頭辞を外して同じブランチとして扱う。SHA や、ローカルにしか無いブランチは対象にしない。

`NAME` は次の順で、先に一意に決まったほうを採用する。

1. `baseline`
2. リポジトリパスのディレクトリ名
3. リポジトリの絶対パス

### テストの範囲

`build-snapshot` と同じにする。`st-projects.json` の各 `srcDir` 直下のパッケージディレクトリのうち、イメージにロードされているものを実行する。`BaselineOf*` とドットで始まるディレクトリは除く。SIS と AgenticBrowser のテストは含めない。

パッケージ名の集め方は次のとおり。

- 上書きしたリポジトリは、今回 fetch した `srcDir` から集める。
- それ以外は、最新の `snapshots/<date>.json` に記録されたそのリポジトリの `sha` を `git archive` して集める。`origin/<branch>` を取り直さない。
- マニフェストに `sha` が無い、オブジェクトがローカルに無い、または `st-projects.json` のリポジトリがマニフェストに無いときは、イメージを置き換えずに失敗する。

テストが失敗しても、ロード済みのイメージは slot に残す。snapshot は失敗時に `snapshots/current` を更新しないが、slot は失敗の中身を `up` や `gui` で見るための場所なので、ここは snapshot と違える。失敗は終了コード 1 と JSON の `tests` で表す。

## 設定ファイル

`slots/slotN/refs.json` は、その slot が次の `--load` で使う ref を覚えるファイルである。`ports.json` と同じく、reset をまたいで残す。`st-projects.json` とはマージしない。

```json
[
  {"repository": "/home/me/git/RepoA", "ref": "feature/xxx"}
]
```

- 要素は `repository` と `ref` だけを持つ。未知のキーは拒否する。
- `repository` は `st-projects.json` に書いた絶対パスと一致させる。
- `ref` は `origin/` を付けないブランチ名にする。
- SHA はここに書かない。実際にロードした SHA は `origin.json` に書く。
- `--ref` でロードに成功したとき、このファイルを渡した集合で置き換える。テストが失敗していても、イメージにはその ref が入っているので更新する。
- fetch や Metacello が失敗したときは更新しない。
- `--load` はファイルを読み直して fetch する。ブランチが進んでいれば新しい SHA をロードする。ファイルの内容は変えない。
- 直接編集してから `--load` してよい。
- `--clear-refs` の成功時だけ削除する。置き換えに失敗したときは残す。

## 記録と status

引数なしの `reset` が書く `origin.json` は、今の形のままにする。

```json
{"source": "snapshots/current", "snapshot": "2026-11-04", "builtAt": "2026-11-04T09:00:00"}
```

上書きに成功したときだけ `refs` を足す。

```json
{
  "source": "snapshots/current",
  "snapshot": "2026-11-04",
  "builtAt": "2026-11-04T09:00:00",
  "refs": [
    {
      "repository": "/home/me/git/RepoA",
      "baseline": "RepoA",
      "ref": "feature/xxx",
      "sha": "abcdef"
    }
  ]
}
```

`ref` は `origin/` を付けない。`sha` はこの実行で archive したコミットである。

テストを実行したときは、結果を `slots/slotN/tests.json` に書く。中身は snapshot マニフェストの `tests` と同じで、`run`、`passed`、`failures`、`errors` を持つ。Pharo が書き出す一時ファイルは読み取ったあと削除する。`tests.json` は reset をまたいで残さない。`--no-test` のときは作らない。

`pds slot N status` と `pds list-slots` は、今のフィールドに加えて常に次を返す。

- `savedRefs`: `refs.json` の配列。ファイルが無ければ `[]`。
- `tests`: `tests.json` のオブジェクト。ファイルが無ければ `null`。

イメージに載っているブランチは `origin.refs` である。次の `--load` が使う記憶は `savedRefs` である。クリーンな reset のあとは、`origin` に `refs` が無く、`savedRefs` に前回の指定が残る。

## 終了コードと stdout

引数なしの `reset`、`--no-test` だけの `reset`、`--clear-refs` は、今どおり成功時は stdout に何も出さない。終了コードは 0。

`--ref` または `--load` を付けた実行は、成功でも失敗でも stdout に JSON を 1 つ出す。

ロードでき、テストを省略したか全件成功したときは終了コード 0。

```json
{
  "slot": 1,
  "loaded": true,
  "origin": {
    "source": "snapshots/current",
    "snapshot": "2026-11-04",
    "builtAt": "2026-11-04T09:00:00",
    "refs": [
      {
        "repository": "/home/me/git/RepoA",
        "baseline": "RepoA",
        "ref": "feature/xxx",
        "sha": "abcdef"
      }
    ]
  },
  "savedRefs": [
    {"repository": "/home/me/git/RepoA", "ref": "feature/xxx"}
  ],
  "tests": {
    "run": 120,
    "passed": 120,
    "failures": [],
    "errors": []
  }
}
```

`--no-test` のときは `"tests": null`。`failures` と `errors` がどちらも空なら、`run` が 0 でも成功とする。

テストが失敗したときは、同じ形の JSON を出して終了コード 1 にする。stderr には `pds: <失敗数> of <run> tests failed` を出す。失敗数は `failures` と `errors` の件数の和である。イメージは残し、`tests.json` も残す。

fetch、archive、マニフェストの SHA 不足、`snapshots/current` の不在、ビルド用ポートの使用中、Pharo が結果ファイルを書かずに失敗した場合は、イメージも `refs.json` も置き換えずに、次の JSON と終了コード 1 を返す。stderr にも同じ `error` を `pds: ...` として出す。

```json
{"slot": 1, "loaded": false, "error": "RepoA: git fetch origin feature/xxx failed: ..."}
```

## パッケージ構成が変わるブランチ

制限は incremental な `build-snapshot` と同じにする。メソッドの変更と、baseline が追加するパッケージや依存は載る。削除やリネームしたパッケージとクラスはイメージに残る。テストの一覧も、ブランチ側の `srcDir` から作るので、ブランチから消えたパッケージは実行しない。そのブランチは、この上書きでは扱い切らない。`build-snapshot --full` で snapshot を作り直す。

slot の中で `st-projects.json` と別ファイルをマージして dev-base から作り直す手順は持たない。

## 実装時に触る場所

- `pds/cli.py`: 上記のオプションと、上書き実行の終了コード。
- `pds/slot.py`: 上書き、`refs.json` の保持と削除、`origin.refs`、`tests.json`、`status` の `savedRefs` と `tests`。
- `pds/sources.py`: 既存の `fetch_branch_sha` と `extract_src_dir` を、指定ブランチに対して使う。
- `pds/st/load_baselines.st` と `pds/st/run_tests.st`: 今のテンプレートを、対象リポジトリとパッケージ一覧を変えて使う。
- `README.md` と `skills/pharo-dev-spaces/SKILL.md`: 上書きコマンド、`refs.json`、`status` の新しいフィールド、削除とリネームの制限を書く。
- ユニットテストで、フラグの組み合わせ、`NAME` の照合、`refs.json` の保持と置換、ロード失敗時にイメージが残ること、テスト失敗時にイメージが残って終了コードが 1 になること、指定外リポジトリをロードスクリプトに含めないこと、をカバーする。

## 対象外

- `up` や `gui` にテストを付けること。
- ローカルブランチ、未 push のコミット、作業ツリーの未コミット変更をロードすること。
- SHA を ref として指定すること。
- 指定しなかったリポジトリを、最新の `origin/<branch>` で再ロードすること。
- テスト失敗のとき、snapshot のようにイメージを捨てること。
