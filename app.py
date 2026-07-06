import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request

import streamlit as st
import streamlit.components.v1 as components


PROJECT_ROOT = Path(".")
DECONSTRUCT_DIR = PROJECT_ROOT / "02-拆解结果库"
RULES_FILE = PROJECT_ROOT / "03-规律库" / "规律汇总报告.md"

DEEPSEEK_API_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()


def read_text(file_path: Path) -> str:
    """统一读取文本文件，兼容 UTF-8 BOM。"""
    return file_path.read_text(encoding="utf-8-sig")


def load_rules_report() -> str:
    """读取规律汇总报告全文。"""
    if not RULES_FILE.exists():
        return "未找到规律汇总报告，请确认 03-规律库/规律汇总报告.md 已存在。"
    return read_text(RULES_FILE)


def build_rules_summary(report_text: str) -> str:
    """提取适合在左侧展示的规律摘要。"""
    wanted_headers = [
        "## 3. 共性规律提炼",
        "## 5. 可复用的爆款公式总结",
        "## 6. 风险提示与注意事项",
    ]
    sections: List[str] = []

    for header in wanted_headers:
        start = report_text.find(header)
        if start == -1:
            continue
        next_header = report_text.find("\n## ", start + 1)
        section = report_text[start:] if next_header == -1 else report_text[start:next_header]
        sections.append(section.strip())

    if sections:
        return "\n\n".join(sections)
    return report_text[:1500]


def load_deconstruction_results() -> List[Dict[str, str]]:
    """读取拆解结果库中的 Markdown 文件。"""
    results: List[Dict[str, str]] = []
    if not DECONSTRUCT_DIR.exists():
        return results

    for file_path in sorted(DECONSTRUCT_DIR.glob("*.md")):
        if file_path.name in {"README.md", "拆解模板.md"}:
            continue
        results.append(
            {
                "file_name": file_path.name,
                "content": read_text(file_path),
            }
        )
    return results


def build_reference_digest(results: List[Dict[str, str]]) -> str:
    """把多篇拆解结果压缩成更适合送给模型的参考摘要。"""
    digests: List[str] = []

    for item in results:
        content = item["content"]
        sample_match = re.search(r"对应样本[：:]\s*(.+)", content)
        summary_match = re.search(r"## 十四、结构化提炼(.*?)(## 十五、可靠性说明|$)", content, re.S)

        sample_name = sample_match.group(1).strip() if sample_match else item["file_name"]
        summary_text = summary_match.group(1).strip() if summary_match else content[:800]
        digests.append(f"### 参考样本：{sample_name}\n{summary_text}")

    return "\n\n".join(digests)


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """兼容模型返回前后夹杂解释文本的情况，尽量提取 JSON。"""
    cleaned = text.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return json.loads(cleaned)

    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        raise ValueError("模型返回中未找到合法 JSON。")
    return json.loads(match.group(0))


def build_prompt(topic: str, rules_text: str, references_text: str) -> str:
    """构造文案生成 Prompt。"""
    return f"""
你现在是「小红书文案生成器」，专门服务于：
- 工业制造业
- 文旅装备
- B端场景
- 工厂源头 / 项目方案 / 场景升级 / 产品讲解

你的任务：基于【用户输入主题】、【已有拆解结果】、【规律汇总报告】，生成一篇可直接使用的小红书笔记文案。

【用户输入主题】
{topic}

【规律汇总报告】
{rules_text}

【拆解结果参考】
{references_text}

请严格遵守以下生成要求：
1. 风格必须符合工业制造业 / 文旅装备 / B端场景赛道
2. 开头 3 行内必须抓住注意力
3. 正文按照“痛点切入 → 解决方案 → 价值证明 → 行动引导”推进
4. 评论区引导必须自然承接询盘转化
5. 不要空泛鸡汤，不要写泛生活类口吻
6. 不要编造具体成交数据、客户案例和价格
7. 输出必须是 JSON，不要输出任何额外解释

请按下面 JSON 结构输出：
{{
  "topic": "主题",
  "titles": ["标题1", "标题2", "标题3"],
  "body": "完整正文，500-800字",
  "image_suggestions": [
    "第1张图建议",
    "第2张图建议",
    "第3张图建议",
    "第4张图建议",
    "第5张图建议",
    "第6张图建议"
  ],
  "comment_guides": [
    {{
      "preset_comment": "预设评论1",
      "author_reply": "作者回复1"
    }},
    {{
      "preset_comment": "预设评论2",
      "author_reply": "作者回复2"
    }},
    {{
      "preset_comment": "预设评论3",
      "author_reply": "作者回复3"
    }}
  ],
  "hashtags": ["标签1", "标签2", "标签3", "标签4", "标签5", "标签6", "标签7", "标签8"]
}}
""".strip()


def call_deepseek(prompt: str) -> Dict[str, Any]:
    """调用 DeepSeek API 生成文案。"""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("未检测到 DEEPSEEK_API_KEY 环境变量。")

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个严谨的小红书文案生成助手，必须只输出合法 JSON。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.7,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }

    req = request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError("模型返回为空。")
        return extract_json_from_text(content)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"API 调用失败：HTTP {exc.code} {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"网络连接失败：{exc.reason}") from exc


def build_markdown_output(result: Dict[str, Any]) -> str:
    """把结构化结果转成适合复制的 Markdown。"""
    lines: List[str] = []
    lines.append(f"# 主题\n{result.get('topic', '')}\n")

    lines.append("## 标题（3个版本）")
    for index, title in enumerate(result.get("titles", []), start=1):
        lines.append(f"{index}. {title}")
    lines.append("")

    lines.append("## 正文")
    lines.append(result.get("body", ""))
    lines.append("")

    lines.append("## 配图建议")
    for index, item in enumerate(result.get("image_suggestions", []), start=1):
        lines.append(f"{index}. {item}")
    lines.append("")

    lines.append("## 评论区引导话术")
    for index, item in enumerate(result.get("comment_guides", []), start=1):
        lines.append(f"### 预设评论{index}")
        lines.append(f"- 用户评论：{item.get('preset_comment', '')}")
        lines.append(f"- 作者回复：{item.get('author_reply', '')}")
        lines.append("")

    lines.append("## 标签推荐")
    lines.append(" ".join(result.get("hashtags", [])))
    lines.append("")
    return "\n".join(lines).strip()


def render_copy_button(text: str) -> None:
    """渲染一键复制按钮。"""
    safe_text = json.dumps(text)
    components.html(
        f"""
        <div style="margin-top: 8px; margin-bottom: 12px;">
            <button
                onclick='navigator.clipboard.writeText({safe_text}); this.innerText="已复制";'
                style="
                    background:#111827;
                    color:white;
                    border:none;
                    padding:10px 16px;
                    border-radius:8px;
                    cursor:pointer;
                    font-size:14px;
                "
            >
                一键复制文案
            </button>
        </div>
        """,
        height=60,
    )


st.set_page_config(
    page_title="小红书文案生成器",
    page_icon="📝",
    layout="wide",
)

st.title("小红书文案生成器")
st.caption("基于拆解结果库 + 规律库，自动生成工业制造业 / 文旅装备 / B端场景小红书文案")

rules_text = load_rules_report()
rules_summary = build_rules_summary(rules_text)
deconstruction_results = load_deconstruction_results()

left_col, right_col = st.columns([1, 2], gap="large")

with left_col:
    st.subheader("规律库摘要")
    st.text_area(
        "来自 03-规律库/规律汇总报告.md",
        value=rules_summary,
        height=700,
        disabled=True,
        label_visibility="collapsed",
    )

with right_col:
    st.subheader("输入主题")
    topic = st.text_input(
        "请输入想写的主题",
        value="工业制造业转型做文旅场景",
        placeholder="例如：太空舱民宿选购避坑指南",
    )

    st.markdown(
        f"""
**当前参考数据**
- 拆解结果数：`{len(deconstruction_results)}` 篇
- 规律报告：`{"已加载" if rules_text else "未加载"}`
- DeepSeek Key：`{"已检测到" if DEEPSEEK_API_KEY else "未检测到"}`
"""
    )

    if st.button("生成文案", type="primary", use_container_width=True):
        if not topic.strip():
            st.error("请输入主题后再生成。")
        elif not deconstruction_results:
            st.error("未读取到 02-拆解结果库 中的拆解结果。")
        elif not rules_text:
            st.error("未读取到 03-规律库/规律汇总报告.md。")
        elif not DEEPSEEK_API_KEY:
            st.error("未检测到 DEEPSEEK_API_KEY 环境变量，无法调用 DeepSeek API。")
        else:
            with st.spinner("正在生成文案，请稍等..."):
                try:
                    references_text = build_reference_digest(deconstruction_results)
                    prompt = build_prompt(topic.strip(), rules_text, references_text)
                    result = call_deepseek(prompt)
                    markdown_output = build_markdown_output(result)

                    st.success("文案生成成功")

                    st.markdown("## 标题（3个版本）")
                    for index, title in enumerate(result.get("titles", []), start=1):
                        st.markdown(f"{index}. {title}")

                    st.markdown("## 正文")
                    st.write(result.get("body", ""))

                    st.markdown("## 配图建议")
                    for index, item in enumerate(result.get("image_suggestions", []), start=1):
                        st.markdown(f"{index}. {item}")

                    st.markdown("## 评论区引导话术")
                    for index, item in enumerate(result.get("comment_guides", []), start=1):
                        st.markdown(f"**预设评论{index}**")
                        st.markdown(f"- 用户评论：{item.get('preset_comment', '')}")
                        st.markdown(f"- 作者回复：{item.get('author_reply', '')}")

                    st.markdown("## 标签推荐")
                    st.write(" ".join(result.get("hashtags", [])))

                    st.markdown("## 可复制 Markdown")
                    render_copy_button(markdown_output)
                    st.text_area(
                        "生成结果",
                        value=markdown_output,
                        height=420,
                        label_visibility="collapsed",
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"生成失败：{exc}")
