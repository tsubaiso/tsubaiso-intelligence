# write-index — 書込前構造ゲート（作成・更新前の必須手順の参照エントリ）

書込スキル（ti-update／ti-data-load／ti-metadata）が PSA/IMA を作成・更新する直前に読む、書込前構造ゲートの参照エントリ（TI クライアントスキル体系 §8.2）。ゲートは `function_only` 判定・参照先マスタの有効条件（C5 参照フィルタ）・自動生成（auto_create）シームの両方向検出を担う。

**実体＝Atlas MCP `atlas_write_seam`（v12.1.0〜）**: 本ゲートの実体は Tsubaiso Atlas MCP サーバーの `atlas_write_seam(target=<API名>)` ツール。読み取り系（`atlas_explain`／`atlas_recipe`）と同じ薄いクライアント型で、意味・構造スナップショットを配布物に同梱しない。旧 P0 のローカル実体（`scripts/atlas_write_index.py` ＋意味定義スナップショット `semantics_v38.json`）は v12.1.0 で除去した（配布物 同梱ゼロ化）。`function_only` 検出・C5 参照フィルタは旧 P0 で未実装だったが、本ツールで実装済み。

## 引き方

作成・更新する対象オブジェクトの API 名で `atlas_write_seam` を 1 回呼ぶ。

- ツール: `atlas_write_seam(target="<オブジェクトAPI名>")`（名前空間プレフィックス `tb_PSA__`／`tb_IMA__` は省略可・標準オブジェクトは接頭辞なし）
- 1 対象 1 応答。参照先マスタの逆引きはサーバー側で解決するためクライアントは 1 コールで済む。
- 全件一覧（旧 `--list`）は抽出防御方針により提供しない。対象 API 名を指定して都度引く。

## 応答の読み方

`atlas_write_seam` 応答の各フィールドで判定する。

- **`function_only`**（配列・機能経由でのみ作成・更新可）: 各要素の `detail.verdict`（`function_only`）・`detail.operation`（create／import 等）・`detail.function_ref`（正規の生成機能）・`detail.exception`（許容経路）・`detail.recipe`（正しい生成手順）・`detail.control_class`（C1 等）。該当 operation は直接 INSERT／インポートせず、正規機能・転記・自動生成・専用画面で生成する。
- **`auto_create_as_source`**（配列・源として）: 対象を保存すると何が自動生成されるか。`detail.arm`（生成機構）・`trigger`（意図フラグ）・`automation`／`service`・`creates_all`・`diff_update` に従い「フラグ→保存→読み戻し→差分 UPDATE→突合」で書く。
- **`auto_create_as_target`**（配列・作成先として＝二重計上ガード）: 対象が別シームで自動生成されないか。要素があれば手動 INSERT 禁止で、生成元 `source` 側のフラグ経由で生成する。
- **`reference_filters`**（配列・C5）: 参照先マスタの有効条件（`active_condition`）。参照項目を埋めるとき、参照先が有効条件を満たすレコードかを確認する。
- 共通 `semantics_version`／`source_sha`（配信版突合用）。`found:false` は対象が未収録＝当て推量で書かない。

## 判定（総合）

- ❌ **直接 INSERT 禁止**: `auto_create_as_target` に要素がある（別シームの自動生成先＝二重計上リスク）。源オブジェクト側のフラグ経由で生成し手動作成しない。
- ❌ **機能経由のみ**: `function_only` に該当 operation がある。正規機能・転記・自動生成・専用画面で生成する（直 INSERT／インポート不可）。
- ⚠️ **シーム経由で書く**: `auto_create_as_source` に要素がある（フラグで下流を自動生成）。「フラグ→保存→読み戻し→差分 UPDATE→突合」で書く。
- ✅ **通常の作成・更新でよい**: いずれも空。レコード自身の入力規則(VR)・必須項目・整合ルールは `atlas_explain` の対象オブジェクト各項目の `rule` を参照する。

## arm（生成機構）の別

各 auto_create シームに `detail.arm` が付く: `flow`（自動起動フローが下流を生成）／`flow_orchestration`（締め・承認で連鎖フラグを立て下流を起動）／`apex_post`（PSA の Apex が下流を insert）／`apex_inbound_sync`（ERP→PSA を定期 upsert＝手動の二重作成・キー衝突注意）／`external_erp`（PSA→外部 ERP 送信で **SF レコードは作らない**）／`apex_internal`（IMA の Apex が在庫操作の保存時に在庫オブジェクトを内部 materialize）／`apex_crosspkg`（**IMA→PSA 横断**＝在庫起点で PSA 財務記録・役務を自動生成。PSA 側を手動作成しない＝二重計上ガード）。

## 可用性と保留規律 [REQUIRED]

本ゲートはサーバー可用性に依存する（読み取り経路と同一 regime）。`atlas_write_seam` が未接続・403（エンタイトルメント失効）で応答しないときは、**書込を保留し、ゲートを迂回して INSERT／UPDATE しない**。利用者に Atlas MCP の接続状態と PSA 契約の有効性の確認を促す。`found:false`（未収録）も同様に、機構を捏造せず人へ引き継ぐ。サーバーは常に最新の意味定義版を返すため、クライアント側での再生成・版追従作業は不要。

## 書込スキルからの呼び出し

ti-update／ti-data-load／ti-metadata は書込直前に本ファイルを発火点で読み、`atlas_write_seam` を引いてゲートを通す。書くレコード自身の入力規則（VR）の充足検証は書込スキル側（例 ti-update `references/input-support.md`）の射程で、本ゲート（構造由来の作成可否・参照先の有効条件）とは射程が異なる。
