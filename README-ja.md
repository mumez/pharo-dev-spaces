# pharo-dev-spaces

pharo の　AIコーディングエージェント用の開発用イメージ管理ツール群

## 課題

AIコーディングエージェントを使い、Pharo Smalltalk用の開発を行うためには、Pharo imageの管理が不可欠だが、適切なツールが存在しない。
https://get.pharo.org/ から、毎回 pharoのイメージをダウンロードし、https://github.com/mumez/PharoSmalltalkInteropServer を入れる手間が発生する。

## 目指すもの

- スクリプト起動で、Pharoのイメージを簡単にビルド、runできる
  - プレーンなPharoイメージ
  - SmalltalkInteropServer (SIS) と AgenticBrowser が入った状態の Pharoイメージのビルド
-　軽量な並行開発のサポート
  - AIエージェントが同時に異なるPharo Smalltalkイメージに対して作業できるようにする (git の worktreeのようなイメージ)
  - それぞれの作業結果を後でマージして、daily開発用スナップショットも作成できるようにする
- AIコーディングエージェント用スキル定義
　　- コーディングエージェント自身が自力でPharoの環境を構築できる
　　- 並行で作業できる
　　- 翌日用のdaily開発用スナップショットも作成できる

## 実装言語

python や shell script　を想定

## 対応コーディングエージェント

- Claude Code

## 動作

1. `setup_plain_pharo --version 140` で plain-pharo以下にPharo 1.4 の イメージ+vmを取得 (curl https://get.pharo.org/64/140+vm | bash)　(plainイメージ)
2. `prepare_dev_pharo` で plain-pharo の dev-pharo にコピーして、SmalltalkInteropServer (SIS) と AgenticBrowser が入った状態にする　(dev-baseイメージ)

1,2 までが　事前の準備。環境をリセットする時を除き、通常は以下3,4の繰り返し


3.　コーディングエージェントに　Pharo実行環境を派生 (git worktree や [agentfs](https://github.com/tursodatabase/agentfs) を使う想定)
　　- 並行に動作させるため、PHARO_SIS_PORTと、MCP の SIS_PORT を派生ごとに変更　
　　- 各派生で .mcp.json のSIS_PORTをオーバーライドする
　　- 各派生で Pharoをヘッドレスで起動(pharo-uiではなくpharoでの起動)、PHARO_SIS_PORTをオーバーライドしてSIS_PORTに一致させるようにする
　　- ソースコード自体はこのリポジトリでは管理しない (AgenticBrowserがtopicのworking directoryとして設定を持っている。ソースは分散して良い)
　　-　ここでのimageはdisposableであり、Pharo.image, Pharo.changesは保存されない 

4. daily開発用スナップショットの作成　(`build_daily_snapshot`)
　　- 1日の終わりに、作業全体をマージしたdaily開発用スナップショット用イメージを(trunkとなるPharo.image, Pharo.changes)作成する。その日に作業したパッケージをすべてロードし、テスト実行してOKであることが作成のための条件。
　　-　翌日以降の派生元として利用される　　
　　-　(スナップショットを一切作成せずに、毎回dev-baseイメージからパッケージ群をロードする方式もある. 対象ソースが大きくなるとロード時間がかかるようになるために避けたい)
　　-　(スナップショットはgitで管理すべき? 単純に日付がついたtarのアーカイブファイルとして、archivesに積んでいく?)

## 実現方式

　　- gitのworktree
　　　　- pharo起動のパスが変わってしまう
　　- agentfs run -session xxx bash で作業
　　　　- パスは変化しない
　　　　- agentfs への依存が増える
　　- Pharo.image, Pharo.changesの単純コピー
    - Pharo-xxx.image, Pharo-xxx.changes で作業
    - 最も単純
    - pharo起動のファイル名が変わる
    - pharo-local/* のキャッシュが共有されるので厳密な分離にはならない 
    - Pharo-xxx.image,changesを消すスクリプトが必要

## 代替案
　　- https://github.com/mumez/pharo-agentic-browser-opencode-docker のような Docker イメージを使う方式。
　　- 並行で開発するには多少ヘビー
　　- OpenCode用になる
