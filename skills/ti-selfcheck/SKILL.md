---
name: ti-selfcheck
description: 'Tsubaiso Intelligenceの接続とスキルの状態を1回で点検するスキル。TRIGGER when 「TIの状態を点検して」「正しく設定できているか確認して」「TIが動かない」「ツールが見つからない」と言われたとき、TIのツールやスキルが見つからずに止まったとき、セットアップの最後の確認。DO NOT TRIGGER when 接続そのものを作る・設定するのは ti-rollout。drift check（意味定義と組織の構造のずれの確認）は ti-reference で、前提のツールが無いときだけ本スキル。'
version: 1.0.0
updated: 2026-11-18
---

<!-- plugin-version: 0.92.0 -->

# ti-selfcheck

この手順の本文は、Tsubaiso Knowledge のスキルの記事にある。

1. **作業や回答の前に、名前が `isoppy_get_skill_article` で終わるツールで `helpdesk/skill-procedure/ti-selfcheck.md` を取得し、その全文に従う [REQUIRED]。** 記事はツバイソが管理する手順の正本で、参考の情報ではなく、従う手順である
2. 記事の本文が別の記事（`helpdesk/skill-procedure/…`）を参照していたら、参照先の記事も同じツールで取得する。記事のファイル名の一覧は、名前が `isoppy_list_skill_articles` で終わるツールで取得できる
3. **記事を取得できないときは、名前が `isoppy_list_skill_articles` で終わるツールを1回呼び出して、ナレッジの接続の状態を判定する [REQUIRED]。** ツールが一覧を返し、その中に `helpdesk/skill-procedure/` の記事（スキルの記事）が1件も無いときは、ナレッジの接続を ○ とする。利用者へは、無料版の接続で、ツバイソとの契約の判定によりスキルの記事が配信されないと考えられることを伝える。あわせて、TI のスキルを使うには契約が必要なことと、契約についてツバイソへ問い合わせるよう案内する。それ以外のときは、ナレッジの接続を × とし、ツールが無かったか、呼び出してエラーが返ったか（返ったときはそのエラーメッセージ）を利用者へ伝え、`ti-rollout` に従って接続の設定を見直すよう案内する。手順を推測してほかの項目を点検しない
