#!/bin/sh
# 書込前の警告フック（PreToolUse）の入口。plugin.json の hooks から直接呼ばれる。
# 判定は write_gate_notice.py が行い、止めずに案内だけを JSON で返す。
# Anthropic のディレクトリの掲載の決まりに合わせ、使う変数は CLAUDE_PLUGIN_ROOT だけにし、
# 置換・展開・起動ツールを使わず、python3 をパスを書き下して呼ぶ。
# python3 が無い環境（Windows など）では何もせずに終える。どの場合も exit 0 で終える。
command -v python3 >/dev/null 2>&1 || exit 0
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ti-core/scripts/write_gate_notice.py"
exit 0
