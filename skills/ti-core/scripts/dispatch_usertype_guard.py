#!/usr/bin/env python3
"""dispatch_usertype_guard.py — Salesforceの接続の dispatch で書き込むときに userType「builder」を付けさせる。

Claude Code の PreToolUse フックとして、配布プラグインの plugin.json から呼ばれる。

## なぜ要るか

Headless 360 の `dispatch` は `userType` を受け取る。ツールの説明は「参考情報」としつつ、
`discover` の説明は業務の操作なら `business` を付けるよう促す。ところが `business` を付けると、
書き込みが Salesforce の画面（Lightning）と同じ制約で検査される＝ページレイアウトの必須・参照のみ、
自由入力の選択リスト（ToDoの件名など）の選択肢の制限がかかり、メール記録は作成できない。
指定なしも、接続の経路によって `business` と同じ扱いになる（検証組織で 2026-10-26 に確認。
Claude のコネクタでは通り、同じユーザーが直接 MCP で接続すると拒否された）。
`builder` なら、接続しているユーザーが「アプリケーションのカスタマイズ」の権限を持つとき REST API と
同じ扱いで通る。権限を持たないユーザーでは `builder` は無視されるだけで害は無い。
スキルの規律（ti-core の description の (4)）だけでは、読まれずに素通りすることがあるため、
道具の層で止める。

## 何をするか・しないか

- ツール名が `__dispatch` で終わり、method が GET 以外で、`userType` が `builder` でないとき
  （`business`・指定なし・その他の値）、permissionDecision=deny と理由を返す。
  POST でも参照の `parameterizedSearch`（日本語の名前で引く経路）は止めない
  モデルは理由に従い、userType に builder を付けて同じ呼び出しをやり直す
- それ以外は何も出さない（権限の確認の流れに触れない。allow は返さない）
- どの入力でも exit 0。読めない入力・想定外の形は黙って通す
- 標準ライブラリだけで動く

自己検証: `python3 dispatch_usertype_guard.py --selftest`
"""
import json
import sys

REASON = (
    "[TI] Salesforceの接続の dispatch で書き込むときは userType に builder を付ける。"
    "business や指定なしだと、画面のページレイアウトの制約（必須・参照のみ・選択リスト値）で検査され、"
    "メール記録の作成も拒否される。userType に builder を付けて、同じ呼び出しをやり直す。"
    "builder でも同じエラーなら、接続しているユーザーの権限（アプリケーションのカスタマイズを持たない）による検査なので、"
    "エラーの種類ごとに次の操作を選ぶ。必須と示された項目は値を指定して再送信する。"
    "選択リスト値に無い件名の設定・メール記録の作成・要求から除けない参照のみの項目への書き込みは、"
    "ti-local-automation（本人権限のローカル実行）で実行する。詳細は ti-core の references/capability-preflight.md。")


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
    path = str(tin.get("url") or "").split("?", 1)[0].rstrip("/").lower()
    if path.endswith("/parameterizedsearch"):  # POST だが参照（組織のデータを変えない）
        return False
    return str(tin.get("userType") or "").strip().lower() != "builder"


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
            "method": "POST", "url": url, "body": {"Subject": "x"}}}, True),
        ("POST・空文字", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": url, "userType": ""}}, True),
        ("POST・builder", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": url, "userType": "builder"}}, False),
        ("PATCH・Builder（大文字・前後の空白）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "PATCH", "url": url + "/00T000000000001", "userType": " Builder "}}, False),
        ("GET・business（dispatch）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "GET", "url": url, "userType": "business"}}, False),
        ("GET・指定なし（dispatch）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "GET", "url": url}}, False),
        ("dispatch_readonly・business", {"tool_name": "mcp__x__dispatch_readonly", "tool_input": {
            "method": "GET", "url": url, "userType": "business"}}, False),
        ("POST・指定なし・parameterizedSearch（参照）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "method": "POST", "url": "/services/data/v66.0/parameterizedSearch", "body": {"q": "x"}}}, False),
        ("method なし（dispatch）", {"tool_name": "mcp__x__dispatch", "tool_input": {
            "url": url}}, False),
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
