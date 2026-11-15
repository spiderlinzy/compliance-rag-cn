# -*- coding: utf-8 -*-
"""批量评估：跑测试集，自动统计 spec 里的三项指标。

指标：
1) 无来源陈述数（硬指标，目标 0）
2) 引用准确率 = 通过验证的条目数 / 模型生成的条目数（目标 ≥90%）
3) 文档外问题正确拒答率（目标 ≥95%）
需要真实 API Key，结果同时存一份到 tests/eval_report.json。
"""
import json
import os

import generator
import verifier
from retriever import Retriever

TEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "test_questions.json")


def run_one(question, retriever):
    ok, q = generator.validate_question(question)
    if not ok:
        return {"refused": True, "reason": q, "generated": 0, "passed": 0, "blocked": 0}
    hard, results = retriever.hard_block(q)
    if hard:
        return {"refused": True, "reason": "硬拦截", "generated": 0, "passed": 0, "blocked": 0}
    data = generator.generate(q, results)
    if not data.get("answerable"):
        return {"refused": True, "reason": "模型判定无法回答", "generated": 0, "passed": 0, "blocked": 0}
    items = data.get("items", [])
    passed, blocked = verifier.verify(items, results)
    return {
        "refused": False,
        "generated": len(items),
        "passed": len(passed),
        "blocked": len(blocked),
        "unsourced": sum(1 for v in blocked if not v.citation_id),
        "detail": [{"claim": v.claim, "id": v.citation_id, "level": v.chunk.level} for v in passed],
    }


def main():
    suite = json.load(open(TEST_PATH, encoding="utf-8"))
    retriever = Retriever()
    rows = []
    for t in suite["questions"]:
        r = run_one(t["question"], retriever)
        r.update(id=t["id"], category=t["category"], question=t["question"])
        rows.append(r)
        state = "拒答" if r["refused"] else f"通过{r['passed']}/生成{r['generated']}，拦截{r['blocked']}"
        print(f"[{t['id']:2d}|{t['category'][:3]}] {state}  {t['question']}")

    total_unsourced = sum(r.get("unsourced", 0) for r in rows)
    gen_items = sum(r["generated"] for r in rows)
    passed_items = sum(r["passed"] for r in rows)
    out_questions = [r for r in rows if r["category"] == "out_of_scope"]
    out_correct = sum(1 for r in out_questions if r["refused"])

    report = {
        "无来源陈述数": total_unsourced,
        "引用准确率": round(passed_items / gen_items, 3) if gen_items else None,
        "文档外拒答率": round(out_correct / len(out_questions), 3),
        "生成条目总数": gen_items,
        "通过条目总数": passed_items,
    }
    print("\n===== 验收指标 =====")
    for k, v in report.items():
        print(f"{k}: {v}")

    json.dump({"summary": report, "rows": rows},
              open(os.path.join(os.path.dirname(TEST_PATH), "eval_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n明细已存 tests/eval_report.json")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print("无法运行：", e)
