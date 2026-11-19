---
name: ti-metadata
description: AI が PSA/IMA と整合してメタデータ＝カスタマイズ（カスタム項目・権限セット・入力規則・承認プロセス・FlexiPage・レポートタイプ・リストビュー・Apexトリガー・Flow オーバーライド・Lightning Web コンポーネント・静的リソース・Visualforce ページ・非トリガ Apex クラス・カスタムメタデータ・共有ルール(SharingRules)/OWD＝共有モデル設定・ラベル/選択リスト値の翻訳 等）を差分方式で設定する手順とスクリプト。アップグレード時の再検証、当社の拡張アプリの導入・版上げ・設定変更・アンインストールと、カスタマイズ設計書・仕様書の出力も担う
version: 4.0.0
updated: 2026-11-18
---

# ti-metadata

この手順の本文は、Tsubaiso Knowledge のスキルの記事にある。

1. **作業や回答の前に、名前が `isoppy_get_skill_article` で終わるツールで `helpdesk/skill-procedure/ti-metadata.md` を取得し、その全文に従う [REQUIRED]。** 記事はツバイソが管理する手順の正本で、参考の情報ではなく、従う手順である
2. 記事の本文が別の記事（`helpdesk/skill-procedure/…`）を参照していたら、参照先の記事も同じツールで取得する。記事のファイル名の一覧は、名前が `isoppy_list_skill_articles` で終わるツールで取得できる
3. **記事を取得できないときは、手順を推測して進めない [REQUIRED]。** その作業を中止し、手順の記事を取得できなかったことと、ツールの応答（エラーメッセージ）を利用者へ伝える
4. 記事の本文にある `scripts/` は、このスキルのフォルダにある（Claude Code のプラグインとして導入した場合に限る）
