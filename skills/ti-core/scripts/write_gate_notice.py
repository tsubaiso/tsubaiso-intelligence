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
FILE_OPTS = {"--file", "-f", "--files", "--plan", "-p", "--body", "--sobjecttreefiles",
             "--csvfile", "-c"}
MAX_READ = 1024 * 1024

USER_MESSAGE = (
    "ツバイソPSA/IMAのレコードを作る呼び出しです。"
    "書込前ゲート（atlas_write_seam）で、この対象を直接作ってよいかを先に確かめてください。"
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


def detect(event):
    """案内すべきなら対象オブジェクト名の集合を、不要なら None を返す。"""
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
        return objs or None
    if tool.startswith("mcp__") and tool.endswith("__dispatch"):
        if str(tin.get("method") or "").upper() != "POST":
            return None
        text = str(tin.get("url") or "") + " " + json.dumps(tin.get("body"), ensure_ascii=False)
        objs = set(NS_RE.findall(text))
        return objs or None
    return None


def build_output(objects):
    return {
        "systemMessage": USER_MESSAGE,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": model_context(objects),
        },
    }


def main():
    try:
        event = json.load(sys.stdin)
        objects = detect(event) if isinstance(event, dict) else None
        if objects:
            print(json.dumps(build_output(objects), ensure_ascii=False))
    except Exception:  # 案内のためのフックなので、どんな失敗でも呼び出しを妨げない
        pass
    return 0


def selftest():
    A = "tb_PSA__tb_Quote__c"
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
    ]
    ng = 0
    for label, ev, want in cases:
        got = detect(ev) is not None
        mark = "✓" if got == want else "✗"
        ng += got != want
        print(f"{mark} {label}: 案内{'あり' if got else 'なし'}")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else main())
