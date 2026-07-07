import json
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request

import streamlit as st


PROJECT_ROOT = Path(".")
PROMPTS_DIR = PROJECT_ROOT / "prompts"
CONFIG_DIR = PROJECT_ROOT / "config"
DECONSTRUCT_DIR = PROJECT_ROOT / "02-拆解结果库"
RULES_FILE = PROJECT_ROOT / "03-规律库" / "规律汇总报告.md"

MODEL_LABELS = {
    "deepseek_chat": "DeepSeek",
    "glm_4_flash": "智谱 GLM-4-Flash",
    "gpt_4o": "GPT-4o",
}


@st.cache_data(show_spinner=False)
def read_text(file_path: Path) -> str:
    """读取 UTF-8 文本，兼容 BOM。"""
    return file_path.read_text(encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def load_prompt(file_name: str) -> str:
    """读取外部提示词文件。"""
    file_path = PROMPTS_DIR / file_name
    if not file_path.exists():
        return ""
    return read_text(file_path)


@st.cache_data(show_spinner=False)
def load_model_config() -> Dict[str, Any]:
    """读取模型配置。"""
    config_path = CONFIG_DIR / "models.json"
    if not config_path.exists():
        return {}
    return json.loads(read_text(config_path))


@st.cache_data(show_spinner=False)
def load_rules_report() -> str:
    """读取规律汇总报告。"""
    if not RULES_FILE.exists():
        return "未找到规律汇总报告。"
    return read_text(RULES_FILE)


def build_rules_summary(report_text: str) -> str:
    """提取适合在侧边栏展示的规律摘要。"""
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
    return report_text[:1800]


@st.cache_data(show_spinner=False)
def load_deconstruction_results() -> List[Dict[str, str]]:
    """读取拆解结果库。"""
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


def build_reference_digest(results: List[Dict[str, str]], max_items: int = 3) -> str:
    """压缩拆解样本，减少上下文噪音。"""
    digests: List[str] = []

    for item in results[:max_items]:
        content = item["content"]
        digests.append(f"### 参考拆解：{item['file_name']}\n{content[:1800]}")

    return "\n\n".join(digests)


def get_model_options(model_config: Dict[str, Any]) -> List[Dict[str, str]]:
    """把配置文件转换成下拉可用的模型列表。"""
    models = model_config.get("models", {})
    options: List[Dict[str, str]] = []

    for model_key, model_info in models.items():
        display_name = MODEL_LABELS.get(model_key) or model_info.get("name") or model_info.get("label") or model_key
        options.append({"key": model_key, "name": display_name})

    return options


def get_selected_model_info(model_config: Dict[str, Any], selected_model: str) -> Dict[str, Any]:
    """读取当前选中的模型配置。"""
    return model_config.get("models", {}).get(selected_model, {})


def init_session_state() -> None:
    """初始化会话状态。"""
    defaults = {
        "mode": "work",
        "messages": [],
        "draft_history": [],
        "api_key": "",
        "latest_output": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def init_static_session_data() -> None:
    """仅在会话首次加载时准备静态数据。"""
    if "rules_text" not in st.session_state:
        st.session_state.rules_text = load_rules_report()
    if "rules_summary" not in st.session_state:
        st.session_state.rules_summary = build_rules_summary(st.session_state.rules_text)
    if "deconstruction_results" not in st.session_state:
        st.session_state.deconstruction_results = load_deconstruction_results()
    if "references_text" not in st.session_state:
        st.session_state.references_text = build_reference_digest(st.session_state.deconstruction_results)
    if "model_config" not in st.session_state:
        st.session_state.model_config = load_model_config()

    model_options = get_model_options(st.session_state.model_config)
    if "model_options" not in st.session_state:
        st.session_state.model_options = model_options

    default_model = st.session_state.model_config.get("default_model", "deepseek_chat")
    valid_keys = [item["key"] for item in st.session_state.model_options]
    if "selected_model" not in st.session_state or st.session_state.selected_model not in valid_keys:
        st.session_state.selected_model = default_model if default_model in valid_keys else valid_keys[0]


def set_mode(mode: str) -> None:
    """切换模式。"""
    if st.session_state.mode != mode:
        st.session_state.mode = mode


def is_edit_request(user_text: str) -> bool:
    """粗略判断是否是连续修改请求。"""
    keywords = [
        "改标题",
        "换开头",
        "改开头",
        "缩短",
        "压缩",
        "重写",
        "拼一下",
        "融合",
        "合并",
        "像我一点",
        "太官方",
        "这个可以了",
        "再来一版",
        "优化一下",
    ]
    return any(keyword in user_text for keyword in keywords)


def build_system_prompt(mode: str) -> str:
    """拼装系统提示词。"""
    if mode == "work":
        return "\n\n".join(
            [
                load_prompt("system_work.md"),
                load_prompt("task_work_delivery.md"),
                load_prompt("task_iterate_edit.md"),
            ]
        ).strip()

    return "\n\n".join(
        [
            load_prompt("system_personal.md"),
            load_prompt("task_personal_startup.md"),
            load_prompt("task_iterate_edit.md"),
        ]
    ).strip()


def build_user_prompt(
    user_text: str,
    mode: str,
    rules_text: str,
    references_text: str,
) -> str:
    """构造本轮用户提示。"""
    mode_name = "工作模式" if mode == "work" else "个人模式"
    latest_output = st.session_state.get("latest_output", "")
    edit_hint = (
        "这是一次连续修改请求，请优先在已有版本基础上局部迭代。"
        if is_edit_request(user_text)
        else "这是一次新的内容请求，请先理解意图再输出。"
    )

    return f"""
当前模式：{mode_name}

用户输入：
{user_text}

任务判断：
{edit_hint}

当前已沉淀规律：
{rules_text[:3000]}

当前可参考拆解：
{references_text[:3500]}

最近一版输出（如有）：
{latest_output[:2500] if latest_output else "暂无"}

请注意：
1. 像聊天助手一样自然回应。
2. 如果是工作模式，优先输出可交付成品，并补充简短汇报说明。
3. 如果是个人模式，优先围绕用户真实条件做内容定位、起号规划和执行方案。
4. 如果用户是在改稿，不要整篇推翻，优先局部修改。
5. 不要让用户填表，直接理解并帮他往前推进。
""".strip()


def build_model_payload(mode: str, user_text: str, rules_text: str, references_text: str) -> List[Dict[str, str]]:
    """生成发给模型的消息列表。"""
    system_prompt = build_system_prompt(mode)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    history = st.session_state.messages[-8:]
    for item in history:
        messages.append({"role": item["role"], "content": item["content"]})

    messages.append(
        {
            "role": "user",
            "content": build_user_prompt(user_text, mode, rules_text, references_text),
        }
    )
    return messages


def call_chat_model(
    api_key: str,
    model_config: Dict[str, Any],
    selected_model: str,
    mode: str,
    user_text: str,
    rules_text: str,
    references_text: str,
) -> str:
    """调用聊天模型。"""
    if not api_key.strip():
        raise RuntimeError("请先在页面左侧填写 API Key。")

    model_info = get_selected_model_info(model_config, selected_model)
    api_url = model_info.get("api_base") or model_info.get("api_url", "")
    model_name = model_info.get("model") or model_info.get("model_name", "")
    api_url = api_url.strip()
    model_name = model_name.strip()

    if not api_url or not model_name:
        raise RuntimeError("当前选中模型配置不完整，请检查 config/models.json。")

    payload = {
        "model": model_name,
        "messages": build_model_payload(mode, user_text, rules_text, references_text),
        "temperature": 0.7,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key.strip()}",
    }

    req = request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=180) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError("模型返回为空。")
        return content
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"API 调用失败：HTTP {exc.code} {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"网络连接失败：{exc.reason}") from exc


def render_mode_switch() -> None:
    """渲染模式切换。"""
    st.subheader("模式切换")
    col1, col2 = st.columns(2)

    work_type = "primary" if st.session_state.mode == "work" else "secondary"
    personal_type = "primary" if st.session_state.mode == "personal" else "secondary"

    with col1:
        if st.button("工作模式", use_container_width=True, type=work_type):
            set_mode("work")
    with col2:
        if st.button("个人模式", use_container_width=True, type=personal_type):
            set_mode("personal")

    mode_desc = (
        "适合领导任务、文案交付、汇报说明、对外可提交内容。"
        if st.session_state.mode == "work"
        else "适合起号规划、内容方向、个人IP、变现路径、长期策划。"
    )
    st.caption(mode_desc)


def render_model_selector() -> None:
    """渲染模型选择下拉。"""
    st.subheader("模型选择")
    options = st.session_state.model_options
    option_names = [item["name"] for item in options]
    key_to_name = {item["key"]: item["name"] for item in options}
    name_to_key = {item["name"]: item["key"] for item in options}

    current_name = key_to_name.get(st.session_state.selected_model, option_names[0])
    selected_name = st.selectbox(
        "选择模型",
        options=option_names,
        index=option_names.index(current_name),
        label_visibility="collapsed",
    )
    st.session_state.selected_model = name_to_key[selected_name]


def render_sidebar(rules_summary: str, deconstruction_results: List[Dict[str, str]]) -> None:
    """渲染侧边栏。"""
    with st.sidebar:
        st.title("助手配置")
        render_mode_switch()
        render_model_selector()

        st.subheader("API Key")
        st.session_state.api_key = st.text_input(
            "直接在这里填 Key",
            value=st.session_state.api_key,
            type="password",
            placeholder="输入通用 API Key",
        )

        selected_model_info = get_selected_model_info(
            st.session_state.model_config,
            st.session_state.selected_model,
        )
        selected_model_name = MODEL_LABELS.get(st.session_state.selected_model) or selected_model_info.get("name") or selected_model_info.get("label") or st.session_state.selected_model

        st.subheader("当前状态")
        st.markdown(
            f"""
- 当前模式：`{"工作模式" if st.session_state.mode == "work" else "个人模式"}`
- 当前模型：`{selected_model_name}`
- 参考拆解：`{len(deconstruction_results)}` 篇
- 规律报告：`已加载`
- API Key：`{"已填写" if st.session_state.api_key else "未填写"}`
"""
        )

        with st.expander("规律库摘要", expanded=False):
            st.text_area(
                "规律摘要",
                value=rules_summary,
                height=320,
                disabled=True,
                label_visibility="collapsed",
            )


def render_chat_history() -> None:
    """渲染聊天记录。"""
    for item in st.session_state.messages:
        with st.chat_message("user" if item["role"] == "user" else "assistant"):
            st.markdown(item["content"])


def handle_user_message(rules_text: str, references_text: str, model_config: Dict[str, Any]) -> None:
    """处理用户输入。"""
    user_text = st.chat_input(
        "直接像聊天一样说：领导让我写一篇XX主题文案 / 我想做个账号 / 改标题 / 换开头..."
    )
    if not user_text:
        return

    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.spinner("正在帮你整理方案..."):
            try:
                result = call_chat_model(
                    api_key=st.session_state.api_key,
                    model_config=model_config,
                    selected_model=st.session_state.selected_model,
                    mode=st.session_state.mode,
                    user_text=user_text,
                    rules_text=rules_text,
                    references_text=references_text,
                )
                st.markdown(result)
                st.session_state.messages.append({"role": "assistant", "content": result})
                st.session_state.latest_output = result
                st.session_state.draft_history.append(result)
            except Exception as exc:  # noqa: BLE001
                error_text = f"生成失败：{exc}"
                st.error(error_text)
                st.session_state.messages.append({"role": "assistant", "content": error_text})


def main() -> None:
    """主入口。"""
    st.set_page_config(
        page_title="内容创作聊天助手",
        page_icon="🧠",
        layout="wide",
    )
    init_session_state()
    init_static_session_data()

    rules_text = st.session_state.rules_text
    rules_summary = st.session_state.rules_summary
    deconstruction_results = st.session_state.deconstruction_results
    references_text = st.session_state.references_text
    model_config = st.session_state.model_config

    render_sidebar(rules_summary, deconstruction_results)

    st.title("内容创作聊天助手")
    st.caption("像聊天一样输入任务或想法，系统自动帮你做策划、起号、写稿和连续改稿。")

    intro = (
        "你现在在【工作模式】。可以直接说：领导让我写一篇XX主题文案。"
        if st.session_state.mode == "work"
        else "你现在在【个人模式】。可以直接说：我想做个账号，我有一辆车、单休、人比较实在。"
    )
    st.info(intro)

    render_chat_history()
    handle_user_message(rules_text, references_text, model_config)


if __name__ == "__main__":
    main()
