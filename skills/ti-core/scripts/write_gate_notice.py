#!/usr/bin/env python3
"""write_gate_notice.py — ツバイソPSA/IMAのレコードを作る呼び出しの直前に、書込前ゲートを案内する。

Claude Code の PreToolUse フックとして、配布プラグインの plugin.json から呼ばれる。

## なぜ要るか

書込前ゲート（`atlas_write_seam`）を引く手順はスキルに書いてある。しかしスキルは読まれない限り
効かない。TI のスキルを一度も読み込まないまま、業務として sf CLI で本番の組織へ直接
レコードを作る計画を立てることは起こりうる。スキルの外から書く経路を、道具の層で拾う。

## 何をするか・しないか

- 検知したら、利用者には systemMessage、モデルには additionalContext で案内を出す
- **止めない。** permissionDecision を返さない（allow を返すと権限の確認を飛ばしてしまう）。
  呼び出しは通常の権限の流れのまま進む
- どの入力でも exit 0。読めない入力・想定外の形は黙って通す（案内が出ないだけ）
- 標準ライブラリだけで動く

## 検知する呼び出し

1. Bash: `sf data create|import|upsert …`（旧形式 `sfdx force:data:record:create` 等も）、
   または `sf api request rest … POST` で、コマンドに `tb_PSA__`／`tb_IMA__` が現れるもの。
   `--file`／`--files`／`--plan`／`--sobject` 等で渡したファイルに現れるものも拾う
2. MCP: ツール名が `__dispatch` で終わり、method が POST で、url か body に
   `tb_PSA__`／`tb_IMA__` が現れるもの（`dispatch_readonly` は GET 専用なので対象外）

## アクションの呼び出しは別の案内にする

1.・2.のうち、パスが `/actions/`（Apex のカスタムアクション `/actions/custom/apex/{名前}`・
標準アクション `/actions/standard/{名前}` 等）を含むものは、レコードを作る呼び出しと決めつけない。
製品のアクションには参照だけのもの（例 `tb_PSA__TbInvocableDetailMasterGetter`）と、レコードを
作成・更新・削除するもの（例 `tb_PSA__TbInvocableCreateExpense`）が同じパスの形で並び、フックは
アクションの定義を読めないため、どちらかを見分けられない。名前の語尾で推し量ることもしない
（命名の規則は製品が保証していない）。そこで「書き込むことがあるアクションの呼び出し」として
案内し、対象にはオブジェクトでなくアクションの名前を示す。以前は URL のアクション名を
オブジェクトとして「レコードを作成する」と案内し、参照だけの呼び出しにも作成の案内が出ていた
（2026-10-29・検証組織で再現。案内が当たらないと読み飛ばされ、本当の作成の前の案内が効かなくなる）。

> - **依存事実**: 製品の Apex のカスタムアクションは `/services/data/vXX.0/actions/custom/apex/{名前空間}__{クラス名}` のパスで呼ばれ、参照だけのものと書き込むものが同じ形で並ぶ。MCP の `dispatch` の `tool_input` のキー名は `method`／`url`／`body`
> - **実証日**: 2026-10-30
> - **実証コマンド**: 検証組織の接続で `dispatch_readonly` の `GET /services/data/v66.0/actions/custom/apex`（一覧に Getter と Creator・Deleter が並ぶ）。`dispatch` の `POST /services/data/v66.0/actions/custom/apex/tb_PSA__TbInvocableDetailMasterGetter`（本文 `{"inputs": []}`・`userType: builder`）で、200 と空の配列が返り、このフックの案内が出る（キー名が一致している）

自己検証: `python3 write_gate_notice.py --selftest`
"""
import json
import os
import re
import shlex
import sys

NS_RE = re.compile(r"\btb_(?:PSA|IMA)__\w+")
SF_WRITE_RE = re.compile(
    r"\bsf\s+data\s+(?:create|import|upsert)\b"
    r"|\bsfdx\s+force:data:(?:record:create|tree:import|bulk:upsert)\b")
SF_REST_RE = re.compile(r"\bsf\s+api\s+request\s+rest\b")
POST_RE = re.compile(r"(?:--method|-X)[\s=]+['\"]?POST\b", re.IGNORECASE)
# アクションの呼び出し（/actions/custom/apex/{名前}・/actions/standard/{名前} 等）。名前を拾う
ACTION_RE = re.compile(r"/actions/(?:custom/[A-Za-z]+|standard)/([A-Za-z0-9_]+)")
FILE_OPTS = {"--file", "-f", "--files", "--plan", "-p", "--body", "--sobjecttreefiles",
             "--csvfile", "-c"}
MAX_READ = 1024 * 1024

USER_MESSAGE = (
    "ツバイソPSA/IMAのレコードを作る呼び出しです。"
    "書込前ゲート（atlas_write_seam）で、この対象を直接作ってよいかを先に確かめてください。"
    "この案内は呼び出しを止めません。")
USER_MESSAGE_ACTION = (
    "ツバイソPSA/IMAのアクションの呼び出しです。参照だけのアクションもあれば、"
    "レコードを作成・更新・削除するアクションもあります。書き込むアクションなら、"
    "書込前ゲート（atlas_write_seam）で対象のオブジェクトを先に確かめてください。"
    "この案内は呼び出しを止めません。")


def model_context(objects):
    names = "、".join(sorted(objects)) if objects else "（対象のオブジェクトを読み取れなかった）"
    return (
        "[TI 書込前ゲートの案内] この呼び出しはツバイソPSA/IMAのレコードを作成する。対象: " + names + "。"
        "このセッションでまだ atlas_write_seam(target=<対象のAPI名>) を引いていないなら、"
        "作成の前に引く。function_only（機能経由でしか作れない）なら直接作らず、応答が示す機能・画面で作る。"
        "auto_create_as_target なら手で作らない。手順の正本は ti-reference の references/write-index.md。"
        "すでに作成してしまった場合は、その事実と対象を利用者へ伝え、ゲートの判定を引いてから扱いを相談する。"
        "このフックは呼び出しを止めない（判定は人とモデルに委ねる）。")


def action_context(actions):
    names = "、".join(sorted(actions))
    return (
        "[TI 書込前ゲートの案内] この呼び出しはツバイソPSA/IMAのアクションを実行する。アクション: " + names + "。"
        "参照だけのアクションならこの案内は当てはまらない。レコードを作成・更新・削除するアクションなら、"
        "このセッションでまだ atlas_write_seam(target=<書き込む対象のオブジェクトのAPI名>) を引いていないとき、"
        "実行の前に引き、このアクションが応答の示す経路（機能・画面）に当たるかを確かめる。"
        "手順の正本は ti-reference の references/write-index.md。"
        "すでに書き込んでしまった場合は、その事実と対象を利用者へ伝え、ゲートの判定を引いてから扱いを相談する。"
        "このフックは呼び出しを止めない（判定は人とモデルに委ねる）。")


def _file_objects(command, cwd):
    """コマンドが渡したファイルから名前空間付きのオブジェクト名を拾う。読めなければ空。"""
    found = set()
    try:
        tokens = shlex.split(command)
    except ValueError:
        return found
    paths = []
    for i, tok in enumerate(tokens):
        opt, eq, val = tok.partition("=")
        if opt in FILE_OPTS:
            if eq:
                paths.append(val)
            elif i + 1 < len(tokens):
                paths.append(tokens[i + 1])
    for raw in paths:
        for p in raw.split(","):
            p = os.path.expanduser(p.strip().lstrip("@"))
            if not p:
                continue
            if not os.path.isabs(p):
                p = os.path.join(cwd or os.getcwd(), p)
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    found.update(NS_RE.findall(f.read(MAX_READ)))
            except OSError:
                continue
    return found


def _classify(path_text, names):
    """アクションの呼び出しなら ("action", アクション名), そうでなければ ("object", 名前) を返す。"""
    actions = set(ACTION_RE.findall(path_text))
    if actions:
        return ("action", actions)
    return ("object", names) if names else None


def detect(event):
    """案内すべきなら (種類, 名前の集合) を、不要なら None を返す。

    種類は "object"（レコードを作る呼び出し・名前はオブジェクト）か
    "action"（アクションの呼び出し・名前はアクション）。
    """
    tool = event.get("tool_name") or ""
    tin = event.get("tool_input") or {}
    if not isinstance(tin, dict):
        return None
    if tool == "Bash":
        cmd = tin.get("command") or ""
        if not isinstance(cmd, str):
            return None
        is_write = bool(SF_WRITE_RE.search(cmd))
        is_rest_post = bool(SF_REST_RE.search(cmd) and POST_RE.search(cmd))
        if not (is_write or is_rest_post):
            return None
        objs = set(NS_RE.findall(cmd)) | _file_objects(cmd, event.get("cwd"))
        if not objs:
            return None
        return _classify(cmd if is_rest_post else "", objs)
    if tool.startswith("mcp__") and tool.endswith("__dispatch"):
        if str(tin.get("method") or "").upper() != "POST":
            return None
        url = str(tin.get("url") or "")
        text = url + " " + json.dumps(tin.get("body"), ensure_ascii=False)
        objs = set(NS_RE.findall(text))
        if not objs:
            return None
        return _classify(url, objs)
    return None


def build_output(found):
    kind, names = found
    if kind == "action":
        user, ctx = USER_MESSAGE_ACTION, action_context(names)
    else:
        user, ctx = USER_MESSAGE, model_context(names)
    return {
        "systemMessage": user,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": ctx,
        },
    }


def main():
    try:
        event = json.load(sys.stdin)
        found = detect(event) if isinstance(event, dict) else None
        if found:
            print(json.dumps(build_output(found), ensure_ascii=False))
    except Exception:  # 案内のためのフックなので、どんな失敗でも呼び出しを妨げない
        pass
    return 0


def selftest():
    A = "tb_PSA__tb_Quote__c"
    G = "tb_PSA__TbInvocableDetailMasterGetter"
    C = "tb_PSA__TbInvocableCreateExpense"
    cases = [
        ("作成（sf data create record）", {"tool_name": "Bash", "tool_input": {
            "command": f"sf data create record -o prod -s {A} -v \"Name='x'\""}}, True),
        ("一括（sf data import bulk）", {"tool_name": "Bash", "tool_input": {
            "command": f"sf data import bulk --sobject {A} --file q.csv -o prod"}}, True),
        ("REST POST", {"tool_name": "Bash", "tool_input": {
            "command": f"sf api request rest /services/data/v62.0/sobjects/{A} --method POST --body @b.json"}}, True),
        ("MCP dispatch POST", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": f"/services/data/v66.0/sobjects/{A}", "body": {"Name": "x"}}}, True),
        ("読み取り（sf data query）", {"tool_name": "Bash", "tool_input": {
            "command": f"sf data query -q \"SELECT Id FROM {A}\" -o prod"}}, False),
        ("REST GET", {"tool_name": "Bash", "tool_input": {
            "command": f"sf api request rest /services/data/v62.0/sobjects/{A}/describe"}}, False),
        ("MCP dispatch_readonly", {"tool_name": "mcp__x__dispatch_readonly", "tool_input": {
            "method": "GET", "url": f"/services/data/v66.0/sobjects/{A}"}}, False),
        ("MCP dispatch POST（標準オブジェクト）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": "/services/data/v66.0/sobjects/Account", "body": {"Name": "x"}}}, False),
        ("無関係（git status）", {"tool_name": "Bash", "tool_input": {"command": "git status"}}, False),
        ("作成（標準オブジェクト）", {"tool_name": "Bash", "tool_input": {
            "command": "sf data create record -s Account -v \"Name='x'\""}}, False),
        ("MCP dispatch POST（参照だけのApexアクション）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": f"/services/data/v66.0/actions/custom/apex/{G}",
            "body": {"inputs": []}}}, "action"),
        ("MCP dispatch POST（作成するApexアクション）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": f"/services/data/v66.0/actions/custom/apex/{C}",
            "body": {"inputs": [{"x": 1}]}}}, "action"),
        ("MCP dispatch POST（標準アクション・本文に項目名）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": "/services/data/v66.0/actions/standard/submit",
            "body": {"inputs": [{"objectId": "a00000000000000AAA", "comment": A}]}}}, "action"),
        ("MCP dispatch POST（顧客のApexアクション・名前空間なし）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": "/services/data/v66.0/actions/custom/apex/MyAction",
            "body": {"inputs": []}}}, False),
        ("REST POST（Apexアクション）", {"tool_name": "Bash", "tool_input": {
            "command": f"sf api request rest /services/data/v66.0/actions/custom/apex/{G} --method POST --body @b.json"}}, "action"),
        ("一括（ファイル名に actions を含む）", {"tool_name": "Bash", "tool_input": {
            "command": f"sf data import bulk --sobject {A} --file /tmp/actions/standard/x.csv -o prod"}}, True),
    ]
    ng = 0
    for label, ev, want in cases:
        found = detect(ev)
        if want is True:
            ok = found is not None and found[0] == "object"
        elif want is False:
            ok = found is None
        else:
            ok = found is not None and found[0] == want
        got = "なし" if found is None else ("あり（アクション）" if found[0] == "action" else "あり（作成）")
        if found is not None:
            out = build_output(found)
            if found[0] == "action" and "を作成する。対象:" in out["hookSpecificOutput"]["additionalContext"]:
                ok = False
        mark = "✓" if ok else "✗"
        ng += not ok
        print(f"{mark} {label}: 案内{got}")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else main())
