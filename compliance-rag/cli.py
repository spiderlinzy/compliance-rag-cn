# -*- coding: utf-8 -*-
"""命令行入口：把 校验 → 检索 → 硬拦截 → 生成 → 引用验证 → 分层输出 串成一条链。

每次提问独立处理，不保留对话上下文（单轮问答）。
输入 quit 或 exit 退出。
"""
import config
import generator
import verifier
from retriever import Retriever

REFUSAL = "无法在知识库中找到可靠来源，请联系合规团队。"


def answer(question, retriever):
    # 分叉 1：输入校验（空、超长）
    ok, q = generator.validate_question(question)
    if not ok:
        print(q)
        return

    # 分叉 2：检索 + 硬拦截（词面零命中或分数过低）
    blocked, results = retriever.hard_block(q)
    if blocked:
        print(REFUSAL)
        return

    # 分叉 3：模型语义判断（answerable=false 即拒答）
    data = generator.generate(q, results)
    if not data.get("answerable"):
        print(REFUSAL)
        return

    # 分叉 4：独立验证器，全部没通过就不输出事实
    passed, blocked_items = verifier.verify(data.get("items", []), results)
    if not passed:
        print("所有陈述均未通过引用验证，无法给出可靠回答，请联系合规团队。")
        _show_blocked(blocked_items)
        return

    # 正常出口：逐条展示事实、引用、置信度，最后给整体置信度
    print("\n" + "=" * 56)
    for v in passed:
        info = config.TRUST_LEVELS[v.chunk.level]
        print(f"事实：{v.claim}")
        print(f"引用：{v.chunk.source} ｜ {v.chunk.locator}（{v.citation_id}）")
        print(f"置信度：{info['label']}（来源为{info['name']}）")
        print("-" * 56)
    print(f"整体置信度：【{verifier.confidence_label(passed)}】")
    _show_blocked(blocked_items)


def _show_blocked(blocked_items):
    """透明展示被拦截的陈述和原因，让用户知道系统拦下了什么。"""
    if not blocked_items:
        return
    print("\n⚠ 以下陈述被引用验证器拦截，未纳入回答：")
    for v in blocked_items:
        print(f"  · {v.claim}  原因：{v.reason}")


def main():
    retriever = Retriever()
    print("可信金融合规问答器（输入 quit 退出）")
    while True:
        try:
            question = input("\n请提问 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("quit", "exit", "q"):
            break
        if question:
            answer(question, retriever)
    print("\n再见。")


if __name__ == "__main__":
    main()
