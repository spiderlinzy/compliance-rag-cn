# -*- coding: utf-8 -*-
"""受控术语表（Controlled Glossary）。

把"材料里概括性类别词的标准下位实例"这种定义性、无争议的归类，显式写成
可审计的确定性知识，而不是依赖模型自带的隐性常识。

它解决的问题：法条只写了"生物识别"，但用户会问"虹膜/指纹是不是敏感信息"。
有了这张表，生成器和验证器都能确认"虹膜属于生物识别"是受控的标准归类，
再结合原文"生物识别属于敏感个人信息"，就能有据作答。

设计原则：
1. 白名单逻辑——只放行表里明确列出的归类，没列的一律按原规则拒答，
   所以表小不会导致错误，只是放行得少。
2. 可增量——先做高概率被追问的类别，遇到答不上的再补，不追求一次做全。
3. 可审计——每个归类都应能在权威来源（法律条文、国家标准）中找到依据。

下位实例参考国家标准《信息安全技术 个人信息安全规范》（GB/T 35273）
对"生物识别信息"的举例：基因、指纹、声纹、掌纹、耳廓、虹膜、面部识别特征等。
"""

# 上位类别术语 -> 标准下位实例（同时收录"技术/信息"的常见说法，便于匹配）
TERM_GLOSSARY = {
    "生物识别": [
        "虹膜", "虹膜识别",
        "指纹",
        "人脸", "人脸识别", "面部识别", "面容",
        "声纹", "掌纹", "耳廓", "基因", "步态",
    ],
}


def build_reverse_index(glossary=None):
    """反向索引：具体实例 -> 上位类别术语。"""
    glossary = glossary or TERM_GLOSSARY
    index = {}
    for term, instances in glossary.items():
        for inst in instances:
            index[inst] = term
    return index


INSTANCE_TO_TERM = build_reverse_index()


def classify(instance):
    """返回某个具体词对应的上位术语；不在表里则返回 None。"""
    return INSTANCE_TO_TERM.get(instance)


def render_for_prompt():
    """渲染成给模型看的文本，明确这是系统受控的标准分类。"""
    return "\n".join(f"- {term} 包括：{('、'.join(instances))}"
                     for term, instances in TERM_GLOSSARY.items())
