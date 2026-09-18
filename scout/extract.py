"""从访谈转写里抽证据，给每条标准一个"建议"。

设计原则：
- AI 只给建议，不直接改项目记录；采纳与否由人在界面上点。
- 引用必须能在原文里逐字找到，找不到的一律丢弃——防止模型编造证据。
- 没配 API key 时退回关键词匹配：只摘句子，不下判断。
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

from .criteria import L1, L2

SYSTEM = (
    "你是早期投资机构的项目筛选助手。根据创业者访谈转写，按给定标准逐条判断，"
    "每条必须给出转写中的逐字引用作为证据；转写里没有依据的，判断填 unk（第一层）或 0（第二层），引用留空。"
    "只输出 JSON，不要任何解释。"
)


def _schema_hint():
    l1 = "\n".join(f'- {c["key"]}（{c["title"]}）：{c["question"]} 取值 pass/unk/fail' for c in L1)
    l2 = "\n".join(
        f'- {c["key"]}（{c["title"]}）：{c["question"]} 取值 1-5，锚点：'
        + "；".join(f"{k}={v}" for k, v in c["anchors"].items())
        for c in L2
    )
    return (
        f"第一层（硬门槛）：\n{l1}\n\n第二层（打分）：\n{l2}\n\n"
        '输出格式：{"items":[{"key":"scene","v":"pass","quote":"原文逐字片段","reason":"一句话理由"}, ...]}，'
        "每个 key 恰好一条。"
    )


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def verify(items, transcript):
    """丢掉引用不在原文里的判断，并把取值收敛到合法范围。"""
    src = _norm(transcript)
    valid_keys = {c["key"]: "l1" for c in L1} | {c["key"]: "l2" for c in L2}
    out = {}
    for it in items:
        key = it.get("key")
        if key not in valid_keys or key in out:
            continue
        quote = (it.get("quote") or "").strip()
        layer = valid_keys[key]
        v = it.get("v")
        if layer == "l1":
            v = v if v in ("pass", "unk", "fail") else "unk"
        else:
            try:
                v = max(0, min(5, int(v)))
            except (TypeError, ValueError):
                v = 0
        note = (it.get("reason") or "").strip()
        if quote and _norm(quote) not in src:
            v, quote, note = ("unk" if layer == "l1" else 0), "", "模型给出的引用在原文中找不到，已丢弃"
        elif not quote:
            v = "unk" if layer == "l1" else 0
        out[key] = {"layer": layer, "v": v, "quote": quote, "reason": note}
    return out


def keyword_fallback(transcript):
    sentences = [s.strip() for s in re.split(r"[。！？!?\n]", transcript) if s.strip()]
    out = {}
    for layer, crits in (("l1", L1), ("l2", L2)):
        for c in crits:
            hits = [s for s in sentences if any(k.lower() in s.lower() for k in c["keywords"])]
            out[c["key"]] = {
                "layer": layer,
                "v": "unk" if layer == "l1" else 0,
                "quote": "；".join(hits[:2]),
                "reason": "关键词匹配到的候选句，需人工判断" if hits else "转写里没找到相关内容",
            }
    return out


def call_llm(transcript, *, timeout=180, retries=2):
    base = os.environ["ARK_BASE_URL"].rstrip("/")
    model = os.environ.get("SCOUT_MODEL") or os.environ.get("ARK_CHAT_A")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _schema_hint() + "\n\n访谈转写：\n" + transcript},
        ],
        # 推理模型的思考过程也计入 max_tokens，给小了会截断 JSON
        "max_tokens": 8000,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["ARK_API_KEY"]},
    )
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                content = json.load(r)["choices"][0]["message"]["content"] or ""
            m = re.search(r"\{.*\}", content, re.S)
            if not m:
                raise ValueError("模型返回为空或不是 JSON")
            return json.loads(m.group(0)).get("items", [])
        except (urllib.error.URLError, ValueError, KeyError, json.JSONDecodeError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"模型调用失败：{last}")


def suggest(transcript):
    """返回 {"mode": "llm"|"keyword", "items": {key: {...}}, "warning": str|None}"""
    transcript = (transcript or "").strip()
    if not transcript:
        raise ValueError("访谈转写是空的")
    if os.environ.get("ARK_API_KEY") and os.environ.get("ARK_BASE_URL"):
        try:
            return {"mode": "llm", "items": verify(call_llm(transcript), transcript), "warning": None}
        except RuntimeError as e:
            return {"mode": "keyword", "items": keyword_fallback(transcript), "warning": str(e) + "，已退回关键词匹配"}
    return {"mode": "keyword", "items": keyword_fallback(transcript), "warning": "未配置模型 API，使用关键词匹配"}
