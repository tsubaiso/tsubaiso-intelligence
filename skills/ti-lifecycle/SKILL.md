---
name: ti-lifecycle
description: 顧客orgカスタマイズを「どの実装形態で・いつ作るか」で判断する開発運用ライフサイクル判断スキル（局面に依存しない）。TRIGGER when 個別要件を宣言的（Flow/入力規則/数式/承認）・Apex・外部スクリプト・製品機能化のどれで実装するかの選択、Anonymous Apex で作ってよいか（設計・開発フェーズ限定・sandbox/トライアル）／運用フェーズへ移行してよいかの判断、着手前ゲートの適用。DO NOT TRIGGER when 導入プロジェクト全体の工程進行は ti-onboarding、契約前の体験演出は ti-poc、メタデータ配備の機構そのものは ti-metadata、個別レコードの申請前・承認前チェックは ti-update。
version: 0.1.11
updated: 2026-08-19
---

# ti-lifecycle — 開発運用ライフサイクル判断

顧客orgのカスタマイズを「設計 → アジャイル構築 → 運用移行」へ導く**判断スキル**。**どう作るかの機構は持たず**、「どの実装形態で・いつ・どのフェーズで作るか」の判断に専念する。配備・投入・参照といった機構は能力スキルに委ね、決まった発火点でそれらを呼ぶ。

本書は薄い索引に徹する（詳細は必要な reference だけを読む方式）。判断の実体は各 reference にある。

## このスキルが持つもの・持たないもの

| 持つ（判断） | 持たない（機構＝委譲先） |
|---|---|
| 要件をどの実装形態で作るかの選択 | メタデータ配備の実行（取得→差分→検証→反映）＝ ti-metadata |
| Anonymous Apex の可否・運用移行の可否 | データ投入・移行の実行（関係保持・複製・前提準備）＝ ti-data-load |
| 着手前ゲートの適用・実務ノウハウをいつ呼ぶかの判断 | 参照先の有効条件チェックや作れない工程の検出ゲート＝ ti-reference |
| — | 個別レコードの申請前・承認前チェック＝ ti-update |

判断は本スキル、機構は能力スキル。この主従を崩さない。

## 発火点（いつ・どの reference を読むか）

| チェックポイント | 読む／呼ぶ | 渡す・確認するもの |
|---|---|---|
| **そのセッションで最初に TI のスキルを使う瞬間（依頼の内容を問わず・1 セッション 1 回）** | ti-core `references/version-freshness.md` | 同梱 `.claude-plugin/plugin.json` の版 |
| 要件をどの実装形態で作るか判断する瞬間（宣言的／Apex／外部／製品機能化） | `references/implementation-form.md` | 要件の性質・継続保守の主体 |
| Anonymous Apex で作ってよいか・運用へ移してよいか判断する瞬間 | `references/anonymous-apex-policy.md` | 現在のフェーズ・書込先org の種別 |
| アジャイル構築の着手前（フェーズ判定・実装形態の確定） | `references/dev-phase-playbook.md` | 現在のフェーズ・要件の性質 |
| 構築中に投入・複製・参照などの機構が要る瞬間 | 能力スキルの該当 reference（`dev-phase-playbook.md` が案内） | 適用対象・暫定/恒久の別 |
| org へ書き込む直前 | ti-core `references/safety-gate.md` | 対象・承認ドラフト（判断層からの記録を残す場合は、この時点で記録ペイロードを下書き＝2段トリガの第1段） |
| 現状仕様を往復で詰める瞬間 | ti-core `references/spec-roundtrip.md` | 実装形態の選択肢・前提 |
| org へメタデータを配備し成功した直後 | ti-spec-view の overlay 記録プロトコル（スキル名参照） | 配備したカスタマイズの対象・実装意図・author（実際のビルド主体）・確信度（＝2段トリガの第2段） |
| 実装形態が「外部スクリプト」で、AI 生成スクリプトが org へ書き込む | ti-core `references/safety-gate.md`（計画提示・ドライラン→人が承認）。機構は ti-local-automation | 対象・変更内容・本人権限内であること |

> 本文中の能力スキル名（ti-metadata・ti-reference・ti-core 等）は配置済みで、フォルダ名＝正準名として辿れる（ti-data-load は `tsubaiso-data-migration` からの改称先で、現在は配置済み）。配備成功直後の記録先 ti-spec-view はハードパスを張らずスキル名参照に留める（相手 references の物理構造に依存させない＝ダングリング回避）。本文が委譲する機構には未配置・未収録のものがありうる（書込前ゲートが `found:false` を返す等。書込前ゲートの実装範囲は `ti-reference references/write-index.md` が正本＝v12.1.0 で `function_only`・C5 参照フィルタ・auto_create 両方向を Atlas MCP `atlas_write_seam` に実装済み）。当該機構に当たったら機構を捏造せず人へ引き継ぐ（または ti-core Knowledge で代替する）。

## reference 索引

| reference | 何を定義するか |
|---|---|
| `references/implementation-form.md` | 要件→実装形態の判断（宣言的が第一選択／レコードトリガの手続き的自動化は Apexトリガー既定・Flow は例外／集計はバッチ／製品機能化は別扱い） |
| `references/anonymous-apex-policy.md` | Anonymous Apex をフェーズで切り替える判断（設計・開発は可・運用は禁止）、禁止の理由、運用移行のゲート |
| `references/dev-phase-playbook.md` | アジャイル構築の着手前2ゲートと、構築中に能力スキルの機構をいつ・なぜ呼ぶかの適用判断 |

## 原則

- **判断はここ、機構は能力スキル**。実装形態の選択・フェーズの可否・着手前ゲートは本スキルが持ち、配備・投入・参照の実行は能力スキルへ委ねる。
- **本書は薄く保つ**。判断の手順・基準は reference に置き、SKILL.md は索引に徹する。
- 出力に内部識別子（API名・SOQL・レコードID）を利用者向けに出さない（ti-core 群A の出力規律に従う）。
