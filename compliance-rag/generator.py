# -*- coding: utf-8 -*-
"""带引用的 RAG 生成模块。

流程：检索片段 → 拼成带编号的参考材料 → 模型只依据材料输出结构化 JSON。
模型只负责给出"事实陈述 + 片段ID"，并在同一次调用里判断 answerable；
置信度不交给它主观判断，而由后面的组装逻辑按引用片段的 FTH 层级计算。
"""
import json

from openai import OpenAI

import config
import glossary

MAX_QUESTION_LEN = 500      # 模块内部参数：问题超长直接拒，就近放

SYSTEM_PROMPT = """你是一个严谨的金融合规问答助手，只能依据"参考材料"回答。铁律：
1. 只使用参考材料里的信息，禁止使用你自己的常识或外部知识。
2. 每一条事实陈述都必须引用支撑它的片段ID，不允许出现无引用的陈述。
3. 只能引用材料中真实给出的片段ID，禁止编造ID。
4. 如果参考材料不足以回答、或材料中没有相关内容，把 answerable 设为 false，items 留空。
5. 每条事实是一个可独立核查的简洁陈述，不要把多个事实塞进一条。
6. 如果多个片段表达的是同一个结论，只保留一条陈述，并引用其中信任层级最高的片段ID（层级 L1 最高，依次 L2、L3、L4 最低），不要为同一结论重复输出。
7. "受控术语表"是系统定义的标准分类，可直接采用：当问题中的具体事物属于表中某术语的下位实例（如虹膜属于生物识别），可以结合定义该术语的原文片段作答，并在陈述中写明这层归类关系；术语表之外的归类仍按第1条处理，不得自行发挥。
8. 陈述尽量逐字采用原文措辞，不要改写、替换或补充原文没有的说法（例如原文写"本政策"就不要替成具体名称）；原文带"……除外""可以不……"等条件或例外限定的，陈述必须完整保留该限定，不能只写主句。拿不准的内容不要写。

只输出 JSON，不要输出任何额外文字，格式：
{"answerable": true 或 false, "items": [{"claim": "事实陈述", "citation_id": "片段ID"}]}"""


def get_client(api_key=None):
    """构建模型客户端。优先用传入的 key（网页上直接输入），否则回退到环境变量/.env。
    key 缺失或还是占位符时明确报错，不静默失败。
    超时 180 秒、关闭自动重试：给模型生成和网络波动留足时间，超时直接报错由界面提示。"""
    key = (api_key or config.API_KEY or "").strip()
    if not key or key.startswith("在这里"):
        raise RuntimeError("还没配置 API Key：在网页顶部的输入框填入，或在 .env 中配置。")
    return OpenAI(api_key=key, base_url=config.MODEL_BASE_URL,
                  timeout=180.0, max_retries=0)


def build_context(results):
    """把检索结果拼成带编号的参考材料，让模型清楚每个片段的 ID 和来源。"""
    blocks = []
    for chunk, _score in results:
        blocks.append(
            f"[片段ID: {chunk.chunk_id}]\n"
            f"来源: {chunk.source} ｜ 层级: {chunk.level} ｜ 定位: {chunk.locator}\n"
            f"原文: {chunk.text}"
        )
    blocks.append(
        "【受控术语表：系统定义的标准分类，可直接采用其下位-上位归类】\n"
        + glossary.render_for_prompt()
    )
    return "\n\n".join(blocks)


def build_messages(question, results):
    """组装 system（铁律）+ user（问题和参考材料）。"""
    user = f"问题：{question}\n\n参考材料：\n{build_context(results)}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def validate_question(question):
    """输入校验：空、超长直接拦下。返回 (是否合法, 处理后的问题或提示)。"""
    q = (question or "").strip()
    if not q:
        return False, "问题不能为空，请重新输入。"
    if len(q) > MAX_QUESTION_LEN:
        return False, f"问题超过 {MAX_QUESTION_LEN} 字，请精简后再问。"
    return True, q


def generate(question, results, api_key=None):
    """调用模型，返回解析后的 dict：{answerable, items}。"""
    client = get_client(api_key)
    messages = build_messages(question, results)
    try:
        # 优先要求结构化 JSON 输出
        resp = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception:
        # 某些兼容接口不支持 response_format，退回普通调用，仍在提示词里要求输出 JSON
        resp = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=messages,
            temperature=0.1,
        )
    return json.loads(resp.choices[0].message.content)
