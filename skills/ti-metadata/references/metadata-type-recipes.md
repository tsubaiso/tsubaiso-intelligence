# metadata-type-recipes — 種別ごとのオーサリング手順と確定した癖

`SKILL.md` の §中核ループ（差分方式）を各メタデータ種別に適用するときの手順と、実機で確定した癖をまとめる。全種別に共通する規律（org カテゴリと安全弁・カスタマイズ着手プリフライト・PSA/IMA 整合ルール）は `SKILL.md` が正本で、本ファイルは種別固有の差分だけを持つ。共有モデル設定（SharingRules／OWD）は `sharing-model.md`。

**着手前に必ず `SKILL.md` §カスタマイズ着手プリフライト を一度通す [REQUIRED]。**

以下の「確定した癖」は、PSA/IMA 導入済みの検証 org（保護カテゴリ）で型ごとに検証して確定した事項。大半は author→checkonly→deploy→verify の一気通貫で確定しているが、**LWC／静的リソースだけは既存資産の read-only 確認**（新規 deploy なし）で確定した点に注意する（当該節に再掲）。

## カスタム項目＋権限セット＋入力規則

1. **作業 org 準備**: 保護カテゴリ org（PSA/IMA 導入済みトライアル）。着手前に対象オブジェクトの現状を **retrieve バックアップ**（既存項目・既存 VR・既存権限セット）。SOQL（Tooling）で既存 VR / サブスクライバ項目を棚卸し（衝突確認）。
2. **管理対象オブジェクトへの VR 追加可否を最小 VR で実機確認**（オブジェクトにより異なるため一律「可」と断定しない）:
   ```bash
   sf project deploy start --dry-run --metadata "ValidationRule:tb_PSA__tb_SalesOrder__c.Test_VR" --target-org <org> --json
   ```
   `INSUFFICIENT_ACCESS` / `cannot modify managed object` 系が返れば不可。
3. **カスタム項目オーサリング**: `objects/{Obj}/fields/{Field}__c.field-meta.xml`。型・ラベル・参照先は describe 一次出典に合わせる（推測しない）。
4. **入力規則オーサリング**: `objects/{Obj}/validationRules/{Rule}.validationRule-meta.xml`。数式は対象項目の API 名・型に整合させ、参照項目を同一 deploy に含める。`errorDisplayField` に対象項目を指定可。PSA/IMA の既存 VR・サーバー側トリガと発火条件が衝突しないか確認（両パッケージ数え上げ）。
5. **権限セットオーサリング**: `permissionsets/{PermSet}.permissionset-meta.xml` に `fieldPermissions` を追加。マネージド項目参照は名前空間付き API 名を `オブジェクト.項目` のドット形式で記述する（例 `tb_PSA__tb_SalesOrder__c.MyField__c`）。
6. **diff → checkonly → deploy → verify**: 中核ループ。デプロイ順序＝項目／VR → 権限セット。保護 org の diff は checkonly の `componentSuccesses` で代替。
7. **突合レポート**: 何が新規／更新されたか、入力規則が意図どおり発火するか（簡易テストデータで）を報告。
8. **本番展開（任意・別途）**: 保護 org で確定後、承認を得て本番へ checkonly → deploy。

**確定した癖**: ①管理対象オブジェクトへのカスタム項目・入力規則・FLS 付与は追加可（管理 VR と共存）。②Apex を含まない検証ジョブは quick deploy 不可（テスト 0 件）＝通常 deploy。③verify で `FieldDefinition`（Tooling）は作成直後の項目を返さないことがあるため `CustomField`／`FieldPermissions` で確認する。

## 承認プロセス（ApprovalProcess）

承認プロセスは「対象オブジェクト＋承認者＋最終/却下アクション」の3点を最小化して型を確立する。最終承認で項目を更新する場合は `WorkflowFieldUpdate` を同梱する（AP の `finalApprovalActions` が参照）。

1. **既存承認プロセスの棚卸し**: `SELECT DeveloperName, Name, TableEnumOrId, State, Type FROM ProcessDefinition`（**通常 SOQL。Tooling API は `ProcessDefinition` を `INVALID_TYPE` で拒否**）。対象オブジェクトに既存の管理 AP があっても**サブスクライバ AP は共存追加できる**。
2. **オーサリング**:
   - `approvalProcesses/{Object}.{Process}.approvalProcess-meta.xml`。最小要素＝`active` / `allowedSubmitters`（`owner` 等）/ `approvalStep`（`assignedApprover.approver.type` は **`adhoc`＝手動選択が org 差異に最も強い**。特定ユーザ名のハードコードを避ける）/ `recordEditability` / `processOrder`。
   - `emailTemplate` の**空要素 `<emailTemplate></emailTemplate>` は入れない**（存在しないテンプレ参照エラーの元）。使うときのみ実テンプレ名を入れる。
   - 最終承認で項目更新するなら `workflows/{Object}.workflow-meta.xml` に `fieldUpdates`（`field`＝サブスクライバ項目は名前空間なし API 名・`literalValue`・`operation=Literal`）を置き、AP の `finalApprovalActions` から `<action><name>{FieldUpdate名}</name><type>FieldUpdate</type></action>` で参照する。
3. **checkonly → deploy → verify**: 中核ループ。承認プロセスとワークフローは同一 deploy 単位（AP が FieldUpdate を参照するため）。
   - **`active=true` のままデプロイで `State=Active` になる**（UI 手動有効化は不要）。
   - verify は `ProcessDefinition`（通常 SOQL）の `State` で確認する。
4. **整合確認**: 既存管理 AP・サーバー側 VR/トリガと申請/承認時アクションが衝突しないか両パッケージ数え上げ。

**確定した癖**: ①管理対象オブジェクトへのサブスクライバ AP 追加可（管理 AP と共存）。②`active=true` 配備可。③最終承認アクションがサブスクライバ項目を更新可。④既存管理 AP・VR・トリガと衝突なし。

## FlexiPage（Lightning record page・作成）

FlexiPage は「**作成**」と「**割当（Activation）**」が分離する点が他種と決定的に違う。作成は差分方式でデプロイできるが、割当は別工程（`SKILL.md` §安全弁 6 の確認ゲート対象）。

1. **既存ページの棚卸し**: 対象オブジェクトの既存 FlexiPage を Tooling SOQL で確認する。
   ```sql
   -- まず EntityDefinition の DurableId を取得（QualifiedApiName 指定）
   SELECT DurableId FROM EntityDefinition WHERE QualifiedApiName = 'tb_PSA__tb_SalesOrder__c'
   -- その DurableId で FlexiPage を絞る（全 RecordPage を引くと管理パッケージ分で巨大になる）
   SELECT Id, DeveloperName, MasterLabel, Type, NamespacePrefix FROM FlexiPage WHERE EntityDefinitionId = '01Id…'
   ```
   管理（`tb_PSA`）の record page が多数あってもサブスクライバ（`NamespacePrefix=null`）は 0 本のことが多く、共存追加のテストになる（VR・AP と同型）。
2. **正しいコンポーネント名を既存ページから確認（最重要の癖）**: 標準コンポーネントの名前を推測で書くと「**コンポーネント flexipage:xxx の設計時のコンポーネント情報を取得できませんでした**」という分かりにくいエラーになる。**真因はコンポーネント名の名前空間誤り**で、API バージョン不一致ではない。既存ページを 1 本 retrieve して有効な名前を確認する。実証で判明した正しい名前:
   - レコード詳細パネル = **`force:detailPanel`**（`flexipage:recordDetailPanel` は不可）
   - ハイライトパネル = **`force:highlightsPanel`**（`flexipage:highlightsPanel` は不可）
   - テンプレートは `flexipage:recordHomeTemplateDesktop`、regions = `header` / `main` / `sidebar`。
3. **オーサリング**: `flexipages/{Page}.flexipage-meta.xml`。最小要素＝`flexiPageRegions`（header/main/sidebar）/ `masterLabel` / `sobjectType`（管理対象は名前空間付き）/ `template` / `type=RecordPage`。**各 `componentInstance` に `<identifier>` が必須**（無いと「component インスタンスには識別子が指定されていません」エラー）。`force:detailPanel` は既定で全項目を表示する。
4. **checkonly → deploy → verify**: 中核ループ。`--metadata "FlexiPage:{名前}"` で対象を絞れる。verify は `FlexiPage`（Tooling SOQL、`DeveloperName` / `NamespacePrefix=null`）で実在確認。
5. **割当（Activation）**: `SKILL.md` §安全弁6 に従う。**作成しただけではどの画面にも表示されない**。割当は AI が用意し、deploy 前に必ずユーザー確認を取る（管理対象オブジェクトでは特に）。作成と割当はデプロイ単位を分け、割当は別承認とする。

**確定した癖**: ①管理対象オブジェクトへのサブスクライバ FlexiPage 作成可（管理ページと共存）。②標準コンポーネントは `force:` 名前空間（`flexipage:` 誤りが「設計時情報取得不可」の真因・API バージョンは無関係）。③`componentInstance` に `identifier` 必須。④**作成 ≠ 割当**＝deploy で作成はできるが割当はされず別工程（`SKILL.md` §安全弁6）。

## レポートタイプ（ReportType）

ReportType（カスタムレポートタイプ）は「対象オブジェクトを baseObject に、報告で使える列を定義する」カスタマイズ。レポート本体（`Report`）はこの土台の上に載る user-content（フォルダ配置が要る別物）なので、カスタマイズの主役は ReportType。

1. **既存 ReportType の棚卸し**: `sf org list metadata --metadata-type ReportType --target-org <org> --json` で一覧を取り、`namespacePrefix` で管理（`tb_PSA`/`tb_IMA`）とサブスクライバ（null）を判別する。サブスクライバ ReportType は既に多数存在しうる（最初から共存実績がある）。最終確証は checkonly で取る。
2. **正しい `field` / `table` 命名を既存から確認（中核ループ author 適用）**: 既存 ReportType を 1 本 retrieve して meta-xml の命名規約を確認する。実証で判明した規約:
   - `baseObject` = 対象オブジェクトの API 名（管理対象は名前空間付き）。
   - 各 `columns` は `field` ＋ `table` ＋ `checkedByDefault`。`table` は baseObject の API 名（同一セクションでは baseObject、join 先セクションでは `Base.Relationship` 形式）。
   - `field` は**標準項目＝素の API 名（`Id`/`Name`/`CreatedDate`）、管理カスタム項目＝名前空間付き、サブスクライバ追加項目＝素の API 名**。
3. **オーサリング**: `reportTypes/{Name}.reportType-meta.xml`。最小要素＝`baseObject` / `category`（管理 ReportType 実例に倣い `other` が安全）/ `deployed`（`true`）/ `label` / `sections`（`columns` 群＋`masterLabel`）。`description` は任意。**サブスクライバ ReportType は名前空間なし**。
4. **checkonly → deploy → verify**: 中核ループ。`--metadata "ReportType:{名前}"` で対象を絞る。checkonly はテスト 0 件のため quick deploy 不可＝通常 deploy。**CLI/クライアントが finalize 段階でタイムアウトしても job-id の `deploy report`、または下記 verify で実判定する**。
   - **verify は `sf org list metadata --metadata-type ReportType` の一覧で対象が `namespacePrefix=null`・`lastModifiedDate` 直近で実在することを確認する**（ReportType は Tooling SOQL 向きではないため metadata list が確実）。
5. **整合確認**: ReportType は読み取り専用の報告定義で VR・トリガを発火させないが、列に出す項目の FLS（権限セット）と参照解決が前提。サブスクライバ項目を列に出すなら §カスタム項目＋権限セット＋入力規則 の FLS 付与と同じ権限セットで可視性を担保する。

**確定した癖**: ①管理対象オブジェクトを baseObject にしたサブスクライバ ReportType 追加可（管理・サブスクライバ既存と共存）。②サブスクライバ項目を素の API 名で報告列に指定可・管理項目は名前空間付き・`table` は baseObject API 名。③`category=other`・最小要素は baseObject/category/deployed/label/sections。④verify は metadata list（Tooling SOQL 不向き）／finalize タイムアウトは job-id で実判定。

## Apex トリガー（＋テストクラス）

Apex は段階導入で最後に置いた最高リスク種。理由は「テストカバレッジ要件（本番 75%）」と「管理対象オブジェクトのトリガはテストの DML が管理 VR・管理トリガを全て通る必要がある」点。トリガ単体ではなく**テストクラスを必ず同梱**し、deploy 単位を 2 コンポーネント（トリガ＋テスト）にする。

1. **既存トリガ・Apex の棚卸し**: `SELECT Name, TableEnumOrId, NamespacePrefix, Status FROM ApexTrigger`（Tooling）で対象オブジェクトの管理／サブスクライバ・トリガを数え上げる。`SELECT Name, NamespacePrefix, Status FROM ApexClass`（Tooling）でサブスクライバ・クラスの衝突名・既存テストを確認する。**両パッケージ数え上げ**（PSA/IMA の管理トリガを把握し発火衝突を予見）。
2. **トリガのオーサリング**: `triggers/{Name}.trigger` ＋ `triggers/{Name}.trigger-meta.xml`（`apiVersion` / `status=Active`）。**サブスクライバ・トリガは名前空間なし**。**サブスクライバ項目のみを操作**し管理ロジックに依存しない（管理トリガとの発火順序は不定）。`before update` 等、被覆するトリガコンテキストを最小化する。
3. **テストクラスのオーサリング**: `classes/{Name}Test.cls` ＋ `.cls-meta.xml`。**管理対象オブジェクトは新規 insert が管理 VR・必須マスタ依存で困難なため、`@isTest(SeeAllData=true)` で既存レコードを 1 件 SELECT → サブスクライバ項目を更新 → `update` でトリガを被覆**する。`Test.startTest()/stopTest()` で囲む。**テスト内 DML はテスト終了時に自動ロールバックされ実データは改変されない**（SeeAllData でも DML はロールバック）。`ORDER BY CreatedDate ASC LIMIT 1` 等で承認ロック中のレコードを避けるとより安全。
4. **checkonly（テスト実行）**: `--metadata "ApexTrigger:{名前}" "ApexClass:{名前}Test" --test-level RunSpecifiedTests --tests {名前}Test`。**`--dry-run` 単体ではテストが走らない**ため `--test-level` を必ず付ける。保護 org 検証では `RunSpecifiedTests`＝自テストのみ（標準ボイラープレートを巻き込まない）。本番は `RunLocalTests` で org 全体 75% を確認。checkonly の `runTestResult.codeCoverage` でトリガのカバレッジ（被覆行/総行）を確認する。
5. **deploy → verify**: **Apex は quick deploy が成立する**（テストを実行した検証ジョブのため）。`tb_mdconfig.py quick --org {org} --job-id {checkonlyのid} --confirm`＝テスト再実行なしで投入できる。finalize タイムアウト／表示バグは job-id の deploy report で実判定。verify は `ApexTrigger`（Tooling SOQL、`Name` / `NamespacePrefix=null` / `Status=Active`）で実在確認。
6. **整合確認**: 追加トリガが管理トリガ・サーバー側 VR と衝突せず発火するか（テストの update が成功し assert が通ること自体が共存の実証になる）。両パッケージ数え上げ。

**確定した癖**: ①管理対象オブジェクトへのサブスクライバ Apex トリガ追加可（管理トリガ共存下）。②テストが管理トリガ＋管理 VR を通って成功＝衝突なし・before→VR 順で VR 充足。③`@isTest(SeeAllData=true)`＋既存レコード update が管理対象トリガ被覆の現実解（新規 insert 回避・DML ロールバックで実データ非改変）。④`RunSpecifiedTests --tests {自テスト}` で標準ボイラープレートを巻き込まず被覆できる。⑤Apex を含む検証ジョブは quick deploy 成立（テスト再実行なし）。

## FlexiPage 割当（App 単位・Activation／CustomApplication）

作成したサブスクライバ FlexiPage を、実際に画面へ出す「割当（Activation）」をメタデータで行う工程。割当は `flexipage-meta.xml` 単独では完結せず、`CustomApplication` の `actionOverrides` 経由で行う。**`SKILL.md` §安全弁6 のとおり管理対象オブジェクトの割当は実行前に必ずユーザー確認**。

1. **既存割当の棚卸し（中核ループ author 適用）**: 対象オブジェクトの割当が現状どのアプリでどのページに向いているかを、サブスクライバアプリを retrieve して確認する。`sf org list metadata --metadata-type CustomApplication` で managed（`namespacePrefix` あり）／subscriber（null）を判別し、subscriber アプリを retrieve。割当は `actionOverrides`（`actionName=View` / `type=Flexipage` / `content=ページ名` / `pageOrSobjectType=対象オブジェクトAPI名` / `formFactor` Large・Small）として表現される。"Action override updated by Lightning App Builder during activation" コメントが UI 有効化由来の割当。
2. **割当方式の選択（安全策＝新規アプリ）**: 既存アプリの割当上書きは実運用画面を切り替えるため高影響。**専用の新規サブスクライバ Lightning アプリ**を作り、その中だけで割当を作るのが既存運用ゼロ影響の安全策。最小要素＝`actionOverrides`（Large/Small の 2 件）＋`formFactors`（Large/Small）＋`label`＋`navType=Standard`＋`uiType=Lightning`＋`tabs`（最低 1 つ、`standard-home` 等）。**サブスクライバ FlexiPage の `content` は名前空間なし**、`pageOrSobjectType` は管理対象なら名前空間付き。
3. **checkonly → deploy → verify**: 中核ループ。`--metadata "CustomApplication:{アプリ名}"` で対象を絞る。Apex 無し＝通常 deploy（quick 不可）。verify は `sf org list metadata --metadata-type CustomApplication` で `namespacePrefix=null` 実在＋**別ディレクトリへ再 retrieve して `actionOverrides` の `content`／`pageOrSobjectType` が永続していること**を確認。
4. **Org-default（オブジェクト既定ページ・全アプリ共通）は管理オブジェクトでは不可**: `object-meta.xml` に org-default の `actionOverrides`（`pageOrSobjectType` なし）を置く部分 deploy は `Must specify a non-empty label for the CustomObject` で弾かれる＝deploy が完全なオブジェクト定義（label）を要求し、管理オブジェクトの改変不可境界に阻まれる。**org-default 割当はサブスクライバ側メタデータでは行えない。割当は App 単位が現実解**。

**確定した癖**: ①管理対象オブジェクトへのサブスクライバ FlexiPage 割当は `CustomApplication actionOverrides`（App 単位）で可・実 deploy で永続。②既存運用ゼロ影響の安全策＝専用の新規アプリに割当を作る。③Org-default（全アプリ共通既定）はサブスクライバ側メタデータでは不可（管理オブジェクト改変境界）。④割当は作成（FlexiPage）と別 deploy 単位・`SKILL.md` §安全弁6 の確認ゲート対象。

## FlexiPage 割当（プロファイル単位・既存アプリ上書き境界）

App 単位割当に続き、(a) プロファイル単位の割当（`profileActionOverrides`）と (b) 既存アプリの割当上書き境界。**`SKILL.md` §安全弁6 のとおり管理対象オブジェクトの割当は実行前に必ずユーザー確認**。

1. **(a) profileActionOverrides（プロファイル単位）**: `CustomApplication` に `profileActionOverrides`（`actionName=View`／`content=ページ名`／`formFactor`／`pageOrSobjectType=対象オブジェクトAPI名`／`profile=プロファイル名`／`type=Flexipage`）を追加。**新規／自前サブスクライバアプリに追加すれば安全**（既存運用ゼロ影響）。プロファイル名は org の実在プロファイルに合わせる（`sf org list metadata --metadata-type Profile` で確認）。
2. **(b) 既存アプリの割当上書き（高影響・原則 checkonly のみ）**: 既存アプリの `actionOverrides` の `content` を別ページへ書き換える。**サブスクライバ自身が作成した unmanaged アプリ（`manageableState=unmanaged`）の割当は技術的に上書き可能**だが、実運用画面を切り替える高影響操作のため `SKILL.md` §安全弁6 の確認ゲート＋原状復帰前提。無確認では deploy しない（checkonly で可否のみ確認）。
3. **checkonly → deploy → verify**: (a) は新規アプリで通常 deploy 可。verify は `CustomApplication` を別ディレクトリへ再 retrieve し `profileActionOverrides` の永続を確認。

**確定した癖**: ①割当は App 単位に加えプロファイル単位（`profileActionOverrides`）も可・新規アプリ上なら安全。②サブスクライバ自身の unmanaged アプリ割当は上書き可能だが実運用画面切替＝高影響で無確認 deploy 禁止。③管理（installed）アプリ本体の改変は別境界。

## リストビュー（ListView）／レポート本体（Report）

ReportType が「報告で使える列の土台」なのに対し、ListView と Report 本体は user-content 寄り。ListView は管理対象オブジェクトへサブスクライバ追加でき、Report 本体は配置可否がレポートタイプの種類で分かれる。

1. **ListView（管理対象オブジェクトへサブスクライバ追加）**: `objects/{Obj}/listViews/{Name}.listView-meta.xml`。最小要素＝`fullName`（サブスクライバは名前空間なし）／`columns`（標準は `NAME`、管理は名前空間付き `tb_PSA__xxx__c`、サブスクライバ項目は素の API 名）／`filterScope`（`Everything` 等）／`filters`（`field`/`operation`/`value`）／`label`。**チェックボックス項目のフィルタ値は `1`／`0`（`true`／`false` は不可）**。既存ページから命名を確認（中核ループ author）。管理 ListView と共存追加可。
2. **ReportFolder（サブスクライバ公開フォルダ）**: `reports/{Folder}.reportFolder-meta.xml`。最小要素＝`accessType`（`Public`）／`name`／`publicFolderAccess`（`ReadWrite`）。サブスクライバ ReportFolder 作成可。
3. **Report 本体（レポートタイプ依存）**: `reports/{Folder}/{Report}.report-meta.xml`。最小要素＝`name`／`format`（`Tabular` 等）／`reportType`／`columns`（`{baseObjectApi}${fieldApi}`）。**`reportType` が標準レポートタイプ（例 `Opportunity`）の Report は配置可。`reportType` がカスタムレポートタイプ（自作・管理問わず）の Report は `invalid report type` で配置不可**（レポートタイプを同一 deploy に同梱しても解消しない＝Salesforce 既知の制約）。**したがって ReportType が配置可能なキャリアで、カスタムレポートタイプ上の Report 本体は UI 作成が現実解**。
4. **checkonly → deploy → verify**: 中核ループ。ListView/ReportFolder の verify は `sf org list metadata --metadata-type ListView`／`ReportFolder` で `namespacePrefix=null` 実在確認。

**確定した癖**: ①管理対象オブジェクトへサブスクライバ ListView 追加可（チェックボックスフィルタ値は `1`/`0`。`true` は「「0」または「1」を使用してください」で失敗）。②サブスクライバ ReportFolder 作成可。③**Report 本体は標準レポートタイプなら配置可・カスタムレポートタイプ参照は Metadata 配置不可**（ReportType が配置キャリア／Report 本体は UI 作成が現実解）。

## Flow オーバーライド（`isOverridable`）

パッケージが `isOverridable=true` で開放した Flow（典型＝record-triggered before-save の自動導出 Flow）を、サブスクライバ Flow で差し替えるカスタマイズ。**管理 Flow の本体を改変しない**点で隔離されているが、置換型・全置換のため**全置換ドリフトが本番展開ブロッカー**になる（`SKILL.md` §安全弁7）。「最も安全」と序列付けない。

1. **対象 Flow がオーバーライド可能か確認（中核ループ author 適用）**: 対象 Flow を retrieve し、meta-xml 本文に **`<isOverridable>true</isOverridable>`** があることを確認する（UI 推測でなくソース確認）。`processType`／`triggerType`（RecordBeforeSave 等）／`recordTriggerType`／対象 object／start filter（どの条件で発火するか）を読む。**両パッケージ数え上げ**＝同一オブジェクト・同一タイミングで競合する Flow/トリガが他パッケージ（PSA/IMA）に無いか確認し、オーバーライド対象を一意に特定する。
2. **オーバーライド Flow のオーサリング**: `flows/{Name}.flow-meta.xml`。**サブスクライバ＝名前空間なし**（`NamespacePrefix=null`）。
   - object/trigger/processType を**元 Flow と同一**にする（異なると checkonly が通らない）。
   - **`<overriddenFlow>{名前空間付きの管理 Flow 名}</overriddenFlow>` を `<label>` 直後に置く**（これが元 Flow を指すオーバーライド宣言。FlowDefinition でも UI 専用操作でもない）。元 Flow の `<isOverridable>` 要素は除去する。
   - **全置換型なので元 Flow の全分岐を再現**し、変更したいケースの代入先だけ差し替える（未再現ケースには値が入らない）。start filter も元と同一にする。
   - `apiVersion` は元 Flow に合わせる。`<status>Active</status>` で deploy（下記）。
3. **checkonly → deploy → verify**: 中核ループ。`--metadata "Flow:{名前}"` で対象を絞る。Apex 無し＝通常 deploy（quick 不可）。finalize 表示バグは job-id で実判定。
   - **活性化（activate）**: 検証 org では **`status=Active` deploy だけで有効化が完結**（UI 操作不要。deploy 直後に `FlowDefinition.ActiveVersionId` がセットされる）。**ただし本番では Flow が非アクティブ配備＋別途有効化（Tooling REST PATCH 等）になりうる**ため、本番展開時は有効化経路を実機確認する（`SKILL.md` §安全弁7-b・`SKILL.md` §残る要実機確認）。有効化は `SKILL.md` §安全弁6 と同様に**管理対象では実行前に必ずユーザー確認**。
   - **verify（機能確認）**: 新規レコードを最小マスタ構成で INSERT し、オーバーライドで変えた項目が期待値になるかを読む。**保護 org では匿名 Apex の `Database.setSavepoint()`＋INSERT→項目読取→`Database.rollback()` が最安全**（テストクラス deploy 不要・永続化なし・実データ非改変）。**機能検証は新規 INSERT で行う**（start filter が「項目変更時」を含む場合、既存レコードの touch update では発火しないため）。オーバーライド登録は `FlowDefinition`（Tooling SOQL、`ActiveVersionId`／`NamespacePrefix=null`）で確認。
4. **クリーンアップ（無効化）**: オーバーライドを無効化するには **FlowDefinition `activeVersionNumber=0` を単独 deploy**（`flowDefinitions/{Name}.flowDefinition-meta.xml`）。アクティブ版ポインタが外れ、置換が止まって管理 Flow が自動復帰する（オーバーライド Flow 本体・`<overriddenFlow>` 宣言は残置＝エビデンス保持）。checkonly は **`deploy start --dry-run --test-level NoTestRun`**（`deploy validate` はテスト 75% を強制するため Apex 非関与の無効化には不適）。
5. **整合確認**: オーバーライドはレコードの**生成元パッケージを問わず適用される**（同オブジェクトの before-save を通る全レコードに効く）。他パッケージ由来のレコードへの意図しない波及が無いか確認する。変えた導出結果を参照するロールアップ・レポート・帳票・意味定義への下流波及も棚卸しする（本番展開時は必須）。

**確定した癖**: ①`isOverridable=true` の record-triggered before-save flow は、サブスクライバが `<overriddenFlow>` を持つ同一 object/trigger/processType の Flow を deploy すると**置換型オーバーライド**になる（管理 Flow 不実行）。②`status=Active` deploy だけで有効化される（少なくとも保護トライアル org では・UI 不要）。③**全置換**＝元の全分岐を再現する必要がある（未再現ケースは値が入らない）。④機能検証は匿名 Apex の savepoint+rollback が保護 org で最安全・新規 INSERT で発火。⑤無効化は FlowDefinition `activeVersionNumber=0` 単独 deploy で完結し管理 Flow が自動復帰する。⑥置換・復帰は双方向で実証済（オーバーライド有効時は差し替えた結果、無効化後は元の導出結果へ戻る）。

## Lightning Web コンポーネント（LWC）／静的リソース（StaticResource）

帳票配備（レコードページ上の薄い描画/添付ボタン・全社共有の角印画像/共通CSS）が要する2型。中核ループ（retrieve→diff→checkonly→deploy→verify）はこの2型も型非依存で扱える。管理対象オブジェクトのレコードページにサブスクライバ LWC を載せ、全社共有 StaticResource をテンプレから参照する用途。

1. **既存の棚卸し**: `SELECT DeveloperName, NamespacePrefix FROM LightningComponentBundle`（Tooling）／`SELECT Name, NamespacePrefix FROM StaticResource`（通常 SOQL）で管理（`tb_PSA`/`tb_IMA`）とサブスクライバ（null）を判別。両パッケージ数え上げ。
2. **LWC オーサリング**: `lwc/{name}/{name}.js` ＋ `.html` ＋ `.js-meta.xml`。**管理対象レコードページに載せるには `.js-meta.xml` に `<isExposed>true</isExposed>` ＋ `<targets><target>lightning__RecordPage</target></targets>` ＋ `<targetConfigs>` の `objects` に管理対象 API 名（名前空間付き）を列挙**する。サブスクライバ LWC は名前空間なし。
3. **StaticResource オーサリング**: `staticresources/{name}.resource`（実体）＋ `.resource-meta.xml`（`contentType`）。角印画像・共通 CSS 等の全社共有資産。サブスクライバは名前空間なし。テンプレ（VF ページ等）からは `{!$Resource.{name}}` で参照する。
4. **checkonly → deploy → verify**: 中核ループ。verify は上記 SOQL で `NamespacePrefix=null` 実在確認＋LWC の `js-meta.xml` の targets/objects を再 retrieve で確認。
5. **配置（FlexiPage）**: LWC の可視化は FlexiPage に `componentInstance`（`componentName` はサブスクライバ LWC なら `c:{name}`）として載せ、割当は `SKILL.md` §安全弁6 に従う。**LWC 自体はコンポーネントとして自由に配備でき、可視化は FlexiPage 割当ゲートに従属**する（配備単位・ゲートが FlexiPage 配置を継承）。
6. **業務ロジック Apex（`@AuraEnabled`）**: LWC が Apex からデータ取得する場合、`@AuraEnabled` メソッドを持つサブスクライバ ApexClass を同梱配備できる（管理対象パッケージ org で稼働実証）。PDF 出力は VF ページ＋サーバ側 `PageReference.getContentAsPdf()` 経路も可。**本番 75% カバレッジは本番投入前ゲート**（`SKILL.md` §安全弁5）。

> **証拠の限定**: 本節の確定事項は、検証 org に既にある帳票配備資産を **read-only で確認**して得たもの（新規 deploy を伴う一気通貫の検証ではない）。他節と証拠の質が異なる点に留意する。

**確定した癖**: ①サブスクライバ LWC は `isExposed`＋`lightning__RecordPage`＋`targetConfigs objects` で管理対象レコードページに配置可（管理対象オブジェクトで成立）。②StaticResource は配備＋`$Resource` 参照可。③`@AuraEnabled` 業務 Apex ＋ VF `getContentAsPdf` の配備・稼働可（保護 org は 0% でも稼働・**本番 75% は本番投入前ゲート**）。④LWC 配置は FlexiPage 割当ゲートを継承する。

## Visualforce ページ（描画面VF）＋非トリガ Apex クラス

帳票の描画面（VF ページ）と、そのカスタムコントローラ／データ取得を担う `@AuraEnabled` 等の**非トリガ業務ロジック Apex クラス**を配備する工程。Apex トリガーと違い発火型でなく、VF ページとコントローラを 1 デプロイ単位（ページ＋クラス＋テスト）で扱う。

1. **既存の棚卸し**: `SELECT Name, NamespacePrefix FROM ApexPage WHERE NamespacePrefix = null` と `SELECT Name, NamespacePrefix, Status FROM ApexClass WHERE NamespacePrefix = null`（Tooling）で衝突名を確認。サブスクライバは名前空間なし。
2. **オーサリング**: `pages/{Name}.page`（＋`.page-meta.xml`）と `classes/{Name}.cls`（＋`.cls-meta.xml`）。VF ページのカスタムコントローラに非トリガクラスを指定すると、両者が同一デプロイ単位で結線される。管理対象オブジェクトを参照する SOQL は名前空間付き API 名で書く。**テストクラスを同梱**（VF コントローラは `Test.setCurrentPage(Page.{VF名})`＋`ApexPages.currentPage().getParameters().put('id', …)` で被覆、`@AuraEnabled` メソッドは直接呼び出しで被覆。管理 VR・必須マスタ依存を避けるため `@isTest(SeeAllData=true)` で既存レコードを読む）。
3. **checkonly（テスト実行）**: `--metadata "ApexPage:{VF名}" "ApexClass:{クラス名}" "ApexClass:{クラス名}Test" --test-level RunSpecifiedTests --tests {クラス名}Test`。保護 org 検証では自テストのみ。`runTestResult.codeCoverage` でクラスのカバレッジを確認。
4. **deploy → verify**: テストを実行した検証ジョブのため **quick deploy 可**（`sf project deploy quick --job-id {checkonlyのid}`）。verify は `ApexPage`（Tooling SOQL、`Name`／`NamespacePrefix=null`）と `ApexClass`（同）で実在確認。
5. **本番カバレッジ**: 非トリガ業務クラスも**本番では org 全体 75%** が必要（保護 org は 0% でも配備・稼働可）。帳票用途では本番 75% の担保は帳票実装（ti-report）側の責務。

**確定した癖**: ①管理対象オブジェクトを参照するサブスクライバ VF ページ＋非トリガクラスの配備可。②VF カスタムコントローラと `@AuraEnabled` は同一デプロイ単位で結線される。③テストは `Test.setCurrentPage(Page.…)`＋`SeeAllData=true` で既存レコードを被覆する。④保護 org は 0% でも配備可・**本番 75% は本番投入前ゲート**（Apex トリガー・LWC と同型）。

## カスタムメタデータ（型＋レコード）

顧客カスタマイズの**確定層スナップショット**等に使う CustomMetadata（`__mdt`）を、型定義とレコードの両方をメタデータ API で配備する工程。CMDT レコードは **DML insert 不可**（保存はメタデータデプロイのみ）で、これが標準トランザクションと切り離した「設定として持つ確定値」の性質を担う。

1. **既存の棚卸し**: `SELECT QualifiedApiName FROM EntityDefinition WHERE QualifiedApiName LIKE '%__mdt'`（Tooling）で管理／サブスクライバ（名前空間なし）を判別。
2. **型のオーサリング**: `objects/{Name}__mdt/{Name}__mdt.object-meta.xml`（`CustomObject`＝`label`／`pluralLabel`／`visibility`）＋ `objects/{Name}__mdt/fields/{Field}__c.field-meta.xml`（`CustomField`）。サブスクライバは名前空間なし。
3. **レコードのオーサリング**: `customMetadata/{Name}.{RecordDevName}.md-meta.xml`（`CustomMetadata`）。**root 要素に `xmlns:xsd="http://www.w3.org/2001/XMLSchema"` を必ず宣言する**（`<value xsi:type="xsd:string">` の `xsd:` を使うため。未宣言だと deploy が `UNKNOWN_EXCEPTION`〔コンポーネント詳細なしのデプロイレベル例外〕で落ちる。動く実例を 1 本 retrieve して名前空間宣言を確認するのが確実＝中核ループ「現状を真実の源に」）。
4. **型→レコードの 2 段配備 [REQUIRED]**: 型とレコードを**同一デプロイに含めない**。checkonly 時点で型が org 未在だとレコードが型に対して検証できず `UNKNOWN_EXCEPTION` で落ちる。**先に型（`CustomObject:{Name}__mdt`）を deploy → 型が org に存在してからレコード（`CustomMetadata:{Name}.{RecordDevName}`）を checkonly→deploy** する。
5. **verify**: レコードは通常 SOQL で読める（`SELECT DeveloperName, {Field}__c FROM {Name}__mdt`。CMDT は Tooling 不要）。型は `EntityDefinition`（Tooling）で確認。

**確定した癖**: ①サブスクライバ `__mdt` 型（`CustomObject`＋フィールド）の配備可。②CMDT レコードは**メタデータ API 配備のみ**（DML insert 不可＝確定値の性質）。③レコード XML は `xmlns:xsd` 宣言必須（未宣言＝`UNKNOWN_EXCEPTION`）。④**型→レコードの 2 段配備必須**（同時配備は型未在で `UNKNOWN_EXCEPTION`）。
