---
name: ti-local-automation
description: 本人権限内で PSA/IMA を任意の Salesforce API（REST/Tooling/Bulk/Composite/バイナリ/独自 Apex REST）でローカル操作する能力スキル。TRIGGER when 標準 MCP ツールに無い API 操作・商談等への数KBを超える・バイナリのファイル添付＋公開リンク発行・数KBを超える・バイナリの授受・Bulk/Composite・独自 Apex REST 呼び出しをローカルスクリプトで行う、Salesforceの接続の dispatch で userType に builder を付けても画面の制約で拒否された書き込み（選択リスト値に無い件名・メール記録の作成・除けない参照のみの項目）を、更新用のコネクタ（createSobjectRecord・updateSobjectRecord）が無いときに実行する。DO NOT TRIGGER when 会話内の少量の参照・更新（標準 MCP で足りる）=標準 MCP/ti-update、会話の接続に任意のREST呼び出しを受けるツール（dispatch系）があるときの公開リンクの1件発行・入力規則やフロー定義の読み取り（会話の接続で足りる）、業務データの一括移行の型と機構=ti-data-load、メタデータ定義の配備=ti-metadata、接続・認証の準備そのもの=ti-rollout。
version: 1.0.0
updated: 2026-11-18
---

# ti-local-automation

この手順の本文は、Tsubaiso Knowledge のスキルの記事にある。

1. **作業や回答の前に、名前が `isoppy_get_skill_article` で終わるツールで `helpdesk/skill-procedure/ti-local-automation.md` を取得し、その全文に従う [REQUIRED]。** 記事はツバイソが管理する手順の正本で、参考の情報ではなく、従う手順である
2. 記事の本文が別の記事（`helpdesk/skill-procedure/…`）を参照していたら、参照先の記事も同じツールで取得する。記事のファイル名の一覧は、名前が `isoppy_list_skill_articles` で終わるツールで取得できる
3. **記事を取得できないときは、手順を推測して進めない [REQUIRED]。** その作業を中止し、手順の記事を取得できなかったことと、ツールの応答（エラーメッセージ）を利用者へ伝える
