import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, parse, request

import streamlit as st


PROJECT_ROOT = Path(".")
PROMPTS_DIR = PROJECT_ROOT / "prompts"
CONFIG_DIR = PROJECT_ROOT / "config"
DECONSTRUCT_DIR = PROJECT_ROOT / "02-拆解结果库"
RULES_FILE = PROJECT_ROOT / "03-规律库" / "规律汇总报告.md"

DEFAULT_IDENTITIES = {
    "work": "我是小红书运营，负责内容创作、拍摄、剪辑。请默认按公司账号运营逻辑给我建议，重视交付、执行和汇报场景。",
    "personal": "我是打工人，正在做个人账号，时间和资源有限。请默认给我可执行、接地气、低成本、能长期坚持的建议。",
}

MODEL_SECRET_KEYS = {
    "deepseek_chat": ["DEEPSEEK_API_KEY", "deepseek_api_key"],
    "glm_4_flash": ["ZHIPU_API_KEY", "BIGMODEL_API_KEY", "zhipu_api_key"],
    "gpt_4o": ["OPENAI_API_KEY", "GPT_API_KEY", "openai_api_key"],
}

MODE_META = {
    "work": {
        "label": "工作模式",
        "session_prefix": "work",
        "intro": "你现在在【工作模式】。可以直接说：领导让我写一篇 XX 主题文案，或者帮我做一版能直接交付的策划。",
        "desc": "适合领导任务、文案交付、汇报说明、对外可提交内容。",
    },
    "personal": {
        "label": "个人模式",
        "session_prefix": "personal",
        "intro": "你现在在【个人模式】。可以直接说：我想做个账号，我有什么资源、什么性格、什么时间安排。",
        "desc": "适合起号规划、内容方向、个人 IP、变现路径和长期内容策划。",
    },
}

SEARCH_KEYWORDS = [
    "最新",
    "最近",
    "这两天",
    "今天",
    "趋势",
    "爆款",
    "热门",
    "选题",
    "赛道",
]


@st.cache_data(show_spinner=False)
def read_text(file_path: Path) -> str:
    """读取 UTF-8 文本。"""
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
        return {"default_model": "deepseek_chat", "models": {}}
    return json.loads(read_text(config_path))


@st.cache_data(show_spinner=False)
def load_rules_report() -> str:
    """读取规律汇总报告。"""
    if not RULES_FILE.exists():
        return "未找到规律汇总报告。"
    return read_text(RULES_FILE)


@st.cache_data(show_spinner=False)
def load_deconstruction_results() -> List[Dict[str, str]]:
    """读取拆解结果库。"""
    results: List[Dict[str, str]] = []
    if not DECONSTRUCT_DIR.exists():
        return results

    for file_path in sorted(DECONSTRUCT_DIR.glob("*.md")):
        results.append({"file_name": file_path.name, "content": read_text(file_path)})
    return results


@st.cache_data(show_spinner=False)
def build_rules_summary(report_text: str) -> str:
    """抽取规律报告中最适合侧边栏展示的摘要。"""
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


def build_reference_digest(results: List[Dict[str, str]], max_items: int = 3) -> str:
    """压缩拆解结果，降低提示词噪音。"""
    digests: List[str] = []
    for item in results[:max_items]:
        digests.append(f"### 参考拆解：{item['file_name']}\n{item['content'][:1800]}")
    return "\n\n".join(digests)


def clean_text(value: str) -> str:
    """清洗模型和搜索上下文中的多余空白。"""
    return re.sub(r"\n{3,}", "\n\n", value.strip())


def get_model_options(model_config: Dict[str, Any]) -> List[Dict[str, str]]:
    """生成模型下拉列表。"""
    options: List[Dict[str, str]] = []
    for model_key, model_info in model_config.get("models", {}).items():
        if not model_info.get("enabled", True):
            continue
        options.append({"key": model_key, "name": model_info.get("name", model_key)})
    return options


def get_selected_model_info(model_config: Dict[str, Any], selected_model: str) -> Dict[str, Any]:
    """获取当前模型配置。"""
    return model_config.get("models", {}).get(selected_model, {})


def get_secret_api_key(model_key: str) -> str:
    """从 secrets 中按模型读取默认 API Key。"""
    try:
        secrets_dict = dict(st.secrets)
    except Exception:  # noqa: BLE001
        return ""

    for secret_name in MODEL_SECRET_KEYS.get(model_key, []):
        value = str(secrets_dict.get(secret_name, "")).strip()
        if value:
            return value
    return ""


def get_config_api_key(model_info: Dict[str, Any]) -> str:
    """从配置文件里读取回退 API Key。"""
    return str(model_info.get("api_key", "")).strip()


def resolve_api_key(model_key: str, model_info: Dict[str, Any]) -> str:
    """按优先级决定最终可用的 API Key。"""
    manual_api_keys = st.session_state.get("manual_api_keys", {})
    manual_key = str(manual_api_keys.get(model_key, "")).strip()
    if manual_key:
        return manual_key

    secret_key = get_secret_api_key(model_key)
    if secret_key:
        return secret_key

    return get_config_api_key(model_info)


def get_mode_prefix(mode: str) -> str:
    """获取模式前缀。"""
    return MODE_META[mode]["session_prefix"]


def get_mode_key(mode: str, suffix: str) -> str:
    """生成模式隔离后的 session_state key。"""
    return f"{get_mode_prefix(mode)}_{suffix}"


def ensure_mode_state(mode: str) -> None:
    """初始化某个模式独立状态。"""
    defaults = {
        get_mode_key(mode, "messages"): [],
        get_mode_key(mode, "draft_history"): [],
        get_mode_key(mode, "latest_output"): "",
        get_mode_key(mode, "identity"): DEFAULT_IDENTITIES[mode],
        get_mode_key(mode, "search_cache"): {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def init_session_state() -> None:
    """初始化全局会话状态。"""
    if "mode" not in st.session_state:
        st.session_state.mode = "work"
    if "manual_api_keys" not in st.session_state:
        st.session_state.manual_api_keys = {}
    if "runtime_logs" not in st.session_state:
        st.session_state.runtime_logs = []

    ensure_mode_state("work")
    ensure_mode_state("personal")


def init_static_session_data() -> None:
    """只在会话开始时准备静态数据。"""
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
    if "model_options" not in st.session_state:
        st.session_state.model_options = get_model_options(st.session_state.model_config)

    valid_keys = [item["key"] for item in st.session_state.model_options]
    default_model = st.session_state.model_config.get("default_model", "deepseek_chat")
    if "selected_model" not in st.session_state or st.session_state.selected_model not in valid_keys:
        st.session_state.selected_model = default_model if default_model in valid_keys else valid_keys[0]

    for model_option in st.session_state.model_options:
        model_key = model_option["key"]
        if model_key not in st.session_state.manual_api_keys:
            model_info = get_selected_model_info(st.session_state.model_config, model_key)
            saved_key = get_secret_api_key(model_key) or get_config_api_key(model_info)
            st.session_state.manual_api_keys[model_key] = saved_key

    if "api_key_input" not in st.session_state:
        current_model = st.session_state.selected_model
        current_info = get_selected_model_info(st.session_state.model_config, current_model)
        st.session_state.api_key_input = resolve_api_key(current_model, current_info)


def log_runtime(message: str) -> None:
    """记录页面级运行日志，便于侧边栏观察。"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    logs = st.session_state.get("runtime_logs", [])
    logs.append(f"[{timestamp}] {message}")
    st.session_state.runtime_logs = logs[-20:]


def sync_api_key_input_for_model() -> None:
    """切换模型时同步当前模型的 API Key 到输入框。"""
    current_model = st.session_state.selected_model
    current_info = get_selected_model_info(st.session_state.model_config, current_model)
    st.session_state.api_key_input = resolve_api_key(current_model, current_info)


def set_mode(mode: str) -> None:
    """切换模式，只更新 session_state。"""
    if st.session_state.mode != mode:
        st.session_state.mode = mode


def get_current_messages(mode: str) -> List[Dict[str, str]]:
    """读取当前模式的消息记录。"""
    return st.session_state[get_mode_key(mode, "messages")]


def get_current_draft_history(mode: str) -> List[str]:
    """读取当前模式的草稿历史。"""
    return st.session_state[get_mode_key(mode, "draft_history")]


def get_current_latest_output(mode: str) -> str:
    """读取当前模式最近一次输出。"""
    return st.session_state[get_mode_key(mode, "latest_output")]


def get_current_identity(mode: str) -> str:
    """读取当前模式身份。"""
    return st.session_state[get_mode_key(mode, "identity")]


def set_current_identity(mode: str, identity_text: str) -> None:
    """更新当前模式身份。"""
    st.session_state[get_mode_key(mode, "identity")] = identity_text.strip()


def append_mode_message(mode: str, role: str, content: str) -> None:
    """往指定模式追加一条消息。"""
    messages = get_current_messages(mode)
    messages.append({"role": role, "content": content})
    st.session_state[get_mode_key(mode, "messages")] = messages


def save_mode_output(mode: str, output_text: str) -> None:
    """保存当前模式最近输出和草稿历史。"""
    st.session_state[get_mode_key(mode, "latest_output")] = output_text
    draft_history = get_current_draft_history(mode)
    draft_history.append(output_text)
    st.session_state[get_mode_key(mode, "draft_history")] = draft_history[-20:]


def is_edit_request(user_text: str) -> bool:
    """判断是否为连续改稿请求。"""
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


def should_trigger_realtime_search(user_text: str) -> bool:
    """判断这轮是否值得补充实时搜索。"""
    return any(keyword in user_text for keyword in SEARCH_KEYWORDS)


def parse_identity_update(user_text: str, current_mode: str) -> Optional[Tuple[str, str]]:
    """识别用户是否在更新身份档案。"""
    normalized = user_text.strip()
    if "记住这个身份" in normalized or "记住我的身份" in normalized:
        return current_mode, normalized.replace("记住这个身份", "").replace("记住我的身份", "").strip("：:，, ")

    mode_prefix_map = {
        "工作模式": "work",
        "个人模式": "personal",
    }

    for text_prefix, mode in mode_prefix_map.items():
        patterns = [
            rf"^{text_prefix}下[，,：: ]*(.*)$",
            rf"^{text_prefix}[，,：: ]*我是(.*)$",
            rf"^{text_prefix}的定位改一下[，,：: ]*(.*)$",
            rf"^{text_prefix}记住[，,：: ]*(.*)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, normalized)
            if match:
                identity_text = match.group(1).strip()
                return mode, identity_text

    if normalized.startswith("我是") and ("记住" in normalized or "以后按这个" in normalized):
        return current_mode, normalized

    return None


def build_identity_confirmation(mode: str, identity_text: str) -> str:
    """生成身份更新确认话术。"""
    mode_label = MODE_META[mode]["label"]
    return (
        f"已记住你的{mode_label}身份设定。\n\n"
        f"**当前身份档案**\n{identity_text}\n\n"
        "后面在这个模式下，我都会默认按这套身份理解你来给建议。"
    )


def build_system_prompt(mode: str, identity_text: str) -> str:
    """组装系统提示词。"""
    system_file = "system_work.md" if mode == "work" else "system_personal.md"
    task_file = "task_work_delivery.md" if mode == "work" else "task_personal_startup.md"

    blocks = [
        load_prompt(system_file),
        load_prompt(task_file),
        load_prompt("task_iterate_edit.md"),
        f"当前模式身份档案：\n{identity_text}",
        (
            "输出必须优先采用讨论式结构：\n"
            "1. 我的判断：先说你看到了什么、参考了什么、为什么这样判断。\n"
            "2. 初稿或方案：再给可执行结果。\n"
            "3. 主动追问：最后自然地问用户这个方向是否对、哪里要改。\n"
            "除非用户明确要求直接成稿，否则不能跳过“我的判断”。\n"
            "“可直接提交版本”或“汇报说明”只能放在第二段里，不能替代第一段。\n"
            "语气要像真人搭档，不要像冷冰冰模板。"
        ),
    ]
    return "\n\n".join([block for block in blocks if block]).strip()


def format_search_context(search_items: List[Dict[str, str]]) -> str:
    """把搜索结果压缩成提示词上下文。"""
    if not search_items:
        return "本轮未补充实时搜索结果。"

    lines = ["本轮补充了实时搜索线索，请优先把它们作为最新市场信号使用："]
    for index, item in enumerate(search_items, start=1):
        lines.append(
            f"{index}. 标题：{item.get('title', '无法获取')} | 来源：{item.get('source', '未知')} | "
            f"摘要：{item.get('snippet', '无法获取')} | 链接：{item.get('link', '无法获取')}"
        )
    return "\n".join(lines)


def get_latest_context_block(mode: str) -> str:
    """获取当前模式最近一次输出。"""
    latest_output = get_current_latest_output(mode)
    return latest_output[:2500] if latest_output else "暂无"


def build_user_prompt(
    user_text: str,
    mode: str,
    rules_text: str,
    references_text: str,
    search_context: str,
) -> str:
    """构造用户提示词。"""
    mode_name = MODE_META[mode]["label"]
    edit_hint = (
        "这是一次连续修改请求，请优先在已确认方向上做局部迭代，不要整篇推翻重来。"
        if is_edit_request(user_text)
        else "这是一次新的内容请求，请先做判断，再给方案或初稿。"
    )

    return clean_text(
        f"""
当前模式：{mode_name}

用户这次的话：
{user_text}

任务判断：
{edit_hint}

当前模式最近一次输出：
{get_latest_context_block(mode)}

规律库约束：
{rules_text[:3000]}

拆解参考：
{references_text[:3500]}

实时搜索补充：
{search_context}

请严格按下面的输出体验来：
1. 先写“我的判断”，说清楚你是怎么理解这个需求的、参考了什么、为什么建议这个方向。
2. 再给“文案初稿”或“可执行方案”。
3. 最后主动追问一句，邀请我继续改，而不是一次性结束。
4. 不要一上来就只给“可直接提交版本”和“汇报说明”，那只能作为第二段里的补充。
5. 如果是工作模式，要更像可交付内容搭档，兼顾交付和汇报口径。
6. 如果是个人模式，要更像陪我一起起号的真人策划，建议要低门槛、能落地。
"""
    )


def build_model_payload(
    mode: str,
    user_text: str,
    rules_text: str,
    references_text: str,
    search_context: str,
) -> List[Dict[str, str]]:
    """生成模型调用消息列表。"""
    system_prompt = build_system_prompt(mode, get_current_identity(mode))
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    history = get_current_messages(mode)[-8:]
    messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": build_user_prompt(user_text, mode, rules_text, references_text, search_context),
        }
    )
    return messages


@st.cache_data(show_spinner=False, ttl=1800)
def search_hot_posts(query: str) -> List[Dict[str, str]]:
    """基于 DuckDuckGo 的轻量实时搜索，补充最新公开网页线索。"""
    url = f"https://duckduckgo.com/html/?q={parse.quote(query)}"
    req = request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )
        },
        method="GET",
    )

    try:
        with request.urlopen(req, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return []

    results: List[Dict[str, str]] = []
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.S,
    )

    for match in pattern.finditer(html):
        title = re.sub(r"<.*?>", "", match.group("title")).strip()
        snippet = re.sub(r"<.*?>", "", match.group("snippet")).strip()
        link = match.group("link").strip()
        if title:
            results.append(
                {
                    "title": title,
                    "snippet": snippet or "无法获取",
                    "link": link,
                    "source": "DuckDuckGo",
                }
            )
        if len(results) >= 5:
            break

    return results


def get_realtime_search_context(user_text: str, mode: str) -> str:
    """获取本轮实时搜索上下文，并做模式内缓存。"""
    if not should_trigger_realtime_search(user_text):
        return "本轮未触发实时搜索。"

    search_query = (
        f"小红书 {user_text} 爆款"
        if mode == "personal"
        else f"小红书 {user_text} 行业案例 爆款"
    )

    mode_cache_key = get_mode_key(mode, "search_cache")
    search_cache = st.session_state.get(mode_cache_key, {})
    if search_query in search_cache:
        return format_search_context(search_cache[search_query])

    results = search_hot_posts(search_query)
    search_cache[search_query] = results
    st.session_state[mode_cache_key] = search_cache

    if results:
        log_runtime(f"{MODE_META[mode]['label']}补充了 {len(results)} 条实时搜索线索。")
    else:
        log_runtime(f"{MODE_META[mode]['label']}本轮没有抓到可用实时搜索结果。")
    return format_search_context(results)


def call_chat_model(
    api_key: str,
    model_config: Dict[str, Any],
    selected_model: str,
    mode: str,
    user_text: str,
    rules_text: str,
    references_text: str,
    search_context: str,
) -> str:
    """调用聊天模型。"""
    if not api_key.strip():
        raise RuntimeError("请先在侧边栏为当前模型填写 API Key。")

    model_info = get_selected_model_info(model_config, selected_model)
    api_url = str(model_info.get("api_base") or model_info.get("api_url", "")).strip()
    model_name = str(model_info.get("model") or model_info.get("model_name", "")).strip()

    if api_url.endswith("/"):
        api_url = f"{api_url}chat/completions"

    if not api_url or not model_name:
        raise RuntimeError("当前选中模型配置不完整，请检查 config/models.json。")

    payload = {
        "model": model_name,
        "messages": build_model_payload(mode, user_text, rules_text, references_text, search_context),
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
    """渲染工作/个人模式切换。"""
    st.subheader("模式切换")
    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "工作模式",
            use_container_width=True,
            type="primary" if st.session_state.mode == "work" else "secondary",
        ):
            set_mode("work")
    with col2:
        if st.button(
            "个人模式",
            use_container_width=True,
            type="primary" if st.session_state.mode == "personal" else "secondary",
        ):
            set_mode("personal")

    st.caption(MODE_META[st.session_state.mode]["desc"])


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
        key="model_selectbox",
    )
    new_key = name_to_key[selected_name]
    if new_key != st.session_state.selected_model:
        st.session_state.selected_model = new_key
        sync_api_key_input_for_model()


def render_api_key_input(model_info: Dict[str, Any]) -> str:
    """渲染当前模型对应的 API Key 输入框。"""
    current_model = st.session_state.selected_model
    model_name = model_info.get("name", current_model)

    st.subheader("API Key")
    input_value = st.text_input(
        f"{model_name} API Key",
        key="api_key_input",
        type="password",
        placeholder="输入当前模型对应的 API Key",
    )

    st.session_state.manual_api_keys[current_model] = input_value.strip()
    return resolve_api_key(current_model, model_info)


def render_sidebar() -> str:
    """渲染侧边栏。"""
    with st.sidebar:
        st.title("助手配置")
        render_mode_switch()
        render_model_selector()

        selected_model_info = get_selected_model_info(
            st.session_state.model_config,
            st.session_state.selected_model,
        )
        active_api_key = render_api_key_input(selected_model_info)

        st.subheader("当前状态")
        st.markdown(
            f"""
- 当前模式：`{MODE_META[st.session_state.mode]['label']}`
- 当前模型：`{selected_model_info.get('name', st.session_state.selected_model)}`
- 参考拆解：`{len(st.session_state.deconstruction_results)}` 篇
- 规律报告：`已加载`
- API Key：`{'已填写' if active_api_key else '未填写'}`
"""
        )

        with st.expander("当前模式身份档案", expanded=False):
            st.text_area(
                "identity_preview",
                value=get_current_identity(st.session_state.mode),
                height=160,
                disabled=True,
                label_visibility="collapsed",
            )

        with st.expander("规律库摘要", expanded=False):
            st.text_area(
                "rules_summary",
                value=st.session_state.rules_summary,
                height=320,
                disabled=True,
                label_visibility="collapsed",
            )

        with st.expander("运行状态", expanded=False):
            runtime_logs = "\n".join(st.session_state.runtime_logs[-12:]) if st.session_state.runtime_logs else "暂无日志"
            st.text_area(
                "runtime_logs",
                value=runtime_logs,
                height=160,
                disabled=True,
                label_visibility="collapsed",
            )

    return active_api_key


def render_chat_history(mode: str) -> None:
    """渲染当前模式历史消息。"""
    for item in get_current_messages(mode):
        with st.chat_message("user" if item["role"] == "user" else "assistant"):
            st.markdown(item["content"])


def handle_identity_instruction(mode: str, user_text: str) -> bool:
    """处理身份更新指令。"""
    identity_update = parse_identity_update(user_text, mode)
    if not identity_update:
        return False

    target_mode, identity_text = identity_update
    if not identity_text:
        identity_text = user_text

    set_current_identity(target_mode, identity_text)
    result = build_identity_confirmation(target_mode, identity_text)
    append_mode_message(mode, "assistant", result)
    if target_mode == mode:
        save_mode_output(mode, result)
    log_runtime(f"{MODE_META[target_mode]['label']}身份档案已更新。")
    with st.chat_message("assistant"):
        st.markdown(result)
    return True


def handle_user_message(active_api_key: str) -> None:
    """处理用户输入。"""
    mode = st.session_state.mode
    user_text = st.chat_input("像聊天一样直接说：领导让我写一篇 XX 文案 / 我想做个账号 / 改标题 / 记住这个身份……")
    if not user_text:
        return

    append_mode_message(mode, "user", user_text)
    with st.chat_message("user"):
        st.markdown(user_text)

    if handle_identity_instruction(mode, user_text):
        return

    with st.chat_message("assistant"):
        with st.spinner("我先帮你判断方向，再整理成初稿..."):
            try:
                search_context = get_realtime_search_context(user_text, mode)
                result = call_chat_model(
                    api_key=active_api_key,
                    model_config=st.session_state.model_config,
                    selected_model=st.session_state.selected_model,
                    mode=mode,
                    user_text=user_text,
                    rules_text=st.session_state.rules_text,
                    references_text=st.session_state.references_text,
                    search_context=search_context,
                )
                st.markdown(result)
                append_mode_message(mode, "assistant", result)
                save_mode_output(mode, result)
            except Exception as exc:  # noqa: BLE001
                error_text = f"生成失败：{exc}"
                st.error(error_text)
                append_mode_message(mode, "assistant", error_text)
                log_runtime(error_text)


def main() -> None:
    """主入口。"""
    st.set_page_config(
        page_title="内容创作聊天助手",
        page_icon="🧠",
        layout="wide",
    )
    init_session_state()
    init_static_session_data()

    active_api_key = render_sidebar()

    mode = st.session_state.mode
    st.title("内容创作聊天助手")
    st.caption("像聊天一样输入任务或想法，系统会结合规律、样本和实时搜索，先判断方向，再给你可执行内容。")
    st.info(MODE_META[mode]["intro"])

    render_chat_history(mode)
    handle_user_message(active_api_key)


if __name__ == "__main__":
    main()
