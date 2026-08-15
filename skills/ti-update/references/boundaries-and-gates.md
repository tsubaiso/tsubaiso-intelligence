# boundaries-and-gates — 隣接スキルとの境界と委譲するゲート

ti-update は「稼働後のデータ（トランザクション＋マスタ）を整合を保って作り・更新し、承認を助ける」を持ち、**構造由来のゲート機構・初期一括/移行の投入機構・実装形態の可否判断は持たない**。それぞれ ti-reference／ti-data-load／ti-lifecycle にあり、本スキルは発火点でそれらを参照する。

## 隣接スキルとの境界（誤発火の決め手）

| 委譲先 | ti-update が持たないもの | 決め手 |
|---|---|---|
| **ti-data-load** | 初期一括ロード・移行・org間コピー・期首残高・dry-run→突合の投入/移行機構 | **機能種別＋量・局面**。初期・大量・移行は ti-data-load、稼働後の日常の作成・更新（トランザクション全般＋マスタ1件〜数件）は ti-update。同じ「マスタを作る」でも初期一括投入は ti-data-load、稼働後に1件追加は ti-update |
| **ti-reference** | 書込前の構造ゲート（作れない工程の検出・参照先の有効条件）／承認前チェックが引く集計・類似取引のレシピ | 構造由来の判定・集計は参照スキルの機構。ti-update は「何を書くか／何を点検するか」を持ち、集計手順・構造ゲートは呼ぶだけ |
| **ti-lifecycle** | 実装形態の可否判断（Flow/Apexで作るか・Anonymous Apex可否・運用移行可否） | 可否の対象＝実装形態なら ti-lifecycle、可否の対象＝個別レコードの業務妥当性なら ti-update。ともに「〜してよいか」だが対象が違う |
| **ti-report** | 帳票レイアウトへの出力（データ→PDF） | 出力方向＝ti-report、取込方向（文書→レコード作成）＝ti-update |
| **ti-onboarding／ti-poc** | 導入プロジェクトの工程進行／契約前の体験演出 | 進行・演出は層3。層3が入力支援・承認支援を要するときは本スキルの reference を発火点で参照する |

**ti-data-load 境界の一句**: 「初期・大量・移行なら ti-data-load、稼働後の日常の作成・更新なら ti-update」。この決め手で「マスタを作りたい」の誤発火を一意化する。

## 書込前構造ゲート（ti-reference へ委譲）

`function_only` 検出・参照先の有効条件フィルタ（作れない工程の検出・参照先の有効性）は **ti-reference の書込前ゲート（write-index 機能）が正本**。ti-update は**書込直前にこのゲートを参照経由で呼ぶ**（再実装しない＝機構の二重管理を避ける）。ゲートの詳細（構造由来の判定）はここに再掲せず、ti-reference へ委譲する。`function_only` 検出・C5 参照フィルタ・auto_create 両方向はいずれも Atlas MCP `atlas_write_seam` が判定する。ゲートが「判定不能／未収録（`found:false`）」を返したら捏造せず人へ引き継ぐ（正本は `ti-reference references/write-index.md`）。

> ti-reference は書込前ゲートの参照ファイル `references/write-index.md`（実体＝Atlas MCP `atlas_write_seam`）を持つ。書込スキルは書込直前にこの write-index.md を発火点で参照してゲートを呼ぶ（SKILL.md の二層注記と一致）。書くレコード自身の入力規則（VR）の充足は ti-update が書込前に検証する（`input-support.md`）。両者は射程が異なる（構造由来の作成可否 vs レコード自身のVR）。

## 承認前チェックの参照レシピ（ti-reference から取得）

承認前チェックの判定に使う集計・過去取引の引き当て（利益率の算定・類似取引の並べ）は **ti-reference のレシピ（Atlas MCP 配信の `atlas_recipe`／`atlas_explain`）から取得**する。判定の是非（承認前チェックの内包）は ti-update、集計手順は ti-reference という分界。移設に伴う機能低下を招かないよう、参照レシピは ti-reference 側に残し ti-update はそれを呼ぶ。

## 書込本命経路の依存

入力支援には2つの経路がある。**本命経路**は明細エディタのサーバー処理を AI/MCP から呼ぶ形で、UI と同等の整合をそのまま得られる。**暫定経路**は直接書込＋突合で、本命経路が使えない組織でも成立する。**到達可否は版番号で判定せず、その組織に現に有るかを自己診断で見る**（ti-core `references/capability-preflight.md`）。本命経路が使えるならそちらへ寄せる。気づいた不足は ti-core `references/feedback.md` へ。

## ti-core 発火点（このスキルが必ず結ぶ3点）

| チェックポイント | 読む | 目的 |
|---|---|---|
| 現状仕様を往復で詰める瞬間（突合結果の提示・点検助言の往復） | ti-core `references/spec-roundtrip.md` | 人間判断を仰ぐ往復 |
| org書込直前（作成・トリガ項目更新・マスタ書込） | ti-core `references/safety-gate.md` | ドラフト提示＋明示承認＋PIIマスキング。入力支援は必ず通す。承認支援は読み取りで書かない |
| 段階拡張の穴・本命経路が使えないこと・意味定義の不足に気づいた瞬間 | ti-core `references/feedback.md` | ナレッジギャップの記録 |

> 本文の能力スキル名（ti-reference・ti-metadata・ti-core・ti-data-load 等）は配置済みで、フォルダ名＝正準名として辿れる（ti-data-load は `tsubaiso-data-migration` からの改称先）。
