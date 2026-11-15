# -*- coding: utf-8 -*-
"""本地网页演示界面（Gradio）：把可信问答链包成浏览器界面，并把
"知识来源"、"答案如何追溯到来源"和"完整推导过程"全部显性化。

只在本机运行、不部署公网。API Key 直接在网页顶部的密码框输入，
只在本次提问时于内存中使用、不写入任何文件，也不离开这台电脑。
启动：python app.py，浏览器会自动打开本地页面。
"""
import html as html_lib
import json
import os
import re
import time

import gradio as gr

import config
import generator
import verifier
from retriever import Retriever, tokenize as tokenize_text

REFUSAL = "无法在知识库中找到可靠来源，请联系合规团队。"

# 四份文件的展示元数据与专属配色（main 主色 / soft 浅底 / border 边框）。
SOURCE_META = {
    "L1": {"title": "中华人民共和国个人信息保护法", "kind": "法律", "label": "高",
           "main": "#b91c1c", "soft": "#fef2f2", "border": "#fecaca"},
    "L2": {"title": "征信业管理条例", "kind": "行政法规", "label": "中高",
           "main": "#1d4ed8", "soft": "#eff6ff", "border": "#bfdbfe"},
    "L3": {"title": "工银融e行个人信息保护政策", "kind": "企业制度", "label": "中",
           "main": "#0f766e", "soft": "#f0fdfa", "border": "#99f6e4"},
    "L4": {"title": "征信中心常见问题解答", "kind": "非正式问答", "label": "低",
           "main": "#b45309", "soft": "#fffbeb", "border": "#fde68a"},
}

retriever = Retriever()


# ---------- 知识来源面板 ----------
def source_panel_html(active=(), asked=False):
    """四张来源卡片；被引用的高亮，提问后未被引用的变暗。"""
    active = set(active)
    cards = []
    for lvl in ("L1", "L2", "L3", "L4"):
        m = SOURCE_META[lvl]
        on = lvl in active
        opacity = "1" if (not asked or on) else "0.5"
        glow = (f"box-shadow:0 0 0 2px {m['main']},0 8px 20px {m['main']}33;"
                if on else "")
        cards.append(f"""
        <div style="flex:1;min-width:150px;background:{m['soft']};border:1px solid
            {m['border']};border-radius:12px;padding:14px;{glow}opacity:{opacity};
            transition:all .3s">
          <span style="display:inline-block;background:{m['main']};color:#fff;font-weight:700;
            font-size:13px;padding:2px 10px;border-radius:999px">{lvl}</span>
          <div style="font-weight:700;margin:8px 0 4px;font-size:15px;color:#111">
            {m['title']}</div>
          <div style="font-size:12.5px;color:#555">{m['kind']} · 信任度{m['label']}</div>
        </div>""")
    return f'<div style="display:flex;gap:12px;flex-wrap:wrap">{"".join(cards)}</div>'


# ---------- 推导溯源面板 ----------
def _step(idx, title, body):
    return f"""
    <div style="display:flex;gap:12px;margin:14px 0">
      <div style="flex:0 0 26px;height:26px;border-radius:50%;background:#334155;color:#fff;
        display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px">{idx}</div>
      <div style="flex:1">
        <div style="font-weight:700;font-size:14px;margin-bottom:4px;color:#111">{title}</div>
        <div style="font-size:13px;color:#475569;line-height:1.75">{body}</div>
      </div>
    </div>"""


def trace_panel(steps):
    return f"""
    <details style="margin-top:18px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;
      padding:14px 16px">
      <summary style="cursor:pointer;font-weight:700;font-size:14px;color:#334155">
        查看完整推导过程（点击展开溯源）
      </summary>
      <div style="margin-top:6px;border-top:1px solid #e2e8f0">{"".join(steps)}</div>
    </details>"""


# ---------- 实时阶段进度面板（运行中显示当前在干什么）----------
STAGES = ["输入校验", "BM25 检索", "调用模型生成", "独立引用验证", "置信度聚合"]

PROGRESS_STYLE = """
<style>
@keyframes ace-spin{to{transform:rotate(360deg)}}
.ace-spinner{width:16px;height:16px;border:2.5px solid #c7d2fe;border-top-color:#4f46e5;
  border-radius:50%;animation:ace-spin .8s linear infinite;display:inline-block}
</style>
"""


def progress_panel(active, detail):
    """纵向列出五个阶段：已完成打勾、当前阶段旋转并说明在干什么、未开始置灰。"""
    rows = []
    for i, name in enumerate(STAGES):
        if i < active:
            badge = ('<span style="width:22px;height:22px;border-radius:50%;background:#059669;'
                     'color:#fff;display:inline-flex;align-items:center;justify-content:center;'
                     'font-weight:700;font-size:13px">✓</span>')
            color, weight, extra = "#065f46", 600, ""
        elif i == active:
            badge = '<span class="ace-spinner"></span>'
            color, weight = "#4338ca", 700
            extra = (f'<div style="font-weight:400;font-size:12.5px;color:#6366f1;margin-top:5px;'
                     f'line-height:1.6">{detail}</div>')
        else:
            badge = (f'<span style="width:22px;height:22px;border-radius:50%;background:#e5e7eb;'
                     f'color:#9ca3af;display:inline-flex;align-items:center;justify-content:center;'
                     f'font-weight:700;font-size:12.5px">{i+1}</span>')
            color, weight, extra = "#9ca3af", 500, ""
        rows.append(f"""
        <div style="display:flex;gap:11px;align-items:flex-start;padding:9px 0">
          <span style="flex:0 0 22px;display:flex;justify-content:center">{badge}</span>
          <span style="flex:1">
            <span style="color:{color};font-weight:{weight};font-size:14px">{name}</span>{extra}
          </span>
        </div>""")
    return (PROGRESS_STYLE + '<div style="background:#eef2ff;border:1px solid #c7d2fe;'
            'border-radius:12px;padding:16px 18px"><div style="font-weight:800;font-size:14.5px;'
            'color:#312e81;margin-bottom:8px">正在处理，请稍候</div>' + "".join(rows) + '</div>')


def _error_html(text):
    return ('<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:22px;'
            'text-align:center;color:#991b1b;font-size:15px;font-weight:700">调用失败或已超时<br>'
            "<span style='font-weight:400;font-size:13px;color:#b91c1c'>"
            '请检查 API Key、模型名或网络后重新提交。</span></div>')


def _candidate_rows(results):
    rows = []
    for c, s in results:
        m = SOURCE_META[c.level]
        rows.append(f"""
        <div style="display:flex;gap:8px;align-items:baseline;margin:3px 0">
          <span style="background:{m['main']};color:#fff;font-size:11.5px;font-weight:700;
            padding:1px 7px;border-radius:5px">{c.level}</span>
          <span style="flex:1">{c.locator} <code style="color:#64748b">{c.chunk_id}</code></span>
          <span style="font-variant-numeric:tabular-nums;font-weight:700;color:#334155">{s:.2f}</span>
        </div>""")
    return "".join(rows)


def _verdict_rows(passed, blocked_items):
    rows = []
    for v in passed:
        rows.append(f"""
        <div style="margin:5px 0"><span style="color:#0f766e;font-weight:700">通过</span>
          · {v.claim}<br><span style="color:#94a3b8;font-size:12px">{v.reason}</span></div>""")
    for v in blocked_items:
        rows.append(f"""
        <div style="margin:5px 0"><span style="color:#b91c1c;font-weight:700">拦截</span>
          · {v.claim}<br><span style="color:#94a3b8;font-size:12px">{v.reason}</span></div>""")
    return "".join(rows)


# ---------- 原文证据弹窗 ----------
def highlight_text(text, claim):
    """把原文中与结论实词重合最多的句子高亮，其余原样转义。"""
    claim_words = set(tokenize_text(claim))
    pieces = [p for p in re.split(r"([^。；！？]+[。；！？]?)", text) if p]
    scored = [(p, len(set(tokenize_text(p)) & claim_words)) for p in pieces]
    best = max((s for _, s in scored), default=0)
    out = []
    for p, s in scored:
        esc = html_lib.escape(p)
        if best > 0 and s == best:
            out.append(f'<mark style="background:#fef08a;border-radius:3px;padding:0 2px">{esc}</mark>')
        else:
            out.append(esc)
    return "".join(out)


def evidence_modal_html(passed):
    """纯 CSS :target 实现的原文证据弹窗（Gradio 不执行内联脚本，故不用 JS）。
    每条证据渲染一个全屏 backdrop（兼作关闭链接）+ 一个居中卡片，徽章用锚点触发。"""
    blocks = ["""
    <style>
    .ev-backdrop{display:none;position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:9998}
    .ev-backdrop:target{display:block}
    .ev-cardbox{display:none;position:fixed;inset:0;z-index:9999;align-items:center;
      justify-content:center;padding:24px}
    .ev-backdrop:target ~ .ev-cardbox{display:flex}
    .ev-card{background:#fff;border-radius:14px;max-width:680px;width:100%;max-height:84vh;
      overflow:auto;box-shadow:0 24px 60px rgba(0,0,0,.32)}
    </style>"""]
    for idx, v in enumerate(passed):
        m = SOURCE_META[v.chunk.level]
        mid = f"ev-modal-{idx}"
        head = f"""
          <span style="background:{m['main']};color:#fff;font-weight:700;font-size:13px;padding:3px 11px;
            border-radius:999px">{v.chunk.level} · {m['label']}</span>
          <span style="margin-left:10px;font-weight:700;font-size:14.5px">{v.chunk.source}</span>
          <span style="margin-left:8px;color:#64748b;font-size:13.5px">{v.chunk.locator}
            <code>{v.citation_id}</code></span>"""
        blocks.append(f"""
        <div class="ev-wrap">
          <a class="ev-backdrop" id="{mid}" href="#ev-close"></a>
          <div class="ev-cardbox">
            <div class="ev-card">
              <div style="padding:16px 22px;border-bottom:1px solid #eee">{head}</div>
              <div style="padding:14px 22px;background:#f8fafc;border-bottom:1px solid #eee;
                font-size:13px;line-height:1.7"><b>本条证据支撑的结论：</b>{html_lib.escape(v.claim)}</div>
              <div style="padding:18px 22px;line-height:1.95;font-size:14.5px;color:#1f2937">
                {highlight_text(v.chunk.text, v.claim)}</div>
              <div style="padding:12px 22px;text-align:right">
                <a href="#ev-close" style="display:inline-block;background:#334155;color:#fff;
                  padding:6px 18px;border-radius:8px;font-size:13.5px;text-decoration:none">关闭</a>
              </div>
            </div>
          </div>
        </div>""")
    return "".join(blocks)


# ---------- 答案区 ----------
def _refusal_html(text):
    return (f'<div style="background:#f3f4f6;border:1px solid #d1d5db;border-radius:12px;'
            f'padding:22px;text-align:center;color:#374151;font-size:16px;font-weight:600">'
            f"无法回答<br><span style='font-weight:400;font-size:14px'>{text}</span></div>")


def _key_missing_html():
    return ('<div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:12px;'
            'padding:22px;text-align:center;color:#92400e;font-size:15px;font-weight:700">'
            '请先在网页顶部输入 API Key<br>'
            "<span style='font-weight:400;font-size:13.5px;color:#b45309'>"
            '密钥只在本次提问时于内存中使用，不会被保存或写入任何文件。</span></div>')


def answer_html(passed, blocked_items):
    parts = ['<h3 style="margin:6px 0 10px">回答</h3>']
    for i, v in enumerate(passed, 1):
        m = SOURCE_META[v.chunk.level]
        parts.append(f"""
        <div style="border:1px solid #eee;border-left:4px solid {m['main']};background:#fafafa;
            border-radius:8px;padding:12px 14px;margin:10px 0">
          <div style="font-weight:700;font-size:15px;color:#111">{i}. {v.claim}</div>
          <div style="margin-top:9px;font-size:13px;line-height:1.9">
            <a href="#ev-modal-{i - 1}" title="点击查看原文证据"
              style="background:{m['main']};color:#fff;padding:2px 9px;border-radius:6px;
              font-weight:600;text-decoration:none">{v.chunk.level} · {m['label']} · 查看原文</a>
            <span style="color:#444;margin-left:8px">{v.chunk.source} ｜ {v.chunk.locator}
              <code style="background:#eee;padding:1px 6px;border-radius:4px">{v.citation_id}</code>
            </span>
          </div>
        </div>""")
    parts.append(
        '<div style="margin:14px 0;font-size:15px">整体置信度：'
        f'<b style="color:#111">【{verifier.confidence_label(passed)}】</b></div>')
    if blocked_items:
        parts.append('<div style="margin-top:14px"><h4 style="color:#b91c1c;margin-bottom:6px">'
                     '以下陈述被引用验证器拦截，未纳入回答：</h4>')
        for v in blocked_items:
            parts.append(f'<div style="font-size:13px;color:#555;margin:4px 0">· {v.claim}'
                         f'<br><span style="color:#9ca3af">原因：{v.reason}</span></div>')
        parts.append('</div>')
    parts.append(evidence_modal_html(passed))
    return "".join(parts)


def respond(question, api_key):
    question = (question or "").strip()
    api_key = (api_key or "").strip()
    steps = []
    total = len(retriever.chunks)
    t0 = time.time()

    # 第 1 步：输入校验
    yield source_panel_html(), progress_panel(0, "正在检查问题是否为空、是否超长…")
    time.sleep(0.15)
    ok, q = generator.validate_question(question)
    if not ok:
        steps.append(_step(1, "输入校验", f"未通过：{q}"))
        yield source_panel_html(), f'<div style="color:#b45309">{q}</div>' + trace_panel(steps)
        return
    steps.append(_step(1, "输入校验",
                       f"问题长度 {len(q)} 字，非空且不超过 500 字，通过。"))

    # 第 2 步：BM25 检索 + 硬拦截
    yield source_panel_html(), progress_panel(1, f"正在 {total} 个片段中做 BM25 检索…")
    time.sleep(0.15)
    blocked, results = retriever.hard_block(q)
    top = results[0][1] if results else 0.0
    if blocked:
        steps.append(_step(2, "BM25 检索与硬拦截",
                           f"在 {total} 个片段中检索，最高分 {top:.2f} 低于阈值 "
                           f"{config.RELEVANCE_CUTOFF}，判定无可靠相关片段，硬拦截，不调用模型。"))
        yield (source_panel_html(asked=True),
               _refusal_html(REFUSAL) + trace_panel(steps))
        return
    steps.append(_step(2, "BM25 检索与硬拦截",
                       f"在 {total} 个片段中按 BM25 分数取前 {len(results)} 个候选："
                       f"{_candidate_rows(results)}最高分 {top:.2f} ≥ 阈值 "
                       f"{config.RELEVANCE_CUTOFF}，通过硬拦截，进入模型判断。"))

    # 密钥检查（不调用模型，缺失直接提示）
    if not api_key:
        steps.append(_step(3, "API Key 检查",
                           "未在网页顶部输入 API Key，已停止，不会调用模型。"))
        yield (source_panel_html(asked=True), _key_missing_html() + trace_panel(steps))
        return

    # 第 3 步：调用模型生成（这一步最耗时，明确告知正在调用模型）
    yield source_panel_html(asked=True), progress_panel(
        2, "正在调用模型生成答案，模型响应可能需要几十秒，请耐心等待，不要重复点击…")
    time.sleep(0.15)
    t_gen = time.time()
    try:
        data = generator.generate(q, results, api_key)
    except Exception as e:
        yield (source_panel_html(asked=True), _error_html(str(e)) + trace_panel(steps))
        return
    gen_secs = time.time() - t_gen
    items = data.get("items", [])
    if not data.get("answerable"):
        steps.append(_step(3, "生成（语义判断）",
                           "模型阅读候选后判断材料不足以回答，answerable=false，拒答。"))
        yield (source_panel_html(asked=True),
               _refusal_html(REFUSAL) + trace_panel(steps))
        return
    gen_rows = "".join(f'<div>· 锚定 <code>{it["citation_id"]}</code>：{it["claim"]}</div>'
                       for it in items)
    steps.append(_step(3, "生成（语义判断）",
                       f"模型判断可回答，生成 {len(items)} 条陈述：{gen_rows}"
                       f"本次模型调用耗时 {gen_secs:.1f} 秒。"))

    # 第 4 步：独立验证（会再次调用模型）
    yield source_panel_html(asked=True), progress_panel(
        3, "正在调用模型做独立引用验证（先结构核查、再语义核查）…")
    time.sleep(0.15)
    t_ver = time.time()
    try:
        passed, blocked_items = verifier.verify(items, results, api_key)
    except Exception as e:
        yield (source_panel_html(asked=True), _error_html(str(e)) + trace_panel(steps))
        return
    ver_secs = time.time() - t_ver
    steps.append(_step(4, "独立验证（结构核查 + 语义核查）",
                       "先做结构核查（引用 ID 是否真实存在），再做独立模型语义核查"
                       "（温度 0.0，原文是否支撑陈述）。逐条判定："
                       f"{_verdict_rows(passed, blocked_items)}"
                       f"本次验证模型调用耗时 {ver_secs:.1f} 秒。"))
    if not passed:
        yield (source_panel_html(asked=True),
               _refusal_html("所有陈述均未通过引用验证，无法给出可靠回答，请联系合规团队。")
               + trace_panel(steps))
        return

    # 第 5 步：置信度聚合
    yield source_panel_html(asked=True), progress_panel(4, "正在按来源层级聚合整体置信度…")
    time.sleep(0.1)
    levels = sorted({v.chunk.level for v in passed})
    conf = verifier.confidence_label(passed)
    level_text = "、".join(f"{l}（{SOURCE_META[l]['label']}）" for l in levels)
    total_secs = time.time() - t0
    steps.append(_step(5, "置信度聚合",
                       f"通过验证的陈述引用了这些来源层级：{level_text}。同一结论取其最强"
                       f"来源、不同结论取最低层级，因此整体置信度 = 【{conf}】。"
                       f"从提交到出结果全程耗时 {total_secs:.1f} 秒。"))
    print(f"[ACE] 问答完成：生成 {gen_secs:.1f}s，验证 {ver_secs:.1f}s，全程 {total_secs:.1f}s")

    yield (source_panel_html(levels, asked=True),
           answer_html(passed, blocked_items) + trace_panel(steps))


PIPELINE_HTML = """
<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:13px;margin:6px 0 4px">
  <span style="background:#eef2ff;color:#3730a3;padding:4px 12px;border-radius:999px;font-weight:600">① 输入校验</span><span>→</span>
  <span style="background:#eef2ff;color:#3730a3;padding:4px 12px;border-radius:999px;font-weight:600">② BM25 检索</span><span>→</span>
  <span style="background:#eef2ff;color:#3730a3;padding:4px 12px;border-radius:999px;font-weight:600">③ 生成</span><span>→</span>
  <span style="background:#eef2ff;color:#3730a3;padding:4px 12px;border-radius:999px;font-weight:600">④ 独立验证</span><span>→</span>
  <span style="background:#eef2ff;color:#3730a3;padding:4px 12px;border-radius:999px;font-weight:600">⑤ 分层输出</span>
</div>
"""

def load_demo_groups():
    """从 tests/test_questions.json 读取演示题，按 group 字段保持顺序分组。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "tests", "test_questions.json")
    data = json.load(open(path, encoding="utf-8"))
    groups = {}
    for item in data["questions"]:
        groups.setdefault(item["group"], []).append(item["question"])
    return groups


DEMO_GROUPS = load_demo_groups()


with gr.Blocks(title="信源 · 可信合规问答") as demo:
    gr.HTML(
        '<h1 style="margin-bottom:2px;letter-spacing:6px">信源</h1>'
        '<div style="color:#94a3b8;font-size:13px;margin-bottom:8px;letter-spacing:2px">'
        "可追溯的可信合规问答</div>"
        '<div style="color:#555;font-size:14px;margin-bottom:8px">'
        "只基于指定的 4 份材料回答，每条事实都可追溯，检索不到即拒答。</div>")
    gr.HTML(PIPELINE_HTML)
    gr.HTML('<h3 style="margin:14px 0 8px">知识来源（4 份，按信任层级排列）</h3>')
    panel = gr.HTML(source_panel_html())
    key_inp = gr.Textbox(
        label="API Key（在网页直接输入；只在本机内存中使用，不会保存或写入文件）",
        type="password", placeholder="在此粘贴 API Key，无需再配置 .env 文件")
    inp = gr.Textbox(label="请输入合规问题",
                     placeholder="例如：什么是敏感个人信息？", lines=2)
    btn = gr.Button("提交提问", variant="primary")
    out = gr.HTML()
    gr.HTML('<h3 style="margin:16px 0 4px">演示问题（点击填入，再点提交；14 题覆盖系统的各种状态）</h3>')
    for group_name, questions in DEMO_GROUPS.items():
        gr.Examples(examples=[[q] for q in questions], inputs=inp, label=group_name)
    btn.click(fn=respond, inputs=[inp, key_inp], outputs=[panel, out])
    inp.submit(fn=respond, inputs=[inp, key_inp], outputs=[panel, out])


if __name__ == "__main__":
    demo.launch(inbrowser=True, theme=gr.themes.Soft())
