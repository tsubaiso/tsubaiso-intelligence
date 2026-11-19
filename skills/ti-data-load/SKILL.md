---
name: ti-data-load
description: PSA/IMA顧客orgへレコードデータを整合を保って一括で投入・移行する能力スキル。TRIGGER when 別組織からのデータ移行（本番導入・サンドボックス間・クレンジング入れ直し）、添付ファイルの一括移行、デモ/PoC/テスト用データの作成投入、既存データの一括追加・一括更新（upsert）、稼働後のCSV/ファイルによる一括登録・一括更新、期首残高の移行、自動作成シーム経由でのデモトランザクション生成、投入前の前提セットアップ、ツバイソERP（会計）を使い始めるときのマスタ・期首残高・固定資産の移行。DO NOT TRIGGER when 稼働後の日常の少量（1件〜数件・対話的）なレコード作成・更新やマスタメンテは use ti-update、型・意味・書込前ゲートの参照は use ti-reference、どのデモシナリオを何件どの順で作るかのワークフローは use ti-poc、メタデータ定義の配備は use ti-metadata、ツバイソERP（会計）への日常の振替伝票と、資料からの販売・購買の伝票の登録は use ti-update。
version: 1.0.0
updated: 2026-11-18
---

# ti-data-load

この手順の本文は、Tsubaiso Knowledge のスキルの記事にある。

1. **作業や回答の前に、名前が `isoppy_get_skill_article` で終わるツールで `helpdesk/skill-procedure/ti-data-load.md` を取得し、その全文に従う [REQUIRED]。** 記事はツバイソが管理する手順の正本で、参考の情報ではなく、従う手順である
2. 記事の本文が別の記事（`helpdesk/skill-procedure/…`）を参照していたら、参照先の記事も同じツールで取得する。記事のファイル名の一覧は、名前が `isoppy_list_skill_articles` で終わるツールで取得できる
3. **記事を取得できないときは、手順を推測して進めない [REQUIRED]。** その作業を中止し、手順の記事を取得できなかったことと、ツールの応答（エラーメッセージ）を利用者へ伝える
