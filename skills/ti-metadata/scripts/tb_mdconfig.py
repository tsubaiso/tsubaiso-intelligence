#!/usr/bin/env python3
"""tb_mdconfig.py — ti-metadata メタデータ設定の効率化ハーネス（PSA/IMA 整合カスタマイズ）v1.5

社内展開向け同梱版。前提・クイックスタートは同階層の README.md を参照。

中核ループ（差分方式）を sf CLI v2 上でラップする:
    [create-sandbox] → retrieve（現状取得・バックアップ）→ diff → checkonly（validation）
    → [quick] deploy → verify（非破壊・別ディレクトリ retrieve＋差分0判定）

共有モデル設定（SharingRules）専用の中核ループ（v1.5 で追加・設計メモ §3.1）:
    retrieve（現状）→ author-merge（現状 buffer へ追記）→ **衝突プリチェック（step5・ゲート）**
    → checkonly → deploy → verify
  衝突プリチェックは `tb_sharing.py` の precheck／unverified_shapes を org 段へ差し込む段で、
  checkonly が捕捉しない access 変化（owner の silent 上書き downgrade／criteria 並存 broaden／
  想定外型）を deploy の**手前で**ゲートする（downgrade・想定外型は --ack-downgrade なしで停止）。
  詳細は設計メモ §3.1 step5・§4-3-a、コマンドは `sharing-precheck`／`sharing-deploy`。

設計原則:
- org は3カテゴリ（本番 / 保護=トライアル・検証 / 使い捨て=sandbox・scratch）で扱う。
    * 本番（PROD_ALIAS_HINTS）  : deploy は --approved-by 必須＋承認ログ。NoTestRun 不可。
    * 保護（PROTECTED_ALIAS_HINTS）: PSA/IMA 導入済みトライアル等。deploy は --confirm 必須。
                                      着手前に retrieve バックアップ推奨（失効・破壊対策）。
    * 使い捨て                 : 制約なし。
- 「現状前提」を retrieve→diff で機械的に担保する。--json 出力を解析し成功/差分を判定する。
- マネージドパッケージ（tb_PSA__ / tb_IMA__）の改変不可境界はオーサリング側で守る。
  本スクリプトは運搬（retrieve/diff/checkonly/deploy/verify）に責務を限定する。

依存: sf CLI v2（`sf --version`）。sf CLI が認証済み org にアクセスできるローカル環境で実行する。

使用例（<org> は自組織の org エイリアスに置換）:
    python3 tb_mdconfig.py retrieve   --org <org> --metadata "CustomField:tb_PSA__tb_SalesOrder__c.MyField__c" --output-dir backup_before
    python3 tb_mdconfig.py diff       --org <org> --source-dir force-app
    python3 tb_mdconfig.py checkonly  --org <org> --source-dir force-app             # 成功時に job-id を表示
    python3 tb_mdconfig.py deploy     --org <trial-org> --source-dir force-app --confirm  # 保護orgは確認必須
    python3 tb_mdconfig.py quick      --org <prod-org>  --job-id 0Af... --approved-by "承認者名"  # 本番は承認必須
    python3 tb_mdconfig.py verify     --org <org> --metadata "CustomField:..." --target-dir force-app
    # Apex（トリガ＋テスト）: 対象を絞り RunSpecifiedTests で自テストのみ実行（Apex トリガー種別）
    python3 tb_mdconfig.py checkonly  --org <org> --metadata "ApexTrigger:MyTrg" "ApexClass:MyTrgTest" --test-level RunSpecifiedTests --tests MyTrgTest
    python3 tb_mdconfig.py quick      --org <org> --job-id 0Af... --confirm  # テスト実行済み検証ジョブ→再実行なしで投入
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
import shutil
import subprocess
import sys

# 同階層の tb_sharing.py（author 段・衝突プリチェック本体）を import する。
# org 段（本ファイル）は retrieve/checkonly/deploy/verify を担い、authoring・衝突検知ロジックは
# tb_sharing に一元化する（二重管理を避ける・設計メモ §3.1 step4/step5・§7）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import tb_sharing  # type: ignore
except ImportError:  # pragma: no cover - 同階層に無い異常時のみ
    tb_sharing = None

# 本番とみなす org エイリアスの接頭辞。deploy/quick は --approved-by（承認ゲート）必須・NoTestRun 不可。
# 自組織の本番 alias 命名に合わせて追加する。
PROD_ALIAS_HINTS = ("prod", "production", "本番")
# 保護（トライアル・検証）org の接頭辞。PSA/IMA 導入済みで破壊困難・失効近い。deploy/quick は --confirm 必須。
# 自組織の検証 org エイリアスをここに追加する（例: 自社のトライアル org 名の一部）。
PROTECTED_ALIAS_HINTS = ("trial", "uat", "sit")

APPROVAL_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deploy_approval.log")


def run_json(cmd: list[str], dry: bool = False) -> tuple[int, dict | None]:
    """sf CLI コマンドを実行し (returncode, parsed_json) を返す。dry=True なら表示のみ。"""
    print(f"$ {' '.join(cmd)}")
    if dry:
        return 0, None
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0 and proc.stderr:
        print(proc.stderr, file=sys.stderr)
    payload: dict | None = None
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        payload = None
    return proc.returncode, payload


def is_prod(alias: str) -> bool:
    a = alias.lower()
    return any(h in a for h in PROD_ALIAS_HINTS)


def is_protected(alias: str) -> bool:
    a = alias.lower()
    return any(h in a for h in PROTECTED_ALIAS_HINTS)


def _gate_deploy(args: argparse.Namespace) -> int | None:
    """deploy/quick 共通の承認・確認ゲート。通過なら None、拒否なら exit code。"""
    if is_prod(args.org):
        if not getattr(args, "approved_by", None):
            print("[BLOCKED] 本番 org への deploy は --approved-by '承認者' が必須です"
                  "（本番デプロイ承認ゲート）。", file=sys.stderr)
            return 3
        if getattr(args, "test_level", None) == "NoTestRun":
            print("[BLOCKED] 本番 org では --test-level NoTestRun は使用できません。", file=sys.stderr)
            return 3
        with open(APPROVAL_LOG, "a", encoding="utf-8") as f:
            f.write(f"{_dt.datetime.now().isoformat()}\torg={args.org}\tapproved_by={args.approved_by}\t"
                    f"source={getattr(args, 'source_dir', '')}{getattr(args, 'job_id', '')}\n")
        print(f"[approval] 本番デプロイ承認者: {args.approved_by}（ログ: {APPROVAL_LOG}）")
    elif is_protected(args.org):
        if not getattr(args, "confirm", False):
            print(f"[BLOCKED] 保護（トライアル・検証）org '{args.org}' への deploy は --confirm が必須です。"
                  "破壊・失効に備え retrieve バックアップを取り、checkonly 成功を確認のうえ実行してください。",
                  file=sys.stderr)
            return 3
        print(f"[confirm] 保護 org への deploy を確認: {args.org}")
    return None


def cmd_create_sandbox(args: argparse.Namespace) -> int:
    """本番（または sandbox ライセンスを持つ org）から開発用 sandbox を作成する。
    注意: トライアル org は sandbox ライセンスを持たず作成不可。本番/EE 等でのみ有効。"""
    cmd = [
        "sf", "org", "create", "sandbox",
        "--name", args.name,
        "--license-type", args.license_type,
        "--target-org", args.prod_alias,
        "--alias", args.name,
        "--wait", str(args.wait),
        "--json",
    ]
    rc, _ = run_json(cmd, args.dry_run)
    return rc


def cmd_create_scratch(args: argparse.Namespace) -> int:
    cmd = [
        "sf", "org", "create", "scratch",
        "--definition-file", args.definition_file,
        "--alias", args.name,
        "--duration-days", str(args.duration_days),
        "--wait", str(args.wait),
        "--json",
    ]
    rc, _ = run_json(cmd, args.dry_run)
    return rc


def cmd_retrieve(args: argparse.Namespace) -> int:
    """現状のメタデータを org から取得する（diff の基準＝現状前提の担保・バックアップ）。
    --output-dir 指定時はそこへ取得し、ローカル force-app を上書きしない（verify/backup 用途）。"""
    cmd = ["sf", "project", "retrieve", "start", "--target-org", args.org, "--wait", str(args.wait), "--json"]
    if args.metadata:
        cmd += ["--metadata", args.metadata]
    elif args.manifest:
        cmd += ["--manifest", args.manifest]
    elif args.source_dir:
        cmd += ["--source-dir", args.source_dir]
    else:
        print("[error] --metadata / --manifest / --source-dir のいずれかが必要", file=sys.stderr)
        return 2
    if getattr(args, "output_dir", None):
        cmd += ["--output-dir", args.output_dir]
    rc, _ = run_json(cmd, args.dry_run)
    return rc


def _summarize_preview(payload: dict | None) -> None:
    """deploy preview の JSON から変更件数を要約表示する。"""
    if not payload:
        return
    res = payload.get("result", {})
    to_deploy = res.get("toDeploy", res.get("toBeDeployed", []))
    conflicts = res.get("conflicts", [])
    if isinstance(to_deploy, list):
        print(f"[diff] デプロイ対象: {len(to_deploy)} 件 / コンフリクト: {len(conflicts) if isinstance(conflicts, list) else conflicts} 件")
        if len(to_deploy) == 0:
            print("[diff] 変更なし（org 現状と一致）")


def cmd_diff(args: argparse.Namespace) -> int:
    """ローカル（オーサリング後）と org 現状の差分プレビュー。
    使い捨て org は source-tracking で正確。保護（トライアル＝非トラッキング）org では
    conflict 検出が限定的なため、retrieve→ローカル diff フォールバックを併用する。"""
    cmd = ["sf", "project", "deploy", "preview", "--target-org", args.org, "--json"]
    if args.source_dir:
        cmd += ["--source-dir", args.source_dir]
    elif args.manifest:
        cmd += ["--manifest", args.manifest]
    rc, payload = run_json(cmd, args.dry_run)
    if rc != 0:
        print("[hint] preview が非対応/エラーの場合、`retrieve --output-dir tmp_now` 後に "
              "`diff -r tmp_now <source-dir>` でローカル差分を取ってください（非トラッキング org フォールバック）。",
              file=sys.stderr)
    else:
        _summarize_preview(payload)
    return rc


def _print_job_id(payload: dict | None) -> None:
    if not payload:
        return
    job_id = payload.get("result", {}).get("id")
    if job_id:
        print(f"[checkonly] 検証ジョブ ID: {job_id} （本番投入は `quick --job-id {job_id}`）")


def cmd_checkonly(args: argparse.Namespace) -> int:
    """checkonly（validation）デプロイ。本デプロイ前に必ず通す。
    --dry-run 単体では Apex テストが走らない。Apex を含む場合は --test-level を明示する。"""
    cmd = ["sf", "project", "deploy", "start", "--dry-run",
           "--target-org", args.org, "--wait", str(args.wait), "--json"]
    if args.metadata:
        cmd += ["--metadata", *args.metadata]
    elif args.manifest:
        cmd += ["--manifest", args.manifest]
    elif args.source_dir:
        cmd += ["--source-dir", args.source_dir]
    if args.test_level:
        cmd += ["--test-level", args.test_level]
        if args.test_level == "RunSpecifiedTests" and args.tests:
            cmd += ["--tests", *args.tests]
    rc, payload = run_json(cmd, args.dry_run)
    if rc == 0:
        _print_job_id(payload)
    return rc


def _resolve_finalize_bug(rc: int, payload: dict | None, org: str, dry: bool) -> int:
    """sf CLI 2.93.7 の finalize メッセージ欠落バグ対策。
    deploy が exit!=0 でも payload が MetadataTransferError(Finalizing メッセージ欠落)なら、
    これは表示バグでサーバー側は成功していることがある。job-id で deploy report を実行し実判定する。
    """
    if rc == 0 or not payload:
        return rc
    msg = str(payload.get("message", ""))
    name = payload.get("name", "")
    job_id = (payload.get("data") or {}).get("id")
    if name == "MetadataTransferError" and "Finalizing" in msg and job_id:
        print(f"[finalize-bug] CLI finalize メッセージ欠落バグを検出。job-id {job_id} の実ステータスを確認します。")
        rcr, rep = run_json(
            ["sf", "project", "deploy", "report", "--job-id", job_id,
             "--target-org", org, "--json"], dry)
        res = (rep or {}).get("result", {})
        status = res.get("status")
        errs = res.get("numberComponentErrors")
        print(f"[finalize-bug] deploy report: status={status} numberComponentErrors={errs}")
        if status == "Succeeded" and not errs:
            print("[finalize-bug] サーバー側デプロイは成功（CLI exit は表示バグ）。")
            return 0
        return rcr or 1
    return rc


def cmd_deploy(args: argparse.Namespace) -> int:
    """本デプロイ。本番は --approved-by（承認ゲート）必須、保護 org は --confirm 必須。"""
    gate = _gate_deploy(args)
    if gate is not None:
        return gate
    cmd = ["sf", "project", "deploy", "start",
           "--target-org", args.org, "--wait", str(args.wait), "--json"]
    if args.metadata:
        cmd += ["--metadata", *args.metadata]
    elif args.manifest:
        cmd += ["--manifest", args.manifest]
    elif args.source_dir:
        cmd += ["--source-dir", args.source_dir]
    if args.test_level:
        cmd += ["--test-level", args.test_level]
        if args.test_level == "RunSpecifiedTests" and args.tests:
            cmd += ["--tests", *args.tests]
    rc, payload = run_json(cmd, args.dry_run)
    return _resolve_finalize_bug(rc, payload, args.org, args.dry_run)


def cmd_quick(args: argparse.Namespace) -> int:
    """checkonly 成功時の job-id を使い、テスト再実行なしで高速デプロイする。
    本番は --approved-by 必須、保護 org は --confirm 必須。
    注意: quick はテストを実行した検証ジョブにしか使えない。Apex 無しの checkonly は
    テスト0件のため CannotQuickDeployError になる → その場合は通常 `deploy` を使う。"""
    gate = _gate_deploy(args)
    if gate is not None:
        return gate
    cmd = ["sf", "project", "deploy", "quick", "--job-id", args.job_id,
           "--target-org", args.org, "--wait", str(args.wait), "--json"]
    rc, payload = run_json(cmd, args.dry_run)
    if rc != 0 and payload and payload.get("name") == "CannotQuickDeployError":
        print("[hint] quick は不可（検証でテストが走っていない）。Apex を含まない変更は "
              "`deploy --source-dir force-app` の通常デプロイを使ってください。", file=sys.stderr)
        return rc
    return _resolve_finalize_bug(rc, payload, args.org, args.dry_run)


def cmd_verify(args: argparse.Namespace) -> int:
    """デプロイ結果を非破壊で突合する。別ディレクトリへ retrieve し、目標と差分0を確認。
    ローカルの目標 XML（force-app）を上書きしない。"""
    verify_dir = args.output_dir or "tmp_verify"
    cmd = ["sf", "project", "retrieve", "start", "--target-org", args.org,
           "--wait", str(args.wait), "--output-dir", verify_dir, "--json"]
    if args.metadata:
        cmd += ["--metadata", args.metadata]
    elif args.manifest:
        cmd += ["--manifest", args.manifest]
    else:
        print("[error] verify には --metadata または --manifest が必要", file=sys.stderr)
        return 2
    rc, _ = run_json(cmd, args.dry_run)
    if rc == 0 and args.target_dir and not args.dry_run:
        print(f"[verify] `diff -r {args.target_dir} {verify_dir}` で目標との差分0を確認してください。")
        dproc = subprocess.run(["diff", "-r", args.target_dir, verify_dir], capture_output=True, text=True)
        if dproc.returncode == 0:
            print("[verify] OK: 目標とデプロイ結果が一致（差分0）")
        else:
            print("[verify] 差分あり:\n" + dproc.stdout)
            return 1
    return rc


# ── 共有モデル設定（SharingRules）: 衝突プリチェックの org 段組込み（v1.5・設計メモ §3.1）──
# tb_sharing.py（author 段）を org 中核ループへ差し込む。checkonly が捕捉しない access 変化
# （owner の (sharedFrom,sharedTo) silent 上書き downgrade／criteria 並存 broaden／想定外型）を
# deploy の手前でゲートする＝access 変化に対する唯一の「事前」防御点（§1.6・§4-3-a）。

SHARING_SUBPATH = os.path.join("main", "default", "sharingRules")


def _require_tb_sharing() -> int | None:
    if tb_sharing is None:
        print("[error] tb_sharing.py が同階層に見つかりません（共有モデル設定コマンドに必須）。",
              file=sys.stderr)
        return 2
    return None


def _find_sharing_xml(base_dir: str, obj: str) -> str | None:
    """base_dir 配下から {obj}.sharingRules-meta.xml を再帰探索し最初の一致を返す。

    retrieve 出力は SFDX レイアウト（force-app/main/default/sharingRules/…）だが、
    フラット配置・別ルートも許容するため glob で頑健に解決する。無ければ None。
    """
    if not base_dir or not os.path.isdir(base_dir):
        return None
    direct = os.path.join(base_dir, SHARING_SUBPATH, f"{obj}.sharingRules-meta.xml")
    if os.path.exists(direct):
        return direct
    flat = os.path.join(base_dir, f"{obj}.sharingRules-meta.xml")
    if os.path.exists(flat):
        return flat
    hits = glob.glob(os.path.join(base_dir, "**", f"{obj}.sharingRules-meta.xml"), recursive=True)
    return hits[0] if hits else None


def _load_existing_sharing(existing_dir: str, objects: list[str]) -> dict[str, str]:
    """object → 既存 SharingRules XML（retrieve 済み）を読み込む。

    ファイルが無い object は「既存ルールなし」＝空文字（→衝突なし・追記のみ）。
    retrieve で SharingRules が存在しない object は出力ファイルが出ないのが正常挙動。
    """
    existing: dict[str, str] = {}
    for obj in objects:
        path = _find_sharing_xml(existing_dir, obj)
        if path:
            with open(path, encoding="utf-8") as f:
                existing[obj] = f.read()
        else:
            existing[obj] = ""
    return existing


def _project_columns(
    header: list[str], data: list[list[str]], objects: list[str]
) -> tuple[list[str], list[list[str]]]:
    """header/data を objects の列だけに射影する（キー列 [0:2] は保持）。

    衝突判定・生成の下位関数（tb_sharing.precheck_csv／generate_from_csv／unverified_shapes_csv）は
    「ヘッダ内の位置＝データ列の位置」（`row[idx + 2]`）を前提にする。したがって header を objects で
    絞る場合、data 側も同じ列を同じ順序で抜き出さないと obj とセルの対応がズレ、誤った access の
    ルール生成・衝突ゲートの誤判定を招く（最上位ブラストレンジの安全ゲートに直結・要修正1）。
    ここで header と data を同じ添字系で射影して整合させる。objects は header[2:] のサブセットで
    与えられる想定（_objects_from_args がヘッダ順で返す）。
    """
    col_index = {obj: i + 2 for i, obj in enumerate(header[2:])}
    sub_header = header[:2] + objects
    sub_data: list[list[str]] = []
    for row in data:
        new_row = list(row[:2])
        for obj in objects:
            j = col_index[obj]
            new_row.append(row[j] if j < len(row) else "")
        sub_data.append(new_row)
    return sub_header, sub_data


def _clear_dir(path: str) -> None:
    """author-merge の出力先を実行前に空にする（前回実行の残骸ルールを押し込まないため・軽微3）。"""
    if path and os.path.isdir(path):
        shutil.rmtree(path)


def _sharing_precheck_core(
    existing: dict[str, str], header: list[str], data: list[list[str]], pkg_installed: str
) -> tuple[dict, list[str], bool, bool]:
    """衝突プリチェックを実行し (conflicts_by_obj, unverified, has_downgrade, has_unverified) を返す。"""
    conflicts = tb_sharing.precheck_csv(existing, header, data, pkg_installed)
    unverified = tb_sharing.unverified_shapes_csv(existing, header)
    has_down = any(c.direction == "downgrade" for cs in conflicts.values() for c in cs)
    return conflicts, unverified, has_down, bool(unverified)


def _print_precheck(conflicts: dict, unverified: list[str]) -> None:
    lines = tb_sharing.render_conflicts_readable(conflicts)
    if not lines and not unverified:
        print("[precheck] 衝突なし（既存共有先と重複する追記はありません）")
        return
    if lines:
        print("[precheck] === 衝突プリチェック（access 変化・checkonly では捕捉されない）===")
        for line in lines:
            print("  " + line)
    if unverified:
        print("[precheck] === 想定外の型（自動判定不可・人手確認が必要）===")
        for w in unverified:
            print("  ⚠ " + w)
    print("[precheck] ※ この差分は checkonly（--dry-run）では success になり捕捉されません"
          "（deploy 前に承認が必要・§4-3-a）。")


def _objects_from_args(header: list[str], filt: list[str] | None) -> list[str]:
    cols = header[2:]
    if not filt:
        return cols
    wanted = set(filt)
    return [o for o in cols if o in wanted or tb_sharing.remove_ns(o) in wanted]


def cmd_sharing_precheck(args: argparse.Namespace) -> int:
    """共有モデル設定の step5 ゲート（org 非依存）。

    retrieve 済み現状 XML ディレクトリ（--existing-dir）と CSV から衝突・想定外型を検出する。
    exit: downgrade または想定外型あり=2（要人手承認）／その他の衝突（upgrade・broaden・redundant）=1／衝突なし=0。
    tb_mdconfig.py に置くことで retrieve→precheck→checkonly→deploy→verify を本ハーネスで一貫実行できる。
    """
    err = _require_tb_sharing()
    if err is not None:
        return err
    header, data = tb_sharing.load_csv(args.csvfile, args.pkg_installed)
    objects = _objects_from_args(header, args.objects)
    if not objects:
        print("[error] --objects が CSV ヘッダのオブジェクト列と一致しません（対象0件）。", file=sys.stderr)
        return 2
    existing = _load_existing_sharing(args.existing_dir, objects)
    # 対象列を objects に絞る際、header と data を同じ添字系で射影して整合させる（要修正1）。
    sub_header, sub_data = _project_columns(header, data, objects)
    conflicts, unverified, has_down, has_unv = _sharing_precheck_core(
        existing, sub_header, sub_data, args.pkg_installed)
    _print_precheck(conflicts, unverified)
    return 2 if (has_down or has_unv) else (1 if conflicts else 0)


def _author_merge(
    existing: dict[str, str], header: list[str], data: list[list[str]],
    pkg_installed: str, source_dir: str
) -> dict[str, str]:
    """現状 buffer（existing）へ CSV を追記し SFDX レイアウトへ書き出す（§3.1 step4）。

    単体ファイル（existing={}）を org へ直接 deploy しない＝必ず retrieve 済み buffer へ merge する
    （owner 衝突の silent 上書きを事前検知するため・§4-3-b）。挿入は XSD グルーピングを守る
    （tb_sharing._insert_rule）。返り値は object → merged XML。
    """
    buffers = tb_sharing.generate_from_csv(header, data, pkg_installed, existing)
    out_dir = os.path.join(source_dir, SHARING_SUBPATH)
    os.makedirs(out_dir, exist_ok=True)
    for obj, xml in buffers.items():
        with open(os.path.join(out_dir, f"{obj}.sharingRules-meta.xml"), "w", encoding="utf-8") as f:
            f.write(xml)
    return buffers


def cmd_sharing_deploy(args: argparse.Namespace) -> int:
    """SharingRules 専用の中核ループを一貫実行する（v1.5・設計メモ §3.1）。

    retrieve（現状）→ author-merge（現状 buffer へ追記・XSD グルーピング）→ 衝突プリチェック（ゲート）
    → checkonly → deploy（本番=--approved-by／保護=--confirm）→ verify。
    downgrade・想定外型は --ack-downgrade なしで停止（exit 3）＝checkonly でも本デプロイでも
    エラーにならない access 縮小・過剰共有を人手承認の手前でブロックする（§4-3-a）。
    """
    err = _require_tb_sharing()
    if err is not None:
        return err
    header, data = tb_sharing.load_csv(args.csvfile, args.pkg_installed)
    objects = _objects_from_args(header, args.objects)
    if not objects:
        print("[error] --objects が CSV ヘッダのオブジェクト列と一致しません（対象0件）。", file=sys.stderr)
        return 2
    backup_dir = args.backup_dir or "tmp_sharing_backup"
    source_dir = args.source_dir or "tmp_sharing_authored"

    # 1) retrieve（現状・バックアップ兼ロールバック資産）
    print("[sharing-deploy] 1/6 retrieve（現状 SharingRules を取得）")
    rcmd = ["sf", "project", "retrieve", "start", "--target-org", args.org,
            "--wait", str(args.wait), "--output-dir", backup_dir, "--json"]
    for obj in objects:
        rcmd += ["--metadata", f"SharingRules:{obj}"]
    rc, _ = run_json(rcmd, args.dry_run)
    if rc != 0 and not args.dry_run:
        print("[sharing-deploy] retrieve に失敗しました。中断します。", file=sys.stderr)
        return rc

    # 2) author-merge（現状 buffer へ追記・XSD グルーピング遵守）
    print("[sharing-deploy] 2/6 author-merge（現状へ追記・単体ファイルを直接 deploy しない）")
    existing = _load_existing_sharing(backup_dir, objects)
    if args.dry_run:
        print("[sharing-deploy] ※ --dry-run では retrieve が表示のみで現状 XML が未取得のため、"
              "以降の衝突プリチェックは既存ルールなし前提の参考値です（実ゲートは本実行で機能）。")
    # header/data を objects で射影して下位関数の位置前提とズレないようにする（要修正1）
    sub_header, sub_data = _project_columns(header, data, objects)
    _clear_dir(source_dir)  # 前回実行の残骸ルールを押し込まない（軽微3）
    _author_merge(existing, sub_header, sub_data, args.pkg_installed, source_dir)

    # 3) 衝突プリチェック（ゲート・checkonly の穴を埋める唯一の事前防御点）
    print("[sharing-deploy] 3/6 衝突プリチェック（access 変化の事前検知・ゲート）")
    conflicts, unverified, has_down, has_unv = _sharing_precheck_core(
        existing, sub_header, sub_data, args.pkg_installed)
    _print_precheck(conflicts, unverified)
    if (has_down or has_unv) and not args.ack_downgrade:
        print("[BLOCKED] downgrade（access 縮小＝業務停止）または想定外の型を検出しました。"
              "内容を承認のうえ --ack-downgrade を付けて再実行してください（§4-3-a）。",
              file=sys.stderr)
        return 3
    if (has_down or has_unv) and args.ack_downgrade:
        print("[ack] downgrade／想定外型を承認済みとして続行します（--ack-downgrade）。")

    # 4) checkonly（メタデータ妥当性のみ担保）
    print("[sharing-deploy] 4/6 checkonly（メタデータ妥当性の検証デプロイ）")
    ccmd = ["sf", "project", "deploy", "start", "--dry-run", "--target-org", args.org,
            "--wait", str(args.wait), "--source-dir", source_dir, "--json"]
    rc, payload = run_json(ccmd, args.dry_run)
    if rc != 0 and not args.dry_run:
        print("[sharing-deploy] checkonly 失敗（メタデータ不正の可能性）。中断します。", file=sys.stderr)
        return rc
    _print_job_id(payload)

    # 5) deploy（本番=--approved-by／保護=--confirm ゲート）
    print("[sharing-deploy] 5/6 deploy（本デプロイ・§7.C 承認）")
    args.source_dir = source_dir  # _gate_deploy の承認ログ用
    gate = _gate_deploy(args)
    if gate is not None:
        return gate
    dcmd = ["sf", "project", "deploy", "start", "--target-org", args.org,
            "--wait", str(args.wait), "--source-dir", source_dir, "--json"]
    rc, payload = run_json(dcmd, args.dry_run)
    rc = _resolve_finalize_bug(rc, payload, args.org, args.dry_run)
    if rc != 0 and not args.dry_run:
        print("[sharing-deploy] deploy 失敗。retrieve 済み現状（"
              f"{backup_dir}）の再デプロイで復元してください（復元ランブック・§4-3-d）。", file=sys.stderr)
        return rc

    # 6) verify（別ディレクトリ再 retrieve・衝突対象の access が意図せず縮小していないか）
    print("[sharing-deploy] 6/6 verify（再 retrieve で反映と非縮小を確認）")
    vcmd = ["sf", "project", "retrieve", "start", "--target-org", args.org,
            "--wait", str(args.wait), "--output-dir", (args.verify_dir or "tmp_sharing_verify"), "--json"]
    for obj in objects:
        vcmd += ["--metadata", f"SharingRules:{obj}"]
    rcv, _ = run_json(vcmd, args.dry_run)
    if rcv != 0 and not args.dry_run:
        print("[sharing-deploy] ⚠ verify の再 retrieve に失敗しました。反映と access 非縮小を"
              "手動で確認してください（deploy 自体は完了しています）。", file=sys.stderr)
    print("[sharing-deploy] 完了。verify ディレクトリで意図したルールの実在と、"
          "衝突対象だった既存ルールの access 非縮小を確認してください（§3.1 step8）。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ti-metadata メタデータ設定ハーネス（PSA/IMA 整合）")
    p.add_argument("--dry-run", action="store_true", help="コマンドを実行せず表示のみ")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("create-sandbox", help="開発用 sandbox を作成（トライアル org は不可）")
    s.add_argument("--prod-alias", required=True, help="source（本番/sandbox ライセンス保有）org エイリアス")
    s.add_argument("--name", required=True, help="sandbox 名/エイリアス")
    s.add_argument("--license-type", default="Developer")
    s.add_argument("--wait", type=int, default=30)
    s.set_defaults(func=cmd_create_sandbox)

    s = sub.add_parser("create-scratch", help="scratch org を作成")
    s.add_argument("--definition-file", default="config/project-scratch-def.json")
    s.add_argument("--name", required=True)
    s.add_argument("--duration-days", type=int, default=7)
    s.add_argument("--wait", type=int, default=10)
    s.set_defaults(func=cmd_create_scratch)

    s = sub.add_parser("retrieve", help="現状メタデータ取得（--output-dir でバックアップ）")
    s.add_argument("--org", required=True)
    s.add_argument("--metadata", help="例: CustomField:tb_PSA__tb_SalesOrder__c.MyField__c")
    s.add_argument("--manifest")
    s.add_argument("--source-dir")
    s.add_argument("--output-dir", help="取得先ディレクトリ（指定で force-app 非上書き）")
    s.add_argument("--wait", type=int, default=30)
    s.set_defaults(func=cmd_retrieve)

    s = sub.add_parser("verify", help="非破壊突合（別ディレクトリ retrieve＋差分0判定）")
    s.add_argument("--org", required=True)
    s.add_argument("--metadata")
    s.add_argument("--manifest")
    s.add_argument("--target-dir", help="目標 force-app（diff -r 比較対象）")
    s.add_argument("--output-dir", help="検証取得先（既定 tmp_verify）")
    s.add_argument("--wait", type=int, default=30)
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("diff", help="org に対する変更プレビュー")
    s.add_argument("--org", required=True)
    s.add_argument("--source-dir", default="force-app")
    s.add_argument("--manifest")
    s.set_defaults(func=cmd_diff)

    s = sub.add_parser("checkonly", help="checkonly（validation）デプロイ・job-id 表示")
    s.add_argument("--org", required=True)
    s.add_argument("--source-dir", default="force-app")
    s.add_argument("--manifest")
    s.add_argument("--metadata", nargs="+", help="対象を絞る（複数可）。例: ApexTrigger:MyTrg ApexClass:MyTrgTest")
    s.add_argument("--test-level", help="NoTestRun(非本番のみ) / RunLocalTests / RunAllTestsInOrg / RunSpecifiedTests")
    s.add_argument("--tests", nargs="+", help="RunSpecifiedTests のとき実行するテストクラス（複数可）")
    s.add_argument("--wait", type=int, default=30)
    s.set_defaults(func=cmd_checkonly)

    s = sub.add_parser("deploy", help="本デプロイ（本番=--approved-by / 保護=--confirm 必須）")
    s.add_argument("--org", required=True)
    s.add_argument("--source-dir", default="force-app")
    s.add_argument("--manifest")
    s.add_argument("--metadata", nargs="+", help="対象を絞る（複数可）。例: ApexTrigger:MyTrg ApexClass:MyTrgTest")
    s.add_argument("--test-level", help="NoTestRun(非本番のみ) / RunLocalTests / RunAllTestsInOrg / RunSpecifiedTests")
    s.add_argument("--tests", nargs="+", help="RunSpecifiedTests のとき実行するテストクラス（複数可）")
    s.add_argument("--wait", type=int, default=30)
    s.add_argument("--approved-by", help="本番デプロイ承認者（承認ゲート）。本番 org には必須")
    s.add_argument("--confirm", action="store_true", help="保護（トライアル）org への deploy 確認")
    s.set_defaults(func=cmd_deploy)

    s = sub.add_parser("quick", help="checkonly job-id で高速デプロイ（テスト再実行なし）")
    s.add_argument("--org", required=True)
    s.add_argument("--job-id", required=True, help="checkonly が返した検証ジョブ ID")
    s.add_argument("--wait", type=int, default=30)
    s.add_argument("--approved-by", help="本番デプロイ承認者（承認ゲート）。本番 org には必須")
    s.add_argument("--confirm", action="store_true", help="保護（トライアル）org への deploy 確認")
    s.set_defaults(func=cmd_quick)

    # 共有モデル設定（SharingRules）専用（v1.5・設計メモ §3.1）
    s = sub.add_parser("sharing-precheck",
                       help="共有ルールの衝突プリチェック（step5・org 非依存ゲート）")
    s.add_argument("--csvfile", required=True, help="共有ルール CSV（可読ルールから生成される裏の中間物）")
    s.add_argument("--existing-dir", dest="existing_dir", required=True,
                   help="retrieve 済み現状 XML ディレクトリ（SFDX レイアウト可）")
    s.add_argument("--pkg-installed", dest="pkg_installed", default="1", choices=["0", "1"])
    s.add_argument("--objects", nargs="+", help="対象オブジェクトを絞る（既定は CSV ヘッダ全列）")
    s.set_defaults(func=cmd_sharing_precheck)

    s = sub.add_parser("sharing-deploy",
                       help="SharingRules 中核ループ（retrieve→author-merge→precheck→checkonly→deploy→verify）")
    s.add_argument("--org", required=True)
    s.add_argument("--csvfile", required=True, help="共有ルール CSV（可読ルールから生成される裏の中間物）")
    s.add_argument("--pkg-installed", dest="pkg_installed", default="1", choices=["0", "1"])
    s.add_argument("--objects", nargs="+", help="対象オブジェクトを絞る（既定は CSV ヘッダ全列）")
    s.add_argument("--backup-dir", dest="backup_dir", help="現状 retrieve 先（既定 tmp_sharing_backup・ロールバック資産）")
    s.add_argument("--source-dir", dest="source_dir", help="author-merge 出力先（既定 tmp_sharing_authored）")
    s.add_argument("--verify-dir", dest="verify_dir", help="verify 再 retrieve 先（既定 tmp_sharing_verify）")
    s.add_argument("--ack-downgrade", dest="ack_downgrade", action="store_true",
                   help="downgrade／想定外型を承認済みとして続行（無指定なら停止）")
    s.add_argument("--approved-by", help="本番デプロイ承認者（承認ゲート）。本番 org には必須")
    s.add_argument("--confirm", action="store_true", help="保護（トライアル）org への deploy 確認")
    s.add_argument("--wait", type=int, default=30)
    s.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="org 呼出しを表示のみ（ローカルの author-merge・precheck ゲートは実行）")
    s.set_defaults(func=cmd_sharing_deploy)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
