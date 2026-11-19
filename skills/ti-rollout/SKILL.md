---
name: ti-rollout
description: Tsubaiso Intelligence を顧客環境で使い始めるための接続・環境セットアップを進めるスキル。TRIGGER when 接続・環境セットアップ・MCP/コネクタ結線・カスタムコネクタ登録・Salesforce(PSA/IMA)標準MCP接続・ツバイソERP（会計）のMCP接続・外部クライアントアプリ作成・接続キー取得・初期セットアップ・「TIの使い方を教えて」（接続後の使い始めの練習）。DO NOT TRIGGER when 導入プロジェクトの工程進行・計画立案・Fit&Gap/設計の段取り=ti-onboarding、契約前の価値実証・トライアル体験=ti-poc、データ移行の実行=ti-data-load、MCP に無い任意 API 操作のローカル実行=ti-local-automation、メタデータ＝カスタマイズ定義の生成・デプロイ=ti-metadata。「TIを導入したい」は接続・環境セットアップの局面のみ本スキルが担い、工程進行・計画は ti-onboarding へ寄せる。
version: 1.0.0
updated: 2026-11-18
---

# ti-rollout

この手順の本文は、Tsubaiso Knowledge のスキルの記事にある。

1. **作業や回答の前に、名前が `isoppy_get_skill_article` で終わるツールで `helpdesk/skill-procedure/ti-rollout.md` を取得し、その全文に従う [REQUIRED]。** 記事はツバイソが管理する手順の正本で、参考の情報ではなく、従う手順である
2. 記事の本文が別の記事（`helpdesk/skill-procedure/…`）を参照していたら、参照先の記事も同じツールで取得する。記事のファイル名の一覧は、名前が `isoppy_list_skill_articles` で終わるツールで取得できる
3. **記事を取得できないときは、手順を推測して進めない [REQUIRED]。** その作業を中止し、手順の記事を取得できなかったことと、ツールの応答（エラーメッセージ）を利用者へ伝える
4. 記事の本文にある `templates/` は、このスキルのフォルダにある（Claude Code のプラグインとして導入した場合に限る）
