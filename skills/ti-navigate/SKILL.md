---
name: ti-navigate
description: '【ベータ】ツバイソPSA/IMAの「その画面はどこにあるか・どうやって開くか」に、クリック経路と直リンクで答えるスキル。TRIGGER when 「〜はどこで見られますか」「〜はどこから入れますか」「〜の画面を開く手順を教えて」「操作手順を順番に教えて」「案件から発注へはどう行きますか」、社員教育・サポート応答・デモ台本づくりで画面の場所や開き方を答えるとき、レポートやダッシュボードの置き場を尋ねられたとき。DO NOT TRIGGER when データの中身・金額・件数を取る集計は ti-reference、レコードの作成・更新は ti-update、画面そのものを作る・配置する（カスタムメタデータの配備）は ti-metadata、帳票レイアウトは ti-report、接続・環境セットアップは ti-rollout。'
version: 1.0.0
updated: 2026-11-18
---

# ti-navigate

この手順の本文は、Tsubaiso Knowledge のスキルの記事にある。

1. **作業や回答の前に、名前が `isoppy_get_skill_article` で終わるツールで `helpdesk/skill-procedure/ti-navigate.md` を取得し、その全文に従う [REQUIRED]。** 記事はツバイソが管理する手順の正本で、参考の情報ではなく、従う手順である
2. 記事の本文が別の記事（`helpdesk/skill-procedure/…`）を参照していたら、参照先の記事も同じツールで取得する。記事のファイル名の一覧は、名前が `isoppy_list_skill_articles` で終わるツールで取得できる
3. **記事を取得できないときは、手順を推測して進めない [REQUIRED]。** その作業を中止し、手順の記事を取得できなかったことと、ツールの応答（エラーメッセージ）を利用者へ伝える
