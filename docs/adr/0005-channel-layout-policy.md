# 0005 — Channel layout policy

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

入力が常に stereo とは限らない: ASMR は通常 stereo だが、`5.1` `7.1` mixed の VOD コンテンツ、`mono` ボイスメモ、`downmix` 既済 stereo, `binaural dummy head` の `stereo` を含む。Balance 解析は L/R の存在を前提にする以上、`stereo` 以外の layout に対する明示的 policy を持たないとサイレントに破綻する。

`PyAV` の `frame.layout.name` は `"stereo"` `"mono"` `"5.1"` `"5.1(side)"` `"7.1"` `"downmix"` 等を返す。

## Decision

`stream.py` に layout dispatch を集約。default policy:

| layout | 振る舞い |
| --- | --- |
| `stereo` | そのまま L/R |
| `mono` | **skip + report に SKIPPED 記録** (balance 解析対象外) |
| `5.1`, `5.1(side)`, `7.1`, `7.1.4` | **ITU downmix で stereo 化**: `L_dn = FL + 0.707·FC + 0.5·(LS + LFE? 抑制) + ...` (BS.775-3 ITU downmix recommendation) |
| `downmix` (already-stereo) | そのまま L/R |
| その他不明 | warn + skip |

CLI flag `--layout-policy fl-fr | downmix | skip` で override 可:

- `fl-fr`: 5.1/7.1 の `FL` `FR` のみ抽出して 2 ch に
- `downmix`: ITU downmix (default)
- `skip`: stereo 以外は全 skip

## Consequences

- ✓ ASMR の実コンテンツ (主に stereo binaural、希に 5.1 映画コンテンツの ASMR 部分) を網羅。
- ✓ mono は最初から弾くので解析結果が無意味になることはない。
- ✗ ITU downmix の係数選択 (LFE をどう扱う等) はバリアントがあるが、`pyav.AudioResampler(layout="stereo")` の挙動に乗ることで処理系の選択を引き受ける (= 我々がオレ流 downmix を発明しない、`feedback_mainstream_packages` 整合)。
