"""两层筛选引擎。纯函数，不碰存储和网络，便于测试。"""

from .criteria import L1, L2, MIN_DIM, REC_LINE

DECISION_STAGE = {"rec": ("已推荐", "good"), "hold": ("暂缓", "warn"), "no": ("不推荐", "bad")}


def weighted_total(p):
    return round(sum(p["l2"][c["key"]]["v"] * c["weight"] for c in L2), 2)


def evaluate(p):
    """返回系统建议：stage / level / reasons / total / text。只是建议，最终由人决定。"""
    fails = [c for c in L1 if p["l1"][c["key"]]["v"] == "fail"]
    if fails:
        reasons = [c["fail_reason"] for c in fails]
        return _res("初筛未通过", "bad", reasons, None, "第一层未过：" + "、".join(reasons))

    pending = [c for c in L1 if p["l1"][c["key"]]["v"] != "pass"]
    if pending:
        names = "、".join(c["title"] for c in pending)
        return _res("待补访谈", "warn", ["信息不全"], None, f"第一层待核实：{names}，补访谈后再判断")

    unscored = [c for c in L2 if not p["l2"][c["key"]]["v"]]
    if unscored:
        return _res("复筛中", "idle", [], None, f"第一层已过，第二层还有 {len(unscored)} 项没打分")

    total = weighted_total(p)
    lows = [c for c in L2 if p["l2"][c["key"]]["v"] < MIN_DIM]
    if total >= REC_LINE and not lows:
        return _res("建议推荐", "good", [], total, f"加权分 {total:.2f} ≥ {REC_LINE}，且没有短板项")

    if lows:
        reasons = [c["low_reason"] for c in lows]
    else:
        weakest = min(L2, key=lambda c: p["l2"][c["key"]]["v"])
        reasons = [weakest["low_reason"]]
    return _res("初筛未通过", "bad", reasons, total, f"第二层未达线（{total:.2f}）：" + "、".join(reasons))


def missing_evidence(p):
    """有判断却没写证据的标准名。证据链是这个系统的底线：每个判断都要能追溯到访谈原话。"""
    miss = [c["title"] for c in L1 if p["l1"][c["key"]]["v"] != "unk" and not p["l1"][c["key"]]["e"].strip()]
    miss += [c["title"] for c in L2 if p["l2"][c["key"]]["v"] and not p["l2"][c["key"]]["e"].strip()]
    return miss


def final_stage(p):
    if p.get("decision") in DECISION_STAGE:
        stage, level = DECISION_STAGE[p["decision"]]
        return {"stage": stage, "level": level}
    ev = evaluate(p)
    return {"stage": ev["stage"], "level": ev["level"]}


def annotate(p):
    return {**p, "eval": evaluate(p), "final": final_stage(p), "missing": missing_evidence(p)}


def summary(projects):
    """复盘：漏斗 + 未通过原因分布。"""
    evals = [evaluate(p) for p in projects]
    passed_l1 = sum(all(p["l1"][c["key"]]["v"] == "pass" for c in L1) for p in projects)
    reasons = {}
    rejected = 0
    for p, ev in zip(projects, evals):
        if ev["stage"] == "初筛未通过" or p.get("decision") == "no":
            rejected += 1
            for r in ev["reasons"] or ["人工判定不推荐"]:
                reasons[r] = reasons.get(r, 0) + 1
    return {
        "funnel": [
            ["访谈", len(projects)],
            ["过第一层", passed_l1],
            ["达到推荐线", sum(ev["stage"] == "建议推荐" for ev in evals)],
            ["已推荐", sum(p.get("decision") == "rec" for p in projects)],
        ],
        "rejected": rejected,
        "reasons": sorted(reasons.items(), key=lambda kv: -kv[1]),
    }


def checklist_markdown(projects):
    lines = ["# 初筛清单", ""]
    for p in projects:
        ev, fin = evaluate(p), final_stage(p)
        line = f"- {p['name'] or '未命名'}（{p.get('track', '')}）— {fin['stage']}"
        if ev["total"] is not None:
            line += f"，{ev['total']:.2f} 分"
        if ev["reasons"]:
            line += "，原因：" + "、".join(ev["reasons"])
        lines.append(line)
    return "\n".join(lines) + "\n"


def _res(stage, level, reasons, total, text):
    return {"stage": stage, "level": level, "reasons": reasons, "total": total, "text": text}
