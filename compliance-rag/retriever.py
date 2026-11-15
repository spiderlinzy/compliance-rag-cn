# -*- coding: utf-8 -*-
"""检索模块：jieba 中文分词 + BM25 关键词检索（含停用词、标点过滤）。

不依赖向量和 embedding，本地即可运行，职责有两个：
1) 召回——把词面最相关的若干片段捞出来、按 BM25 分数排序；
2) 硬拦截——实词零命中，或最高分低于阈值时，调模型前直接判无、省一次调用。

关键词检索分不清"片段里有这个词"和"片段能回答这个问题"，所以语义层面的
"能不能答"不在这一层下结论，交给生成模块读片段后判断，再由验证器兜底。
"""
import jieba
from rank_bm25 import BM25Okapi

import config
from corpus import load_corpus

# 停用词：虚词、代词、疑问词、量词等，在长文本里到处出现，
# 保留会让无关问题也拿到虚高分数。词之间有空格，用 split() 拆成一个个词。
STOPWORDS = set("""的 地 得 了 吗 呢 吧 啊 呀 在 是 我 你 他 她 它 们 这 那
怎么 怎样 什么 如何 为什么 哪 里 个 把 被 让 向 为 对 到 从 等 之 其 此 该
不 没 有 和 与 及 或 而 但 也 都 就 还 又 很 最 能 会 要 做 请 帮 给 现在
上 下 里 中 一 二 三 四 五 六 七 八 九 十 每 各 某 几 多少 一部 可以 需要""".split())

# 标点：不是语义内容，保留会让含大量问号的长片段刷分、挤掉真正含关键词的片段。
# 注意这里直接用 set() 把字符串拆成单个字符（字符之间没有空格，不能用 split()）。
PUNCTUATION = set("""？?，,。.；;：:、！!（）()（）“”"''‘’《》〈〉—…·-－_／/＼\\[]{}【】<>「」『』~～#￥%&*+""")


def tokenize(text):
    """中文分词，并去掉停用词、标点、空白词，只留实词。"""
    return [w for w in jieba.lcut(text)
            if w.strip() and w not in STOPWORDS and w not in PUNCTUATION]


class Retriever:
    def __init__(self, chunks=None):
        self.chunks = chunks or load_corpus()
        self.tokens = [tokenize(c.text) for c in self.chunks]
        self.bm25 = BM25Okapi(self.tokens)

    def search(self, query, top_k=None):
        """返回 [(chunk, score), ...]，按相关性从高到低，取前 K 条。"""
        scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self.chunks, scores), key=lambda x: x[1], reverse=True)
        return [(c, float(s)) for c, s in ranked[:(top_k or config.TOP_K)]]

    def hard_block(self, query):
        """硬拦截：返回 (是否拦截, 检索结果)。
        实词零命中（结果为空），或最高分低于阈值，都判 True 直接拒答。"""
        results = self.search(query)
        blocked = (not results) or (results[0][1] < config.RELEVANCE_CUTOFF)
        return blocked, results


if __name__ == "__main__":
    r = Retriever()
    for q in ["处理个人信息需要本人同意吗", "不良征信记录保留多久", "红烧肉怎么做", "今天天气怎么样"]:
        blocked, results = r.hard_block(q)
        print(f"\n问题：{q} →", "硬拦截（直接拒答）" if blocked else "进入模型判断")
        for chunk, score in results:
            print(f"  {score:5.2f}  [{chunk.level}|{chunk.locator}] {chunk.text[:34]}…")
