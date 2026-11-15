# -*- coding: utf-8 -*-
"""引用验证器（项目核心，对应书中 6.7.1）。

独立于生成环节，做两层核查：
1) 结构校验（纯规则、零成本）：引用的片段 ID 必须真实存在于本次检索结果，
   拦截凭空捏造的 ID；
2) 支撑性校验（独立模型调用）：把"陈述"和"引用原文"交给模型判断原文是否真的支持，
   拦截"ID 是真的、但原文跟陈述对不上"的错引。
核查与生成是两次独立的模型调用，形成权力制衡，避免"运动员兼裁判"。
"""
import json
from dataclasses import dataclass

from generator import get_client
import config
import glossary


@dataclass
class VerifiedItem:
    claim: str          # 一条事实陈述
    citation_id: str    # 它引用的片段 ID
    valid: bool         # 是否通过核查
    reason: str         # 判定理由
    chunk: object = None  # 对应的片段对象（通过后用来算置信度）


VERIFY_PROMPT = """你是独立的引用核查员。对每个配对，判断"原文"是否支持"陈述"。
只有原文信息能合理推出陈述时才算支持；原文没有、与陈述矛盾、或需要额外信息，都算不支持。
但会同时提供"受控术语表"，它是系统定义的标准分类：若陈述中的下位-上位归类（如虹膜属于生物识别）
与术语表一致，这一步视为有依据，只需再确认上位术语被原文支持即可；术语表之外的归类仍算不支持。
只输出 JSON 数组，不要其他文字：
[{"index": 0, "supported": true, "reason": "简短理由"}]"""


def structure_check(items, results):
    """第一层：ID 真实性校验（不调模型）。返回 (待语义核查, 已判定失败)。"""
    id_map = {c.chunk_id: c for c, _s in results}
    pending, failed = [], []
    for item in items:
        cid = item.get("citation_id", "")
        if cid not in id_map:
            failed.append(VerifiedItem(item.get("claim", ""), cid, False, "引用ID不存在（疑似编造）"))
        else:
            pending.append((item, id_map[cid]))
    return pending, failed


def semantic_check(pending, api_key=None):
    """第二层：批量语义核查，一次模型调用判断所有配对。"""
    if not pending:
        return []
    pairing = []
    for i, (item, chunk) in enumerate(pending):
        pairing.append(f"[{i}]\n陈述：{item['claim']}\n原文：{chunk.text}")
    user_content = ("受控术语表：\n" + glossary.render_for_prompt()
                    + "\n\n待核查配对：\n\n" + "\n\n".join(pairing))
    client = get_client(api_key)
    resp = client.chat.completions.create(
        model=config.MODEL_NAME,
        messages=[
            {"role": "system", "content": VERIFY_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
    )
    verdicts = json.loads(resp.choices[0].message.content)
    by_index = {v["index"]: v for v in verdicts}

    out = []
    for i, (item, chunk) in enumerate(pending):
        # 验证器若漏返回某条，保守按不通过处理，宁可拦下也不放过
        v = by_index.get(i, {"supported": False, "reason": "验证器未返回结果，保守拦截"})
        out.append(VerifiedItem(
            claim=item["claim"],
            citation_id=chunk.chunk_id,
            valid=bool(v["supported"]),
            reason=v.get("reason", ""),
            chunk=chunk,
        ))
    return out


def verify(items, results, api_key=None):
    """完整验证：先结构、再语义，返回 (通过列表, 拦截列表)。"""
    pending, failed = structure_check(items, results)
    checked = semantic_check(pending, api_key)
    passed = [v for v in checked if v.valid]
    blocked = failed + [v for v in checked if not v.valid]
    return passed, blocked


def confidence_label(passed):
    """按通过条目引用片段的 FTH 层级算整体置信度。
    取所有来源里最低的层级（木桶效应），保证置信度不超过材料的信任级。"""
    if not passed:
        return "无法回答"
    min_rank = min(config.TRUST_LEVELS[v.chunk.level]["rank"] for v in passed)
    return next(info["label"] for info in config.TRUST_LEVELS.values() if info["rank"] == min_rank)
