#!/usr/bin/env python3
"""tb_sharing.py — 共有モデル設定（SharingRules）の author 段（案B・Python 再実装）v0.3

設計: 共有モデル設定（SharingRules／OWD）の author 段・org 段。

役割（org 非依存の author のみ・§3.0 / §3.1 step4・step5）:
  1. 可読ルール（可視範囲ポリシー）→ 従来 CSV（正本実装互換スキーマ）へ翻訳
  2. CSV → SharingRules XML 生成（正本実装の XML 追記処理を構造等価で移植）
  3. 衝突プリチェック（§3.1 step5・§4-3-a）＝retrieve 済み現状 XML に対して
     追記ルールの (sharedFrom, sharedTo)〔criteria は (sharedTo, field, value)〕衝突を検出し、
     access 差分（downgrade＝過少共有／upgrade＝過剰共有）を可読ルールへ提示する。
     ※ 保護org実測（§1.6）で owner rule は (sharedFrom,sharedTo) で SF が
       一意化し、衝突追記が既存 access を silent 縮小（Edit→Read）・checkonly は非捕捉 と確定。
       checkonly では捕捉できないため本段が access 変化に対する唯一の「事前」防御点。
  4. 可読ルール（業務語のルール文＋帰結注記）の出力
  5. ゴールデン比較用の正規化（非決定要素＝ルール名 TB+hex16 / 日付 を placeholder 化）

org に触れる段（retrieve / checkonly / deploy / verify）は tb_mdconfig.py に委譲する
（ブラストレンジ物理分離＝§4-1 / §7）。本モジュールは XML を作る・解析するだけで org へは書かない。
SharingRules deploy は REPLACE 意味論（安全側仮定・§1.6-2）ゆえ org 適用は必ず
「現状 retrieve → その buffer へ追記 → deploy」とする（単体ファイルを org へ直接 deploy しない）。

正本オラクル: PSA パッケージ標準の共有ルール一括デプロイ実装（以下「正本実装」）。
  CI で正本を回したゴールデン XML と本モジュール出力を normalize 後に構造等価比較する（§5）。
"""
from __future__ import annotations

import argparse
import csv as _csv
import datetime as _dt
import json
import os
import re
import secrets
import sys
import xml.etree.ElementTree as _ET
from dataclasses import dataclass, field

# ── 正本実装と一致させる定数（テンプレ・特例）─────────────────────
# 各行は Ruby heredoc の字下げ（4 / 8 スペース）を忠実に再現する。

CRITERIA_TEMPLATE = (
    "    <sharingCriteriaRules>\n"
    "        <fullName>REPLACE_NAME</fullName>\n"
    "        <accessLevel>REPLACE_LEVEL</accessLevel>\n"
    "        <description>REPLACE_DESC</description>\n"
    "        <label>REPLACE_LABEL</label>\n"
    "        <sharedTo>SHARED_TO</sharedTo>\n"
    "        <criteriaItems>\n"
    "            <field>{ns}tb_DepartmentCode__c</field>\n"
    "            <operation>equals</operation>\n"
    "            <value>REPLACE_DEPT</value>\n"
    "        </criteriaItems>\n"
    "        ACCOUNT_SETTINGS\n"
    "    </sharingCriteriaRules>\n"
)

OWNER_TEMPLATE = (
    "    <sharingOwnerRules>\n"
    "        <fullName>REPLACE_NAME</fullName>\n"
    "        <accessLevel>REPLACE_LEVEL</accessLevel>\n"
    "        <description>REPLACE_DESC</description>\n"
    "        <label>REPLACE_LABEL</label>\n"
    "        <sharedTo>SHARED_TO</sharedTo>\n"
    "        <sharedFrom>\n"
    "            <allInternalUsers></allInternalUsers>\n"
    "        </sharedFrom>\n"
    "        ACCOUNT_SETTINGS\n"
    "    </sharingOwnerRules>\n"
)

ACCOUNT_SETTINGS = (
    "        <accountSettings>\n"
    "            <caseAccessLevel>Read</caseAccessLevel>\n"
    "            <contactAccessLevel>Read</contactAccessLevel>\n"
    "            <opportunityAccessLevel>Read</opportunityAccessLevel>\n"
    "        </accountSettings>\n"
)

ACCOUNT_SETTINGS_PLACEHOLDER = "        ACCOUNT_SETTINGS\n"

EMPTY_SHARINGRULES = '<SharingRules xmlns="http://soap.sforce.com/2006/04/metadata"/>'
OPEN_SHARINGRULES = '<SharingRules xmlns="http://soap.sforce.com/2006/04/metadata">'
CLOSE_SHARINGRULES = "</SharingRules>"

ALL_INTERNAL_USER = "__ALL_INTERNAL_USER"

# 正規化（ゴールデン比較・非決定要素の消去）
_RULE_NAME_RE = re.compile(r"TB[0-9a-fA-F]{16}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ── 名前空間ヘルパ（正本実装の名前空間付与・除去 相当）──────
def ns_prefix(pkg_installed: int | str) -> str:
    return "tb_PSA__" if str(pkg_installed) == "1" else ""


def remove_ns(name: str) -> str:
    return name.replace("tb_PSA__", "")


def add_ns(name: str) -> str:
    return name if name.startswith("tb_PSA__") else f"tb_PSA__{name}"


def normalize_object_apiname(name: str, pkg_installed: int | str) -> str:
    """正本実装の XML 追記処理 冒頭の pkg_installed による object_apiname 正規化。"""
    if str(pkg_installed) == "0":
        return remove_ns(name)
    # pkg_installed == 1: tb_ 始まりのみ add_ns（Account 等はそのまま）
    return add_ns(name) if name.startswith("tb_") else name


# ── ルール XML 生成（正本実装のテンプレート展開 相当）────────────────
def _fill_rule(
    template: str,
    *,
    object_apiname: str,
    dest_group: str,
    crud: str,
    source_dept: str,
    ns: str,
    name: str,
    label: str,
    date: str,
) -> str:
    rule = template.format(ns=ns) if "{ns}" in template else template
    rule = rule.replace("REPLACE_NAME", name)
    rule = rule.replace("REPLACE_LEVEL", crud)
    rule = rule.replace(
        "REPLACE_DESC",
        f"この共有ルールはツバイソによりスクリプト実行で {date} にデプロイされました。",
    )
    rule = rule.replace("REPLACE_LABEL", label)
    rule = rule.replace("REPLACE_DEPT", source_dept)
    # 共有先
    if dest_group == ALL_INTERNAL_USER:
        rule = rule.replace("SHARED_TO", "<allInternalUsers></allInternalUsers>")
    else:
        rule = rule.replace("SHARED_TO", f"<group>{dest_group}</group>")
    # Account 特例（accountSettings ブロック）
    if object_apiname == "Account":
        rule = rule.replace(ACCOUNT_SETTINGS_PLACEHOLDER, ACCOUNT_SETTINGS)
    else:
        rule = rule.replace(ACCOUNT_SETTINGS_PLACEHOLDER, "")
    return rule


def build_rule(
    *,
    object_apiname: str,
    source_dept: str,
    dest_group: str,
    crud: str,
    pkg_installed: int | str,
    name: str | None = None,
    label: str | None = None,
    date: str | None = None,
) -> str:
    """1 セル分の共有ルール XML 断片を生成する。

    name/label/date を明示すると決定的に出力する（テスト・ゴールデン用）。
    省略時は Ruby 同様に非決定（TB+hex16 / 当日日付）。
    """
    ns = ns_prefix(pkg_installed)
    name = name if name is not None else "TB" + secrets.token_hex(8)
    label = label if label is not None else "TB" + secrets.token_hex(8)
    date = date if date is not None else _dt.datetime.now().strftime("%Y-%m-%d")
    template = OWNER_TEMPLATE if source_dept == ALL_INTERNAL_USER else CRITERIA_TEMPLATE
    return _fill_rule(
        template,
        object_apiname=object_apiname,
        dest_group=dest_group,
        crud=crud,
        source_dept=source_dept,
        ns=ns,
        name=name,
        label=label,
        date=date,
    )


def _idempotent_regex(*, is_owner: bool, crud: str, dest_group: str, source_dept: str) -> re.Pattern:
    """正本実装の冪等判定正規表現の移植（[^<>]* を保つ）。

    注意（Ruby と同じ既知エッジ）:
      - dest_group == __ALL_INTERNAL_USER のとき <group> が無いため決して一致しない
      - Account 行は accountSettings ブロックが末尾にあり、この regex が跨げないため一致しない
    これらは正本の挙動であり、構造等価のため意図的に再現する（補強は skill 側 checkonly/diff）。
    """
    c = re.escape(crud)
    d = re.escape(dest_group)
    s = re.escape(source_dept)
    if is_owner:
        pat = (
            r"<sharingOwnerRules>[^<>]*<fullName>[^<>]*</fullName>[^<>]*"
            r"<accessLevel>" + c + r"</accessLevel>[^<>]*<description>[^<>]*</description>[^<>]*"
            r"<label>[^<>]*</label>[^<>]*<sharedTo>[^<>]*<group>" + d + r"</group>[^<>]*</sharedTo>[^<>]*"
            r"<sharedFrom>[^<>]*<allInternalUsers></allInternalUsers>[^<>]*</sharedFrom>[^<>]*"
            r"</sharingOwnerRules>"
        )
    else:
        pat = (
            r"<sharingCriteriaRules>[^<>]*<fullName>[^<>]*</fullName>[^<>]*"
            r"<accessLevel>" + c + r"</accessLevel>[^<>]*<description>[^<>]*</description>[^<>]*"
            r"<label>[^<>]*</label>[^<>]*<sharedTo>[^<>]*<group>" + d + r"</group>[^<>]*</sharedTo>[^<>]*"
            r"<criteriaItems>[^<>]*<field>[^<>]*?tb_DepartmentCode__c</field>[^<>]*"
            r"<operation>equals</operation>[^<>]*<value>" + s + r"</value>[^<>]*</criteriaItems>[^<>]*"
            r"</sharingCriteriaRules>"
        )
    return re.compile(pat)


def _insert_rule(buffer: str, rule: str, *, is_owner: bool) -> str:
    """ルール断片を XSD 要素グルーピングを守って挿入する（保護org実測  で確定）。

    Metadata API の SharingRules は**同一種別の要素が隣接**していなければならず、
    retrieve した org XML は canonical 順（criteria 群 → owner 群）で返る。
    naive に `</SharingRules>` 直前へ挿入すると criteria を owner 群の後ろに置き
    `Element sharingCriteriaRules is duplicated at this location` で deploy 失敗する。
    → owner は末尾（owner 群）へ、criteria は既存 criteria 群の直後（無ければ owner 群の前）へ。
    """
    if EMPTY_SHARINGRULES in buffer:
        return buffer.replace(EMPTY_SHARINGRULES, OPEN_SHARINGRULES + "\n" + rule + CLOSE_SHARINGRULES)
    if is_owner:
        # owner 群は canonical で末尾 → 既存 owner と隣接する（criteria の後ろ）
        return buffer.replace(CLOSE_SHARINGRULES, rule + CLOSE_SHARINGRULES)
    # criteria: 既存 criteria 群の末尾へ（隣接維持）
    marker = "</sharingCriteriaRules>"
    idx = buffer.rfind(marker)
    if idx != -1:
        pos = idx + len(marker)
        if buffer[pos:pos + 1] == "\n":
            pos += 1
        return buffer[:pos] + rule + buffer[pos:]
    # criteria が無い → 最初の owner 群の直前へ（criteria を owner より前に）
    owner_open = "<sharingOwnerRules>"
    oidx = buffer.find(owner_open)
    if oidx != -1:
        line_start = buffer.rfind("\n", 0, oidx) + 1
        return buffer[:line_start] + rule + buffer[line_start:]
    return buffer.replace(CLOSE_SHARINGRULES, rule + CLOSE_SHARINGRULES)


def apply_cell(
    buffer: str,
    *,
    object_apiname: str,
    source_dept: str,
    dest_group: str,
    crud: str,
    pkg_installed: int | str,
    name: str | None = None,
    label: str | None = None,
    date: str | None = None,
) -> tuple[str, bool]:
    """既存 XML buffer に 1 セル分のルールを追記する（冪等・正本実装 相当）。

    返り値 (new_buffer, appended?)。既に同一ルールがあれば buffer 不変・appended=False。
    挿入は XSD 要素グルーピングを守る（`_insert_rule`・保護org実測で確定した必須要件）。
    """
    is_owner = source_dept == ALL_INTERNAL_USER
    if _idempotent_regex(is_owner=is_owner, crud=crud, dest_group=dest_group, source_dept=source_dept).search(buffer):
        return buffer, False
    rule = build_rule(
        object_apiname=object_apiname,
        source_dept=source_dept,
        dest_group=dest_group,
        crud=crud,
        pkg_installed=pkg_installed,
        name=name,
        label=label,
        date=date,
    )
    return _insert_rule(buffer, rule, is_owner=is_owner), True


# ── CSV ロード（正本実装の CSV ロード 相当）──────────────────────────
def load_csv(path: str, pkg_installed: int | str) -> tuple[list[str], list[list[str]]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(_csv.reader(f))
    return parse_csv_rows(rows, pkg_installed)


def parse_csv_rows(rows: list[list[str]], pkg_installed: int | str) -> tuple[list[str], list[list[str]]]:
    rows = [r for r in rows if r and not str(r[0]).startswith("#")]
    header = None
    data = []
    for r in rows:
        if str(r[0]).startswith("[HEADER]"):
            header = r
        else:
            data.append(r)
    if header is None:
        raise ValueError("ヘッダ行（[HEADER]）が見つかりません。")
    # ヘッダ列 3 列目以降のオブジェクト名を名前空間正規化（add_custom_ns 相当）
    norm_header = [header[0], header[1]] + [
        normalize_object_apiname(h, pkg_installed) for h in header[2:]
    ]
    return norm_header, data


def generate_from_csv(
    header: list[str],
    data: list[list[str]],
    pkg_installed: int | str,
    existing: dict[str, str] | None = None,
    *,
    deterministic: bool = False,
) -> dict[str, str]:
    """CSV（header, data）から object → SharingRules XML の dict を生成する。

    existing: object → 既存 XML（retrieve 結果）。無ければ空 self-closing から開始。
    deterministic: True でルール名/日付を固定（テスト・ゴールデン用）。
    """
    existing = existing or {}
    buffers: dict[str, str] = {}
    seq = 0
    for row in data:
        source_dept = row[0]
        dest_group = row[1]
        for idx, obj in enumerate(header[2:]):
            cell = row[idx + 2] if idx + 2 < len(row) else ""
            if str(cell).strip() == "":
                continue  # ブランクは何もしない（追記のみ）
            buf = buffers.get(obj, existing.get(obj, EMPTY_SHARINGRULES))
            if deterministic:
                name = f"TB{seq:016x}"
                label = f"TB{seq:016x}"
                date = "0000-00-00"
            else:
                name = label = date = None
            buf, _ = apply_cell(
                buf,
                object_apiname=obj,
                source_dept=source_dept,
                dest_group=dest_group,
                crud=cell,
                pkg_installed=pkg_installed,
                name=name,
                label=label,
                date=date,
            )
            buffers[obj] = buf
            seq += 1
    return buffers


# ── ゴールデン比較用の正規化 ─────────────────────────────────────────────────
def normalize_xml(xml: str) -> str:
    """非決定要素（ルール名 TB+hex16 / 日付）を placeholder 化して構造等価比較できるようにする。"""
    xml = _RULE_NAME_RE.sub("TB__NAME__", xml)
    xml = _DATE_RE.sub("__DATE__", xml)
    return xml


# ── 衝突プリチェック（§3.1 step5・§4-3-a）────────────────────────────────────
# 保護org実測＋追試（保護org実機検証）で確定した挙動を事前防御する:
#   - owner rule は (sharedFrom, sharedTo) で Salesforce が一意化する。既存と同一共有元・共有先へ
#     追記すると deploy 側（後発）が勝ち、既存 access を silent に上書き・縮小しうる（Edit→Read 実測）。
#     → downgrade（過少共有＝業務停止）／upgrade（過剰共有）を承認提示（direction=downgrade/upgrade/same）。
#   - criteria rule は (sharedTo, field, value) では一意化されず、同一 identity・別 fullName は org 上で
#     並存する（追試2 で確定＝R1 Read と R2 Edit が5本目として共存）。∴ 追記は既存を上書き・縮小せず
#     実効アクセスは UNION（max）。criteria のリスクは silent downgrade ではなく「重複ルールの累積」と
#     「UNION で実効が上振れ（過剰共有）」＝ direction=broaden（実効が上がる）／redundant（同一以下＝重複）。
#   - checkonly（--dry-run）は access 変化を捕捉しない（success を返す）＝本段が唯一の「事前」防御点。
#   - SharingRules deploy は additive（省略は削除しない・追試1 で REPLACE を反証）。削除は destructiveChanges。

_MD_NS = "{http://soap.sforce.com/2006/04/metadata}"
ACCESS_RANK = {"Read": 1, "Edit": 2}  # 数値が大きいほど強い共有。未知値は 0（＝どの変化も検知）


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _shared_target_typed(el) -> tuple[str, str]:
    """<sharedTo>／<sharedFrom> 要素から (型, 値) を返す。

    型＝子要素タグ（allInternalUsers / group / role / roleAndSubordinates / portalRole …）、
    値＝allInternalUsers は __ALL_INTERNAL_USER、それ以外はテキスト（group コード等）。
    """
    for child in el:
        t = _strip_ns(child.tag)
        if t == "allInternalUsers":
            return t, ALL_INTERNAL_USER
        return t, (child.text or "").strip()
    return "", ""


def _shared_target(el) -> str:
    """後方互換＝値のみ返す（group コード or __ALL_INTERNAL_USER）。"""
    return _shared_target_typed(el)[1]


@dataclass
class SharingRule:
    kind: str                       # "owner" | "criteria"
    full_name: str
    access: str                     # Read | Edit
    shared_to: str                  # group DeveloperName or __ALL_INTERNAL_USER
    shared_from: str | None = None  # owner: __ALL_INTERNAL_USER or group code
    field: str | None = None        # criteria
    operation: str | None = None    # criteria
    value: str | None = None        # criteria
    shared_to_type: str | None = None    # allInternalUsers / group / role …（想定外型ガード用）
    shared_from_type: str | None = None  # owner の付与元タグ（allInternalUsers か否か）
    criteria_item_count: int = 0    # criteria: <criteriaItems> の個数（複数条件＝AND の検出用）
    has_boolean_filter: bool = False  # criteria: <booleanFilter>（OR 条件等）を持つか

    def conflict_key(self) -> tuple:
        if self.kind == "owner":
            return ("owner", self.shared_from, self.shared_to)
        # criteria: field は名前空間差を吸収して比較（tb_PSA__… / tb_… を同一視）
        return ("criteria", self.shared_to, remove_ns(self.field or ""), self.value)


def parse_sharing_rules(xml: str) -> list[SharingRule]:
    """SharingRules XML（retrieve 結果 or 生成物）を SharingRule のリストへ解析する。

    空／self-closing／パース不能は空リストを返す（顧客orgの想定外XMLで落とさない）。

    注意: <criteriaItems> が複数（AND 条件）あるルールは、field/operation/value を最後の 1 件で
    上書きする（並存挙動を確定させたのは単一条件の型のみのため）。複数条件・booleanFilter の
    ルールは `criteria_item_count` / `has_boolean_filter` に痕跡を残し、unverified_shapes が
    「想定外の型（人手確認）」へ倒す（§9・衝突判定を単一条件前提で誤適用しない）。
    """
    xml = (xml or "").strip()
    if not xml:
        return []
    try:
        root = _ET.fromstring(xml)
    except _ET.ParseError:
        return []
    rules: list[SharingRule] = []
    for el in root:
        tag = _strip_ns(el.tag)
        if tag == "sharingOwnerRules":
            kind = "owner"
        elif tag == "sharingCriteriaRules":
            kind = "criteria"
        else:
            continue
        full_name = access = shared_to = ""
        shared_from = fld = op = val = None
        shared_to_type = shared_from_type = None
        crit_count = 0
        has_boolean = False
        for c in el:
            ct = _strip_ns(c.tag)
            if ct == "fullName":
                full_name = (c.text or "").strip()
            elif ct == "accessLevel":
                access = (c.text or "").strip()
            elif ct == "sharedTo":
                shared_to_type, shared_to = _shared_target_typed(c)
            elif ct == "sharedFrom":
                shared_from_type, shared_from = _shared_target_typed(c)
            elif ct == "booleanFilter":
                has_boolean = True
            elif ct == "criteriaItems":
                crit_count += 1
                for ci in c:
                    cit = _strip_ns(ci.tag)
                    if cit == "field":
                        fld = (ci.text or "").strip()
                    elif cit == "operation":
                        op = (ci.text or "").strip()
                    elif cit == "value":
                        val = (ci.text or "").strip()
        rules.append(
            SharingRule(
                kind=kind, full_name=full_name, access=access, shared_to=shared_to,
                shared_from=shared_from, field=fld, operation=op, value=val,
                shared_to_type=shared_to_type, shared_from_type=shared_from_type,
                criteria_item_count=crit_count, has_boolean_filter=has_boolean,
            )
        )
    return rules


@dataclass
class Conflict:
    object_apiname: str
    kind: str                # "owner" | "criteria"
    shared_to: str
    existing_access: str
    new_access: str
    direction: str           # owner: downgrade|upgrade|same ／ criteria: broaden|redundant
    existing_full_name: str
    source_dept: str | None = None  # criteria の条件値（部門コード）／owner は None


def _conflict_direction(kind: str, existing_access: str, new_access: str) -> str:
    """owner は上書き（downgrade/upgrade/same）、criteria は並存＝UNION（broaden/redundant）。

    保護org追試で確定＝owner rule は (sharedFrom,sharedTo) 一意化で後発が既存を上書き、
    criteria rule は同一 identity でも並存し実効は UNION（縮小は起きない）。
    """
    e = ACCESS_RANK.get(existing_access, 0)
    n = ACCESS_RANK.get(new_access, 0)
    if kind == "owner":
        if n < e:
            return "downgrade"
        if n > e:
            return "upgrade"
        return "same"
    # criteria: 並存（上書きなし）＝実効 UNION。縮小は原理的に起きない。
    return "broaden" if n > e else "redundant"


def _candidate_key(source_dept: str, dest_group: str) -> tuple:
    """追記しようとする 1 セルの衝突一意化キー（SharingRule.conflict_key と同形）。"""
    shared_to = ALL_INTERNAL_USER if dest_group == ALL_INTERNAL_USER else dest_group
    if source_dept == ALL_INTERNAL_USER:
        return ("owner", ALL_INTERNAL_USER, shared_to)
    return ("criteria", shared_to, "tb_DepartmentCode__c", source_dept)


def precheck_object(existing_xml: str, object_apiname: str, cells: list[tuple]) -> list[Conflict]:
    """既存 XML に対し、追記予定セル群 [(source_dept, dest_group, crud), …] の衝突を検出する。

    同一 (sharedFrom,sharedTo)〔criteria は (sharedTo,field,value)〕の既存ルールがある場合のみ
    Conflict を返す（新規共有先は衝突なし＝返さない）。direction=same も含めて返す
    （呼び出し側でフィルタ可能。same＝冪等・access 変化なし）。
    """
    by_key: dict[tuple, SharingRule] = {}
    for r in parse_sharing_rules(existing_xml):
        by_key.setdefault(r.conflict_key(), r)
    conflicts: list[Conflict] = []
    for source_dept, dest_group, crud in cells:
        if str(crud).strip() == "":
            continue
        key = _candidate_key(source_dept, dest_group)
        ex = by_key.get(key)
        if ex is None:
            continue
        shared_to = ALL_INTERNAL_USER if dest_group == ALL_INTERNAL_USER else dest_group
        conflicts.append(
            Conflict(
                object_apiname=object_apiname,
                kind=key[0],
                shared_to=shared_to,
                existing_access=ex.access,
                new_access=crud,
                direction=_conflict_direction(key[0], ex.access, crud),
                existing_full_name=ex.full_name,
                source_dept=None if source_dept == ALL_INTERNAL_USER else source_dept,
            )
        )
    return conflicts


def precheck_csv(
    existing: dict[str, str], header: list[str], data: list[list[str]], pkg_installed: int | str
) -> dict[str, list[Conflict]]:
    """CSV（header/data）と既存 XML 群から object → 衝突リストを返す（same を除く access 変化のみ）。"""
    result: dict[str, list[Conflict]] = {}
    for idx, obj in enumerate(header[2:]):
        cells: list[tuple] = []
        for row in data:
            cell = row[idx + 2] if idx + 2 < len(row) else ""
            if str(cell).strip() == "":
                continue
            cells.append((row[0], row[1], cell))
        if not cells:
            continue
        conflicts = [c for c in precheck_object(existing.get(obj, ""), obj, cells) if c.direction != "same"]
        if conflicts:
            result[obj] = conflicts
    return result


def render_conflicts_readable(
    conflicts_by_obj: dict[str, list[Conflict]], object_labels: dict[str, str] | None = None
) -> list[str]:
    """衝突を可読ルールの言葉（§3.6）へ翻訳。

    owner: downgrade＝弱まる（業務停止）／upgrade＝強まる（過剰共有・上書き）。
    criteria: broaden＝並存で実効が上がる（過剰共有）／redundant＝重複（実効変わらず）。
    ※ criteria は上書き・縮小は起きない（並存＝実効 UNION・追試2 で確定）。
    """
    object_labels = object_labels or {}
    lines: list[str] = []
    for obj, conflicts in conflicts_by_obj.items():
        olabel = object_labels.get(obj, obj)
        for c in conflicts:
            to = "全社員" if c.shared_to == ALL_INTERNAL_USER else c.shared_to
            scope = f"（部門 {c.source_dept} 分）" if c.source_dept else ""
            ej = _ACCESS_JA.get(c.existing_access, c.existing_access)
            nj = _ACCESS_JA.get(c.new_access, c.new_access)
            if c.direction == "downgrade":
                lines.append(
                    f"⚠[要注意・弱まる] {olabel}{scope}：《{to}》の既存共有『{ej}』を『{nj}』に"
                    f"**弱めます**（編集できなくなる等・業務停止のおそれ）。よろしいですか。"
                )
            elif c.direction == "upgrade":
                lines.append(
                    f"⚠[要注意・強まる] {olabel}{scope}：《{to}》の既存共有『{ej}』を『{nj}』に"
                    f"**強めます**（過剰共有＝機密露出のおそれ）。よろしいですか。"
                )
            elif c.direction == "broaden":
                lines.append(
                    f"⚠[要注意・重複で強まる] {olabel}{scope}：《{to}》に既存の『{ej}』ルールがあり、"
                    f"『{nj}』を重ねると両方が並存＝実効は『{nj}』に**強まります**（過剰共有のおそれ）。よろしいですか。"
                )
            elif c.direction == "redundant":
                lines.append(
                    f"[重複] {olabel}{scope}：《{to}》には既に『{ej}』の共有ルールがあり、"
                    f"『{nj}』の追加は実効を変えません（重複ルールが増えるだけ）。"
                )
            else:
                lines.append(f"[変化なし] {olabel}{scope}：《{to}》は既に『{ej}』のため変わりません。")
    return lines


# ── 想定外型ガード（§9・確定＋保険）────────────────────────────────────────
# owner/criteria の一意化・並存挙動は保護org追試で確定したが、実測した型は
#   owner: sharedFrom=allInternalUsers・sharedTo=group/allInternalUsers
#   criteria: sharedTo=group/allInternalUsers・条件フィールド=tb_DepartmentCode__c・operation=equals
#            （かつ criteriaItems 単一条件・booleanFilter なし）
# に限られる（実CSV の運用像＝この2型のみ）。retrieve した現状 XML にこれ以外の型
#   （role/portal 宛の共有先、allInternalUsers 以外を元にする owner、別の条件フィールド/演算子、
#    複数 criteriaItems（AND）・booleanFilter（OR）を持つルール 等）
# が存在する場合、一意化/並存の前提を検証していないため precheck が誤判定しうる。
# → 自動判定せず「人手確認が要る」と警告を出す安全弁（将来型が増えても安全側に倒れる）。
_VERIFIED_SHARED_TO_TYPES = {"allInternalUsers", "group"}
_VERIFIED_OWNER_SHARED_FROM_TYPES = {"allInternalUsers"}
_VERIFIED_CRITERIA_FIELD = "tb_DepartmentCode__c"


def unverified_shapes(existing_xml: str, object_apiname: str = "") -> list[str]:
    """retrieve 済み現状 XML に、追試で検証していない型の既存ルールがあれば警告リストを返す。"""
    warnings: list[str] = []
    for r in parse_sharing_rules(existing_xml):
        why: list[str] = []
        if (r.shared_to_type or "") not in _VERIFIED_SHARED_TO_TYPES:
            why.append(f"共有先が group/全社員以外（{r.shared_to_type or '不明'}）")
        if r.kind == "owner":
            if (r.shared_from_type or "") not in _VERIFIED_OWNER_SHARED_FROM_TYPES:
                why.append(f"付与元が allInternalUsers 以外（{r.shared_from_type or '不明'}）")
        else:  # criteria
            if remove_ns(r.field or "") != _VERIFIED_CRITERIA_FIELD:
                why.append(f"条件フィールドが {_VERIFIED_CRITERIA_FIELD} 以外（{r.field}）")
            if (r.operation or "equals") != "equals":
                why.append(f"条件演算子が equals 以外（{r.operation}）")
            # 複数条件（AND）／booleanFilter（OR）は単一条件前提の衝突判定が崩れるため人手へ倒す
            if r.criteria_item_count >= 2:
                why.append(f"条件が複数（criteriaItems {r.criteria_item_count} 件の AND）")
            if r.has_boolean_filter:
                why.append("booleanFilter（OR 等の複合条件）を持つ")
        if why:
            pfx = f"{object_apiname}: " if object_apiname else ""
            warnings.append(
                f"{pfx}{r.kind} rule {r.full_name}＝想定外の型（{'・'.join(why)}）"
                f"→ 自動判定せず人手確認（一意化/並存の前提が未検証）"
            )
    return warnings


def unverified_shapes_csv(existing: dict[str, str], header: list[str]) -> list[str]:
    """object → 既存 XML 群を横断して想定外型の警告をまとめる。"""
    out: list[str] = []
    for obj in header[2:]:
        out.extend(unverified_shapes(existing.get(obj, ""), obj))
    return out


# ── 可読ルール（可視範囲ポリシー）→ CSV 翻訳（§3.0 step2 / §3.5 / §3.6）──────
@dataclass
class TranslateResult:
    header: list[str]
    data: list[list[str]]
    readable: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_ACCESS_JA = {"Read": "閲覧", "Edit": "編集"}


def _expand_objects(spec, object_sets: dict[str, list[str]]) -> list[str]:
    if isinstance(spec, str):
        return list(object_sets.get(spec, [spec]))
    result: list[str] = []
    for s in spec:
        result.extend(object_sets.get(s, [s]))
    return result


def policy_to_csv(policy: dict, config: dict | None = None) -> TranslateResult:
    """可視範囲ポリシー（意図の構造データ）→ 正本実装互換 CSV へ翻訳。

    policy:
      { "pkg_installed": 0|1,
        "teams": [ {"dept_code","group","access", "objects"(set名/配列),
                     ["manager_group","manager_access"(任意)]} ],
        "company_wide": [ {"group","access","objects"} ] }
    config:
      { "object_sets": {name: [obj,...]},
        "criteria_eligible": {obj: bool},   # tb_DepartmentCode__c 保有 = 条件ベース可
        "object_labels": {obj: "日本語ラベル"} }
    条件ベース（team）で criteria_eligible=False のオブジェクトは除外し警告する（§3.1-2 の翻訳段）。
    """
    config = config or {}
    object_sets = config.get("object_sets", {})
    eligible = config.get("criteria_eligible", {})
    labels = config.get("object_labels", {})

    teams = policy.get("teams", [])
    company = policy.get("company_wide", [])

    # 列（オブジェクト）＝参照される全オブジェクトの和集合（安定順）
    col_order: list[str] = []
    for entry in teams + company:
        for obj in _expand_objects(entry.get("objects", []), object_sets):
            if obj not in col_order:
                col_order.append(obj)
    header = ["-", "-"] + col_order

    data: list[list[str]] = []
    readable: list[str] = []
    warnings: list[str] = []

    def label_of(obj: str) -> str:
        return labels.get(obj, obj)

    def cells_for(objs: list[str], access: str, require_eligible: bool) -> tuple[list[str], list[str]]:
        row = ["" for _ in col_order]
        used: list[str] = []
        for obj in objs:
            if require_eligible and not eligible.get(obj, True):
                warnings.append(
                    f"{label_of(obj)} は共有ルールで部門別に絞れないため（条件フィールド不在）、"
                    f"この設定から除外し、権限セット／OWD で制御します。"
                )
                continue
            row[col_order.index(obj)] = access
            used.append(obj)
        return row, used

    # team = 条件ベース（source=部門コード）
    for t in teams:
        dept = t["dept_code"]
        group = t["group"]
        access = t.get("access", "Read")
        objs = _expand_objects(t.get("objects", []), object_sets)
        row, used = cells_for(objs, access, require_eligible=True)
        if used:
            data.append([dept, group] + row)
            readable.append(
                f"{label_of_dept(t)}のメンバーは、自部門の"
                f"{'・'.join(label_of(o) for o in used)}を「{_ACCESS_JA.get(access, access)}」できます"
            )
        # 責任者グループへの任意付与（条件ベース）
        mgr = t.get("manager_group")
        if mgr:
            m_access = t.get("manager_access", "Read")
            mrow, mused = cells_for(objs, m_access, require_eligible=True)
            if mused:
                data.append([dept, mgr] + mrow)
                readable.append(
                    f"{label_of_dept(t)}の責任者は、自部門の"
                    f"{'・'.join(label_of(o) for o in mused)}を「{_ACCESS_JA.get(m_access, m_access)}」できます"
                )

    # company_wide = 所有者ベース（source=__ALL_INTERNAL_USER）
    for c in company:
        group = c["group"]
        access = c.get("access", "Read")
        objs = _expand_objects(c.get("objects", []), object_sets)
        row, used = cells_for(objs, access, require_eligible=False)
        if used:
            data.append([ALL_INTERNAL_USER, group] + row)
            readable.append(
                f"{c.get('label', group)}は、全社の"
                f"{'・'.join(label_of(o) for o in used)}を「{_ACCESS_JA.get(access, access)}」できます"
            )

    # 帰結注記（generic）
    if teams:
        readable.append(
            "（帰結）部門ごとの可視化を設定したデータは、他部門のメンバーからは見えなくなります。"
        )
    # 警告は重複排除（同一オブジェクトが複数行から除外されても1回だけ通知）
    warnings = list(dict.fromkeys(warnings))
    return TranslateResult(header=header, data=data, readable=readable, warnings=warnings)


def label_of_dept(team: dict) -> str:
    return team.get("dept_label") or team.get("dept_code") or team.get("group")


def csv_text(header: list[str], data: list[list[str]]) -> str:
    """header/data を 正本実装互換 CSV テキストへ（[HEADER] 行付き）。"""
    import io

    out = io.StringIO()
    w = _csv.writer(out)
    w.writerow(["[HEADER]", header[1]] + header[2:] if header[0] != "[HEADER]" else header)
    # ヘッダは列1に [HEADER] を置く規約（列1/2 はキー列プレースホルダ）
    for row in data:
        w.writerow(row)
    return out.getvalue()


# ── CLI（author のみ・org には触れない）──────────────────────────────────────
def _cmd_policy_compile(args: argparse.Namespace) -> int:
    with open(args.policy, encoding="utf-8") as f:
        policy = json.load(f)
    config = {}
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
    res = policy_to_csv(policy, config)
    print("=== 可読ルール（人が読む・編集の起点）===")
    for line in res.readable:
        print("・" + line)
    if res.warnings:
        print("\n=== 注意 ===")
        for w in res.warnings:
            print("⚠ " + w)
    if args.csv_out:
        with open(args.csv_out, "w", encoding="utf-8") as f:
            f.write(csv_text(res.header, res.data))
        print(f"\n[csv] {args.csv_out} を書き出しました（裏の中間物・手編集しない）")
    return 0


def _cmd_author_csv(args: argparse.Namespace) -> int:
    header, data = load_csv(args.csvfile, args.pkg_installed)
    existing: dict[str, str] = {}
    buffers = generate_from_csv(header, data, args.pkg_installed, existing, deterministic=args.deterministic)
    import os

    os.makedirs(args.output_dir, exist_ok=True)
    for obj, xml in buffers.items():
        path = os.path.join(args.output_dir, f"{obj}.sharingRules-meta.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"[author] {path}")
    print(f"[done] {len(buffers)} オブジェクトの SharingRules を生成（org 未書込・checkonly は tb_mdconfig.py へ）")
    return 0


def _cmd_precheck(args: argparse.Namespace) -> int:
    """既存 SharingRules XML（retrieve 済みディレクトリ）と CSV から衝突を事前検出する（§3.1 step5）。

    org へは触れない。retrieve 済み現状 XML はディレクトリで受け取る（tb_mdconfig.py が用意）。
    downgrade または想定外型を1件でも検出したら exit 2（gate 用）。
    その他の衝突（upgrade・broaden・redundant）は exit 1、衝突なしは exit 0。
    """
    header, data = load_csv(args.csvfile, args.pkg_installed)
    existing: dict[str, str] = {}
    if args.existing_dir and os.path.isdir(args.existing_dir):
        for obj in header[2:]:
            path = os.path.join(args.existing_dir, f"{obj}.sharingRules-meta.xml")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    existing[obj] = f.read()
    conflicts = precheck_csv(existing, header, data, args.pkg_installed)
    lines = render_conflicts_readable(conflicts)
    unverified = unverified_shapes_csv(existing, header)
    if not lines and not unverified:
        print("衝突なし（既存共有先と重複する追記はありません）")
        return 0
    if lines:
        print("=== 衝突プリチェック（access 変化の事前検知・checkonly では捕捉されない）===")
        for line in lines:
            print(line)
    if unverified:
        print("\n=== 想定外の型（自動判定不可・人手確認が必要）===")
        for w in unverified:
            print("⚠ " + w)
    has_down = any(c.direction == "downgrade" for cs in conflicts.values() for c in cs)
    print(
        "\n※ この差分は checkonly（--dry-run）では success になり捕捉されません。"
        "deploy 前に承認が必要です（§4-3-a）。"
    )
    # downgrade（業務停止）または想定外型（前提未検証）は最上位の要確認＝exit 2
    return 2 if (has_down or unverified) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="共有モデル設定 author（案B・org 非依存）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("policy-compile", help="可視範囲ポリシー→可読ルール＋（任意で）CSV")
    s.add_argument("--policy", required=True, help="可視範囲ポリシー JSON")
    s.add_argument("--config", help="object_sets / criteria_eligible / object_labels JSON")
    s.add_argument("--csv-out", help="裏の CSV 書き出し先（正本実装互換）")
    s.set_defaults(func=_cmd_policy_compile)

    s = sub.add_parser("author-csv", help="CSV→SharingRules XML 生成（org 未書込）")
    s.add_argument("--csvfile", required=True)
    s.add_argument("--pkg-installed", dest="pkg_installed", default="1", choices=["0", "1"])
    s.add_argument("--output-dir", required=True)
    s.add_argument("--deterministic", action="store_true", help="ルール名/日付固定（ゴールデン用）")
    s.set_defaults(func=_cmd_author_csv)

    s = sub.add_parser("precheck", help="既存 XML と CSV の (sharedFrom,sharedTo) 衝突を事前検出")
    s.add_argument("--csvfile", required=True)
    s.add_argument("--existing-dir", dest="existing_dir", required=True, help="retrieve 済み現状 XML ディレクトリ")
    s.add_argument("--pkg-installed", dest="pkg_installed", default="1", choices=["0", "1"])
    s.set_defaults(func=_cmd_precheck)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
