# sharing-model — 共有モデル設定（SharingRules／OWD）

PSA 標準の共有機構（レコード可視範囲＝個人→チーム→全社）を、顧客導入時に正しくセットアップする設定支援。**当社は独自の権限エンジンを作らず、既存の共有機構を理解して設定支援する**（不変条件）。他のメタデータ種別と違い org 全体の可視範囲を変えるため、`SKILL.md` §安全弁8 の最上位ブラストレンジ扱い＝**アドバイザリー（導入セットアップ）専用**で、参照系・レポート実行時経路とは物理的に別経路にする。

## 扱う機構

- **共有ルール2型**＝(a) 所有者ベース `sharingOwnerRules`（付与元＝全内部ユーザ→グループ＝管理・スタッフ部門への全社共有）、(b) 条件ベース `sharingCriteriaRules`（条件フィールド＝部門コードを条件に→グループ＝部門/チーム単位の可視化）。条件ベースは条件フィールドを持つ obj のみ対象＝**持たない obj（集計オブジェクト等）は所有者ベースか権限セット/OWD に委ねる**。
- **OWD（組織の共有設定）**＝各 obj の `sharingModel`/`externalSharingModel`。共有ルールは OWD を「拡張」するため、拡張対象は非公開（Private）にしておく必要がある（既に全社参照なら共有ルールは無意味）。
- **付与先＝部門公開グループ**＝部門マスタ由来の公開グループ（部門・部門責任者）。当社が独自にグループを作らず、部門マスタ登録時に自動生成される公開グループを共有先に使う。

## 入力モデル＝意図ヒアリング→可読ルール（正）→裏CSV [REQUIRED]

ユーザーは共有機構（親子・主従マスタ/トランザクションの別・設定の帰結）を理解しなくてよい。

1. AI が業務語で「誰が・どのデータを・見るだけ／編集も」を意図ヒアリングする（シェアリングルール・条件フィールド等の語は出さない）。
2. AI が共有ルールへ翻訳する（型判定・オブジェクト展開・条件不可 obj 除外・部門名→グループ解決は AI が裏で行う）。
3. 人が読める可読ルール文＋帰結注記を最終アウトプットにする（正・編集の起点）。
4. 変更は可読ルール起点で会話編集する。
5. 裏で CSV（正本実装互換スキーマ）へ翻訳して適用する。

**源泉の正は可読ルール・CSV/XML は生成物（手編集しない）。**

## 中核フロー（中核ループへの写像）

1. 意図ヒアリング→可視範囲ポリシー（内部構造データ）を起こす。
2. ポリシー→CSV 生成＋スキーマ検証（`[HEADER]`／キー列／既知 obj API 名の describe 照合／値 Read・Edit・空／source が全内部ユーザ指定か有効部門コード／dest_group が実在公開グループ）。**条件ベース行に条件フィールド不在 obj が載る場合はエラーで事前に弾く**（翻訳段の除外＋checkonly の二重防御。実機検証で checkonly は componentFailure「no CustomField named …（条件フィールドの API 名）… found」として捕捉すると確定。条件フィールドの実 API 名は `scripts/tb_sharing.py` の定数で確認できる）。
3. retrieve（現状取得・**ロールバック資産として保持**）。**deploy は additive（実機検証・省いたルールは消さない）だが、owner 衝突の silent 上書きを事前検知＋源泉一元化のため retrieve→merge は必須**。**ルール削除は omission では起きず destructiveChanges（`SharingCriteriaRule`／`SharingOwnerRule`）で行う（実機検証で実証）**。**なお同梱の生成器は空セルをスキップする＝削除を生成しない**（追記のみ）。CSV のセルを空にしても既存ルールは消えず deploy は成功して返るため、**意図的に共有を縮小する場合は destructiveChanges を別途用意する**（SF の制約ではなく生成器の初版スコープ）。
4. author（**retrieve 済み現状 XML へ追記＝衝突検知のため必ず既存 buffer に追記**。単体ファイル `author-csv`（`existing={}`）を org へ直接 deploy しない。冪等＝既存一致はスキップ。**挿入は XSD 要素グルーピングを守る**＝retrieve 由来 XML の criteria 群→owner 群の順を崩さない・崩すと `Element … is duplicated at this location` で deploy 失敗〔実機検証で確定〕）。
5. **衝突プリチェック（access 変化の事前検知・checkonly の穴を埋める）[REQUIRED]**＝**owner rule は (sharedFrom,sharedTo) の上書き衝突→downgrade（業務停止）／upgrade（過剰共有）**、**criteria rule は (sharedTo,field,value) の重複→broaden（実効 UNION↑＝過剰共有）／redundant（重複）**（実機検証＝criteria は上書きせず並存・downgrade は原理的に起きない）を retrieve 済み現状 XML と突合して可読ルールで承認提示する（`tb_sharing.py precheck --csvfile … --existing-dir …`＝downgrade 検出で exit2）。**想定外型ガード**＝検証済みの型（owner 付与元＝全内部ユーザ／criteria 条件フィールド＝部門コード・operation `equals`／共有先 group・全社員）以外（role/portal 宛・別付与元・別条件フィールド等）を現状 XML に検出したら**自動判定せず「人手確認が必要」と警告し exit2**（`unverified_shapes`・将来型が増えても安全側に倒す）。§安全弁8(b) のとおり checkonly は捕捉しないため**本段が唯一の「事前」防御点**。**この step5 は org 段（`tb_mdconfig.py`）へ組込み済み**＝`sharing-precheck`（retrieve 済みディレクトリ＋CSV のゲート・SFDX レイアウト解決）／`sharing-deploy`（retrieve→author-merge→precheck ゲート→checkonly→deploy→verify を一貫実行し、downgrade・想定外型は `--ack-downgrade` なしで停止＝exit3）。
6. checkonly（`sf project deploy start --dry-run … -m SharingRules`。生成される共有ルール一覧を可読ルールの言葉で承認提示。**役割限定＝メタデータ妥当性のみ担保・access 縮小/共有再計算ブラストは担保しない**）。
7. deploy（本デプロイ・承認必須。保護 org `--confirm`／本番 `--approved-by`。共有再計算 `sharing operation already in progress` はリトライ）。
8. verify（別ディレクトリ再 retrieve／SOQL で実効共有を突合。**衝突対象だった既存ルールの access が意図せず縮小していないことも確認**）。

## 実装

**author 段＝`scripts/tb_sharing.py`（org 非依存）**: CSV→SharingRules XML 生成器（PSA パッケージ標準の共有ルール一括デプロイ実装〔正本実装〕の生成ロジックを構造等価で再実装＝2型分岐・Account 特例 `accountSettings`・冪等・名前空間トグル）＋可視範囲ポリシー→CSV／可読ルール翻訳器＋**衝突プリチェック**（`precheck`＝retrieve 済み現状 XML を解析し (sharedFrom,sharedTo)〔criteria は (sharedTo,field,value)〕衝突を検出、access 差分を可読ルールで提示）。正本実装との構造等価は内部の回帰・CI で担保する（顧客環境に Ruby は不要）。

**org 段＝`scripts/tb_mdconfig.py`**（retrieve/checkonly/deploy/verify・共有ルール専用の中核ループに衝突プリチェックを組込み）: `tb_sharing.py` の `precheck`／`unverified_shapes` を org 中核ループへ差し込み、checkonly が捕捉しない access 変化を deploy の手前でゲートする。ブラストレンジ物理分離は維持（org へ書くのは本ファイルのみ・authoring/衝突ロジックは `tb_sharing` に一元化して import）。

- 使用例（author）: `python3 tb_sharing.py policy-compile --policy p.json --config c.json --csv-out out.csv`（可読ルール＋裏 CSV）／`python3 tb_sharing.py author-csv --csvfile out.csv --pkg-installed 1 --output-dir force-app/main/default/sharingRules`
- 使用例（衝突プリチェック単体・org 非依存）: `python3 tb_mdconfig.py sharing-precheck --csvfile out.csv --existing-dir <retrieve済みディレクトリ> --pkg-installed 1`（downgrade／想定外型で exit2・upgrade/broaden のみ exit1・clean exit0）
- 使用例（org 適用・一貫実行）: `python3 tb_mdconfig.py sharing-deploy --org <org> --csvfile out.csv --pkg-installed 1 --confirm`（retrieve→author-merge→**precheck ゲート**→checkonly→deploy→verify。downgrade・想定外型は `--ack-downgrade` を付けて承認するまで停止＝exit3。`--dry-run` で org 呼出しを表示のみにしてローカルのゲートを事前確認可）
- 使用例（個別段の従来経路）: `python3 tb_mdconfig.py checkonly --org <org> --metadata "SharingRules:<対象オブジェクトAPI名>"` → `deploy --confirm`（保護 org）→ `verify`

## 確定した癖

①SharingRules コンテナ deploy は **additive**（省いたルールを消さない＝REPLACE ではない）。削除は destructiveChanges で明示する。②**owner rule は (sharedFrom,sharedTo) で SF が一意化**し、衝突追記が既存 access を silent 上書き（Edit→Read）する。③**criteria rule は (sharedTo,field,value) では一意化されず並存する**（上書きしない・実効 UNION）ため、重複は broaden／redundant として提示する。④checkonly は access 変化を捕捉しない（メタデータ妥当性のみ）＝author 段の衝突プリチェックが唯一の事前防御点。⑤挿入は XSD 要素グルーピング（criteria 群→owner 群）を守らないと `duplicated at this location` で deploy 失敗する。⑥誤設定の復元は着手前 retrieve した現状 XML の再デプロイ＝復元ランブック（実機検証で機能を確認済）。
