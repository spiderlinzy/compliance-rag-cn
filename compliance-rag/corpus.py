# -*- coding: utf-8 -*-
"""语料加载与切片：把 docs/ 下的 4 份 markdown 切成带元数据的 Chunk。

两层切分：
1. 先按材料自身结构切——L1/L2 按"第X条"、L3 按"一、二、"大节、L4 按"问："；
2. 切完仍超长的片段，再用固定窗口 + 重叠二次切，保证每块大小适中。
每个 Chunk 自包含：编号、正文、来源、层级、定位、章节。
"""
import os
import re
from dataclasses import dataclass

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")

# 结构识别正则
RE_CHAPTER = re.compile(r"^第[一二三四五六七八九十]+章")            # 第一章 …
RE_ARTICLE = re.compile(r"^第[一二三四五六七八九十百零0-9]+条$")   # 第十三条
RE_POLICY_SECTION = re.compile(r"^[一二三四五六七八九十]+、")       # 一、二、…
RE_QUESTION = re.compile(r"^问[：:]")                              # 问：

MAX_CHARS = 450     # 单个片段超过这个字数就二次切
OVERLAP = 60        # 二次切的重叠字数，避免把边界处的上下文切断


@dataclass
class Chunk:
    chunk_id: str       # 唯一编号（引用锚点），如 L1-001
    text: str           # 正文
    source: str         # 来源文件名
    level: str          # 信任层级 L1 … L4
    locator: str        # 人类可读定位，如"第十三条"
    chapter: str = ""   # 所属章节，可空


def read_body(path):
    """读取 md，跳过标题(#)和元数据引用块(>)，只留正文行。"""
    lines = []
    for ln in open(path, encoding="utf-8").read().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln.startswith(">"):
            continue
        lines.append(ln)
    return lines


def parse_by_article(lines):
    """L1/L2：按"第X条"切，同时跟踪"第X章"。返回 (文本, 条目, 章节) 列表。"""
    out, buf, chapter, article = [], [], "", ""

    def flush():
        if article and buf:
            out.append(("".join(buf).strip(), article, chapter))

    for ln in lines:
        if RE_CHAPTER.match(ln):
            flush(); buf = []; chapter = ln
        elif RE_ARTICLE.match(ln):
            flush(); buf = []; article = ln
        else:
            buf.append(ln)
    flush()
    return out


def parse_faq(lines):
    """L4：识别两种问题起始——"问："行，或"一、二、…"直接提问行。
    若"一、"下一行是"问："，说明它是分组标题而非问题，跳过。"""
    n = len(lines)
    starts = []
    for i, ln in enumerate(lines):
        if RE_QUESTION.match(ln):
            starts.append(i)
        elif RE_POLICY_SECTION.match(ln):
            nxt = lines[i + 1] if i + 1 < n else ""
            if not RE_QUESTION.match(nxt):
                starts.append(i)
    out = []
    for k, st in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else n
        seg = lines[st:end]
        out.append(("".join(seg).strip(), seg[0], ""))
    return out


def parse_policy(lines):
    """L3：按大节（一、二、…）切。目录里也有一份，取最后出现的"一、"作为正文起点。"""
    body_start = max(i for i, ln in enumerate(lines) if ln.startswith("一、"))
    lines = lines[body_start:]
    bounds = [i for i, ln in enumerate(lines) if RE_POLICY_SECTION.match(ln)] + [len(lines)]
    out = []
    for k in range(len(bounds) - 1):
        seg = lines[bounds[k]:bounds[k + 1]]
        out.append(("".join(seg[1:]).strip(), seg[0], ""))
    return out


def window_split(text):
    """超长片段按固定窗口 + 重叠切分；短片段原样返回。"""
    if len(text) <= MAX_CHARS:
        return [text]
    parts, i = [], 0
    while i < len(text):
        parts.append(text[i:i + MAX_CHARS])
        i += MAX_CHARS - OVERLAP
    return parts


def glob_md():
    return [os.path.join(DOCS_DIR, f) for f in sorted(os.listdir(DOCS_DIR)) if f.endswith(".md")]


def load_corpus():
    """加载 docs/ 全部文档，返回 Chunk 列表。"""
    chunks = []
    for path in glob_md():
        source = os.path.basename(path)
        level = source.split("_")[0]              # L1_xxx.md → L1
        body = read_body(path)
        if level in ("L1", "L2"):
            raw = parse_by_article(body)
        elif level == "L3":
            raw = parse_policy(body)
        else:
            raw = parse_faq(body)
        for text, locator, chapter in raw:
            for j, piece in enumerate(window_split(text)):
                cid = f"{level}-{len(chunks) + 1:03d}"
                loc = locator if j == 0 else f"{locator}（续{j}）"
                chunks.append(Chunk(cid, piece, source, level, loc, chapter))
    return chunks


if __name__ == "__main__":
    cs = load_corpus()
    print(f"共切出 {len(cs)} 个片段\n")
    for level in ("L1", "L2", "L3", "L4"):
        group = [c for c in cs if c.level == level]
        print(f"{level}: {len(group)} 个，示例定位 → {group[0].locator if group else '无'}")
    print("\n--- 抽一个片段看结构 ---")
    print(next(c for c in cs if c.level == "L1"))
