import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
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

MODE_META = {
    "work": {
        "label": "工作模式",
        "session_prefix": "work",
        "intro": "你现在在【工作模式】。可以直接说：领导让我写一篇 XX 主题文案，或者帮我做一版能直接交付的策划。",
        "desc": "适合工作场景下的内容需求、文案撰写和日常沟通表达。",
    },
    "personal": {
        "label": "个人模式",
        "session_prefix": "personal",
        "intro": "你现在在【个人模式】。可以直接说：我想做个账号，我有什么资源、什么性格、什么时间安排。",
        "desc": "适合起号规划、内容方向、个人 IP、变现路径和长期内容策划。",
    },
}

SEARCH_KEYWORDS = ["最新", "最近", "这两天", "今天", "趋势", "爆款", "热门", "选题", "赛道"]

PROVIDER_DISPLAY_ORDER = ["openai_compatible", "deepseek", "zhipu"]
PROVIDER_LABELS = {
    "openai_compatible": "OpenAI",
    "deepseek": "DeepSeek",
    "zhipu": "质谱",
}
AUTO_DETECT_MODEL_ORDER = ["glm_4_flash", "deepseek_chat"]


@st.cache_data(show_spinner=False)
def read_text(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def load_prompt(file_name: str) -> str:
    file_path = PROMPTS_DIR / file_name
    if not file_path.exists():
        return ""
    return read_text(file_path)


@st.cache_data(show_spinner=False)
def load_model_config() -> Dict[str, Any]:
    config_path = CONFIG_DIR / "models.json"
    if not config_path.exists():
        return {"default_model": "deepseek_chat", "models": {}}
    return json.loads(read_text(config_path))


def save_model_config(model_config: Dict[str, Any]) -> None:
    config_path = CONFIG_DIR / "models.json"
    config_path.write_text(
        json.dumps(model_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    load_model_config.clear()
    read_text.clear()


def persist_default_model(model_key: str) -> None:
    model_config = st.session_state.get("model_config") or load_model_config()
    if model_config.get("default_model") == model_key:
        return
    model_config["default_model"] = model_key
    save_model_config(model_config)
    st.session_state.model_config = model_config


@st.cache_data(show_spinner=False)
def load_rules_report() -> str:
    if not RULES_FILE.exists():
        return "未找到规律汇总报告。"
    return read_text(RULES_FILE)


@st.cache_data(show_spinner=False)
def load_deconstruction_results() -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    if not DECONSTRUCT_DIR.exists():
        return results
    for file_path in sorted(DECONSTRUCT_DIR.glob("*.md")):
        results.append({"file_name": file_path.name, "content": read_text(file_path)})
    return results


@st.cache_data(show_spinner=False)
def build_rules_summary(report_text: str) -> str:
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
    digests: List[str] = []
    for item in results[:max_items]:
        digests.append(f"### 参考拆解：{item['file_name']}\n{item['content'][:1800]}")
    return "\n\n".join(digests)


def clean_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.strip())


def get_selected_model_info(model_config: Dict[str, Any], selected_model: str) -> Dict[str, Any]:
    return model_config.get("models", {}).get(selected_model, {})


def get_provider_key(model_info: Dict[str, Any]) -> str:
    return str(model_info.get("provider", "")).strip()


def get_provider_models(model_config: Dict[str, Any], provider_key: str) -> List[Tuple[str, Dict[str, Any]]]:
    provider_models: List[Tuple[str, Dict[str, Any]]] = []
    for model_key, model_info in model_config.get("models", {}).items():
        if not model_info.get("enabled", True):
            continue
        if get_provider_key(model_info) == provider_key:
            provider_models.append((model_key, model_info))
    return provider_models


def get_provider_api_key_from_config(model_config: Dict[str, Any], model_key: str) -> str:
    model_info = get_selected_model_info(model_config, model_key)
    provider_key = get_provider_key(model_info)
    if not provider_key:
        return str(model_info.get("api_key", "")).strip()
    for _sibling_model_key, sibling_info in get_provider_models(model_config, provider_key):
        api_key = str(sibling_info.get("api_key", "")).strip()
        if api_key:
            return api_key
    return ""


def sync_provider_api_key_in_config(model_config: Dict[str, Any], model_key: str, api_key: str) -> Dict[str, Any]:
    models = model_config.get("models", {})
    model_info = models.get(model_key, {})
    provider_key = get_provider_key(model_info)
    normalized_key = api_key.strip()
    if not provider_key:
        if model_key in models:
            models[model_key]["api_key"] = normalized_key
        return model_config
    for sibling_model_key, _sibling_info in get_provider_models(model_config, provider_key):
        models[sibling_model_key]["api_key"] = normalized_key
    return model_config


def get_model_options(model_config: Dict[str, Any]) -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    for model_key, model_info in model_config.get("models", {}).items():
        if not model_info.get("enabled", True):
            continue
        options.append({"key": model_key, "name": model_info.get("name", model_key)})
    return options


def build_provider_display_options(model_config: Dict[str, Any]) -> List[Dict[str, str]]:
    grouped_items: List[Dict[str, str]] = []
    seen_providers = set()
    ordered_providers = list(PROVIDER_DISPLAY_ORDER)
    ordered_providers.extend(
        [
            get_provider_key(model_info)
            for _model_key, model_info in model_config.get("models", {}).items()
            if model_info.get("enabled", True) and get_provider_key(model_info) not in PROVIDER_DISPLAY_ORDER
        ]
    )
    for provider_key in ordered_providers:
        if not provider_key or provider_key in seen_providers:
            continue
        provider_models = get_provider_models(model_config, provider_key)
        if not provider_models:
            continue
        display_names = [str(item[1].get("label") or item[1].get("name") or item[0]) for item in provider_models]
        grouped_items.append(
            {
                "key": provider_models[0][0],
                "provider": provider_key,
                "name": f"{PROVIDER_LABELS.get(provider_key, provider_key)}（{' / '.join(display_names)}）",
            }
        )
        seen_providers.add(provider_key)
    return grouped_items


def resolve_api_key(model_key: str, model_info: Dict[str, Any]) -> str:
    manual_api_keys = st.session_state.get("manual_api_keys", {})
    provider_key = get_provider_key(model_info)
    if provider_key:
        for sibling_model_key, _sibling_info in get_provider_models(st.session_state.model_config, provider_key):
            manual_key = str(manual_api_keys.get(sibling_model_key, "")).strip()
            if manual_key:
                return manual_key
        return get_provider_api_key_from_config(st.session_state.model_config, model_key)
    manual_key = str(manual_api_keys.get(model_key, "")).strip()
    if manual_key:
        return manual_key
    return str(model_info.get("api_key", "")).strip()


def persist_model_api_key(model_key: str, api_key: str) -> None:
    model_config = st.session_state.get("model_config") or load_model_config()
    models = model_config.get("models", {})
    if model_key not in models:
        return
    normalized_key = api_key.strip()
    current_key = get_provider_api_key_from_config(model_config, model_key)
    if current_key == normalized_key:
        return
    sync_provider_api_key_in_config(model_config, model_key, normalized_key)
    save_model_config(model_config)
    st.session_state.model_config = model_config
    provider_key = get_provider_key(models[model_key])
    if provider_key:
        for sibling_model_key, _sibling_info in get_provider_models(model_config, provider_key):
            st.session_state.manual_api_keys[sibling_model_key] = normalized_key


def verify_api_key_with_model(api_key: str, model_info: Dict[str, Any]) -> bool:
    api_url = str(model_info.get("api_base") or model_info.get("api_url", "")).strip()
    model_name = str(model_info.get("model") or model_info.get("model_name", "")).strip()
    if api_url.endswith("/"):
        api_url = f"{api_url}chat/completions"
    if not api_url or not model_name or not api_key.strip():
        return False
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "temperature": 0,
        "max_tokens": 5,
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
        with request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        content = str(data.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
        return bool(content)
    except Exception:
        return False


def detect_model_by_real_verification(
    api_key: str,
    model_config: Dict[str, Any],
    verify_func: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
) -> Tuple[Optional[str], bool]:
    normalized_key = api_key.strip()
    if not normalized_key:
        return None, False
    verifier = verify_func or verify_api_key_with_model
    for model_key in AUTO_DETECT_MODEL_ORDER:
        model_info = get_selected_model_info(model_config, model_key)
        if not model_info or not model_info.get("enabled", True):
            continue
        if verifier(normalized_key, model_info):
            return model_key, False
    return None, True


def get_model_display_name(model_key: str) -> str:
    model_info = get_selected_model_info(st.session_state.model_config, model_key)
    return str(model_info.get("name", model_key))


def get_mode_prefix(mode: str) -> str:
    return MODE_META[mode]["session_prefix"]


def get_mode_key(mode: str, suffix: str) -> str:
    return f"{get_mode_prefix(mode)}_{suffix}"


def ensure_mode_state(mode: str) -> None:
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
    if "mode" not in st.session_state:
        st.session_state.mode = "work"
    if "manual_api_keys" not in st.session_state:
        st.session_state.manual_api_keys = {}
    if "runtime_logs" not in st.session_state:
        st.session_state.runtime_logs = []
    if "api_key_status" not in st.session_state:
        st.session_state.api_key_status = ""
    if "api_key_requires_manual_selection" not in st.session_state:
        st.session_state.api_key_requires_manual_selection = False
    ensure_mode_state("work")
    ensure_mode_state("personal")


def init_static_session_data() -> None:
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
    if "provider_display_options" not in st.session_state:
        st.session_state.provider_display_options = build_provider_display_options(st.session_state.model_config)

    valid_keys = [item["key"] for item in st.session_state.model_options]
    default_model = st.session_state.model_config.get("default_model", "deepseek_chat")
    if "selected_model" not in st.session_state or st.session_state.selected_model not in valid_keys:
        st.session_state.selected_model = default_model if default_model in valid_keys else valid_keys[0]

    for model_option in st.session_state.model_options:
        model_key = model_option["key"]
        model_info = get_selected_model_info(st.session_state.model_config, model_key)
        config_key = get_provider_api_key_from_config(st.session_state.model_config, model_key)
        current_manual = str(st.session_state.manual_api_keys.get(model_key, "")).strip()
        if config_key and current_manual != config_key:
            st.session_state.manual_api_keys[model_key] = config_key
        elif model_key not in st.session_state.manual_api_keys:
            st.session_state.manual_api_keys[model_key] = config_key

    if "api_key_input" not in st.session_state:
        current_model = st.session_state.selected_model
        current_info = get_selected_model_info(st.session_state.model_config, current_model)
        st.session_state.api_key_input = resolve_api_key(current_model, current_info)


def log_runtime(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    logs = st.session_state.get("runtime_logs", [])
    logs.append(f"[{timestamp}] {message}")
    st.session_state.runtime_logs = logs[-20:]


def sync_api_key_input_for_model() -> None:
    current_model = st.session_state.selected_model
    current_info = get_selected_model_info(st.session_state.model_config, current_model)
    st.session_state.api_key_input = resolve_api_key(current_model, current_info)


def set_mode(mode: str) -> None:
    if st.session_state.mode != mode:
        st.session_state.mode = mode


def get_current_messages(mode: str) -> List[Dict[str, str]]:
    return st.session_state[get_mode_key(mode, "messages")]


def get_current_draft_history(mode: str) -> List[str]:
    return st.session_state[get_mode_key(mode, "draft_history")]


def get_current_latest_output(mode: str) -> str:
    return st.session_state[get_mode_key(mode, "latest_output")]


def get_current_identity(mode: str) -> str:
    return st.session_state[get_mode_key(mode, "identity")]


def set_current_identity(mode: str, identity_text: str) -> None:
    st.session_state[get_mode_key(mode, "identity")] = identity_text.strip()


def append_mode_message(mode: str, role: str, content: str) -> None:
    messages = get_current_messages(mode)
    messages.append({"role": role, "content": content})
    st.session_state[get_mode_key(mode, "messages")] = messages


def save_mode_output(mode: str, output_text: str) -> None:
    st.session_state[get_mode_key(mode, "latest_output")] = output_text
    draft_history = get_current_draft_history(mode)
    draft_history.append(output_text)
    st.session_state[get_mode_key(mode, "draft_history")] = draft_history[-20:]


def is_edit_request(user_text: str) -> bool:
    keywords = ["改标题", "换开头", "改开头", "缩短", "压缩", "重写", "拼一个", "融合", "合并", "像我一点", "太官方", "这个可以吗", "再来一版", "优化一个"]
    return any(keyword in user_text for keyword in keywords)


def should_trigger_realtime_search(user_text: str) -> bool:
    return any(keyword in user_text for keyword in SEARCH_KEYWORDS)


def parse_identity_update(user_text: str, current_mode: str) -> Optional[Tuple[str, str]]:
    normalized = user_text.strip()
    if "记住这个身份" in normalized or "记住我的身份" in normalized:
        return current_mode, normalized.replace("记住这个身份", "").replace("记住我的身份", "").strip("：: ")

    mode_prefix_map = {"工作模式": "work", "个人模式": "personal"}
    for text_prefix, mode in mode_prefix_map.items():
        patterns = [
            rf"^{text_prefix}[:： ]*(.*)$",
            rf"^{text_prefix}[：: ]*我是(.*)$",
            rf"^{text_prefix}的定位改一下[:： ]*(.*)$",
            rf"^{text_prefix}记住[：: ]*(.*)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, normalized)
            if match:
                return mode, match.group(1).strip()

    if normalized.startswith("我是") and ("记住" in normalized or "以后按这个" in normalized):
        return current_mode, normalized
    return None


def build_identity_confirmation(mode: str, identity_text: str) -> str:
    mode_label = MODE_META[mode]["label"]
    return (
        f"已记住你的{mode_label}身份设定。\n\n"
        f"**当前身份档案**\n{identity_text}\n\n"
        "后面在这个模式下，我都会默认按这套身份理解你来给建议。"
    )


def build_system_prompt(mode: str, identity_text: str) -> str:
    system_file = "system_work.md" if mode == "work" else "system_personal.md"
    task_file = "task_work_delivery.md" if mode == "work" else "task_personal_startup.md"
    blocks = [
        load_prompt(system_file),
        load_prompt(task_file),
        load_prompt("task_iterate_edit.md"),
        f"当前模式身份档案：\n{identity_text}",
    ]
    return "\n\n".join([block for block in blocks if block]).strip()


def format_search_context(search_items: List[Dict[str, str]]) -> str:
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
    latest_output = get_current_latest_output(mode)
    return latest_output[:2500] if latest_output else "暂无"


def build_user_prompt(
    user_text: str,
    mode: str,
    rules_text: str,
    references_text: str,
    search_context: str,
) -> str:
    mode_name = MODE_META[mode]["label"]
    edit_hint = (
        "这是一轮连续修改请求，请优先在已确认方向上做局部迭代，不要整篇推翻重来。"
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
"""
    )


def build_model_payload(
    mode: str,
    user_text: str,
    rules_text: str,
    references_text: str,
    search_context: str,
) -> List[Dict[str, str]]:
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
    except Exception:
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
            results.append({"title": title, "snippet": snippet or "无法获取", "link": link, "source": "DuckDuckGo"})
        if len(results) >= 5:
            break
    return results


def get_realtime_search_context(user_text: str, mode: str) -> str:
    if not should_trigger_realtime_search(user_text):
        return "本轮未触发实时搜索。"
    search_query = f"小红书 {user_text} 爆款" if mode == "personal" else f"小红书 {user_text} 行业案例 爆款"
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
    if not api_key.strip():
        raise RuntimeError("请先在侧边栏填写当前平台的 API Key。")
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
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key.strip()}"}
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
    st.subheader("模式切换")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("工作模式", use_container_width=True, type="primary" if st.session_state.mode == "work" else "secondary"):
            set_mode("work")
    with col2:
        if st.button("个人模式", use_container_width=True, type="primary" if st.session_state.mode == "personal" else "secondary"):
            set_mode("personal")
    st.caption(MODE_META[st.session_state.mode]["desc"])


def render_model_selector() -> None:
    st.subheader("模型选择")
    options = st.session_state.model_options
    provider_options = st.session_state.provider_display_options
    provider_by_model = {}
    for provider_option in provider_options:
        provider_models = get_provider_models(st.session_state.model_config, provider_option["provider"])
        for model_key, _model_info in provider_models:
            provider_by_model[model_key] = provider_option["name"]

    provider_labels = [item["name"] for item in provider_options]
    current_provider_label = provider_by_model.get(st.session_state.selected_model, provider_labels[0] if provider_labels else "")
    if provider_labels:
        selected_provider_label = st.selectbox(
            "选择平台",
            options=provider_labels,
            index=provider_labels.index(current_provider_label),
            label_visibility="collapsed",
            key="provider_selectbox",
        )
        selected_provider = next(item for item in provider_options if item["name"] == selected_provider_label)
        provider_models = get_provider_models(st.session_state.model_config, selected_provider["provider"])
        model_name_to_key = {
            str(model_info.get("label") or model_info.get("name") or model_key): model_key
            for model_key, model_info in provider_models
        }
        model_labels = list(model_name_to_key.keys())
        current_model_label = next(
            (label for label, key in model_name_to_key.items() if key == st.session_state.selected_model),
            model_labels[0],
        )
        selected_model_label = st.selectbox(
            "选择模型",
            options=model_labels,
            index=model_labels.index(current_model_label),
            key="model_selectbox",
        )
        new_key = model_name_to_key[selected_model_label]
        if new_key != st.session_state.selected_model:
            st.session_state.selected_model = new_key
            sync_api_key_input_for_model()
            if st.session_state.api_key_requires_manual_selection:
                persist_default_model(new_key)


def render_api_key_input(model_info: Dict[str, Any]) -> str:
    current_model = st.session_state.selected_model
    model_name = model_info.get("name", current_model)
    current_saved_key = resolve_api_key(current_model, model_info)
    expander_title = f"API Key（{'已配置' if current_saved_key else '未配置'}）"
    with st.expander(expander_title, expanded=False):
        col_input, col_action = st.columns([5, 1])
        with col_input:
            input_value = st.text_input(
                f"{model_name} API Key",
                key="api_key_input",
                type="password",
                placeholder="直接粘贴 OpenAI 格式 API Key，系统会先自动验证平台",
                label_visibility="collapsed",
            )
        with col_action:
            clear_clicked = st.button("清除", key=f"clear_api_key_{current_model}", use_container_width=True)

        if clear_clicked:
            provider_key = get_provider_key(model_info)
            for sibling_model_key, _sibling_info in get_provider_models(st.session_state.model_config, provider_key):
                st.session_state.manual_api_keys[sibling_model_key] = ""
            persist_model_api_key(current_model, "")
            st.session_state.api_key_input = ""
            st.session_state.api_key_status = f"已清除 {PROVIDER_LABELS.get(provider_key, model_name)} 平台的 API Key"
            st.session_state.api_key_requires_manual_selection = False
            return ""

        normalized_input = input_value.strip()
        if not normalized_input:
            provider_key = get_provider_key(model_info)
            for sibling_model_key, _sibling_info in get_provider_models(st.session_state.model_config, provider_key):
                st.session_state.manual_api_keys[sibling_model_key] = ""
            persist_model_api_key(current_model, "")
            st.session_state.api_key_status = ""
            st.session_state.api_key_requires_manual_selection = False
            return resolve_api_key(current_model, model_info)

        if st.session_state.api_key_requires_manual_selection:
            provider_key = get_provider_key(model_info)
            for sibling_model_key, _sibling_info in get_provider_models(st.session_state.model_config, provider_key):
                st.session_state.manual_api_keys[sibling_model_key] = normalized_input
            persist_model_api_key(current_model, normalized_input)
            persist_default_model(current_model)
            st.session_state.api_key_status = f"已按你手动选择的模型保存到 {PROVIDER_LABELS.get(provider_key, provider_key)} 平台"
            return resolve_api_key(current_model, model_info)

        detected_model, requires_manual = detect_model_by_real_verification(normalized_input, st.session_state.model_config)
        if detected_model:
            detected_info = get_selected_model_info(st.session_state.model_config, detected_model)
            detected_provider = get_provider_key(detected_info)
            for sibling_model_key, _sibling_info in get_provider_models(st.session_state.model_config, detected_provider):
                st.session_state.manual_api_keys[sibling_model_key] = normalized_input
            persist_model_api_key(detected_model, normalized_input)
            if st.session_state.selected_model != detected_model:
                st.session_state.selected_model = detected_model
                sync_api_key_input_for_model()
            persist_default_model(detected_model)
            st.session_state.api_key_requires_manual_selection = False
            st.session_state.api_key_status = f"已自动验证成功，当前 Key 属于：{PROVIDER_LABELS.get(detected_provider, detected_provider)}"
            return resolve_api_key(detected_model, detected_info)

        provider_key = get_provider_key(model_info)
        for sibling_model_key, _sibling_info in get_provider_models(st.session_state.model_config, provider_key):
            st.session_state.manual_api_keys[sibling_model_key] = normalized_input
        st.session_state.api_key_requires_manual_selection = True
        st.session_state.api_key_status = "无法识别，请手动选择模型。选择后系统将按你选的平台直接保存并使用该 Key。"
        return normalized_input


def render_sidebar() -> str:
    with st.sidebar:
        st.title("助手配置")
        render_mode_switch()
        render_model_selector()
        selected_model_info = get_selected_model_info(st.session_state.model_config, st.session_state.selected_model)
        active_api_key = render_api_key_input(selected_model_info)
        selected_model_info = get_selected_model_info(st.session_state.model_config, st.session_state.selected_model)

        if st.session_state.api_key_status:
            if "无法识别" in st.session_state.api_key_status:
                st.warning(st.session_state.api_key_status)
            else:
                st.success(st.session_state.api_key_status)

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
            st.text_area("identity_preview", value=get_current_identity(st.session_state.mode), height=160, disabled=True, label_visibility="collapsed")
        with st.expander("规律库摘要", expanded=False):
            st.text_area("rules_summary", value=st.session_state.rules_summary, height=320, disabled=True, label_visibility="collapsed")
        with st.expander("运行状态", expanded=False):
            runtime_logs = "\n".join(st.session_state.runtime_logs[-12:]) if st.session_state.runtime_logs else "暂无日志"
            st.text_area("runtime_logs", value=runtime_logs, height=160, disabled=True, label_visibility="collapsed")
    return active_api_key


def render_chat_history(mode: str) -> None:
    for item in get_current_messages(mode):
        if item["role"] == "user":
            left_col, right_col = st.columns([1, 1.4])
            with right_col:
                st.markdown(
                    f"""
<div style="
    background:#2e7d32;
    color:white;
    padding:10px 14px;
    border-radius:16px;
    margin:6px 0 6px auto;
    width:fit-content;
    max-width:100%;
    font-size:14px;
    line-height:1.6;
    box-shadow:0 1px 2px rgba(0,0,0,.08);
">
{item["content"]}
</div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            left_col, right_col = st.columns([1.4, 1])
            with left_col:
                st.markdown(
                    f"""
<div style="
    background:#f3f5f7;
    color:#1f2937;
    padding:10px 14px;
    border-radius:16px;
    margin:6px auto 6px 0;
    width:fit-content;
    max-width:100%;
    font-size:14px;
    line-height:1.6;
    box-shadow:0 1px 2px rgba(0,0,0,.08);
">
{item["content"]}
</div>
                    """,
                    unsafe_allow_html=True,
                )


def handle_identity_instruction(mode: str, user_text: str) -> bool:
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
    mode = st.session_state.mode
    user_text = st.chat_input("像聊天一样直接说：领导让我写一篇 XX 文案 / 我想做个账号 / 改标题 / 记住这个身份…")
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
            except Exception as exc:
                error_text = f"生成失败：{exc}"
                st.error(error_text)
                append_mode_message(mode, "assistant", error_text)
                log_runtime(error_text)


def main() -> None:
    st.set_page_config(page_title="内容创作聊天助手", page_icon="📝", layout="wide")
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
