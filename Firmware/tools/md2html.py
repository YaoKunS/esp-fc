#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md2html.py —— 把 Docs/ 下的中文 Markdown 说明文档转成**自包含 HTML 页面**

【为什么要有这个脚本】
    本项目已有的《ESP-FC技术说明书.html》是精工排版的手写页面（封面 / 目录 /
    note-warn-danger 提示块 / 表格），它其实是 **HTML 为源**、Markdown 是由
    html2md.py 反向投影出来的。但 Docs/ 下另外几份文档（适配说明、变更说明）
    是 **Markdown 为源**，此前没有对应的 HTML 版；本脚本补上这个方向，
    让三者都能在浏览器里直接阅读 / 打印 / 分享。

【设计取舍】
    1. 不依赖任何第三方库：本机实测没有 pandoc，也没有 python-markdown，
       故自己实现一个覆盖本项目 Markdown 用法的轻量转换器（见下方 SUPPORTED）。
       只做「够用且正确」，不追求 CommonMark 全兼容。
    2. 不引 CDN：生成的 HTML 完全离线自包含，双击即可打开，适合随发布件
       一起分发（发布物里不应出现必须联网才能渲染的 JS/CSS）。
    3. 样式复用：CSS 直接抄自 Docs/ESP-FC技术说明书.html 的 <style> 块，
       保证与现有说明书同一套观感；另补 blockquote / hr 两条本项目用到的样式。
    4. 输出用 write_bytes 显式写 UTF-8 + LF：Windows 下若用 write_text，
       换行会被转成 CRLF，且默认编码可能不是 UTF-8（本仓库已踩过
       「整文件假 diff」的坑，见 release 打包脚本的处理方式）。

【支持的 Markdown 子集（三份目标文档实测覆盖）】
    - 一级标题（作封面标题）、二/三/四级标题（二级自动生成目录锚点）
    - 段落、行尾双空格换行、水平分隔线 ---
    - 围栏代码块 ```lang（内容整体 HTML 转义）
    - 表格（含对齐行 |:---|---:|、单元格内转义竖线 \\|）
    - 引用块 >（按 🔴 / ⚠️ / ✅ / ★ 自动套 danger / warn / ok / note 配色，
      其余用克制的灰色 quote）
    - 有序 / 无序列表，支持一层缩进的二级列表
    - 行内：`代码`、**粗体**、*斜体*、[文字](链接)、<https://自动链接>

【用法】
    python Firmware/tools/md2html.py                 # 转换 META 里登记的三份文档
    python Firmware/tools/md2html.py 某个文档.md      # 只转换指定文件（可多个）
    输出为同目录同名 .html；Markdown 原文保持不变，改完 md 重跑即可「同步」。
"""

from __future__ import annotations

import html
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径定位：本文件在 Firmware/tools/ 下，向上两级即仓库根目录。
# 用 __file__ 而不是 cwd，保证从任意目录调用都能找到 Docs/。
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "Docs"

# ---------------------------------------------------------------------------
# 封面元数据：每份文档单独定制，避免把品牌口径写死在模板里。
# 🔴 品牌铁律：火龙果硬件署 (c) 微辣火龙果（malagis / MildlySpicyDragon），
#    2025 星火奖属火龙果项目；耀坤智联只署「固件适配」，两品牌互相独立。
#    英文品牌名固定 MildlySpicyDragon，禁止意译。
# ---------------------------------------------------------------------------
META = {
    "耀坤版V1.1_变更说明_20261127.md": {
        "badge": "ESP-FC耀坤版 · V1.1 · 2026-11-27",
        "sub": "本轮改动 · 验证记录 · 发布件指纹 · 推送状态",
        "facts": [
            ("分支", "yaokun-organized"),
            ("上游", "rtlopez/esp-fc（(c) Ramon Lopez，MIT）"),
            ("适用板型", "耀坤 S3（ESP32-S3） / 微辣火龙果 2.0（经典 ESP32）"),
            ("本地最新提交", "0376595（待授权推送）"),
        ],
    },
    "耀坤S3适配说明.md": {
        "badge": "ESP-FC耀坤版 · V1.1 · 硬件适配",
        "sub": "耀坤 S3 无人机 · 板级引脚定义与全部改动根因",
        "facts": [
            ("主控", "ESP32-S3（R8N8 / N4R2）"),
            ("编译环境", "pio run -e esp32s3_yaokun"),
            ("上游", "rtlopez/esp-fc（(c) Ramon Lopez，MIT）"),
            ("固件适配", "耀坤智联（YaoKunSmart）"),
        ],
    },
    "火龙果2.0适配说明.md": {
        "badge": "微辣火龙果 2.0 · ESP-FC耀坤版 · V1.1",
        "sub": "经典 ESP32 板型 · 与耀坤 S3 同系列板框的适配说明",
        "facts": [
            ("主控", "ESP32 经典片 WROOM（4MB，无 PSRAM）"),
            ("编译环境", "pio run -e esp32_hlg20"),
            ("硬件设计", "(c) 微辣火龙果（malagis / MildlySpicyDragon）"),
            ("固件适配", "耀坤智联（YaoKunSmart）"),
        ],
    },
}

# ---------------------------------------------------------------------------
# 样式：逐行抄自 Docs/ESP-FC技术说明书.html（第 8~106 行），末尾追加
# blockquote / hr 两条本项目 Markdown 会用到、而原说明书没有的样式。
# 原说明书的 .note/.warn/.danger/.ok 提示块配色在这里直接复用。
# ---------------------------------------------------------------------------
CSS = r"""
  :root{
    --brand:#0f766e; --brand-dark:#0b5a54; --ink:#0f172a; --ink2:#334155;
    --ink3:#64748b; --line:#e2e8f0; --bg:#ffffff; --bg2:#f8fafc;
    --code-bg:#0f172a;
  }
  *{box-sizing:border-box;}
  body{
    margin:0; background:var(--bg2); color:var(--ink);
    font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB","Source Han Sans SC",sans-serif;
    font-size:15px; line-height:1.85; -webkit-font-smoothing:antialiased;
  }
  .wrap{max-width:1080px; margin:0 auto; padding:0 24px 80px; background:var(--bg);
         box-shadow:0 0 40px rgba(15,23,42,.06);}

  .cover{padding:64px 24px 48px; background:linear-gradient(135deg,#0f172a 0%,#134e4a 55%,#0f766e 130%);
         color:#fff; margin:0 -24px 40px;}
  .cover .badge{display:inline-block; background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.25);
         padding:4px 14px; border-radius:20px; font-size:12.5px; letter-spacing:.5px; margin-bottom:20px;}
  .cover h1{margin:0 0 12px; font-size:40px; font-weight:800; letter-spacing:1px; line-height:1.3;}
  .cover .sub{font-size:16.5px; color:#cbd5e1; margin-bottom:28px; font-weight:300;}
  .cover .facts{display:flex; flex-wrap:wrap; gap:10px 30px; font-size:13.5px; color:#e2e8f0;
         border-top:1px solid rgba(255,255,255,.16); padding-top:20px;}
  .cover .facts b{color:#fff; font-weight:600;}

  .toc{background:var(--bg2); border:1px solid var(--line); border-radius:12px;
       padding:26px 30px; margin-bottom:48px;}
  .toc h2{margin:0 0 16px; font-size:17px; color:var(--brand); border:0; padding:0;}
  .toc ol{columns:2; column-gap:40px; margin:0; padding-left:22px; font-size:14px;}
  .toc li{margin:5px 0; break-inside:avoid;}
  .toc a{color:var(--ink2); text-decoration:none;}
  .toc a:hover{color:var(--brand);}
  .toc .d{font-size:12px; color:var(--ink3); margin-left:6px;}

  h2{font-size:25px; font-weight:700; color:var(--brand); margin:56px 0 20px;
     padding-bottom:12px; border-bottom:3px solid var(--brand); letter-spacing:.5px;}
  h3{font-size:19px; font-weight:700; color:var(--ink); margin:36px 0 14px;
     padding-left:13px; border-left:5px solid var(--brand);}
  h4{font-size:16px; font-weight:700; color:var(--ink2); margin:24px 0 10px;}
  p{margin:12px 0;}

  code{background:#f1f5f9; color:#b91c1c; padding:2px 7px; border-radius:4px;
       font-family:"Cascadia Mono","Consolas","Courier New",monospace; font-size:13.5px;}
  pre{background:var(--code-bg); color:#e2e8f0; padding:18px 22px; border-radius:10px;
      overflow-x:auto; font-size:13.5px; line-height:1.75;
      font-family:"Cascadia Mono","Consolas","Courier New",monospace;}
  pre code{background:none; color:inherit; padding:0; font-size:13.5px;}
  .note{background:#eff6ff; border-left:5px solid #2563eb; padding:14px 20px; border-radius:0 8px 8px 0; margin:18px 0;}
  .warn{background:#fff7ed; border-left:5px solid #ea580c; padding:14px 20px; border-radius:0 8px 8px 0; margin:18px 0;}
  .danger{background:#fef2f2; border-left:5px solid #dc2626; padding:14px 20px; border-radius:0 8px 8px 0; margin:18px 0;}
  .ok{background:#f0fdf4; border-left:5px solid #16a34a; padding:14px 20px; border-radius:0 8px 8px 0; margin:18px 0;}

  table{width:100%; border-collapse:collapse; margin:18px 0; font-size:14px;}
  th{background:#f1f5f9; color:var(--ink); font-weight:700; padding:11px 12px;
     border:1px solid var(--line); text-align:left;}
  td{padding:10px 12px; border:1px solid var(--line); vertical-align:top;}
  tbody tr:nth-child(even){background:#fcfdfe;}
  table.tight td, table.tight th{padding:7px 10px; font-size:13.5px;}
  td code{white-space:nowrap;}

  ul,ol{padding-left:26px;} li{margin:6px 0;}

  .grid2{display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:20px 0;}
  .card{background:var(--bg2); border:1px solid var(--line); border-radius:10px; padding:18px 22px;}
  .card h5{margin:0 0 8px; font-size:14.5px; color:var(--brand); font-weight:700;}
  .card p{margin:0; font-size:13.5px; color:var(--ink2); line-height:1.7;}

  .step{display:flex; gap:16px; margin:14px 0; align-items:flex-start;}
  .step .no{flex:0 0 34px; height:34px; border-radius:50%; background:var(--brand); color:#fff;
       display:flex; align-items:center; justify-content:center; font-weight:700; font-size:15px;}
  .step .tx{flex:1;}
  .step .tx b{display:block; margin-bottom:2px; color:var(--ink);}
  .step .tx span{font-size:13.5px; color:var(--ink3);}

  .flow{display:flex; flex-direction:column; gap:0; margin:24px 0;}
  .fnode{background:#fff; border:2px solid var(--line); border-radius:10px; padding:14px 18px;
         display:flex; align-items:center; gap:14px;}
  .fnode .tag{flex:0 0 auto; background:var(--brand); color:#fff; font-size:12px; font-weight:700;
         padding:3px 10px; border-radius:12px;}
  .fnode .ttl{font-weight:700; font-size:14.5px;}
  .fnode .desc{font-size:13px; color:var(--ink3); margin-left:auto; text-align:right; max-width:52%;}
  .farrow{height:22px; display:flex; justify-content:center; align-items:center; color:var(--ink3); font-size:16px;}
  .fnode.hl{border-color:var(--brand); background:#fef2f2;}

  /* ---- 以下为 Markdown 转换新增：引用块与分隔线 ---- */
  blockquote{margin:16px 0; padding:10px 20px; border-radius:0 8px 8px 0;
             background:var(--bg2); border-left:5px solid #94a3b8; color:var(--ink2);}
  blockquote p{margin:4px 0;}
  hr{border:0; border-top:1px solid var(--line); margin:34px 0;}

  footer{margin-top:70px; padding-top:26px; border-top:2px solid var(--line);
         text-align:center; color:var(--ink3); font-size:13px; line-height:2;}

  @media print{
    body{background:#fff;} .wrap{box-shadow:none; max-width:100%; padding:0;}
    .toc{page-break-after:always;}
    h2{page-break-after:avoid;} h3{page-break-after:avoid;}
    table,pre,.fnode{page-break-inside:avoid;}
    .cover{-webkit-print-color-adjust:exact; print-color-adjust:exact;}
    *{-webkit-print-color-adjust:exact; print-color-adjust:exact;}
  }
  @media (max-width:760px){
    .grid2{grid-template-columns:1fr;} .toc ol{columns:1;}
    .cover h1{font-size:28px;}
    .fnode{flex-wrap:wrap;} .fnode .desc{max-width:100%; text-align:left; margin-left:0;}
  }
"""


# ---------------------------------------------------------------------------
# 行内渲染
# ---------------------------------------------------------------------------
def inline(text: str) -> str:
    """
    渲染一行里的行内 Markdown，返回可直接塞进 <p>/<td>/<li> 的 HTML 片段。

    处理顺序很关键：
      ① 先把 `代码` 抠出来换成占位符 —— 否则代码里的 *、[、< 会被后面的
         粗体/链接规则误伤（本项目代码块里就有 `b'$M<'` 这种内容）；
      ② 再整体 HTML 转义（& < >），杜绝原文里的尖括号被当成标签；
      ③ 链接、粗体、斜体依次替换；
      ④ 最后把占位符回填成 <code>。
    参数 text：单行原始 Markdown 文本；返回 HTML 片段。
    """
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        # 占位符用 \x00N\x00：正常文本里不可能出现，避免与正文冲突
        codes.append("<code>" + html.escape(m.group(1), quote=False) + "</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)

    # [文字](链接)：URL 里不含空格与右括号；文字部分已在上面转义过
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        text,
    )
    # 自动链接 <https://...>：转义后形如 &lt;https://...&gt;
    text = re.sub(
        r"&lt;((?:https?|mailto):[^&\s]+)&gt;",
        lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
        text,
    )
    # 粗体必须在斜体之前，否则 **x** 会被当成两个空斜体
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)

    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


# ---------------------------------------------------------------------------
# 表格
# ---------------------------------------------------------------------------
def split_table_row(line: str) -> list[str]:
    """
    拆一行表格为单元格列表。

    🔴 坑：单元格正文里可能出现转义竖线 `\\|`（例如变更说明里的
    `print \\| tee`），直接 split('|') 会把一行拆成错列。故用
    (?<!\\\\)\\| 只在「前面不是反斜杠」处切分，再把 \\| 还原成 |。
    """
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [p.replace("\\|", "|").strip() for p in re.split(r"(?<!\\)\|", s)]


def is_sep_row(line: str) -> bool:
    """判断是否为表格的对齐分隔行（如 | :--- | ---: |）。"""
    if not line.strip().startswith("|"):
        return False
    cells = split_table_row(line)
    return bool(cells) and all(
        re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells
    )


def cell_align(spec: str) -> str:
    """由对齐分隔行的单元格文本得出 style 属性（左右对齐用默认值即可）。"""
    s = spec.replace(" ", "")
    if s.startswith(":") and s.endswith(":"):
        return ' style="text-align:center"'
    if s.endswith(":"):
        return ' style="text-align:right"'
    return ""


def render_table(rows: list[str]) -> str:
    """把连续若干行 |...| 渲染成 <table>；首行作表头，第二行若为分隔行则跳过。"""
    grid = [split_table_row(r) for r in rows]
    has_sep = len(grid) >= 2 and is_sep_row(rows[1])
    head = grid[0]
    body = grid[2:] if has_sep else grid[1:]
    aligns = [cell_align(c) for c in (grid[1] if has_sep else [])]

    out = ["<table>", "<thead><tr>"]
    for j, c in enumerate(head):
        a = aligns[j] if j < len(aligns) else ""
        out.append(f"<th{a}>{inline(c)}</th>")
    out.append("</tr></thead>")
    if body:
        out.append("<tbody>")
        for row in body:
            out.append("<tr>")
            for j, c in enumerate(row):
                a = aligns[j] if j < len(aligns) else ""
                out.append(f"<td{a}>{inline(c)}</td>")
            out.append("</tr>")
        out.append("</tbody>")
    out.append("</table>")
    return "".join(out)


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)$")


def is_list_item(line: str) -> bool:
    """是否为列表项（- / * / + / 1. 开头）。"""
    return bool(LIST_RE.match(line))


def render_list(lines: list[str]) -> str:
    """
    渲染有序/无序列表，支持一层缩进的二级列表。

    本批文档实测只出现两级（顶格 + 两空格缩进），故用「缩进栈」实现：
    缩进变大就开新一层 <ul>/<ol>，变小就逐层闭合；同层若列表类型从 ol
    变成 ul，先闭合再重开，避免把有序项塞进无序容器。
    非列表行视为上一项的续行，拼到该项文字后面。
    """
    parsed: list[tuple[int, str, str]] = []  # (缩进, 标签, 文本)
    for ln in lines:
        m = LIST_RE.match(ln)
        if m:
            indent = len(m.group(1))
            tag = "ol" if re.match(r"\d+\.", m.group(2)) else "ul"
            parsed.append((indent, tag, m.group(3)))
        elif parsed and ln.strip():
            # 续行：接到上一项，避免列表被截断成段落
            i, t, s = parsed[-1]
            parsed[-1] = (i, t, s + " " + ln.strip())

    out: list[str] = []
    stack: list[tuple[int, str]] = []  # [(缩进, 标签)]
    for indent, tag, text in parsed:
        if not stack:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        elif indent > stack[-1][0]:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        else:
            while len(stack) > 1 and indent < stack[-1][0]:
                out.append(f"</{stack.pop()[1]}>")
            if stack[-1][1] != tag:
                # 同一层级换类型（ol <-> ul）：闭合后重开
                out.append(f"</{stack.pop()[1]}>")
                out.append(f"<{tag}>")
                stack.append((indent, tag))
        out.append(f"<li>{inline(text)}</li>")
    while stack:
        out.append(f"</{stack.pop()[1]}>")
    return "".join(out)


# ---------------------------------------------------------------------------
# 引用块
# ---------------------------------------------------------------------------
def render_quote(lines: list[str]) -> str:
    """
    渲染 > 引用块。

    配色沿用原说明书的 .note/.warn/.danger/.ok：带 🔴 用红、⚠️ 用橙、
    ✅ 用绿、★/💡 用蓝；其余用新增的灰色 blockquote，避免整页全是蓝框。
    块内的 `- ` 列表前缀去掉后按行 <br> 连接（本项目引用块里没有更复杂结构）。
    """
    plain = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        s = re.sub(r"^[-*+]\s+", "• ", s)  # 引用内的列表项转成圆点，保留可读性
        plain.append(s)
    body = "<br>".join(inline(s) for s in plain)
    joined = "".join(plain)

    if "🔴" in joined:
        cls = "danger"
    elif "⚠" in joined:
        cls = "warn"
    elif "✅" in joined:
        cls = "ok"
    elif "★" in joined or "💡" in joined:
        cls = "note"
    else:
        cls = ""
    attr = f' class="{cls}"' if cls else ""
    return f"<blockquote{attr}><p>{body}</p></blockquote>"


# ---------------------------------------------------------------------------
# 块级解析总入口
# ---------------------------------------------------------------------------
def is_block_start(lines: list[str], i: int) -> bool:
    """
    判断第 i 行是否开启了一个新块，供「段落收集」循环提前收尾。
    不判断会出的错：段落把紧跟其后的表格 / 标题 / 列表整段吞进 <p>。
    """
    if i >= len(lines):
        return True
    s = lines[i].strip()
    if not s:
        return True
    if s.startswith("```") or s.startswith(">") or s.startswith("|"):
        return True
    if re.match(r"^#{1,6}\s+", lines[i]):
        return True
    if re.match(r"^\s*(---+|\*\*\*+|___+)\s*$", lines[i]):
        return True
    if is_list_item(lines[i]):
        return True
    return False


def convert(md_text: str, meta: dict, src_name: str) -> str:
    """
    把一份 Markdown 文本转换成完整 HTML 页面字符串。

    参数：
      md_text  —— Markdown 原文（UTF-8 文本）
      meta     —— META 里登记的封面信息（badge / sub / facts）
      src_name —— 源文件名，写进 <title> 与页脚，便于追溯来源
    返回：完整的 <!DOCTYPE html> 页面字符串
    """
    lines = md_text.replace("\r\n", "\n").split("\n")
    body: list[str] = []
    toc: list[tuple[str, str]] = []
    title = ""
    i = 0
    h2_count = 0

    while i < len(lines):
        line = lines[i]
        s = line.strip()

        if not s:  # 空行只作分隔，不产生内容
            i += 1
            continue

        # ① 围栏代码块：整段原样转义，不做任何行内解析
        if s.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            body.append("<pre><code>" + html.escape("\n".join(buf), quote=False) + "</code></pre>")
            continue

        # ② 标题：一级作封面标题（正文不再重复输出 h1），二级进目录
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                if not title:
                    title = text
                i += 1
                continue
            if level == 2:
                h2_count += 1
                anchor = f"s{h2_count}"
                toc.append((anchor, text))
                body.append(f'<h2 id="{anchor}">{inline(text)}</h2>')
            elif level == 3:
                body.append(f"<h3>{inline(text)}</h3>")
            else:
                body.append(f"<h4>{inline(text)}</h4>")
            i += 1
            continue

        # ③ 水平分隔线
        if re.match(r"^\s*(---+|\*\*\*+|___+)\s*$", line):
            body.append("<hr>")
            i += 1
            continue

        # ④ 引用块（连续 > 行合并为一个块）
        if s.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            body.append(render_quote(buf))
            continue

        # ⑤ 表格（当前行以 | 开头且下一行是对齐分隔行）
        if s.startswith("|") and i + 1 < len(lines) and is_sep_row(lines[i + 1]):
            buf = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                buf.append(lines[i])
                i += 1
            body.append(render_table(buf))
            continue

        # ⑥ 列表（含缩进续行，续行以空白开头且非空）
        if is_list_item(line):
            buf = []
            while i < len(lines) and (
                is_list_item(lines[i])
                or (
                    lines[i].startswith((" ", "\t"))
                    and lines[i].strip()
                    # 🔴 缩进的代码块 / 引用 / 表格绝不能当「列表续行」吞掉。
                    #    实测坑：变更说明里「- `ModelConfig.h`：...」后面跟了
                    #    一段缩进两空格的 ```cpp 代码块，早期版本会把整段围栏
                    #    连同代码塞进 <li>，渲染成 ``<code>cpp #ifdef ...</code>``
                    #    这种乱码。此处收尾，交回主循环按围栏代码块处理。
                    and not lines[i].strip().startswith(("```", ">", "|"))
                )
            ):
                buf.append(lines[i])
                i += 1
            body.append(render_list(buf))
            continue

        # ⑦ 普通段落：连续非空且未开启新块的行合并为一段
        buf = []
        while i < len(lines) and lines[i].strip() and not is_block_start(lines, i):
            buf.append(lines[i])
            i += 1
        if buf:
            parts = []
            for ln in buf:
                br = ln.endswith("  ")  # Markdown 约定：行尾两空格 = 强制换行
                parts.append(inline(ln.rstrip()) + ("<br>" if br else ""))
            # 中文段落用空串拼接（不会插入多余空格）；行尾双空格已显式 <br>
            body.append("<p>" + "".join(parts) + "</p>")

    if not title:
        title = Path(src_name).stem

    # 封面
    facts = "".join(
        f"<span>{html.escape(k)}　<b>{html.escape(v)}</b></span>"
        for k, v in meta["facts"]
    )
    cover = (
        '<div class="cover">'
        f'<span class="badge">{html.escape(meta["badge"])}</span>'
        f"<h1>{html.escape(title)}</h1>"
        f'<div class="sub">{html.escape(meta["sub"])}</div>'
        f'<div class="facts">{facts}</div>'
        "</div>"
    )

    # 目录（只列二级标题，与现有说明书一致）
    toc_html = ""
    if toc:
        toc_html = (
            '<div class="toc"><h2>目录</h2><ol>'
            + "".join(f'<li><a href="#{a}">{html.escape(t)}</a></li>' for a, t in toc)
            + "</ol></div>"
        )

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    footer = (
        "<footer>"
        f"本页由 <code>Firmware/tools/md2html.py</code> 从 "
        f"<code>{html.escape(src_name)}</code> 生成 · 内容与 Markdown 版同步 · {stamp}<br>"
        "上游 ESP-FC (c) Ramon Lopez（MIT） · 耀坤智联（YaoKunSmart）固件适配"
        "</footer>"
    )

    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n<body>\n<div class=\"wrap\">\n"
        + cover
        + toc_html
        + "\n".join(body)
        + "\n"
        + footer
        + "\n</div>\n</body>\n</html>\n"
    )


def default_meta(name: str) -> dict:
    """未登记在 META 里的文档临时刻一套通用封面，保证脚本对任意 md 都能跑。"""
    return {
        "badge": "ESP-FC耀坤版 · 文档",
        "sub": "Docs/ 说明文档的 HTML 同步版",
        "facts": [
            ("分支", "yaokun-organized"),
            ("上游", "rtlopez/esp-fc（(c) Ramon Lopez，MIT）"),
            ("固件适配", "耀坤智联（YaoKunSmart）"),
            ("源文件", name),
        ],
    }


def main(argv: list[str]) -> int:
    """
    命令行入口：不传参数时转换 META 里登记的三份文档；传文件名则只转这些文件。
    🔴 用 write_bytes 而不是 write_text：显式 UTF-8 + LF，避免 Windows 下
       默认编码与 CRLF 造成整文件假 diff（本项目 pack_release.py 已踩过此坑）。
    """
    names = argv[1:] or list(META.keys())
    ok = True
    for name in names:
        src = Path(name)
        if not src.is_absolute() and not src.exists():
            src = DOCS / name
        if not src.exists():
            print(f"[md2html][错误] 找不到源文件：{name}")
            ok = False
            continue
        dst = src.with_suffix(".html")
        meta = META.get(src.name, default_meta(src.name))
        out = convert(src.read_text(encoding="utf-8"), meta, src.name)
        dst.write_bytes(out.encode("utf-8"))
        print(f"[md2html] {src.name} -> {dst.name}  ({len(out):,} chars, {len(out.encode('utf-8')):,} bytes)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
