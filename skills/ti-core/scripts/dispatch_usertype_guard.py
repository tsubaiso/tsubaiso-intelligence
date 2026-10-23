#!/usr/bin/env python3
"""dispatch_usertype_guard.py — Salesforceの接続の dispatch で書き込むときに userType「business」を外させる。

Claude Code の PreToolUse フックとして、配布プラグインの plugin.json から呼ばれる。

## なぜ要るか

Headless 360 の `dispatch` は `userType` を受け取る。ツールの説明は「参考情報」としつつ、
`discover` の説明は業務の操作なら `business` を付けるよう促す。ところが `business` を付けると、
書き込みが Salesforce の画面（Lightning）と同じ制約で検査される＝ページレイアウトの必須・参照のみ、
自由入力の選択リスト（ToDoの件名など）の選択肢の制限がかかり、メール記録は作成できない。
指定なし・`builder` なら REST API と同じ扱いで通る（検証組織で 2026-10-22 に送り分けて確認）。
利用者の操作は業務なので、AI は説明に従って `business` を付け、作成が毎回弾かれる。
スキルの規律（ti-core の description の (4)）だけでは、読まれずに素通りすることがあるため、
道具の層で止める。

## 何をするか・しないか

- ツール名が `__dispatch` で終わり、method が GET 以外で、`userType` が `business` のときだけ、
  permissionDecision=deny と理由を返す。モデルは理由に従い、userType を外して同じ呼び出しをやり直す
- それ以外は何も出さない（権限の確認の流れに触れない。allow は返さない）
- どの入力でも exit 0。読めない入力・想定外の形は黙って通す
- 標準ライブラリだけで動く

自己検証: `python3 dispatch_usertype_guard.py --selftest`
"""
import json
import sys

REASON = (
    "[TI] Salesforceの接続の dispatch で書き込むときは userType を付けない。"
    "userType が business だと、画面のページレイアウトの制約（必須・参照のみ・選択リストの選択肢）で検査され、"
    "メール記録の作成も拒否される。userType を外して（付けるなら builder）、同じ呼び出しをやり直す。"
    "外しても同じエラーなら、組織側の検査として扱う。詳細は ti-core の references/capability-preflight.md。")


def detect(event):
    """止めるべき呼び出しなら True。"""
    tool = event.get("tool_name") or ""
    tin = event.get("tool_input") or {}
    if not isinstance(tin, dict):
        return False
    if not (tool.startswith("mcp__") and tool.endswith("__dispatch")):
        return False
    if str(tin.get("method") or "").upper() in ("", "GET"):
        return False
    return str(tin.get("userType") or "").strip().lower() == "business"


def build_output():
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON,
        },
    }


def main():
    try:
        event = json.load(sys.stdin)
        if isinstance(event, dict) and detect(event):
            print(json.dumps(build_output(), ensure_ascii=False))
    except Exception:  # 想定外の入力では何もしない
        pass
    return 0


def selftest():
    url = "/services/data/v66.0/sobjects/Task"
    cases = [
        ("POST・business", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": url, "body": {"Subject": "x"}, "userType": "business"}}, True),
        ("PATCH・business（大文字）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "PATCH", "url": url + "/00T000000000001", "userType": "Business"}}, True),
        ("DELETE・business", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "DELETE", "url": url + "/00T000000000001", "userType": "business"}}, True),
        ("POST・指定なし", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": url, "body": {"Subject": "x"}}}, False),
        ("POST・builder", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": url, "userType": "builder"}}, False),
        ("GET・business（dispatch）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "GET", "url": url, "userType": "business"}}, False),
        ("dispatch_readonly・business", {"tool_name": "mcp__x__dispatch_readonly", "tool_input": {
            "method": "GET", "url": url, "userType": "business"}}, False),
        ("無関係（Bash）", {"tool_name": "Bash", "tool_input": {"command": "git status"}}, False),
        ("入力の形が違う", {"tool_name": "mcp__x__dispatch", "tool_input": "POST"}, False),
    ]
    ng = 0
    for label, ev, want in cases:
        got = detect(ev)
        mark = "✓" if got == want else "✗"
        ng += got != want
        print(f"{mark} {label}: {'止める' if got else '通す'}")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else main())
