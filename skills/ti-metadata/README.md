# ti-metadata — メタデータ設定スキル

PSA/IMA（Salesforce マネージドパッケージ）のカスタマイズ（メタデータ編集）を、AI が PSA/IMA の現状と整合性を保って設定するためのスキルです。実組織の現状を真実の源にした **差分方式（retrieve → author → diff → checkonly → deploy → verify）** を中核に、カスタム項目・権限セット・入力規則・承認プロセス・FlexiPage（作成＋割当）・レポートタイプ・リストビュー・Apex トリガー・Flow オーバーライド・Lightning Web コンポーネント・静的リソース・Visualforce ページ・非トリガ Apex クラス・カスタムメタデータ・共有ルール（SharingRules）／OWD までを、実機検証で確定した手順として収録しています。

このスキルは特定のプラグインやロールパックに依存しません。`sf CLI v2`＋`Python 3`＋認証済み org があれば単体で機能します。

## 同梱物

| ファイル | 役割 |
|---|---|
| `SKILL.md` | スキル本体。org カテゴリと安全弁・カスタマイズ着手プリフライト・疎結合設計原則・アップグレード再検証・中核ループ・PSA/IMA 整合ルール |
| `references/metadata-type-recipes.md` | 種別ごとのオーサリング手順と確定した癖（12 節） |
| `references/sharing-model.md` | 共有モデル設定（SharingRules／OWD）＝アドバイザリー専用・衝突検知つき追記 |
| `scripts/tb_mdconfig.py` | 中核ループ（retrieve/diff/checkonly/quick deploy/deploy/verify）を sf CLI v2 上でラップするハーネス。本番＝承認ゲート、検証 org＝確認ゲート内蔵 |
| `scripts/tb_sharing.py` | 共有モデル設定の author 段（CSV→SharingRules XML 生成・可読ルール翻訳・衝突プリチェック）。org には書かない |
| `README.md` | 本ファイル（前提・インストール・クイックスタート） |

## 前提条件

- **Salesforce CLI v2**（`sf --version` で確認。`sfdx` 旧版ではなく `sf` コマンド）
- **Python 3.8 以上**（スクリプトは標準ライブラリのみ・追加 pip 不要）
- **作業対象 org への認証**（`sf org login web --alias <org>` 等で事前にログイン済み）
- 整合検証は **PSA/IMA 導入済みの org**（トライアル／検証 org）で行うのが前提。素の Dev Edition scratch では PSA/IMA 未導入のため整合検証は限定的

## インストール

このディレクトリ一式を任意の場所へ配置するだけです。スクリプトは実行権限を付けておくと便利です。

```bash
chmod +x scripts/tb_mdconfig.py
sf --version            # v2 系であること
python3 scripts/tb_mdconfig.py -h
```

**初回のみ**：自組織の検証 org・本番 org のエイリアス命名に合わせて、`scripts/tb_mdconfig.py` 冒頭の定数を調整します。

- `PROD_ALIAS_HINTS`：本番とみなす org エイリアスの接頭辞（既定 `prod`／`production`／`本番`）。本番は `--approved-by` 必須・`NoTestRun` 拒否。
- `PROTECTED_ALIAS_HINTS`：保護（トライアル・検証）org の接頭辞（既定 `trial`／`uat`／`sit`）。**自社の検証 org エイリアスの一部をここに足す**と、その org への deploy が `--confirm` ゲート対象になります。

## クイックスタート（中核ループ）

sf CLI のメタデータ DX プロジェクト（`force-app` を持つ作業ディレクトリ）内で実行します。`<org>` は自組織のエイリアスに置き換えてください。

```bash
# 1. 現状取得（バックアップ）— 触る範囲を先に退避
python3 scripts/tb_mdconfig.py retrieve --org <org> \
  --metadata "CustomField:tb_PSA__tb_SalesOrder__c.MyField__c" --output-dir backup_before

# 2. author（オーサリング）— force-app 配下に目標メタデータを置く
#    種別ごとの手順は references/metadata-type-recipes.md を参照

# 3. checkonly（検証デプロイ・書込なし）— 成功すると job-id を表示
python3 scripts/tb_mdconfig.py checkonly --org <org> --source-dir force-app

# 4. deploy（本デプロイ）— 検証 org は --confirm 必須
python3 scripts/tb_mdconfig.py deploy --org <trial-org> --source-dir force-app --confirm

# 5. verify（非破壊突合）— 別ディレクトリへ再 retrieve して差分0を確認
python3 scripts/tb_mdconfig.py verify --org <org> \
  --metadata "CustomField:tb_PSA__tb_SalesOrder__c.MyField__c" --target-dir force-app
```

Apex トリガー（テストクラス同梱・カバレッジ要件あり）は checkonly でテストを走らせ、成功ジョブを quick deploy します（下記は検証 org 前提。本番 org の quick は `--confirm` ではなく `--approved-by "承認者名"` が必要で、付けないと承認ゲートで弾かれます）。

```bash
python3 scripts/tb_mdconfig.py checkonly --org <org> \
  --metadata "ApexTrigger:MyTrg" "ApexClass:MyTrgTest" \
  --test-level RunSpecifiedTests --tests MyTrgTest
python3 scripts/tb_mdconfig.py quick --org <org> --job-id <上で表示されたid> --confirm
```

## 安全のための約束ごと（必読）

- **着手前に `SKILL.md §カスタマイズ着手プリフライト` を一度通す**（6 軸ルーブリック→リスクレベル→ゲート）。中・高リスクは `§疎結合設計原則` に沿った代替案を既定にします。
- **org は 3 カテゴリで扱う**：本番（承認ゲート）／保護＝トライアル・検証（確認ゲート＋着手前バックアップ）／使い捨て（制約なし）。詳細は `SKILL.md §org カテゴリと安全弁`。
- **本デプロイ前に必ず checkonly を先行**。Apex を含む場合はテストレベルを明示。
- **本番 org への deploy は承認者の明示承認が必須**（`--approved-by`）。組織に本番変更管理ルールがあればそれを優先します。
- **マネージドパッケージ（`tb_PSA__`／`tb_IMA__`）の管理対象本体は変更不可**。許されるのは拡張（管理対象オブジェクトへの項目追加・FLS 付与・VR 追加・サブスクライバ承認プロセス／FlexiPage／ReportType／Apex トリガ追加 等）のみ。
- **FlexiPage の「割当（Activation）」は管理対象オブジェクトでは特に、実行前に必ずユーザー（依頼者・管理者）の確認を取る**。割当は作成と別 deploy 単位です。
- **Flow オーバーライドは置換型・全置換**。本番展開はドリフト監視とセットでのみ可（`SKILL.md §安全弁7`）。
- **共有ルール／OWD は最上位のブラストレンジ**。アドバイザリー専用・衝突プリチェック必須（`references/sharing-model.md`）。
- **PSA と IMA は双方向に後付け拡張する**ため、VR・トリガの整合は両パッケージを数え上げて確認します（片方だけで結論しない）。

## 未検証の残課題

`SKILL.md §残る要実機確認` を参照してください。主なものは、カスタムレポートタイプを参照する Report 本体の Metadata 配置（不可＝UI 作成が現実解）／管理（installed）アプリ本体の割当改変境界／Apex の本番カバレッジ運用（org 全体 75%）／Flow オーバーライドの本番有効化経路と全置換ドリフト監視方式／共有ルールの本番展開ゲート（共有再計算の実行影響）です。
