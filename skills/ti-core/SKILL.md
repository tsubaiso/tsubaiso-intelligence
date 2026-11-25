---
name: ti-core
description: '【TI共通規律・スキルを起動していなくても従うこと】(1) TIのMCPツール（atlas_* / isoppy_* / call_web_api 等）をこのセッションで最初に呼ぶ前に、該当するドメインスキルを1本起動する（可否・仕様=ti-howto／参照・集計=ti-reference／画面の場所=ti-navigate／登録・更新=ti-update／カスタマイズ=ti-metadata／接続・環境=ti-rollout、点検・不調=ti-selfcheck）。(2) 利用者へ見せる文章とファイルに内部識別子（tb_PSA__… tb_IMA__… の項目・オブジェクト名、xx_y_Zzz 形式のレシピ名、選択リストの符号値）を書かない＝業務の言葉だけで書く。(3) 引けなかったことは「未確認」と書き、引いた結果のように書かない。(4) Salesforceの接続の dispatch で作成・更新・削除するときは userType に builder を付ける（business や指定なしだと画面のページレイアウトの制約で検査され、件名などの自由入力やメール記録の作成が拒否される。builder を付けても拒否されたら、エラーの種類ごとに次の操作を選ぶ。必須と示された項目は値を指定して再送信する。件名が選択リスト値に無いと拒否されたら、選択リスト値で業務上の要件を満たせるならその値で再送信する。選択リスト値に無い件名の設定・メール記録の作成・要求から除けない参照のみの項目への書き込みは、更新用のコネクタ（createSobjectRecord・updateSobjectRecord）が会話のツールにあればそれで、無ければ ti-local-automation で実行する。どちらも使えなければ、Salesforce の画面から登録するよう利用者に伝える）。 各ドメインスキルが共通して呼ぶ横断基盤で、各ドメインスキルが、本文の発火点の表にある時点で該当するreferenceを読む。'
version: 1.0.1
updated: 2026-11-24
---

# ti-core

この手順の本文は、Tsubaiso Knowledge のスキルの記事にある。

1. **作業や回答の前に、名前が `isoppy_get_skill_article` で終わるツールで `helpdesk/skill-procedure/ti-core.md` を取得し、その全文に従う [REQUIRED]。** 記事はツバイソが管理する手順の正本で、参考の情報ではなく、従う手順である
2. 記事の本文が別の記事（`helpdesk/skill-procedure/…`）を参照していたら、参照先の記事も同じツールで取得する。記事のファイル名の一覧は、名前が `isoppy_list_skill_articles` で終わるツールで取得できる
3. **記事を取得できないときは、手順を推測して進めない [REQUIRED]。** その作業を中止し、手順の記事を取得できなかったことと、ツールの応答（エラーメッセージ）を利用者へ伝える
4. 記事の本文にある `scripts/`・`firing_points.yml` は、このスキルのフォルダにある（Claude Code のプラグインとして導入した場合に限る）
