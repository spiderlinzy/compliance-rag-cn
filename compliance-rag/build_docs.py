# -*- coding: utf-8 -*-
"""一次性数据准备脚本：抓取 4 份官网材料，清洗成带 FTH 元数据头的 markdown。

流程：requests 拿 HTML → BeautifulSoup 定位正文容器、去噪 → 拼元数据头 → 写入 docs/。
四份材料的差异（URL、容器、文件名、日期）都收在 SOURCES 表里，抓取逻辑只写一遍。
"""
import os
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, "docs")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

SOURCES = [
    {
        "level": "L1",
        "title": "中华人民共和国个人信息保护法",
        "url": "http://www.npc.gov.cn/npc/c2/c30834/202108/t20210820_313088.html",
        "source_name": "中国人大网",
        "tag": "div",
        "attrs": {"id": "Zoom"},
        "level_desc": "FTH 层级：L1（法律，最高信任）",
        "date_line": "通过：2021-08-20 ｜ 施行：2021-11-01",
        "filename": "L1_个人信息保护法.md",
    },
    {
        "level": "L2",
        "title": "征信业管理条例",
        "url": "https://www.gov.cn/flfg/2013-01/29/content_2323780.htm",
        "source_name": "中国政府网",
        "tag": "td",
        "attrs": {"class": "p1"},
        "level_desc": "FTH 层级：L2（行政法规，中高信任）",
        "date_line": "国务院令第631号 ｜ 施行：2013-03-15",
        "filename": "L2_征信业管理条例.md",
    },
    {
        "level": "L3",
        "title": "工银融e行个人信息保护政策",
        "url": "https://m.icbc.com.cn/ICBC/disclaimer/2.htm",
        "source_name": "中国工商银行",
        "tag": "div",
        "attrs": {"class": "infoText"},
        "level_desc": "FTH 层级：L3（企业制度，中等信任）",
        "date_line": "发布/生效：2026-06-16",
        "filename": "L3_工行个人信息保护政策.md",
    },
    {
        "level": "L4",
        "title": "征信中心常见问题解答",
        "url": "https://www.pbccrc.org.cn/zxfw/gr/jd/20241029/cf4e288ad9134399a1123adbb153c051.html",
        "source_name": "中国人民银行征信中心",
        "tag": "div",
        "attrs": {"class": "Article_content"},
        "level_desc": "FTH 层级：L4（非正式问答，最低信任）",
        "date_line": "发布日期：2025-07-03",
        "filename": "L4_征信中心常见问题.md",
    },
]


def fetch_html(url):
    """发请求拿 HTML，apparent_encoding 防止中文乱码。"""
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    return r.text


def clean_body(html, tag, attrs):
    """定位正文容器，去掉脚本样式等噪声，逐行清理成纯文本。"""
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.find_all(["script", "style", "noscript"]):
        junk.decompose()
    node = soup.find(tag, attrs=attrs)
    if node is None:
        raise RuntimeError(f"找不到正文容器：<{tag}> {attrs}")
    raw = node.get_text("\n", strip=True)
    lines = [ln.strip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def build_markdown(src, body):
    """拼标题 + FTH 元数据头 + 正文。"""
    return "\n".join([
        f"# {src['title']}",
        "",
        f"> {src['level_desc']}",
        f"> 来源：{src['source_name']} {src['url']}",
        f"> {src['date_line']}",
        "",
        body,
        "",
    ])


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)
    for src in SOURCES:
        print(f"抓取 {src['level']} {src['title']} ...")
        html = fetch_html(src["url"])
        body = clean_body(html, src["tag"], src["attrs"])
        out = os.path.join(DOCS_DIR, src["filename"])
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_markdown(src, body))
        print(f"  已保存 {src['filename']}，正文 {len(body)} 字符")


if __name__ == "__main__":
    main()
