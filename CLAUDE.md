# CLAUDE.md — asmr-balance

このプロジェクトで Claude / AI agents が作業する際の方針。
project root に置いてあるので、リポジトリ内で claude を起動すると自動で context に入る。

## 最優先: アーキテクチャの美しさ

修正範囲の広さ・touch するファイル数・規模の大きさは **一切考慮しない**。
「最小差分」「既存に寄せる」を理由に醜い設計を選ばない。

具体的には:

- 重複コード (同じ frozenset が CLI と web に転がっている等) は必ず単一の正規モジュールに集約する。
  例: 受理する音声ファイル拡張子は `src/asmr_balance/source/audio_extensions.py:AUDIO_EXTENSIONS`
  にだけ存在し、CLI も Web もそこから import する。
- HTTP / use case / domain / DTO の層は躊躇わずに切る。`/api/inspect` ですら
  `web/routes/inspect.py` (HTTP adapter) / `web/use_cases/inspect.py` (orchestration) /
  `web/dto.py` (Pydantic 境界) に分離する。
- 大きな architectural decision は `docs/adr/` に ADR を残す
  (例: `0014-web-frontend-layering.md`)。
- Core API の互換性を壊さずに目的を達成できないと判断したら、core を直すこと自体を躊躇わない。

## 静かな失敗を避ける

進捗・状態は常に一目で分かる状態に保つ。

- ロギングは `structlog` (`src/asmr_balance/logging.py`) を経由する。`print()` は defensive grep
  (`just lint-defensive`) で禁止されている。
- scan job の per-file 進捗は SSE (`/api/scan/{id}/events`) でリアルタイム配信する。
- 致命的でない失敗 (decode error 等) は `MetricRecord` の `ScanStatus.ERRORED` として
  集約に残す。途中で爆発させず、ユーザーに必ず見せる。

## 警告は逃げず根本解決

- `# noqa`, `# type: ignore`, `--no-verify` で警告を黙らせない
  (`Justfile:lint-defensive` で grep されている)。
- 根本原因を直す。テストが落ちる場合はテストの方を直さず、まず production code を疑う。

## 開発・実行はすべて Docker 内

ホストに直接 Python / uv を入れない。すべて `docker compose run --rm app …` か
`just …` 経由。

- `just bootstrap` — docker build + uv sync + pre-commit/lefthook 設置
- `just dev` — fmt + lint-static + lint-defensive + typos + 高速テスト
- `just cov` — branch coverage 100% gate
- `just web` — Web UI 起動 (Phase 1)
- 詳細は `Justfile` と `README.md` 参照

## Web UI が正面玄関 (Phase 1+)

CLI も従来通り残すが、メインのインターフェースは Web。
`docker compose up web` → http://localhost:8000。
ASMR ファイルの drag & drop で 1 ファイル inspect、`/library` ボリュームマウントで
ライブラリ scan の両対応。

設計詳細: [docs/adr/0014-web-frontend-layering.md](docs/adr/0014-web-frontend-layering.md)

## 対象ユーザーは ASMR 視聴者 (制作者ではない)

このツールの対象は **これから ASMR を聴く人** であって、ASMR を制作する人ではない。
- diagnosis / insights の文言・recommendation はすべて視聴前に判断する人向けに書く。
  「DAW で…」「マイク位置…」「Limiter…」のような制作側 advice は NG。
- 代わりに「イヤホン推奨」「音量控えめに」「就寝視聴向き」「BGM 用途 OK」「binaural 視聴
  期待してたなら別音源を」のような視聴体験を左右する advice を提供する。
- 翻訳層は `src/asmr_balance/web/views/diagnosis.py` / `insights.py` の 2 ファイル。
  domain (rules) は pure なので触らず、view 層で listener-friendly に変換する。

## CI / hooks ミラー

`lefthook` (pre-commit / pre-push) と GitHub Actions ワークフローは同じ gate を実行する。
PR で初めて落ちる事故が起きないよう、ローカルで `just ci` が green になるまで push しない。
