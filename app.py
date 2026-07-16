import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib import error, request

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system.md"

DEFAULT_MODEL_CONFIG: Dict[str, Any] = {
    "default_model": "deepseek_chat",
    "models": {
        "deepseek_chat": {
            "name": "DeepSeek",
            "provider": "deepseek",
            "api_base": "https://api.deepseek.com/chat/completions",
            "model": "deepseek-chat",
            "api_key": "",
            "enabled": True,
        },
        "glm_4_flash": {
            "name": "智谱 GLM-4-Flash",
            "provider": "zhipu",
            "api_base": "https://open.bigmodel.cn/api/paas/v4/",
            "model": "glm-4-flash",
            "api_key": "",
            "enabled": True,
        },
        "gpt_4o": {
            "name": "GPT-4o",
            "provider": "openai_compatible",
            "api_base": "https://api.openai.com/v1/",
            "model": "gpt-4o",
            "api_key": "",
            "enabled": True,
        },
    },
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg-0: #f5f7fb;
            --bg-1: #eef2f7;
            --panel: rgba(255, 255, 255, 0.96);
            --panel-strong: rgba(255, 255, 255, 1);
            --border: rgba(24, 31, 54, 0.08);
            --text-main: rgba(19, 24, 39, 0.96);
            --text-sub: rgba(19, 24, 39, 0.76);
            --text-muted: rgba(19, 24, 39, 0.54);
            --shadow: 0 18px 50px rgba(20, 28, 48, 0.08);
        }

        html, body, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main {
            min-height: 100%;
            background: linear-gradient(145deg, var(--bg-0) 0%, var(--bg-1) 100%);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid rgba(24, 31, 54, 0.08);
        }

        [data-testid="stSidebar"] > div:first-child {
            margin: 12px;
            border-radius: 18px;
            padding: 10px 12px 14px 12px;
            background: rgba(245, 247, 251, 0.88);
            border: 1px solid rgba(24, 31, 54, 0.08);
            box-shadow: 0 10px 26px rgba(20, 28, 48, 0.05);
        }

        .main .block-container {
            max-width: 1200px;
            padding-top: 2rem;
            padding-bottom: 7.5rem;
            color: var(--text-main);
        }

        .main .block-container h1,
        .main .block-container h2,
        .main .block-container h3,
        .main .block-container p,
        .main .block-container span,
        .main .block-container div {
            color: var(--text-main);
        }

        .hero-shell {
            border-radius: 22px;
            background: rgba(255, 255, 255, 0.98);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            padding: 1.55rem 1.55rem 1.15rem 1.55rem;
            margin-bottom: 1.1rem;
        }

        .hero-shell *,
        .hero-shell h1,
        .hero-shell p,
        .hero-shell div {
            color: var(--text-main) !important;
        }

        .hero-kicker {
            color: var(--text-muted) !important;
            font-size: 0.78rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            margin-bottom: 0.4rem;
        }

        .hero-title {
            color: var(--text-main) !important;
            font-size: clamp(2rem, 4vw, 3rem);
            line-height: 1.05;
            font-weight: 800;
            letter-spacing: -0.04em;
            margin: 0 0 0.45rem 0;
        }

        .hero-subtitle {
            color: var(--text-sub) !important;
            font-size: 1rem;
            line-height: 1.65;
            max-width: 52rem;
            margin: 0;
        }

        .welcome-panel {
            margin-top: 0.9rem;
            padding: 1rem 1.1rem 1.05rem 1.1rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.98);
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
        }

        .welcome-title {
            margin: 0 0 0.35rem 0;
            font-size: 1.02rem;
            font-weight: 700;
            color: var(--text-main);
        }

        .welcome-copy {
            margin: 0;
            color: var(--text-sub);
            line-height: 1.6;
            font-size: 0.94rem;
        }

        .welcome-pills {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin-top: 0.85rem;
        }

        .welcome-pill {
            padding: 0.42rem 0.7rem;
            border-radius: 999px;
            background: #f5f7fb;
            border: 1px solid rgba(24, 31, 54, 0.08);
            color: var(--text-sub);
            font-size: 0.82rem;
        }

        .empty-hint {
            margin-top: 0.9rem;
            padding: 0.95rem 1rem;
            border-radius: 16px;
            border: 1px dashed rgba(24, 31, 54, 0.14);
            background: rgba(255, 255, 255, 0.96);
            color: var(--text-sub) !important;
        }

        [data-testid="stChatMessage"] {
            border-radius: 16px;
            padding: 0.12rem 0.18rem;
            margin-bottom: 0.8rem;
        }

        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
            color: var(--text-main);
        }

        [data-testid="stChatMessage"]:has([aria-label="user"]) {
            display: flex;
            justify-content: flex-end;
        }

        [data-testid="stChatMessage"]:has([aria-label="assistant"]) {
            display: flex;
            justify-content: flex-start;
        }

        [data-testid="stChatMessage"]:has([aria-label="user"]) > div {
            max-width: min(78%, 820px);
            border-radius: 16px;
            background: #ffffff;
            border: 1px solid rgba(24, 31, 54, 0.08);
            padding: 0.92rem 1rem;
            box-shadow: 0 12px 28px rgba(20, 28, 48, 0.08);
        }

        [data-testid="stChatMessage"]:has([aria-label="assistant"]) > div {
            max-width: min(78%, 820px);
            border-radius: 16px;
            background: #ffffff;
            border: 1px solid rgba(24, 31, 54, 0.08);
            padding: 0.92rem 1rem;
            box-shadow: 0 12px 28px rgba(20, 28, 48, 0.08);
        }

        [data-testid="stChatMessageUser"] {
            display: flex !important;
            justify-content: flex-end !important;
        }

        [data-testid="stChatMessageAssistant"] {
            display: flex !important;
            justify-content: flex-start !important;
        }

        [data-testid="stChatMessageUser"] div {
            max-width: 80% !important;
            background: #ffffff !important;
            border: 1px solid rgba(24, 31, 54, 0.08) !important;
            border-radius: 16px !important;
            padding: 12px 18px !important;
            box-shadow: 0 12px 28px rgba(20, 28, 48, 0.08);
        }

        [data-testid="stChatMessageAssistant"] div {
            max-width: 80% !important;
            background: #ffffff !important;
            border: 1px solid rgba(24, 31, 54, 0.08) !important;
            border-radius: 16px !important;
            padding: 12px 18px !important;
            box-shadow: 0 12px 28px rgba(20, 28, 48, 0.08);
        }

        [data-testid="stChatInput"] {
            background: rgba(255, 255, 255, 0.98);
            border-top: 1px solid rgba(24, 31, 54, 0.08);
        }

        [data-testid="stChatInput"] textarea {
            border-radius: 14px !important;
        }

        [data-testid="stChatInput"] textarea:focus {
            border: 1px solid rgba(140, 167, 255, 0.75) !important;
            box-shadow: 0 0 0 1px rgba(140, 167, 255, 0.2), 0 0 0 4px rgba(140, 167, 255, 0.08) !important;
        }

        [data-testid="stTextInput"] input,
        [data-testid="stSelectbox"] [role="combobox"] {
            border-radius: 12px !important;
            background: #ffffff !important;
            border-color: rgba(24, 31, 54, 0.12) !important;
            color: var(--text-main) !important;
        }

        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] span {
            color: var(--text-main);
        }

        [data-testid="stSidebar"] .stExpander {
            border-radius: 14px;
            border: 1px solid rgba(24, 31, 54, 0.08);
            background: rgba(255, 255, 255, 0.96);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def read_text(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8-sig")


def load_model_config() -> Dict[str, Any]:
    config_path = CONFIG_DIR / "models.json"
    if not config_path.exists():
        data = json.loads(json.dumps(DEFAULT_MODEL_CONFIG, ensure_ascii=False))
        data["saved_configs"] = []
        return data
    try:
        data = json.loads(read_text(config_path))
    except (OSError, json.JSONDecodeError):
        data = json.loads(json.dumps(DEFAULT_MODEL_CONFIG, ensure_ascii=False))
    if "saved_configs" not in data or not isinstance(data.get("saved_configs"), list):
        data["saved_configs"] = []
    return data


def save_model_config_to_disk(model_config: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_path = CONFIG_DIR / "models.json"
    payload = json.loads(json.dumps(model_config, ensure_ascii=False))
    if "saved_configs" not in payload or not isinstance(payload.get("saved_configs"), list):
        payload["saved_configs"] = []
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_selected_model_info(model_config: Dict[str, Any], selected_model: str) -> Dict[str, Any]:
    return model_config.get("models", {}).get(selected_model, {})


def get_model_options(model_config: Dict[str, Any]) -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    for model_key, model_info in model_config.get("models", {}).items():
        if model_info.get("enabled", True):
            options.append({"key": model_key, "name": str(model_info.get("name", model_key))})
    return options


def get_saved_configs(model_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    saved_configs = model_config.get("saved_configs", [])
    if isinstance(saved_configs, list):
        return [item for item in saved_configs if isinstance(item, dict) and item.get("id")]
    return []


def generate_saved_config_name(saved_configs: List[Dict[str, Any]]) -> str:
    existing_names = {str(item.get("name", "")).strip() for item in saved_configs}
    index = 1
    while True:
        candidate = f"配置{index}"
        if candidate not in existing_names:
            return candidate
        index += 1


def make_saved_config_record(name: str, api_key: str, api_base: str, model_name: str) -> Dict[str, str]:
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    return {
        "id": uuid.uuid4().hex,
        "name": name,
        "api_key": api_key,
        "api_base": api_base,
        "model": model_name,
        "created_at": timestamp,
    }


def get_saved_config_by_id(model_config: Dict[str, Any], config_id: str) -> Optional[Dict[str, Any]]:
    for item in get_saved_configs(model_config):
        if str(item.get("id", "")).strip() == str(config_id).strip():
            return item
    return None


def apply_saved_config_to_session_state(saved_config: Dict[str, Any]) -> None:
    if "saved_config_selector" not in st.session_state:
        st.session_state.saved_config_selector = ""
    if "saved_configs" not in st.session_state:
        st.session_state.saved_configs = []
    if "current_config_name" not in st.session_state:
        st.session_state.current_config_name = ""
    if "saved_config_name_input" not in st.session_state:
        st.session_state.saved_config_name_input = ""
    if "applied_saved_config_id" not in st.session_state:
        st.session_state.applied_saved_config_id = ""

    st.session_state.api_key_input = str(saved_config.get("api_key", "")).strip()
    st.session_state.api_base_input = str(saved_config.get("api_base", "")).strip()
    st.session_state.custom_model_name = str(saved_config.get("model", "")).strip()
    st.session_state.saved_config_name_input = str(saved_config.get("name", "")).strip()
    st.session_state.current_config_name = str(saved_config.get("name", "")).strip()
    st.session_state.saved_config_selector = str(saved_config.get("id", "")).strip()
    st.session_state.applied_saved_config_id = str(saved_config.get("id", "")).strip()


def persist_saved_config(model_config: Dict[str, Any], saved_config: Dict[str, Any]) -> Dict[str, Any]:
    updated_config = json.loads(json.dumps(model_config, ensure_ascii=False))
    saved_configs = get_saved_configs(updated_config)
    saved_configs.append(saved_config)
    updated_config["saved_configs"] = saved_configs
    save_model_config_to_disk(updated_config)
    return updated_config


def update_saved_config(model_config: Dict[str, Any], saved_config: Dict[str, Any]) -> Dict[str, Any]:
    updated_config = json.loads(json.dumps(model_config, ensure_ascii=False))
    saved_configs = get_saved_configs(updated_config)
    target_id = str(saved_config.get("id", "")).strip()
    next_saved_configs: List[Dict[str, Any]] = []
    replaced = False
    for item in saved_configs:
        if str(item.get("id", "")).strip() == target_id:
            next_saved_configs.append(saved_config)
            replaced = True
        else:
            next_saved_configs.append(item)
    if not replaced:
        next_saved_configs.append(saved_config)
    updated_config["saved_configs"] = next_saved_configs
    save_model_config_to_disk(updated_config)
    return updated_config


def delete_saved_config(model_config: Dict[str, Any], config_id: str) -> Dict[str, Any]:
    updated_config = json.loads(json.dumps(model_config, ensure_ascii=False))
    saved_configs = [
        item
        for item in get_saved_configs(updated_config)
        if str(item.get("id", "")).strip() != str(config_id).strip()
    ]
    updated_config["saved_configs"] = saved_configs
    save_model_config_to_disk(updated_config)
    return updated_config


def resolve_api_key(model_key: str, model_info: Dict[str, Any]) -> str:
    manual_api_keys = st.session_state.get("manual_api_keys", {})
    manual_key = str(manual_api_keys.get(model_key, "")).strip()
    return manual_key or str(model_info.get("api_key", "")).strip()


def init_session_state() -> None:
    if "model_config" not in st.session_state:
        st.session_state.model_config = load_model_config()
    if "model_options" not in st.session_state:
        st.session_state.model_options = get_model_options(st.session_state.model_config)
    if "manual_api_keys" not in st.session_state:
        st.session_state.manual_api_keys = {}
    if "selected_model" not in st.session_state:
        valid_keys = [item["key"] for item in st.session_state.model_options]
        default_model = st.session_state.model_config.get("default_model", "deepseek_chat")
        st.session_state.selected_model = default_model if default_model in valid_keys else (valid_keys[0] if valid_keys else default_model)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_identity" not in st.session_state:
        st.session_state.current_identity = ""
    if "api_key_input" not in st.session_state:
        current_model = st.session_state.selected_model
        st.session_state.api_key_input = resolve_api_key(current_model, get_selected_model_info(st.session_state.model_config, current_model))
    if "api_base_input" not in st.session_state:
        st.session_state.api_base_input = ""
    if "custom_model_name" not in st.session_state:
        st.session_state.custom_model_name = str(st.session_state.get("model_name_input", "")).strip()
    if "saved_config_name_input" not in st.session_state:
        st.session_state.saved_config_name_input = ""
    if "saved_config_selector" not in st.session_state:
        st.session_state.saved_config_selector = ""
    if "saved_configs" not in st.session_state:
        st.session_state.saved_configs = []
    if "current_config_name" not in st.session_state:
        st.session_state.current_config_name = ""
    if "applied_saved_config_id" not in st.session_state:
        st.session_state.applied_saved_config_id = ""
    if "api_key_detect_status" not in st.session_state:
        st.session_state.api_key_detect_status = ""

    for model_option in st.session_state.model_options:
        model_key = model_option["key"]
        model_info = get_selected_model_info(st.session_state.model_config, model_key)
        config_key = str(model_info.get("api_key", "")).strip()
        current_manual = str(st.session_state.manual_api_keys.get(model_key, "")).strip()
        if config_key and current_manual != config_key:
            st.session_state.manual_api_keys[model_key] = config_key
        elif model_key not in st.session_state.manual_api_keys:
            st.session_state.manual_api_keys[model_key] = config_key


def detect_model_from_api_key(api_key: str, model_config: Dict[str, Any]) -> Optional[str]:
    normalized_key = api_key.strip()
    if not normalized_key:
        return None

    models = model_config.get("models", {})
    if normalized_key.startswith("sk-"):
        # 优先走 DeepSeek / OpenAI 兼容链路
        for model_key, model_info in models.items():
            if not model_info.get("enabled", True):
                continue
            provider = str(model_info.get("provider", "")).strip().lower()
            if provider in {"deepseek", "openai_compatible"}:
                return model_key
        return "deepseek_chat" if "deepseek_chat" in models else None

    for model_key, model_info in models.items():
        if not model_info.get("enabled", True):
            continue
        provider = str(model_info.get("provider", "")).strip().lower()
        if provider == "zhipu":
            return model_key
    return "glm_4_flash" if "glm_4_flash" in models else None


def get_detected_model_label(model_key: str, model_config: Dict[str, Any]) -> str:
    return str(get_selected_model_info(model_config, model_key).get("name", model_key))


def resolve_model_name(model_config: Dict[str, Any], selected_model: str) -> str:
    custom_model_name = str(st.session_state.get("custom_model_name", "")).strip()
    if custom_model_name:
        return custom_model_name

    model_info = get_selected_model_info(model_config, selected_model)
    provider = str(model_info.get("provider", "")).strip().lower()
    if provider == "openai_compatible":
        return "gpt-4.5"

    config_model_name = str(model_info.get("model") or model_info.get("model_name", "")).strip()
    if config_model_name:
        return config_model_name

    default_model_key = str(model_config.get("default_model", "")).strip()
    default_model_info = get_selected_model_info(model_config, default_model_key)
    return str(default_model_info.get("model") or default_model_info.get("model_name", "")).strip()


def infer_identity_from_user_text(user_text: str) -> None:
    normalized = user_text.strip()
    if "我是" in normalized and len(normalized) > 2:
        st.session_state.current_identity = normalized


def build_system_prompt() -> str:
    if SYSTEM_PROMPT_FILE.exists():
        return read_text(SYSTEM_PROMPT_FILE).strip()
    return "你是一个能干的助手。根据用户说的话，自然回应即可。不需要遵循任何预设流程，不需要套用任何模板。根据对话内容自己决定怎么帮用户，可以追问、可以直接给建议、可以写文案、可以做策划，完全看当时在聊什么。"


def build_messages(user_text: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [{"role": "system", "content": build_system_prompt()}]
    identity = str(st.session_state.get("current_identity", "")).strip()
    if identity:
        messages.append({"role": "system", "content": f"当前会话身份：{identity}"})
    messages.extend(st.session_state.messages[-16:])
    messages.append({"role": "user", "content": user_text})
    return messages


def call_chat_model(
    api_key: str,
    model_config: Dict[str, Any],
    selected_model: str,
    user_text: str,
) -> str:
    if not api_key.strip():
        raise RuntimeError("请先在侧边栏填写当前模型的 API Key。")

    model_info = get_selected_model_info(model_config, selected_model)
    api_url = str(st.session_state.get("api_base_input", "")).strip()
    if not api_url:
        api_url = str(model_info.get("api_base") or model_info.get("api_url", "")).strip()
    api_url = api_url.rstrip("/")
    if not api_url.endswith("chat/completions"):
        api_url = f"{api_url}/chat/completions"

    model_name = resolve_model_name(model_config, selected_model)
    if not api_url or not model_name:
        raise RuntimeError("当前选中模型配置不完整，请检查 config/models.json。")

    payload = {
        "model": model_name,
        "messages": build_messages(user_text),
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


def render_sidebar() -> str:
    with st.sidebar:
        st.title("⚡ 智能体")

        saved_configs = get_saved_configs(st.session_state.model_config)
        saved_config_ids = {str(item.get("id", "")).strip() for item in saved_configs}
        if st.session_state.get("saved_config_selector", "") not in saved_config_ids:
            st.session_state.saved_config_selector = ""
            st.session_state.applied_saved_config_id = ""

        with st.expander("📋 历史消息", expanded=True):
            if st.session_state.messages:
                for item in st.session_state.messages[-12:]:
                    role_label = "你" if item["role"] == "user" else "助手"
                    preview = str(item["content"]).strip().replace("\n", " ")
                    if len(preview) > 70:
                        preview = f"{preview[:70]}..."
                    st.caption(f"{role_label}：{preview}")
            else:
                st.caption("暂无历史消息")

        current_model = st.session_state.selected_model
        current_info = get_selected_model_info(st.session_state.model_config, current_model)

        st.caption(st.session_state.api_key_detect_status or "未连接")

        with st.expander("📁 已保存配置", expanded=True):
            if saved_configs:
                saved_options = [""] + [str(item.get("id", "")).strip() for item in saved_configs]

                def format_saved_config(option_id: str) -> str:
                    if not option_id:
                        return "请选择已保存配置"
                    saved_item = get_saved_config_by_id(st.session_state.model_config, option_id)
                    if not saved_item:
                        return "请选择已保存配置"
                    label = str(saved_item.get("name", option_id)).strip() or option_id
                    model_label = str(saved_item.get("model", "")).strip()
                    if model_label:
                        return f"{label}  ·  {model_label}"
                    return label

                selected_saved_id = st.selectbox(
                    "已保存配置",
                    options=saved_options,
                    key="saved_config_selector",
                    format_func=format_saved_config,
                )
                if selected_saved_id:
                    selected_saved = get_saved_config_by_id(st.session_state.model_config, selected_saved_id)
                    if selected_saved and selected_saved_id != st.session_state.get("applied_saved_config_id", ""):
                        apply_saved_config_to_session_state(selected_saved)

                for saved_item in saved_configs:
                    saved_id = str(saved_item.get("id", "")).strip()
                    saved_name = str(saved_item.get("name", saved_id)).strip() or saved_id
                    saved_model = str(saved_item.get("model", "")).strip() or "未填写模型"
                    col_left, col_right = st.columns([0.78, 0.22], vertical_alignment="center")
                    with col_left:
                        st.caption(f"{saved_name} · {saved_model}")
                    with col_right:
                        if st.button("删除", key=f"delete_saved_config_{saved_id}", use_container_width=True):
                            updated_config = delete_saved_config(st.session_state.model_config, saved_id)
                            st.session_state.model_config = updated_config
                            st.session_state.model_options = get_model_options(updated_config)
                            if str(st.session_state.get("saved_config_selector", "")).strip() == saved_id:
                                st.session_state.saved_config_selector = ""
                                st.session_state.applied_saved_config_id = ""
                            st.rerun()
            else:
                st.caption("暂无已保存配置")

        with st.expander("⚙️ 高级设置", expanded=False):
            api_key_input = st.text_input(
                "API Key",
                key="api_key_input",
                type="password",
                placeholder="直接粘贴密钥",
            )
            st.text_input(
                "API Base URL",
                key="api_base_input",
                placeholder="例如：https://artislg.com/api/v1",
                help="留空则使用当前模型配置中的默认地址",
            )
            st.text_input(
                "模型名称",
                key="custom_model_name",
                placeholder="例如：gpt-4.5",
                help="留空则使用自动识别到的默认模型名",
            )

            if "saved_config_name_input" not in st.session_state:
                st.session_state.saved_config_name_input = ""
            st.text_input(
                "配置名称",
                key="saved_config_name_input",
                placeholder="例如：工作配置",
                help="不填则自动生成名称",
            )
            if st.button("保存配置", use_container_width=True):
                current_name = str(st.session_state.get("saved_config_name_input", "")).strip()
                if not current_name:
                    current_name = generate_saved_config_name(saved_configs)
                current_api_key = str(st.session_state.get("api_key_input", "")).strip()
                current_api_base = str(st.session_state.get("api_base_input", "")).strip()
                current_model_name = str(st.session_state.get("custom_model_name", "")).strip()
                saved_record = make_saved_config_record(current_name, current_api_key, current_api_base, current_model_name)
                updated_config = persist_saved_config(st.session_state.model_config, saved_record)
                st.session_state.model_config = updated_config
                st.session_state.model_options = get_model_options(updated_config)
                st.session_state.saved_config_selector = str(saved_record["id"])
                st.session_state.applied_saved_config_id = str(saved_record["id"])
                st.session_state.saved_config_name_input = current_name
                st.rerun()

        normalized_input = api_key_input.strip()
        if not normalized_input:
            st.session_state.api_key_detect_status = ""
            st.session_state.manual_api_keys[current_model] = ""
        else:
            detected_model = detect_model_from_api_key(normalized_input, st.session_state.model_config)
            if detected_model:
                st.session_state.selected_model = detected_model
                st.session_state.manual_api_keys[detected_model] = normalized_input
                st.session_state.api_key_detect_status = f"已连接：{get_detected_model_label(detected_model, st.session_state.model_config)}"
                current_model = detected_model
                current_info = get_selected_model_info(st.session_state.model_config, current_model)
            else:
                st.session_state.manual_api_keys[current_model] = normalized_input
                st.session_state.api_key_detect_status = "未能识别该 Key，请手动选择模型和 Base URL"

        return resolve_api_key(current_model, current_info)


def render_chat_history() -> None:
    for item in st.session_state.messages:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])


def handle_user_message(active_api_key: str) -> None:
    user_text = st.chat_input("直接说吧")
    if not user_text:
        return

    infer_identity_from_user_text(user_text)
    st.session_state.messages.append({"role": "user", "content": user_text})

    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            try:
                result = call_chat_model(
                    api_key=active_api_key,
                    model_config=st.session_state.model_config,
                    selected_model=st.session_state.selected_model,
                    user_text=user_text,
                )
                st.markdown(result)
                st.session_state.messages.append({"role": "assistant", "content": result})
            except Exception as exc:  # noqa: BLE001
                error_text = f"生成失败：{exc}"
                st.error(error_text)
                st.session_state.messages.append({"role": "assistant", "content": error_text})


def main() -> None:
    st.set_page_config(
        page_title="自由对话助手",
        page_icon="💬",
        layout="wide",
    )
    init_session_state()
    inject_styles()

    active_api_key = render_sidebar()

    st.markdown(
        """
        <div class="hero-shell">
            <div class="hero-kicker">Free conversation</div>
            <h1 class="hero-title">自由对话助手</h1>
            <p class="hero-subtitle">像正常聊天一样直接说，系统会根据上下文自由回应。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.messages:
        st.markdown(
            """
            <div class="welcome-panel">
                <div class="welcome-title">准备好了，直接开聊</div>
                <p class="welcome-copy">这里没有模式切换，也没有固定模板。你可以直接问问题、让它写文案、做策划，或者先把 API Key 和 Base URL 配好再开始。</p>
                <div class="welcome-pills">
                    <span class="welcome-pill">直接对话</span>
                    <span class="welcome-pill">自由回复</span>
                    <span class="welcome-pill">会话独立</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="empty-hint">
                还没有历史消息。你可以直接在下方输入，或者先在左侧粘贴 API Key 和 Base URL。
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_chat_history()
    handle_user_message(active_api_key)


if __name__ == "__main__":
    main()
