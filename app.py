import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request

import streamlit as st


PROJECT_ROOT = Path(".")
CONFIG_DIR = PROJECT_ROOT / "config"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system.md"


def read_text(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8-sig")


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


def get_model_options(model_config: Dict[str, Any]) -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    for model_key, model_info in model_config.get("models", {}).items():
        if not model_info.get("enabled", True):
            continue
        options.append({"key": model_key, "name": model_info.get("name", model_key)})
    return options


def get_selected_model_info(model_config: Dict[str, Any], selected_model: str) -> Dict[str, Any]:
    return model_config.get("models", {}).get(selected_model, {})


def resolve_api_key(model_key: str, model_info: Dict[str, Any]) -> str:
    manual_api_keys = st.session_state.get("manual_api_keys", {})
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
    current_key = str(models[model_key].get("api_key", "")).strip()
    if current_key == normalized_key:
        return

    models[model_key]["api_key"] = normalized_key
    save_model_config(model_config)
    st.session_state.model_config = model_config


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
        st.session_state.selected_model = default_model if default_model in valid_keys else valid_keys[0]
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_identity" not in st.session_state:
        st.session_state.current_identity = ""
    if "api_key_input" not in st.session_state:
        current_model = st.session_state.selected_model
        current_info = get_selected_model_info(st.session_state.model_config, current_model)
        st.session_state.api_key_input = resolve_api_key(current_model, current_info)
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


def sync_api_key_input_for_model() -> None:
    current_model = st.session_state.selected_model
    current_info = get_selected_model_info(st.session_state.model_config, current_model)
    st.session_state.api_key_input = resolve_api_key(current_model, current_info)


def detect_model_from_api_key(api_key: str, model_config: Dict[str, Any]) -> Optional[str]:
    normalized_key = api_key.strip()
    if not normalized_key:
        return None

    models = model_config.get("models", {})
    if normalized_key.startswith("sk-"):
        for model_key, model_info in models.items():
            if not model_info.get("enabled", True):
                continue
            provider = str(model_info.get("provider", "")).strip().lower()
            if provider in {"deepseek", "openai_compatible"}:
                return model_key
        return None

    for model_key, model_info in models.items():
        if not model_info.get("enabled", True):
            continue
        provider = str(model_info.get("provider", "")).strip().lower()
        if provider == "zhipu":
            return model_key
    return None


def get_detected_model_label(model_key: str, model_config: Dict[str, Any]) -> str:
    model_info = get_selected_model_info(model_config, model_key)
    return str(model_info.get("name", model_key))


def infer_identity_from_user_text(user_text: str) -> None:
    normalized = user_text.strip()
    if normalized.startswith("我是") and len(normalized) > 2:
        identity_text = normalized
    elif "我是" in normalized and len(normalized) > 2:
        identity_text = normalized
    else:
        return
    st.session_state.current_identity = identity_text


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
    api_url = str(model_info.get("api_base") or model_info.get("api_url", "")).strip()
    model_name = str(model_info.get("model") or model_info.get("model_name", "")).strip()
    if api_url.endswith("/"):
        api_url = f"{api_url}chat/completions"

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
        st.title("助手配置")

        selected_model_info = get_selected_model_info(
            st.session_state.model_config,
            st.session_state.selected_model,
        )
        current_model = st.session_state.selected_model
        model_name = selected_model_info.get("name", current_model)
        col_input, col_action = st.columns([5, 1])
        with col_input:
            input_value = st.text_input(
                f"{model_name} API Key",
                key="api_key_input",
                type="password",
                placeholder="直接粘贴 API Key",
                label_visibility="collapsed",
            )
        with col_action:
            clear_clicked = st.button("清除", key=f"clear_api_key_{current_model}", use_container_width=True)

        if clear_clicked:
            st.session_state.manual_api_keys[current_model] = ""
            persist_model_api_key(current_model, "")
            st.session_state.api_key_input = ""
            st.session_state.api_key_detect_status = ""
            st.rerun()

        normalized_input = input_value.strip()
        if not normalized_input:
            st.session_state.manual_api_keys[current_model] = ""
            persist_model_api_key(current_model, "")
            st.session_state.api_key_detect_status = ""
        else:
            detected_model = detect_model_from_api_key(normalized_input, st.session_state.model_config)
            if detected_model:
                st.session_state.manual_api_keys[detected_model] = normalized_input
                persist_model_api_key(detected_model, normalized_input)
                st.session_state.api_key_detect_status = f"已连接：{get_detected_model_label(detected_model, st.session_state.model_config)}"
                if st.session_state.selected_model != detected_model:
                    st.session_state.selected_model = detected_model
                    sync_api_key_input_for_model()
                current_model = detected_model
                selected_model_info = get_selected_model_info(st.session_state.model_config, current_model)
            else:
                st.session_state.api_key_detect_status = "未能识别该 Key，请手动选择模型"
                st.session_state.manual_api_keys[current_model] = normalized_input
                persist_model_api_key(current_model, normalized_input)

        status_text = st.session_state.api_key_detect_status or "未连接"
        st.caption(status_text)

        with st.expander("高级设置", expanded=False):
            options = st.session_state.model_options
            option_names = [item["name"] for item in options]
            key_to_name = {item["key"]: item["name"] for item in options}
            name_to_key = {item["name"]: item["key"] for item in options}

            current_name = key_to_name.get(st.session_state.selected_model, option_names[0])
            selected_name = st.selectbox(
                "选择模型",
                options=option_names,
                index=option_names.index(current_name),
                key="model_selectbox",
            )
            new_key = name_to_key[selected_name]
            if new_key != st.session_state.selected_model:
                st.session_state.selected_model = new_key
                sync_api_key_input_for_model()

        return resolve_api_key(current_model, selected_model_info)


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

    active_api_key = render_sidebar()

    st.title("自由对话助手")
    st.caption("像正常聊天一样直接说，模型会根据上下文自由回应。")

    render_chat_history()
    handle_user_message(active_api_key)


if __name__ == "__main__":
    main()
