---
name: ti-onboarding
description: 本番導入プロジェクトを工程進行・段取りする導入支援スキル（PSA/ERP導入・契約後寄り）。TRIGGER when 導入計画の立案・タスク分解、Fit&Gap や重要マスタ設計の工程進行、7工程（計画・管理／設計／制作／構築・設定／データ移行／教育／運用テスト）の現在地把握と次工程の段取り、Sandbox→本番への着地支援。DO NOT TRIGGER when 契約前の価値実証は ti-poc、個別要件の実装形態や Anonymous Apex 可否・運用移行の判断は ti-lifecycle、単一の能力で完結する作業は層2スキル（ti-reference 等）。
version: 0.1.8
updated: 2026-07-21
---

# ti-onboarding — 導入支援（工程進行）

契約顧客の本番導入プロジェクトを「計画 → 設計 → 制作 → 構築 → データ移行 → 教育 → 運用テスト」の工程で進める**進行スキル**。**能力は再実装せず**、各工程で層2スキルを工程順に呼び、実装形態の判断は ti-lifecycle を参照する。原則は一貫して「**AI が下書き、人が判断**」。

本書は薄い索引に徹する（詳細は必要な reference だけを読む方式）。工程の順序づけ・対話ループ・モード設定の実体は各 reference にある。

## このスキルが持つもの・持たないもの

| 持つ（進行＝順序づけ・段取り） | 持たない（能力・判断＝委譲先） |
|---|---|
| 導入工程（7工程／ERP工程）の現在地把握と次工程の段取り | 参照・集計の実行＝ ti-reference／可視化＝ ti-spec-view |
| 設計工程の AI リード対話ループ（業務説明→Fit&Gap→マスタ設計→反復） | データ投入・移行の実行＝ ti-data-load／帳票＝ ti-report |
| onboarding モード（全量・本番前提）で層2を呼ぶ挙動設定 | メタデータ配備の機構＝ ti-metadata／入力支援・承認前チェック＝ ti-update |
| poc からのモード遷移の受け・ロール別の出し分け | 実装形態の判断（宣言的/Apex/外部/製品機能化・Anonymous Apex 可否・運用移行）＝ ti-lifecycle |
| — | 契約前の価値実証・トライアル体験の演出＝ ti-poc |

進行はこのスキル、能力は層2、判断は ti-lifecycle。この主従を崩さない。単一の能力で完結する作業（集計を1本・マスタを1件・可視化を1枚・受注を1件）は層2へ直接落とし、本スキルを経由しない。

## モードと未判定既定（発火時にまず確認）

本スキル（契約後寄り）と ti-poc（契約前寄り）は同じ層2能力を違う局面モードで束ねる**連続体**で、相互排他ではない。**契約状態が判明した時点で poc→onboarding へモードが遷移**する。契約状態・環境が読めないときは、**フェーズを確定せず、参照・可視化のみで応答し、書込・環境前提を要する段に入る前に契約状態と環境（トライアル／Sandbox／本番）を能動的に確認する**。onboarding モード（全量・本番前提）を安易に既定にしない（本番 org への誤書込を避ける）。

## 発火点（いつ・どの reference を読むか）

| チェックポイント | 読む／呼ぶ | 渡す・確認するもの |
|---|---|---|
| 導入工程のどこにいて次に何をするか段取りする瞬間 | `references/process-map.md` | 現在の工程・環境（トライアル/Sandbox/本番） |
| 設計工程で業務モデル・Fit&Gap・マスタ設計を対話で進める瞬間 | `references/design-lead-loop.md` | 業務プロセス説明・実帳票・関与すべき現場責任者 |
| onboarding モードの挙動・poc からの引き継ぎ・ロール別出し分けを決める瞬間 | `references/mode-and-handoff.md` | 契約状態・データ規模・ロール |
| 設計工程で業務の流れ・構造・集計を示す瞬間 | ti-reference の該当 reference（`process-map.md` が案内） | 対象プロセス・意味定義の参照点 |
| 現状のカスタマイズを把握・可視化する瞬間 | ti-spec-view の該当 reference | 対象 org・可視化の範囲 |
| 制作・構築工程でメタデータ配備・帳票が要る瞬間 | ti-metadata／ti-report の該当 reference | 配備対象・帳票の仕様 |
| データ移行工程で大量投入・移行が要る瞬間 | ti-data-load の該当 reference（大量 I/O はスクリプト経路） | 移行対象・dry-run→突合の前提 |
| 運用テスト工程で入力支援・申請前/承認前チェックが要る瞬間 | ti-update の該当 reference | 対象レコード・チェック観点 |
| 制作・構築工程で「どの実装形態で作るか」の判断が要る瞬間 | ti-lifecycle の該当 reference | 要件の性質・継続保守の主体 |
| org へ書き込む直前（制作・構築・データ移行・運用テスト） | ti-core `references/safety-gate.md` | 対象・承認ドラフト |
| 現状仕様を往復で詰める瞬間（Fit&Gap・マスタ設計の確定） | ti-core `references/spec-roundtrip.md` | 現状仕様・変更指示 |
| 工程で繰り返し詰まる／ナレッジが不足した瞬間 | ti-core `references/feedback.md` | 匿名化した摩擦シグナル |
| 一次解決で解けず利用者が未解決のまま／繰り返し詰まると判定した瞬間 | ti-core `references/support-escalation.md` | 本人の許可・再現手順（PII・業務データ本体・認証情報は載せない） |

> 本文中の能力スキル名（ti-reference・ti-metadata・ti-report・ti-update・ti-spec-view・ti-lifecycle・ti-core・ti-data-load）は配置済みで、フォルダ名＝正準名として辿れる（ti-data-load は `tsubaiso-data-migration` からの改称先）。未配置の機構・スキルに当たったら機構を捏造せず人へ引き継ぐ（または ti-core Knowledge で代替する）。

## reference 索引

| reference | 何を定義するか |
|---|---|
| `references/process-map.md` | PSA 7工程マップ（各工程で呼ぶ層2能力・ti-lifecycle 参照点・トライアル→Sandbox→本番の環境進行）＋ERP 工程の差分（仕訳分析ほか）＋大量 I/O のスクリプト経路 |
| `references/design-lead-loop.md` | 設計工程の AI リード対話ループ（インプット→業務説明→操作説明→Fit&Gap→マスタ設計→反復）。マスタ設計シミュレーションは合成（接地=ti-reference／投入=ti-data-load／集計・可視化=ti-reference・ti-spec-view／統合提案=ループ内推論）で専用能力を持たない |
| `references/mode-and-handoff.md` | onboarding モードの挙動軸・poc⇄onboarding の引き継ぎ（契約成立でのモード遷移・未判定既定）・ロール別の出し分け・段階導入と二層モデル |

## 原則

- **進行はここ、能力は層2、判断は ti-lifecycle**。工程の順序づけ・段取り・モード設定は本スキルが持ち、各工程の実作業と実装形態の判断は委譲先で行う。
- **AI が下書き、人が判断**。全工程で下書きを示し、確定・承認は人に委ねる。設計工程では関与すべき現場責任者・論点を能動的に明示する。
- **本書は薄く保つ**。工程の手順・対話ループ・モード設定は reference に置き、SKILL.md は索引に徹する。
- 出力に内部識別子（API 名・SOQL・レコード ID）を利用者向けに出さない（ti-core 群A の出力規律に従う）。
