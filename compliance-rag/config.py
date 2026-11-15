"""集中配置：模型接口信息 + FTH 信任层级 + 检索全局参数。

这里把书中第 3 章的 FTH（事实信任层级）直接编码成一张表，
后面检索和生成模块都通过它判断"某份材料最多能给多高的置信度"。

只在单个模块内部使用的参数（如切片长度、温度）就近放在各自模块里，
不堆到这里，保持 config 只管"跨模块共享、全局统一"的东西。
"""
import os
from dotenv import load_dotenv

# .env 仅用于命令行（cli.py）；网页界面（app.py）直接在页面输入 key，无需此文件。
load_dotenv()  # 从同目录的 .env 读取，没有 .env 时用默认值，不报错

# --- 模型连接（网页未输入 key 时，命令行回退到这里；不硬编码进代码）---
API_KEY = os.getenv("API_KEY", "")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODEL_NAME = os.getenv("MODEL_NAME", "doubao-seed-2-1-pro-260915")

# --- FTH 信任层级：rank 越大越权威；label 是输出给用户看的置信度 ---
TRUST_LEVELS = {
    "L1": {"rank": 4, "label": "高",   "name": "法律"},
    "L2": {"rank": 3, "label": "中高", "name": "行政法规"},
    "L3": {"rank": 2, "label": "中",   "name": "企业制度"},
    "L4": {"rank": 1, "label": "低",   "name": "非正式问答"},
}

# --- 检索全局参数 ---
TOP_K = 4          # 每次取最相关的几个片段递给模型
# 硬拦截阈值：最高分低于此值，说明查询实词在语料里几乎没命中，直接拒答、不调用模型。
# 注意：通过硬拦截只代表"值得让模型看一眼"，最终能不能答由生成模块做语义判断。
RELEVANCE_CUTOFF = 3.0
