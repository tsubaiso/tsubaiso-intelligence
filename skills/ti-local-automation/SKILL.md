---
name: ti-local-automation
description: 本人権限内で PSA/IMA を任意の Salesforce API（REST/Tooling/Bulk/Composite/バイナリ/独自 Apex REST）でローカル操作する能力スキル。AI がローカルでスクリプトを生成・実行し、標準 MCP ツールでは届かない操作（大容量・バイナリのファイル添付＋公開リンク発行、一括処理、Composite 等）を安全に行う。TRIGGER when 標準 MCP ツールに無い API 操作・商談等へのファイル添付＋公開リンク発行・大容量/バイナリの授受・Bulk/Composite・独自 Apex REST 呼び出しをローカルスクリプトで行う。DO NOT TRIGGER when 会話内の少量の参照・更新（標準 MCP で足りる）=標準 MCP/ti-update、業務データの一括移行の型と機構=ti-data-load、メタデータ定義の配備=ti-metadata、接続・認証の準備そのもの=ti-rollout。
version: 0.1.2
updated: 2026-07-31
---

# ti-local-automation — ローカル API スクリプティング（任意 API 操作の機構）

標準 MCP ツールで届かない PSA/IMA 操作を、**AI がローカルで生成したスクリプトが、本人権限内の Salesforce API を直接呼んで**行う能力スキル。ファイル添付＋公開リンク発行は同梱レシピの一つ。

原則: **大きなデータ（ファイルのバイト列等）を AI の会話に載せない**（パス／ディスク経由でスクリプトが直接読む）。書込は承認・ドライランを通す。**認証・接続は再実装せず ti-rollout の本人接続（api スコープ ECA）を使う**。

## 前提（認証・接続）

- 本人権限内の **api スコープ OAuth トークン**（専用 ECA・ローカル本人認証）を使う。準備・認証の手順は **ti-rollout `references/api-eca-setup.md`** が持つ（本スキルでは再掲しない）。トークンは OS キーチェーンに保管。
- できることは常に**本人が Salesforce でできる範囲**に限られる（越権しない）。

## このスキルが持つもの・持たないもの

| 持つ（任意 API 操作の機構） | 持たない（委譲先） |
|---|---|
| ローカルスクリプトによる REST/Tooling/Bulk/Composite/バイナリ操作 | 認証・接続の準備＝ti-rollout |
| ファイル添付＋公開リンク発行レシピ（ContentVersion/ContentDistribution） | 業務データ一括移行の型・機構＝ti-data-load |
| 大容量/バイナリを壊さず授受（会話を経由しない） | メタデータ定義の配備＝ti-metadata |
| — | 書込前の構造ゲート・型・API 名＝ti-reference |

## 発火点（いつ・何を読む/呼ぶ）

| チェックポイント | 読む／呼ぶ |
|---|---|
| org へ書き込む直前（作成・更新・添付・Bulk・Composite） | ti-core `references/safety-gate.md`（承認ドラフト提示・ドライラン→人が承認） |
| 書込前の構造ゲート・API 名・型が要る瞬間 | ti-reference `references/write-index.md` |
| 認証・接続が未準備 | ti-rollout（本人接続の準備・api スコープ ECA） |
| 大量の業務データ投入・移行 | ti-data-load（型と機構） |
| 繰り返し詰まる摩擦／機能不足を検知 | ti-core `references/feedback.md` |

## レシピ

- **ファイル添付＋公開リンク**: 商談等へ ContentVersion をマルチパートで添付（`FirstPublishLocationId` で対象レコードへ紐付け）→ ContentDistribution で公開リンク（パスワードなし・期限指定）発行 → URL 返却。**ファイル本体は会話に載せずパス／ディスク経由**（実証済み・15MB 破損なし）。公開リンクは**パスワードなしなら URL を知る誰でもアクセス可**になるため、発行時の safety-gate 承認ドラフトに**公開範囲（URL を知る誰でも／期限）**を明記し、必要ならパスワード付き・短期限を選ぶ。
- **ライブラリの特定フォルダへ配置**: `FirstPublishLocationId` にライブラリ（ContentWorkspace）を指定してアップロード（フォルダ ID の直指定は本番で受け付けられないことがある）→ 生成された `ContentFolderMember` の `ParentContentFolderId` を目的フォルダ（ContentFolder）へ更新して移動。パスワード付き・無期限等は ContentDistribution の `PreferencesPasswordRequired`／`PreferencesExpires` で指定（本番実証済み）。
- （順次追加）一括更新（Bulk/upsert のうち移行に当たらない稼働後の少量〜中量）、Composite での複数レコード一括作成、独自 Apex REST 呼び出し 等。

## 顧客レシピの作成・配布（標準/顧客固有の2層）

本スキルは**土台**（レシピ実行の型＋認証＋safety-gate）を提供する。**汎用の標準レシピは本スキル（Tsubaiso Intelligence Skill＝ツバイソ標準の配布物）に置く**。**顧客業務固有のレシピはツバイソ標準の配布物に入れず、顧客が自社プラグイン（別リポジトリ／別マーケットプレイス）に置いて社内配布する**（ツバイソ標準の定期更新との衝突を避けるため）。

顧客レシピの作り方（作成・配布キット）:

1. 自社プラグインを用意する（Cowork のプラグイン作成。作成手順はクライアント側の公式ドキュメントに従う）。
2. レシピを書く: **確定論的スクリプト＋使い方＋safety-gate 注記**。認証は本スキルが使う ECA（`ti-rollout` の本人接続・api スコープ）を再利用する（新設不要。ECA の構成正本は `ti-rollout references/api-eca-setup.md`）。
3. **検証 org で確認**（ドライラン・本人権限内）。
4. **レビュー承認**（誰がレシピを足せるかを顧客側で決める＝顧客の管理者/開発担当が承認する）。
5. 自社プラグインとして社内配布 → 各ユーザーの AI が利用。

統制は 3 ゲートが層をまたいで効く: **実行＝ECA 権限セット**（保有者のみ・本人権限内・フェイルクローズ）／**作成＝レビュー承認**／**書込＝safety-gate**。L1（本スキル・標準）と L2（顧客固有）は**リポジトリを分離**し、**参照は L2→L1 の一方向のみ**とする（L1 が L2 を参照しないため、ツバイソ標準の更新が顧客レシピに引きずられない）。

## 原則

- **本人権限内・最小権限**。書込は承認・ドライラン。削除は既定で行わない。
- **大きなデータを AI の会話に通さない**（パス／ディスク経由でスクリプトが直接扱う）。
- **認証・機構の重複を作らない**（接続＝ti-rollout、型＝ti-reference、移行＝ti-data-load へ委譲）。本スキルは「任意 API を叩く機構」に徹する。
- 利用者向け出力に内部識別子（API 名・SOQL・レコード ID・鍵値）を出さない。業務語へ翻訳しレコードはリンク化する。
