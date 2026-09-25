#!/usr/bin/env python3
"""check_firing.py — 規約が定めた先行手順を踏んだかを、セッション記録から機械で数える。

## なぜ要るか

スキルの発火は4段（在処・索引・認知・実行）で、**3段目の「いま自分がその条件の中にいる」
という認知だけが痕跡を残さない**。証跡を出す担い手が発火すべき本人と同じなので、
発火しなければ証跡も出ず、**不発の応答は正常系と一文字も変わらない**。

2026-09-14、本番組織へ見積レコードを作る作業で、書込前ゲート `atlas_write_seam` を
引かずに INSERT し入力規則2本に連続で弾かれた。意味定義は回避手順まで持っていたが、
引く導線に辿り着けなかった。索引は直したが、**直した効果を測る手段が無い**。

本スクリプトは、AI の自己申告に依存せず、**実際に何を呼んだか**をセッション記録から
再構成して発火率を出す。予防ではなく観測で、事故そのものは止めない。

## 何を判定するか（機械化の境界）

判定できるのは次の2層まで。

  L1 事象の有無     … その操作・その主張が記録に在るか
  L2 事象の対の成立 … A が在るなら、その前に B が在るか（順序と対象の一致つき）
  L3 内容への従属   … B の返りの中身に従って A を行ったか  ← **判定できない**

したがって発火点は「トリガ事象 → 先行必須事象」の形でしか宣言できない。
「〜する瞬間」「〜を検討するとき」のように痕跡を残さない引き金は宣言できない。

## 使い方

    python3 check_firing.py --mode post [--since 30] [--from 2026-09-01] [--to 2026-09-14]
    python3 check_firing.py --mode post --points /path/to/firing_points.yml
    python3 check_firing.py --selftest          # 陽性・陰性の両側を実測する
    python3 check_firing.py --selftest --probe-store   # 記録の在処だけを確かめる

宣言の在処は `--points` か環境変数 `TSUBAISO_FIRING_POINTS`（`:` 区切りで複数）。
既定は本スクリプトの1つ上の `firing_points.yml`。**場所をコードへ焼き込まない**のは
環境ごとに在処が違うため。

## 終了コード

    0 = 不発なし
    1 = 不発あり（severity: violation の発火点のみ。advisory は列挙するだけ）
    2 = **未判定**（記録に到達できない・宣言が読めない）。成功へ丸めない
    3 = 引数エラー

`exit 2` を `0` と同じ扱いにしないこと。ホスト実行できない環境・記録のパス構造が
変わった環境では「検査していない」のであって「問題が無い」のではない。

## 顧客環境での扱い [REQUIRED]

  - **観測は任意**。ホスト実行の手段が無い環境では走らない。必須にすると実行不能な
    必須手順になる
  - **セッション記録は利用者のデータ**。本スクリプトは記録を読むだけで外へ送らない。
    出力する `events.jsonl` にも業務データ（項目の値・本文）を入れず、
    発火点 ID・状態・対象オブジェクトの API 名・時刻・セッションのハッシュだけを残す

## 実測（config-governance §統制は陽性ケースで発火することを実測する）

  - 陽性 / 陰性 / 未判定 の3側を `--selftest` が合成検体で毎回確かめる
  - 実行不能（記録に到達できない）は exit 2 で明示し、成功へ丸めない

標準ライブラリのみ。既存ファイルの書き換えはせず events.jsonl への追記だけを行う。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HOME = Path.home()

# --------------------------------------------------------------------------
# 記録の在処（環境依存事実。SKILL.md 側の reference に実証日つきで記載）
# --------------------------------------------------------------------------

DEFAULT_SESSION_GLOBS = [
    # Cowork（デスクトップアプリ）— 本体セッション
    str(HOME / "Library/Application Support/Claude/local-agent-mode-sessions"
             / "*/*/local_*/.claude/projects/*/*.jsonl"),
    # Cowork — サブエージェント
    str(HOME / "Library/Application Support/Claude/local-agent-mode-sessions"
             / "*/*/local_*/.claude/projects/*/*/subagents/*.jsonl"),
    # Claude Code（CLI）
    str(HOME / ".claude/projects/*/*.jsonl"),
]

DEFAULT_OUT = "events.jsonl"

# 観測の起点。これより前は TI をプラグインとして配布しておらず、スキルの導線が
# 今と違う。前提が違う記録を同じ母集団に入れると発火率が意味を失う
# （`ti-debug-monitoring §検収の起点` と同じ理由・同じ値）。
#
# 2026-09-14 実測: この起点を外すと、2026-06-21 の 1 セッションにあるメタデータ
# デプロイ 7 件が「発火率 0%」として出る。当時は安全ゲートの reference が配布物に
# 無く、**統制の不全ではなく観測範囲の誤り**だった。
DEFAULT_BASELINE = "2026-08-01"

# 読込系ツール（requires.read_path の判定に使う）
READ_TOOLS = {"Read", "read_file", "read_multiple_files", "get_file_contents"}


# --------------------------------------------------------------------------
# 宣言ファイルの読み込み（制限付き YAML の自前パーサ）
# --------------------------------------------------------------------------
#
# PyYAML を要求しないのは、顧客環境に入っている保証が無いため。
# 対応するのは本スキーマが使う範囲だけで、それ以外は明示的に撥ねる。
#   - トップレベルはマッピングの並び（`- key: value`）
#   - 値はスカラ・インラインリスト（`[a, b]`）・インラインマップ（`{a: b}`）・ネストマップ
#   - アンカー・複数行文字列・コメント以外の記法は非対応

class DeclError(Exception):
    pass


def _scalar(tok: str):
    tok = tok.strip()
    if not tok:
        return None
    if tok[0] in "\"'" and tok[-1] == tok[0] and len(tok) >= 2:
        return tok[1:-1]
    low = tok.lower()
    if low in ("null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if re.fullmatch(r"-?\d+", tok):
        return int(tok)
    return tok


def _split_top(s: str, sep: str = ","):
    """括弧・引用符の内側を無視して分割する。"""
    out, buf, depth, quote = [], "", 0, None
    for ch in s:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf += ch
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == sep and depth == 0:
            out.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf)
    return out


def _inline(tok: str):
    tok = tok.strip()
    if tok.startswith("[") and tok.endswith("]"):
        return [_inline(p) for p in _split_top(tok[1:-1])]
    if tok.startswith("{") and tok.endswith("}"):
        d = {}
        for p in _split_top(tok[1:-1]):
            if ":" not in p:
                raise DeclError(f"インラインマップの要素に ':' がありません: {p}")
            k, v = p.split(":", 1)
            d[k.strip()] = _inline(v)
        return d
    return _scalar(tok)


def _strip_comment(line: str) -> str:
    out, quote = "", None
    for ch in line:
        if quote:
            out += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            out += ch
            continue
        if ch == "#":
            break
        out += ch
    return out.rstrip()


def parse_points(text: str):
    """制限付き YAML → list[dict]。"""
    rows = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        rows.append((indent, line.strip()))

    items, stack = [], []

    def container_for(indent):
        while stack and stack[-1][0] >= indent:
            stack.pop()
        return stack[-1][1] if stack else None

    for indent, body in rows:
        if body.startswith("- "):
            if indent != 0:
                raise DeclError(f"ネストしたリストには対応していません: {body}")
            cur = {}
            items.append(cur)
            stack = [(0, cur)]
            body = body[2:].strip()
            indent = 1
            if not body:
                continue
        target = container_for(indent)
        if target is None:
            raise DeclError(f"所属先が決まらない行です: {body}")
        if ":" not in body:
            raise DeclError(f"'key: value' の形ではありません: {body}")
        key, val = body.split(":", 1)
        key, val = key.strip(), val.strip()
        if val == "":
            child = {}
            target[key] = child
            stack.append((indent, child))
        else:
            target[key] = _inline(val)
    return items


# --------------------------------------------------------------------------
# 対象オブジェクト名の正規化
# --------------------------------------------------------------------------
#
# 2026-09-14 実測: `atlas_write_seam` の `target` は短縮形 34 件・名前空間あり 42 件で
# 割れている（`SalesOrder__c` と `tb_PSA__tb_SalesOrder__c` が混在）。書込ツール側は
# 常に名前空間つき。**推測で完全一致にすると半分を取りこぼす**ので、名前空間を剥がして
# 比べる。

#
# 実測では3つの形が混在する。
#   tb_PSA__tb_SalesOrder__c ／ tb_SalesOrder__c ／ SalesOrder__c
# したがって (1) 名前空間を剥がし (2) 先頭のパッケージ接頭辞も剥がして比べる。
#
# **(2) は取り違えを生みうる**（`tb_Project__c` と標準の `Project__c` が同一視される）。
# それでも剥がすのは、剥がさないと短縮形の seam が一度も当たらず、**実際には引いた回まで
# 不発として数える**ため。偽陽性で埋まった統制は読み飛ばされて機能しなくなる
# （config-governance §統制は陽性ケースで発火することを実測する 原則6）。
# 衝突が実際に起きたら、宣言側へ完全一致を指定する逃げ道を足す。

_PKG_PREFIX = re.compile(r"^(tb_|tbi_|ima_)", re.I)


def normalize_object(name):
    if not isinstance(name, str) or not name:
        return None
    n = name.strip()
    # 名前空間つきカスタムオブジェクト（`ns__obj__c`）は先頭の名前空間を剥がす
    while n.count("__") >= 2:
        n = n.split("__", 1)[1]
    n = _PKG_PREFIX.sub("", n)
    return n.lower()


# 書込ツールが対象オブジェクトを渡すキー（2026-09-14 実測で確定。推測では書かない）
OBJECT_KEYS = ("sobject-name", "object_type", "sobjectType", "objectName", "target")


def extract_object(inp):
    if not isinstance(inp, dict):
        return None
    for k in OBJECT_KEYS:
        if k in inp:
            v = normalize_object(inp[k])
            if v:
                return v
    return None


# --------------------------------------------------------------------------
# セッション記録の読み込み
# --------------------------------------------------------------------------

def _flat(value, limit=6000):
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:limit]
    try:
        return json.dumps(value, ensure_ascii=False)[:limit]
    except Exception:  # noqa: BLE001
        return str(value)[:limit]


def load_turns(path):
    """1ファイルを turn の並びへ畳む。

    turn の境界は「tool_result を含まない role=user のメッセージ」。
    tool_result も role=user で来るため、これで本物の利用者発言だけを拾える。
    """
    turns, cur, seq = [], None, 0
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return []
    with fh:
        for line in fh:
            try:
                o = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            m = o.get("message") or {}
            role = m.get("role")
            content = m.get("content")
            ts = o.get("timestamp") or ""
            if role == "user":
                blocks = content if isinstance(content, list) else []
                has_result = any(isinstance(b, dict) and b.get("type") == "tool_result"
                                 for b in blocks)
                if not has_result:
                    cur = {"ts": ts, "tools": [], "texts": []}
                    turns.append(cur)
                    continue
            if role != "assistant" or not isinstance(content, list):
                continue
            if cur is None:
                cur = {"ts": ts, "tools": [], "texts": []}
                turns.append(cur)
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    seq += 1
                    cur["tools"].append({
                        "seq": seq,
                        "name": (b.get("name") or "").split("__")[-1],
                        "full": b.get("name") or "",
                        "input": b.get("input") or {},
                        "ts": ts,
                    })
                elif b.get("type") == "text":
                    t = b.get("text") or ""
                    if t.strip():
                        cur["texts"].append(t)
    return turns


def local_ts(ts):
    """記録の時刻はUTC。日付で切るときは実行機の地方時へ直してから比べる。

    2026-09-14 実測: UTC のまま日付でスライスすると JST とは9時間ずれ、
    「マージの前後」で切ったつもりの境界が実際には別の位置に来る。
    地方時を固定値で持たず実行機から取るのは、顧客が別のタイムゾーンにいるため。
    """
    if not ts:
        return ""
    try:
        dt = _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return str(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone().isoformat(timespec="seconds")


def iter_session_files(globs, since_days=None, date_from=None, date_to=None):
    seen, files = set(), []
    for g in globs:
        for f in glob.glob(g):
            if f in seen:
                continue
            seen.add(f)
            files.append(f)
    if since_days is not None:
        cutoff = _dt.datetime.now().timestamp() - since_days * 86400
        files = [f for f in files if os.path.getmtime(f) >= cutoff]
    return sorted(files)


# --------------------------------------------------------------------------
# 判定
# --------------------------------------------------------------------------

_PAT_CACHE = {}


def _compiled(pattern):
    p = _PAT_CACHE.get(pattern)
    if p is None:
        p = _PAT_CACHE[pattern] = re.compile(pattern)
    return p


def _match_tool(patterns, name):
    if isinstance(patterns, str):
        patterns = [patterns]
    for p in patterns or []:
        if re.search(str(p), name):
            return True
    return False


def evaluate_turn(point, turn, prior_tools):
    """1 turn を判定して結果の並びを返す。

    返す status は fired / missed / undetermined の3値。
    **未判定を fired にも missed にも混ぜない**（確認できた項目だけを確認済みと表示する）。
    """
    trig = point.get("trigger") or {}
    req = point.get("requires") or {}
    scope = str(req.get("scope") or "session")
    out = []

    events = []
    if trig.get("tool"):
        for t in turn["tools"]:
            if _match_tool(trig["tool"], t["name"]):
                events.append(("tool", t))
    # text_all は「すべてに当たる」＝共起の要求。1本の正規表現へ先読みで畳むと
    # 長文で計算量が跳ねるので、短い式を順に当てる形にしてある。
    text_pats = trig.get("text_all") or ([trig["text"]] if trig.get("text") else [])
    if text_pats:
        pats = [_compiled(str(p)) for p in text_pats]
        for txt in turn["texts"]:
            if all(p.search(txt) for p in pats):
                events.append(("text", {"seq": 10 ** 9, "name": "(text)",
                                        "input": {}, "ts": turn["ts"]}))
                break

    for kind, ev in events:
        window = list(turn["tools"]) if scope == "turn" else prior_tools + turn["tools"]
        window = [w for w in window if w["seq"] < ev["seq"]]

        want_obj = None
        undetermined = False
        if req.get("same_object"):
            want_obj = extract_object(ev["input"])
            if want_obj is None and kind == "tool":
                undetermined = True

        hit = None
        for w in window:
            if req.get("tool") and not _match_tool(req["tool"], w["name"]):
                continue
            if req.get("read_path"):
                if w["name"] not in READ_TOOLS and "read" not in w["name"].lower():
                    continue
                if not re.search(str(req["read_path"]), _flat(w["input"])):
                    continue
            if req.get("same_object") and want_obj is not None:
                if extract_object(w["input"]) != want_obj:
                    continue
            hit = w
            break

        if undetermined:
            status = "undetermined"
        elif hit:
            status = "fired"
        else:
            status = "missed"
        out.append({
            "point": point["id"],
            "severity": point.get("severity", "violation"),
            "status": status,
            "object": want_obj or extract_object(ev["input"]),
            "trigger": ev["name"],
            "ts": ev["ts"] or turn["ts"],
        })
    return out


def scan(files, points, date_from=None, date_to=None):
    results, reached = [], 0
    for f in files:
        turns = load_turns(f)
        if not turns:
            continue
        reached += 1
        sid = hashlib.sha1(f.encode("utf-8")).hexdigest()[:12]
        prior = []
        for ti, turn in enumerate(turns):
            lts = local_ts(turn["ts"])
            in_range = True
            if date_from and lts and lts[:len(date_from)] < date_from:
                in_range = False
            if date_to and lts and lts[:len(date_to)] > date_to:
                in_range = False
            if in_range:
                for p in points:
                    for r in evaluate_turn(p, turn, prior):
                        r["session"] = sid
                        r["turn"] = ti
                        r["file"] = os.path.basename(f)
                        results.append(r)
            prior = prior + turn["tools"]
    return results, reached


# --------------------------------------------------------------------------
# 出力
# --------------------------------------------------------------------------

def summarize(results, points):
    by = {p["id"]: {"fired": 0, "missed": 0, "undetermined": 0} for p in points}
    for r in results:
        by.setdefault(r["point"], {"fired": 0, "missed": 0, "undetermined": 0})
        by[r["point"]][r["status"]] += 1
    return by


def render(results, points, reached, out_path=None):
    by = summarize(results, points)
    meta = {p["id"]: p for p in points}
    print(f"走査したセッション記録: {reached} 件")
    print()
    print("発火点ごとの母数と発火率")
    print(f"  {'発火点':<34} {'母数':>5} {'発火':>5} {'不発':>5} {'未判定':>6} {'発火率':>7}")
    violations = 0
    for pid, c in by.items():
        total = c["fired"] + c["missed"] + c["undetermined"]
        judged = c["fired"] + c["missed"]
        rate = f"{100 * c['fired'] / judged:.0f}%" if judged else "—"
        print(f"  {pid:<34} {total:>5} {c['fired']:>5} {c['missed']:>5} "
              f"{c['undetermined']:>6} {rate:>7}")
        if total == 0:
            print(f"      ⚠ 母数 0。トリガが一度も起きていないか、宣言が当たっていない")
        if judged and c["fired"] == 0:
            print(f"      ⚠ 発火率 0%。宣言の条件か置き場の誤りを先に疑う")
        if meta.get(pid, {}).get("severity", "violation") == "violation":
            violations += c["missed"]

    misses = [r for r in results if r["status"] == "missed"]
    if misses:
        print()
        print(f"不発の明細（新しい順・最大20件／全 {len(misses)} 件）")
        for r in sorted(misses, key=lambda x: x["ts"], reverse=True)[:20]:
            sev = meta.get(r["point"], {}).get("severity", "violation")
            mark = "✗" if sev == "violation" else "·"
            obj = r["object"] or "—"
            print(f"  {mark} [{local_ts(r['ts'])[:19]}] {r['point']} / {obj} "
                  f"(session {r['session']} turn {r['turn']})")
        print("  ✗ = severity violation（終了コードに反映）  · = advisory（列挙のみ）")

    if out_path:
        written = append_events(results, out_path)
        print()
        print(f"{out_path} へ {written} 件を追記しました（冪等・重複は event_id で弾く）")
    return violations


def append_events(results, out_path):
    """業務データを入れない。発火点 ID・状態・対象の API 名・時刻だけを残す。"""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    known = set()
    if path.exists():
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    known.add(json.loads(line).get("event_id"))
                except Exception:  # noqa: BLE001
                    continue
    written = 0
    with open(path, "a", encoding="utf-8") as fh:
        for r in results:
            eid = hashlib.sha1(
                f"{r['session']}|{r['turn']}|{r['point']}|{r['ts']}|{r['object']}"
                .encode("utf-8")).hexdigest()
            if eid in known:
                continue
            known.add(eid)
            fh.write(json.dumps({
                "event_id": eid, "point": r["point"], "status": r["status"],
                "object": r["object"], "ts": r["ts"], "session": r["session"],
                "turn": r["turn"], "severity": r["severity"],
            }, ensure_ascii=False) + "\n")
            written += 1
    return written


# --------------------------------------------------------------------------
# 自己検証
# --------------------------------------------------------------------------

POSITIVE = [
    {"role": "user", "content": "見積明細を作ってください"},
    {"role": "assistant", "content": [
        {"type": "tool_use", "name": "mcp__x__createSobjectRecord",
         "input": {"sobject-name": "tb_PSA__tb_QuoteDetail__c", "body": {}}}]},
]

NEGATIVE = [
    {"role": "user", "content": "見積明細を作ってください"},
    {"role": "assistant", "content": [
        {"type": "tool_use", "name": "mcp__y__atlas_write_seam",
         "input": {"target": "QuoteDetail__c"}}]},   # 短縮形でも当たること
    {"role": "assistant", "content": [
        {"type": "tool_use", "name": "mcp__x__createSobjectRecord",
         "input": {"sobject-name": "tb_PSA__tb_QuoteDetail__c", "body": {}}}]},
]

UNDETERMINED = [
    {"role": "user", "content": "作ってください"},
    {"role": "assistant", "content": [
        {"type": "tool_use", "name": "mcp__x__createSobjectRecord",
         "input": {"body": {}}}]},                   # 対象が取れない
]

WRONG_OBJECT = [
    {"role": "user", "content": "見積明細を作ってください"},
    {"role": "assistant", "content": [
        {"type": "tool_use", "name": "mcp__y__atlas_write_seam",
         "input": {"target": "tb_PSA__tb_SalesOrder__c"}}]},   # 別オブジェクト
    {"role": "assistant", "content": [
        {"type": "tool_use", "name": "mcp__x__createSobjectRecord",
         "input": {"sobject-name": "tb_PSA__tb_QuoteDetail__c", "body": {}}}]},
]


def _write_fixture(d, name, msgs):
    p = Path(d) / f"{name}.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for m in msgs:
            fh.write(json.dumps({"message": m,
                                 "timestamp": "2026-09-14T01:00:00.000Z"},
                                ensure_ascii=False) + "\n")
    return str(p)


def selftest(points, probe_store=False):
    ok = True
    if probe_store:
        files = iter_session_files(DEFAULT_SESSION_GLOBS)
        print(f"記録の在処: {len(files)} 件のセッション記録に到達")
        if not files:
            print("  ✗ 0 件。パス構造が変わったか、ホスト実行でない可能性がある")
            print("    0 件は『記録がまだ無い』正常系と同じ顔をしている。ここで止める")
            return False
        turns = load_turns(files[-1])
        tools = sum(len(t["tools"]) for t in turns)
        texts = sum(len(t["texts"]) for t in turns)
        print(f"  最新の1件: turn {len(turns)} / tool_use {tools} / 応答本文 {texts}")
        return tools > 0

    wp = [p for p in points if p["id"] == "write_seam_before_record_write"]
    if not wp:
        print("✗ 自己検証に使う宣言 write_seam_before_record_write が見つからない")
        return False

    cases = [
        ("陽性（seam を引かずに作成）", POSITIVE, "missed"),
        ("陰性（短縮形の seam を先に引いた）", NEGATIVE, "fired"),
        ("陰性（別オブジェクトの seam は当たらない）", WRONG_OBJECT, "missed"),
        ("未判定（対象が取れない）", UNDETERMINED, "undetermined"),
    ]
    with tempfile.TemporaryDirectory() as d:
        for label, msgs, want in cases:
            f = _write_fixture(d, label.replace("（", "_").replace("）", ""), msgs)
            res, _ = scan([f], wp)
            got = res[0]["status"] if res else "(検出なし)"
            mark = "✓" if got == want else "✗"
            if got != want:
                ok = False
            print(f"  {mark} {label}: 期待 {want} / 実測 {got}")

    # 宣言パーサの検体
    try:
        parsed = parse_points(
            "- id: t\n  trigger:\n    tool: [a, b]\n  requires:\n"
            "    tool: c\n    same_object: true\n  severity: advisory\n")
        assert parsed[0]["trigger"]["tool"] == ["a", "b"], parsed
        assert parsed[0]["requires"]["same_object"] is True, parsed
        assert parsed[0]["severity"] == "advisory", parsed
        print("  ✓ 宣言パーサ: ネストマップ・インラインリスト・真偽値を復元")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"  ✗ 宣言パーサ: {e}")

    print()
    print("陽性・陰性・未判定の3側とも意図どおり" if ok else "意図と違う結果がある")
    return ok


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

def resolve_points_paths(arg):
    if arg:
        return [p for p in arg.split(":") if p]
    env = os.environ.get("TSUBAISO_FIRING_POINTS")
    if env:
        return [p for p in env.split(":") if p]
    return [str(Path(__file__).resolve().parent.parent / "firing_points.yml")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode", choices=["post"], help="post = 完了セッションの事後走査")
    ap.add_argument("--points", help="宣言ファイル（':' 区切りで複数）")
    ap.add_argument("--since", type=int, help="更新日が直近 N 日の記録だけを見る")
    ap.add_argument("--from", dest="date_from",
                    help=f"この地方時以降の turn だけ（既定 {DEFAULT_BASELINE}）。"
                         "YYYY-MM-DD または YYYY-MM-DDTHH:MM")
    ap.add_argument("--to", dest="date_to", help="この地方時以前の turn だけ")
    ap.add_argument("--all", action="store_true",
                    help="観測の起点を外して全期間を見る（傾向を眺める用途のみ。"
                         "導線の前提が違う記録が混ざるので改善の判断根拠にしない）")
    ap.add_argument("--out", help="events.jsonl の書き出し先（省略時は書かない）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--probe-store", action="store_true",
                    help="--selftest と併用。記録の在処だけを確かめる")
    a = ap.parse_args(argv)

    paths = resolve_points_paths(a.points)
    points = []
    for p in paths:
        try:
            points += parse_points(Path(p).read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(f"未判定: 宣言ファイルが見つかりません: {p}", file=sys.stderr)
            return 2
        except DeclError as e:
            print(f"未判定: 宣言ファイルを読めません: {p}: {e}", file=sys.stderr)
            return 2
    for p in points:
        if "id" not in p or "trigger" not in p:
            print(f"未判定: id か trigger が無い宣言があります: {p}", file=sys.stderr)
            return 2

    if a.selftest:
        return 0 if selftest(points, a.probe_store) else 1

    if a.mode != "post":
        ap.print_help()
        return 3

    globs = os.environ.get("TSUBAISO_SESSION_GLOBS")
    globs = [g for g in globs.split(":")] if globs else DEFAULT_SESSION_GLOBS
    files = iter_session_files(globs, since_days=a.since)
    if not files:
        print("未判定: セッション記録に1件も到達できませんでした。", file=sys.stderr)
        print("  サンドボックスからは記録の在処が見えません。ホストで実行してください。",
              file=sys.stderr)
        print("  0 件は『記録がまだ無い』正常系と同じ顔をしているので、"
              "成功として扱いません。", file=sys.stderr)
        return 2

    date_from = a.date_from or (None if a.all else DEFAULT_BASELINE)
    results, reached = scan(files, points, date_from, a.date_to)
    if reached == 0:
        print("未判定: 記録は見つかりましたが、読める形の turn がありませんでした。",
              file=sys.stderr)
        return 2
    violations = render(results, points, reached, a.out)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
