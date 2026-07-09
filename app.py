import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib import error, parse, request

import streamlit as st
import streamlit.components.v1 as components


PROJECT_ROOT = Path(".")
PROMPTS_DIR = PROJECT_ROOT / "prompts"
CONFIG_DIR = PROJECT_ROOT / "config"
CONVERSATIONS_FILE = CONFIG_DIR / "conversations.json"
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

SEARCH_KEYWORDS = ["最新", "最近", "这两天", "近7天", "近一周", "上周", "这周", "今天", "趋势", "风向", "爆款", "热门", "选题", "赛道", "爆文"]
CONTENT_INTENT_KEYWORDS = [
    "策划",
    "选题",
    "内容",
    "文案",
    "脚本",
    "图文",
    "视频",
    "获客",
    "种草",
    "定位",
    "起号",
    "标题",
    "方向",
    "赛道",
    "产品",
    "获客",
    "避坑",
    "脚本",
    "口播",
    "封面",
    "灵感",
    "爆文",
    "热点",
    "对标",
    "拆解",
    "打法",
    "模板",
    "框架",
    "案例",
    "怎么做内容",
    "怎么起号",
    "写一篇",
    "写一版",
    "找爆款",
    "找灵感",
]
INDUSTRY_HINT_KEYWORDS = [
    "工业制造",
    "制造业",
    "工厂",
    "机械",
    "设备",
    "自动化",
    "工业设计",
    "设计师",
    "新能源",
    "储能",
    "光伏",
    "机器人",
    "太空舱",
    "度假屋",
    "民宿",
    "露营",
    "露营装备",
    "酒店",
    "旅拍",
    "家居",
    "美妆",
    "穿搭",
    "母婴",
    "餐饮",
    "咖啡",
    "健身",
    "减肥",
    "教育",
    "留学",
    "装修",
    "护肤",
    "珠宝",
    "婚礼",
    "本地生活",
    "电商",
    "跨境",
    "家电",
    "数码",
    "汽车",
    "宠物",
    "医疗",
    "大健康",
    "保险",
    "金融",
    "B2B",
    "ToB",
    "企业服务",
    "职场",
    "求职",
    "知识付费",
    "旅游",
    "探店",
    "摄影",
    "连锁",
]
SEARCH_TOPIC_STOPWORDS = [
    "帮我",
    "帮忙",
    "请你",
    "策划",
    "一篇",
    "一个",
    "一下",
    "内容",
    "文案",
    "脚本",
    "图文",
    "视频",
    "小红书",
    "获客",
    "种草",
    "选题",
    "标题",
    "方案",
    "方向",
    "怎么做",
    "怎么写",
    "帮我做",
    "我想做",
    "给我",
    "关于",
    "写一篇",
    "写一版",
    "做一个",
    "做一版",
    "出一版",
    "帮我写",
    "帮我做",
    "帮我出",
]
MAX_SMART_REFERENCE_ITEMS = 6
SMART_REFERENCE_DAYS = 7
SUPPORTED_SKILL_ALIASES = {
    "xiaohongshu-skill": [
        "xiaohongshu-skill",
        "小红书skill",
        "小红书 Skill",
        "小红书爆款skill",
    ]
}

PROVIDER_DISPLAY_ORDER = ["openai_compatible", "deepseek", "zhipu"]
PROVIDER_LABELS = {
    "openai_compatible": "OpenAI",
    "deepseek": "DeepSeek",
    "zhipu": "质谱",
}
AUTO_DETECT_MODEL_ORDER = ["glm_4_flash", "deepseek_chat"]

WORK_MODE_SYSTEM_PROMPT = """
你是“内容工作助手”。

你最重要的工作不是直接交付一份完整内容，而是像一个真人内容同事一样，先把方向问清、把关键细节聊清，再一步一步往下推进。

输出原则：
1. 禁止一次性输出完整内容。每一轮只能推进一个部分，等用户确认后再继续。
2. 禁止使用任何结构化标签作为回复开头，也禁止在正文里自然滑回这种模板口吻：
   - “任务理解：”
   - “交付：”
   - “目标对象：”
   - “主要用途：”
   - “内容方案：”
   - “执行建议：”
   - “可直接提交版本”
   - “汇报说明”
   - “交付说明”
   - “给领导/同事的汇报口径”
3. 回复第一句必须像真人聊天，不像在写材料。
   - 第一行优先用自然问句开头
   - 可以半句话
   - 可以直接追问
   - 可以先接住用户的意思，再问关键点
4. 禁止使用以下词汇/句式：
   - “早安/晚安/朋友们/家人们”
   - “今天又是充满活力的一天”
   - “让我们一起来看看我的日常吧”
   - “你们喜欢吗？我可是花了心思的哦”
   - “工作总是充满挑战但也是充满乐趣的”
   - 任何通用型正能量开场白
5. 语气像真人发微信语音：
   - 半句话也可以
   - 问句开头也可以
   - 允许自嘲、吐槽、反问
   - 不需要完整的“起承转合”文章结构
   - 可以只说关键信息，不需要过渡句

对话推进规则：
1. 用户没有明确说“直接给完整方案”“一次性出完”“直接出终稿”时，必须先追问至少 1 到 2 个关键问题。
2. 关键问题优先围绕这些信息补齐：
   - 你到底想突出哪一类差异
   - 目标客户是谁
   - 形式偏图文还是视频
   - 想偏获客、种草还是品牌认知
   - 想重点讲价格、体验、场景还是服务
3. 在关键问题没问清之前，不要直接给完整策划方案，不要直接给完整标题组，不要直接给完整内容框架。
4. 问完关键问题后，才可以给 2 到 3 个方向建议。

默认流程：
- 第一轮：先追问 1 到 2 个关键问题，或者在信息极少时只给 2 到 3 个方向选项，然后问用户更倾向哪个
- 第二轮：根据用户补充的信息，再收敛成更清楚的方向判断
- 第三轮：再往下给结构建议
- 第四轮：用户确认后再给初稿
- 只有用户明确说“直接给完整方案”或“一次性出完”时，才允许跳步骤

你服务的对象是一位会做新媒体内容的人，他可能会让你帮他：
- 想选题
- 拆方向
- 聊内容怎么做
- 改文案
- 推进成稿

你尤其擅长：
- 用问句开头，而不是陈述句
- 先给选项，再问倾向，而不是先给结论
- 把“写文案”变成“聊文案”，让用户在对话中逐步确认方向
- 把模糊需求先问清，再推进

表达要求：
- 永远用“你”，不要用“您好”或“您”
- 不要写成“视频脚本写作指南”那种完整讲解
- 不要上来就像写方案
- 像真人同事说话一样自然
- 每一轮都以一个问题结尾，等用户回你

你可以参考这种感觉：
- “这个方向可以，不过我得先确认一下，你更想突出价格差异，还是住宿体验差异？”
- “太空舱和普通度假屋拿来做对比是能成立的。你是想拿它做获客内容，还是更偏种草一点？”
- “如果是图文，那我会先把对比维度定下来。不然一上来写，内容会很散。你更想先讲哪块？”

【硬规则】
如果用户没有明确说“直接出终稿”“直接给完整方案”或“一次性给完”，则必须分步推进。
分步推进时：
- 第一轮先追问至少 1 到 2 个关键问题，或者只给少量方向选项
- 不能直接输出完整方案
- 不能直接输出完整框架
- 不能直接输出完整标题组
- 每一轮都必须以一个问题结尾，等用户回复后再继续
""".strip()

WORK_MODE_TASK_PROMPT = """
你当前处于【工作模式】。

当用户在聊工作任务、获客内容、选题策划、图文方向、脚本方向时，请按下面逻辑执行：

1. 先判断这轮最该做什么
- 用户这轮到底只问了什么
- 现在最该补的关键信息是什么
- 哪一步还没聊清

2. 强制执行的回复规则
- 不要用“任务理解：”“交付：”“目标对象：”“主要用途：”“内容方案：”“执行建议：”开头
- 不要输出“可直接提交版本”
- 不要输出“汇报说明/交付说明”
- 不要输出“给领导/同事的汇报口径”
- 不要把回复写成工作汇报材料
- 不要把回复写成完整策划方案

3. 先追问，再建议
- 如果用户没有明确说“直接给完整方案”或“一次性出完”，先追问至少 1 到 2 个关键问题
- 关键问题没问清之前，不要直接给完整方向，不要直接给完整框架，不要直接给完整文案
- 如果信息太少，也可以只先给 2 到 3 个方向选项，然后问用户更偏哪个

4. 当前这一步该怎么答
- 用户问选题：先问想偏哪种对比维度、目标人群、内容目的
- 用户问脚本：先问更偏信息流还是故事型、图文还是视频、想讲到多细
- 用户问改稿：只改当前这一步，不顺手把后面的全做掉

5. 语气要求
- 像真人聊天，不像提交材料
- 可以短句、半句话、问句、断句
- 第一行优先自然追问，不要像在做任务拆解

6. 每轮结尾
- 每一轮都必须用一个自然问题结尾
- 等用户回复，再推进下一步

7. 只有在用户明确说“直接出终稿”“直接给完整方案”“一次性给完”时
- 才允许跳过中间步骤，直接输出完整内容
""".strip()

PERSONAL_MODE_SYSTEM_PROMPT = """
你是“个人内容策划助手”。

你最重要的工作不是直接交付一份完整内容，而是像一个真人内容搭子一样，先把方向聊清、把资源条件问清，再一步一步往下推进。

输出原则：
1. 禁止一次性输出完整内容。每一轮只能推进一个部分，等用户确认后再继续。
2. 禁止使用任何结构化标签作为回复开头，也禁止在正文里自然滑回这种模板口吻：
   - “任务理解：”
   - “交付：”
   - “目标对象：”
   - “主要用途：”
   - “内容方案：”
   - “执行建议：”
   - “可直接提交版本”
   - “汇报说明”
   - “交付说明”
3. 回复第一句必须像真人聊天，不像在写材料。
   - 第一行优先用自然问句开头
   - 可以半句话
   - 可以直接追问
   - 可以先接住用户的意思，再问关键点
4. 禁止使用以下词汇/句式：
   - “早安/晚安/朋友们/家人们”
   - “今天又是充满活力的一天”
   - “让我们一起来看看我的日常吧”
   - “你们喜欢吗？我可是花了心思的哦”
   - “工作总是充满挑战但也是充满乐趣的”
   - 任何通用型正能量开场白
5. 语气像真人发微信语音：
   - 半句话也可以
   - 问句开头也可以
   - 允许自嘲、吐槽、反问
   - 不需要完整的“起承转合”文章结构
   - 可以只说关键信息，不需要过渡句

对话推进规则：
1. 用户没有明确说“直接给完整方案”“一次性出完”“直接出终稿”时，必须先追问至少 1 到 2 个关键问题。
2. 关键问题优先围绕这些信息补齐：
   - 你现在有什么资源
   - 你想做什么方向
   - 你更适合图文还是视频
   - 你想偏表达型、干货型还是记录型
   - 你是想先起号、先找定位还是先变现
3. 在关键问题没问清之前，不要直接给完整起号方案，不要直接给完整选题组，不要直接给完整内容框架。
4. 问完关键问题后，才可以给 2 到 3 个方向建议。

默认流程：
- 第一轮：先追问 1 到 2 个关键问题，或者在信息极少时只给 2 到 3 个方向选项，然后问用户更倾向哪个
- 第二轮：根据用户补充的信息，再收敛成更清楚的方向判断
- 第三轮：再往下给结构建议
- 第四轮：用户确认后再给初稿
- 只有用户明确说“直接给完整方案”或“一次性出完”时，才允许跳步骤

你服务的对象是想做个人账号的人，他可能会让你帮他：
- 找方向
- 定定位
- 拆内容路线
- 聊选题怎么做
- 推进成稿

你尤其擅长：
- 用问句开头，而不是陈述句
- 先给选项，再问倾向，而不是先给结论
- 把“写文案”变成“聊文案”，让用户在对话中逐步确认方向
- 把模糊需求先问清，再推进

表达要求：
- 永远用“你”，不要用“您好”或“您”
- 不要写成“账号定位指南”那种完整讲解
- 不要上来就像写方案
- 像真人同事说话一样自然
- 每一轮都以一个问题结尾，等用户回你

你可以参考这种感觉：
- “这个方向不是不能做，但我得先知道你现阶段是想先起号，还是已经准备开始接单了？”
- “如果你时间不多，我反而不建议一上来做太重的内容。你更能稳定做图文，还是偶尔拍视频？”
- “先别急着定完整路线，我想先确认一下，你更想放大职业经验，还是生活方式这块？”

【硬规则】
如果用户没有明确说“直接出终稿”“直接给完整方案”或“一次性给完”，则必须分步推进。
分步推进时：
- 第一轮先追问至少 1 到 2 个关键问题，或者只给少量方向选项
- 不能直接输出完整方案
- 不能直接输出完整框架
- 不能直接输出完整标题组
- 每一轮都必须以一个问题结尾，等用户回复后再继续
""".strip()

PERSONAL_MODE_TASK_PROMPT = """
你当前处于【个人模式】。

当用户在聊起号、定位、内容方向、个人 IP、变现思路时，请按下面逻辑执行：

1. 先判断这轮最该做什么
- 用户这轮到底只问了什么
- 现在最该补的关键信息是什么
- 哪一步还没聊清

2. 强制执行的回复规则
- 不要用“任务理解：”“交付：”“目标对象：”“主要用途：”“内容方案：”“执行建议：”开头
- 不要输出“可直接提交版本”
- 不要输出“汇报说明/交付说明”
- 不要把回复写成完整指南
- 不要把回复写成完整策划方案

3. 先追问，再建议
- 如果用户没有明确说“直接给完整方案”或“一次性出完”，先追问至少 1 到 2 个关键问题
- 关键问题没问清之前，不要直接给完整方向，不要直接给完整框架，不要直接给完整文案
- 如果信息太少，也可以只先给 2 到 3 个方向选项，然后问用户更偏哪个

4. 当前这一步该怎么答
- 用户问定位：先问资源、时间、内容偏好、变现目标
- 用户问选题：先问想讲给谁听、偏图文还是视频、偏记录还是输出
- 用户问改稿：只改当前这一步，不顺手把后面的全做掉

5. 语气要求
- 像真人聊天，不像提交材料
- 可以短句、半句话、问句、断句
- 第一行优先自然追问，不要像在做任务拆解

6. 每轮结尾
- 每一轮都必须用一个自然问题结尾
- 等用户回复，再推进下一步

7. 只有在用户明确说“直接出终稿”“直接给完整方案”“一次性给完”时
- 才允许跳过中间步骤，直接输出完整内容
""".strip()


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


def get_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_conversation_title(messages: List[Dict[str, str]]) -> str:
    for item in messages:
        content = str(item.get("content", "")).strip()
        if content:
            compact = re.sub(r"\s+", " ", content)
            return compact[:20]
    return "新对话"


def create_conversation_record(mode: str) -> Dict[str, Any]:
    timestamp = get_timestamp()
    return {
        "id": str(uuid.uuid4()),
        "title": "新对话",
        "is_custom_title": False,
        "messages": [],
        "mode": mode,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def load_conversations() -> List[Dict[str, Any]]:
    if not CONVERSATIONS_FILE.exists():
        return []
    try:
        data = json.loads(read_text(CONVERSATIONS_FILE))
    except Exception:
        return []
    if isinstance(data, list):
        conversations: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            item.setdefault("title", "新对话")
            item.setdefault("is_custom_title", False)
            item.setdefault("messages", [])
            item.setdefault("mode", "work")
            item.setdefault("created_at", get_timestamp())
            item.setdefault("updated_at", item.get("created_at", get_timestamp()))
            conversations.append(item)
        return conversations
    return []


def save_conversations(conversations: List[Dict[str, Any]]) -> None:
    CONVERSATIONS_FILE.write_text(
        json.dumps(conversations, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    read_text.clear()


def sort_conversations(conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(conversations, key=lambda item: str(item.get("updated_at", "")), reverse=True)


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


def normalize_search_text(value: str) -> str:
    text = re.sub(r"[，。！？、,.!?\-_/（）()\[\]【】：“”\"'`~]+", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_search_topic(user_text: str) -> str:
    normalized = normalize_search_text(user_text)
    topic = normalized
    for stopword in SEARCH_TOPIC_STOPWORDS:
        topic = topic.replace(stopword, " ")
    topic = re.sub(r"\s+", " ", topic).strip()
    if not topic:
        return normalized[:24]
    return topic[:32]


def should_trigger_smart_reference(user_text: str) -> bool:
    normalized = user_text.strip()
    if not normalized:
        return False
    has_content_intent = any(keyword in normalized for keyword in CONTENT_INTENT_KEYWORDS)
    has_industry_hint = any(keyword in normalized for keyword in INDUSTRY_HINT_KEYWORDS)
    asks_for_recent_hits = any(keyword in normalized for keyword in SEARCH_KEYWORDS)
    return has_content_intent or has_industry_hint or asks_for_recent_hits


def should_trigger_realtime_search(user_text: str) -> bool:
    normalized = user_text.strip()
    if not normalized:
        return False
    has_content_intent = any(keyword in normalized for keyword in CONTENT_INTENT_KEYWORDS)
    has_industry_hint = any(keyword in normalized for keyword in INDUSTRY_HINT_KEYWORDS)
    asks_for_recent_hits = any(keyword in normalized for keyword in SEARCH_KEYWORDS)
    return asks_for_recent_hits or (has_content_intent and has_industry_hint)


def get_requested_skill_name(user_text: str) -> str:
    normalized = user_text.strip()
    if not normalized.startswith("用"):
        return ""
    for canonical_name, aliases in SUPPORTED_SKILL_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical_name
    return ""


def build_smart_reference_query(user_text: str, mode: str) -> str:
    topic = extract_search_topic(user_text)
    if not topic:
        topic = user_text.strip()[:24]
    if any(keyword in user_text for keyword in ["获客", "转化", "引流"]):
        return f"site:xiaohongshu.com {topic} 小红书 最近{SMART_REFERENCE_DAYS}天 获客 引流 转化 爆款 热门"
    if any(keyword in user_text for keyword in ["脚本", "口播", "视频"]):
        return f"site:xiaohongshu.com {topic} 小红书 最近{SMART_REFERENCE_DAYS}天 视频 口播 脚本 爆款 热门"
    if any(keyword in user_text for keyword in ["文案", "图文", "选题", "策划"]):
        return f"site:xiaohongshu.com {topic} 小红书 最近{SMART_REFERENCE_DAYS}天 爆款 热门 选题 标题"
    if mode == "work":
        return f"site:xiaohongshu.com {topic} 小红书 最近{SMART_REFERENCE_DAYS}天 行业案例 爆款 热门"
    return f"site:xiaohongshu.com {topic} 小红书 最近{SMART_REFERENCE_DAYS}天 热门 爆款 笔记"


def parse_xhs_skill_json(raw_text: str) -> List[Dict[str, str]]:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            records = data["items"]
        elif isinstance(data.get("data"), list):
            records = data["data"]
        else:
            records = [data]
    elif isinstance(data, list):
        records = data
    else:
        return []

    parsed_items: List[Dict[str, str]] = []
    for item in records[:MAX_SMART_REFERENCE_ITEMS]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("note_title") or item.get("name") or "").strip()
        snippet = str(
            item.get("desc")
            or item.get("content")
            or item.get("summary")
            or item.get("note_desc")
            or ""
        ).strip()
        author = str(item.get("author") or item.get("nickname") or item.get("user_name") or "小红书").strip()
        link = str(item.get("url") or item.get("link") or item.get("note_url") or "").strip()
        likes = str(item.get("liked_count") or item.get("like_count") or item.get("likes") or "").strip()
        favorites = str(item.get("collected_count") or item.get("collect_count") or item.get("favorites") or "").strip()
        comments = str(item.get("comment_count") or item.get("comments") or "").strip()
        source = f"小红书/{author}" if author else "小红书"
        if likes:
            source = f"{source}/赞{likes}"
        interaction_parts = []
        if likes:
            interaction_parts.append(f"点赞{likes}")
        if favorites:
            interaction_parts.append(f"收藏{favorites}")
        if comments:
            interaction_parts.append(f"评论{comments}")
        if title:
            parsed_items.append(
                {
                    "title": title,
                    "snippet": snippet or "未提供摘要",
                    "link": link or "未提供链接",
                    "source": source,
                    "interactions": " / ".join(interaction_parts) if interaction_parts else "互动数据缺失",
                }
            )
    return parsed_items


def search_xiaohongshu_with_skill(query: str) -> List[Dict[str, str]]:
    if not shutil.which("xiaohongshu-skill"):
        return []
    command = [
        "xiaohongshu-skill",
        "search",
        query,
        "--sort-by=热门",
        f"--days={SMART_REFERENCE_DAYS}",
        f"--limit={MAX_SMART_REFERENCE_ITEMS}",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
            check=False,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return parse_xhs_skill_json(result.stdout.strip())


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
        get_mode_key(mode, "smart_reference_cache"): {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def hydrate_mode_state_from_conversation(conversation: Dict[str, Any]) -> None:
    mode = str(conversation.get("mode", "work"))
    ensure_mode_state(mode)
    messages = conversation.get("messages", [])
    st.session_state[get_mode_key(mode, "messages")] = messages if isinstance(messages, list) else []
    assistant_messages = [
        str(item.get("content", "")).strip()
        for item in messages
        if isinstance(item, dict) and item.get("role") == "assistant" and str(item.get("content", "")).strip()
    ]
    st.session_state[get_mode_key(mode, "latest_output")] = assistant_messages[-1] if assistant_messages else ""
    st.session_state[get_mode_key(mode, "draft_history")] = []


def sync_current_conversation_from_mode_state() -> None:
    conversation_id = st.session_state.get("current_conversation_id", "")
    conversations = st.session_state.get("conversations", [])
    if not conversation_id or not conversations:
        return
    mode = st.session_state.mode
    messages = get_current_messages(mode)
    for item in conversations:
        if item.get("id") != conversation_id:
            continue
        item["mode"] = mode
        item["messages"] = messages
        if not item.get("is_custom_title", False):
            item["title"] = build_conversation_title(messages)
        item["updated_at"] = get_timestamp()
        break
    st.session_state.conversations = sort_conversations(conversations)
    save_conversations(st.session_state.conversations)


def rename_conversation(conversation_id: str, new_title: str) -> bool:
    normalized_title = re.sub(r"\s+", " ", new_title).strip()
    if not normalized_title:
        return False

    updated = False
    conversations = st.session_state.get("conversations", [])
    for item in conversations:
        if item.get("id") != conversation_id:
            continue
        item["title"] = normalized_title[:20]
        item["is_custom_title"] = True
        item["updated_at"] = get_timestamp()
        updated = True
        break

    if not updated:
        return False

    st.session_state.conversations = sort_conversations(conversations)
    save_conversations(st.session_state.conversations)
    return True


def switch_conversation(conversation_id: str) -> None:
    sync_current_conversation_from_mode_state()
    conversations = st.session_state.get("conversations", [])
    target = next((item for item in conversations if item.get("id") == conversation_id), None)
    if not target:
        return
    st.session_state.current_conversation_id = conversation_id
    st.session_state.mode = str(target.get("mode", "work"))
    hydrate_mode_state_from_conversation(target)


def create_and_select_new_conversation(mode: Optional[str] = None) -> None:
    conversation_mode = mode or st.session_state.get("mode", "work")
    new_conversation = create_conversation_record(conversation_mode)
    conversations = st.session_state.get("conversations", [])
    conversations.append(new_conversation)
    st.session_state.conversations = sort_conversations(conversations)
    save_conversations(st.session_state.conversations)
    switch_conversation(new_conversation["id"])


def delete_conversation(conversation_id: str) -> None:
    conversations = st.session_state.get("conversations", [])
    remaining = [item for item in conversations if item.get("id") != conversation_id]
    st.session_state.conversations = sort_conversations(remaining)
    save_conversations(st.session_state.conversations)
    if not remaining:
        create_and_select_new_conversation(st.session_state.get("mode", "work"))
        return
    current_id = st.session_state.get("current_conversation_id", "")
    if current_id == conversation_id:
        switch_conversation(remaining[0]["id"])


def init_session_state() -> None:
    if "mode" not in st.session_state:
        st.session_state.mode = "work"
    if "conversations" not in st.session_state:
        st.session_state.conversations = load_conversations()
    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = ""
    if "manual_api_keys" not in st.session_state:
        st.session_state.manual_api_keys = {}
    if "runtime_logs" not in st.session_state:
        st.session_state.runtime_logs = []
    if "api_key_status" not in st.session_state:
        st.session_state.api_key_status = ""
    if "api_key_requires_manual_selection" not in st.session_state:
        st.session_state.api_key_requires_manual_selection = False
    if "editing_conversation_id" not in st.session_state:
        st.session_state.editing_conversation_id = ""
    if "chat_text_input" not in st.session_state:
        st.session_state.chat_text_input = ""
    if "chat_input_text" not in st.session_state:
        st.session_state.chat_input_text = ""
    if "recording" not in st.session_state:
        st.session_state.recording = False
    if "clear_chat_input" not in st.session_state:
        st.session_state.clear_chat_input = False
    ensure_mode_state("work")
    ensure_mode_state("personal")
    if not st.session_state.conversations:
        create_and_select_new_conversation(st.session_state.mode)
    elif not st.session_state.current_conversation_id:
        switch_conversation(sort_conversations(st.session_state.conversations)[0]["id"])


def render_voice_input_widget() -> None:
    components.html(
        """
        <div id="voice-input-mount"></div>
        <script>
        (function () {
          const parentDoc = window.parent.document;
          const wrapper = parentDoc.querySelector('[data-testid="stAppViewContainer"]');
          if (!wrapper) return;

          const input = parentDoc.querySelector('input[aria-label="chat_text_input"]');
          if (!input) return;

          let host = parentDoc.getElementById('speech-input-host');
          if (!host) {
            host = parentDoc.createElement('button');
            host.id = 'speech-input-host';
            host.type = 'button';
            host.innerText = '🎤';
            host.title = '语音输入';
            host.style.marginLeft = '8px';
            host.style.height = '38px';
            host.style.minWidth = '44px';
            host.style.borderRadius = '10px';
            host.style.border = '1px solid rgba(49,51,63,0.2)';
            host.style.background = '#ffffff';
            host.style.cursor = 'pointer';
          }

          const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
          if (!SpeechRecognition) {
            host.style.display = 'none';
            return;
          }

          const buttonMount = input.parentElement && input.parentElement.parentElement;
          if (buttonMount && host.parentElement !== buttonMount) {
            buttonMount.appendChild(host);
          }

          host.style.display = 'inline-block';
          let recognition = new SpeechRecognition();
          recognition.lang = 'zh-CN';
          recognition.interimResults = false;
          recognition.maxAlternatives = 1;

          host.onclick = function () {
            host.innerText = '🎙️';
            try { recognition.start(); } catch (e) {}
          };

          recognition.onresult = function (event) {
            const transcript = (event.results[0] && event.results[0][0] && event.results[0][0].transcript) || '';
            if (!transcript) return;
            input.focus();
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeSetter.call(input, transcript);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            host.innerText = '🎤';
          };

          recognition.onerror = function () {
            host.innerText = '🎤';
          };

          recognition.onend = function () {
            host.innerText = '🎤';
          };
        })();
        </script>
        """,
        height=0,
    )


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
        sync_current_conversation_from_mode_state()


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
    sync_current_conversation_from_mode_state()


def append_mode_message(mode: str, role: str, content: str) -> None:
    messages = get_current_messages(mode)
    messages.append({"role": role, "content": content})
    st.session_state[get_mode_key(mode, "messages")] = messages
    sync_current_conversation_from_mode_state()


def save_mode_output(mode: str, output_text: str) -> None:
    st.session_state[get_mode_key(mode, "latest_output")] = output_text
    draft_history = get_current_draft_history(mode)
    draft_history.append(output_text)
    st.session_state[get_mode_key(mode, "draft_history")] = draft_history[-20:]
    sync_current_conversation_from_mode_state()


def is_edit_request(user_text: str) -> bool:
    keywords = ["改标题", "换开头", "改开头", "缩短", "压缩", "重写", "拼一个", "融合", "合并", "像我一点", "太官方", "这个可以吗", "再来一版", "优化一个"]
    return any(keyword in user_text for keyword in keywords)


def is_visual_optimization_request(user_text: str) -> bool:
    normalized = user_text.strip()
    if not normalized:
        return False
    visual_keywords = [
        "画面怎么优化",
        "画面如何优化",
        "这个画面怎么优化",
        "画面怎么改",
        "这张图怎么改",
        "图片怎么改",
        "封面怎么改",
        "封面怎么优化",
        "视觉怎么优化",
        "排版怎么改",
        "光线怎么改",
        "构图怎么改",
    ]
    return any(keyword in normalized for keyword in visual_keywords)


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


def build_system_prompt(mode: str, identity_text: str, user_text: str = "") -> str:
    builtin_prompt = WORK_MODE_SYSTEM_PROMPT if mode == "work" else PERSONAL_MODE_SYSTEM_PROMPT
    builtin_task_prompt = WORK_MODE_TASK_PROMPT if mode == "work" else PERSONAL_MODE_TASK_PROMPT
    blocks = [
        builtin_prompt,
        builtin_task_prompt,
        load_prompt("task_iterate_edit.md"),
    ]
    if is_visual_optimization_request(user_text):
        blocks.append(load_prompt("task_visual_optimization.md"))
    blocks.append(f"当前模式身份档案：\n{identity_text}")
    return "\n\n".join([block for block in blocks if block]).strip()


def format_search_context(search_items: List[Dict[str, str]]) -> str:
    if not search_items:
        return "搜索暂时不可用，我先按已有规律库、拆解库和历史上下文继续判断。"
    lines = [f"刚搜了这个赛道最近 {SMART_REFERENCE_DAYS} 天的小红书相关热门内容，请优先把它们作为最新市场信号使用："]
    for index, item in enumerate(search_items, start=1):
        lines.append(
            f"{index}. 标题：{item.get('title', '无法获取')} | 来源：{item.get('source', '未知')} | "
            f"摘要：{item.get('snippet', '无法获取')} | 链接：{item.get('link', '无法获取')}"
        )
    lines.append("回答时先说你刚看了最近内容，再提炼 2 到 3 个可借鉴点，最后结合规律库给具体选题、文案或策划建议。")
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
    smart_reference_context: str,
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

智能爆款参考：
{smart_reference_context or "本轮没有补充到可用的最新爆款参考，继续按规律库和拆解库判断。"}

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
    smart_reference_context: str,
) -> List[Dict[str, str]]:
    system_prompt = build_system_prompt(mode, get_current_identity(mode), user_text)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    history = get_current_messages(mode)[-30:]
    messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": build_user_prompt(
                user_text,
                mode,
                rules_text,
                references_text,
                search_context,
                smart_reference_context,
            ),
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


def format_smart_reference_context(search_items: List[Dict[str, str]], query: str) -> str:
    if not search_items:
        return ""
    lines = [
        f"我搜了最近 {SMART_REFERENCE_DAYS} 天关于“{query}”的小红书热门内容，下面这些结果要优先影响本轮判断："
    ]
    for index, item in enumerate(search_items, start=1):
        lines.append(
            f"{index}. 标题：{item.get('title', '无法获取')} | 来源：{item.get('source', '未知')} | "
            f"互动：{item.get('interactions', '无法获取')} | 摘要：{item.get('snippet', '无法获取')} | 链接：{item.get('link', '无法获取')}"
        )
    lines.append("回答时先总结最近什么角度更火、为什么火，再基于这些结果给用户可执行建议。")
    return "\n".join(lines)


@st.cache_data(show_spinner=False, ttl=1800)
def search_smart_reference_posts(query: str) -> List[Dict[str, str]]:
    skill_results = search_xiaohongshu_with_skill(query)
    if skill_results:
        return skill_results
    return search_hot_posts(query)


def get_realtime_search_context(user_text: str, mode: str) -> str:
    if not should_trigger_realtime_search(user_text):
        return "本轮未触发实时搜索。"
    topic = extract_search_topic(user_text)
    if not topic:
        topic = user_text.strip()[:24]
    search_query = (
        f"site:xiaohongshu.com {topic} 小红书 最近{SMART_REFERENCE_DAYS}天 热门 爆款 笔记"
        if mode == "personal"
        else f"site:xiaohongshu.com {topic} 小红书 最近{SMART_REFERENCE_DAYS}天 行业案例 爆款 热门"
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
        log_runtime(f"{MODE_META[mode]['label']}实时搜索暂时不可用，已静默回退到规律库和拆解库。")
    return format_search_context(results)


def get_smart_reference_context(user_text: str, mode: str) -> str:
    requested_skill = get_requested_skill_name(user_text)
    if not requested_skill and not should_trigger_smart_reference(user_text):
        return ""
    search_query = build_smart_reference_query(user_text, mode)
    cache_key = get_mode_key(mode, "smart_reference_cache")
    search_cache = st.session_state.get(cache_key, {})
    if search_query in search_cache:
        return format_smart_reference_context(search_cache[search_query], search_query)

    results = search_smart_reference_posts(search_query)
    search_cache[search_query] = results
    st.session_state[cache_key] = search_cache

    if results:
        trigger_label = requested_skill or "自动爆款搜索"
        log_runtime(f"{MODE_META[mode]['label']}{trigger_label} 命中 {len(results)} 条最近爆款参考。")
        return format_smart_reference_context(results, search_query)

    log_runtime(f"{MODE_META[mode]['label']}最近爆款搜索未命中，已静默回退到原有规律库。")
    return ""


def call_chat_model(
    api_key: str,
    model_config: Dict[str, Any],
    selected_model: str,
    mode: str,
    user_text: str,
    rules_text: str,
    references_text: str,
    search_context: str,
    smart_reference_context: str,
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
        "messages": build_model_payload(
            mode,
            user_text,
            rules_text,
            references_text,
            search_context,
            smart_reference_context,
        ),
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
        st.subheader("对话列表")
        conversations = sort_conversations(st.session_state.get("conversations", []))
        st.session_state.conversations = conversations
        for conversation in conversations:
            conversation_id = str(conversation.get("id", ""))
            title = str(conversation.get("title", "新对话"))[:20] or "新对话"
            is_editing = st.session_state.get("editing_conversation_id", "") == conversation_id
            item_col, edit_col, delete_col = st.columns([5, 1, 1])
            with item_col:
                if st.button(
                    title,
                    key=f"switch_conversation_{conversation_id}",
                    use_container_width=True,
                    type="primary" if st.session_state.get("current_conversation_id") == conversation_id else "secondary",
                ):
                    switch_conversation(conversation_id)
                    st.session_state.editing_conversation_id = ""
            with edit_col:
                if st.button("✏️", key=f"edit_conversation_{conversation_id}", use_container_width=True):
                    st.session_state.editing_conversation_id = "" if is_editing else conversation_id
                    st.rerun()
            with delete_col:
                if st.button("删", key=f"delete_conversation_{conversation_id}", use_container_width=True):
                    if st.session_state.get("editing_conversation_id") == conversation_id:
                        st.session_state.editing_conversation_id = ""
                    delete_conversation(conversation_id)
                    st.rerun()
            if is_editing:
                st.text_input(
                    "重命名对话",
                    value=title,
                    key=f"rename_input_{conversation_id}",
                    label_visibility="collapsed",
                    placeholder="输入新的会话标题",
                )
                save_col, cancel_col = st.columns(2)
                with save_col:
                    if st.button("保存", key=f"save_conversation_{conversation_id}", use_container_width=True):
                        rename_value = st.session_state.get(f"rename_input_{conversation_id}", "")
                        if rename_conversation(conversation_id, rename_value):
                            st.session_state.editing_conversation_id = ""
                            st.rerun()
                with cancel_col:
                    if st.button("取消", key=f"cancel_conversation_{conversation_id}", use_container_width=True):
                        st.session_state.editing_conversation_id = ""
                        st.rerun()
        if st.button("新建对话", use_container_width=True, key="create_new_conversation"):
            sync_current_conversation_from_mode_state()
            st.session_state.editing_conversation_id = ""
            create_and_select_new_conversation(st.session_state.mode)
            st.rerun()

        st.divider()
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


def render_chat_layout_styles() -> None:
    st.markdown(
        """
<style>
.block-container {
    padding-bottom: 110px !important;
}

.main > div:first-child {
    height: calc(100vh - 220px) !important;
    overflow: hidden !important;
}

.stChatInput {
    position: sticky !important;
    bottom: 0 !important;
    background: white !important;
    padding: 10px 0 !important;
    border-top: 1px solid #ddd !important;
    z-index: 999 !important;
}

[data-testid="stVerticalBlock"] [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
    height: 100%;
}

section[data-testid="stSidebar"] {
    z-index: 1000 !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_bottom_scroll_anchor() -> None:
    st.markdown('<div id="chat-bottom-anchor"></div>', unsafe_allow_html=True)
    components.html(
        """
        <script>
        (function () {
          const parentDoc = window.parent.document;
          const anchorId = "chat-bottom-anchor";

          function findScrollableParent(node) {
            let current = node;
            while (current) {
              const style = window.getComputedStyle(current);
              const overflowY = style ? style.overflowY : "";
              if ((overflowY === "auto" || overflowY === "scroll") && current.scrollHeight > current.clientHeight) {
                return current;
              }
              current = current.parentElement;
            }
            return parentDoc.scrollingElement || parentDoc.documentElement;
          }

          function scrollToBottom() {
            const anchor = parentDoc.getElementById(anchorId);
            if (!anchor) return false;
            const scrollParent = findScrollableParent(anchor);
            if (scrollParent) {
              scrollParent.scrollTop = scrollParent.scrollHeight;
            }
            anchor.scrollIntoView({ block: "end", behavior: "auto" });
            return true;
          }

          let attempts = 0;
          const timer = window.setInterval(function () {
            attempts += 1;
            if (scrollToBottom() || attempts > 20) {
              window.clearInterval(timer);
            }
          }, 150);

          window.setTimeout(scrollToBottom, 0);
          window.setTimeout(scrollToBottom, 300);
          window.setTimeout(scrollToBottom, 800);
        })();
        </script>
        """,
        height=0,
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


def handle_user_message(active_api_key: str, user_text: str) -> None:
    mode = st.session_state.mode
    user_text = user_text.strip()
    if not user_text:
        return
    append_mode_message(mode, "user", user_text)
    if handle_identity_instruction(mode, user_text):
        return
    try:
        smart_reference_context = get_smart_reference_context(user_text, mode)
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
            smart_reference_context=smart_reference_context,
        )
        append_mode_message(mode, "assistant", result)
        save_mode_output(mode, result)
    except Exception as exc:
        error_text = f"生成失败：{exc}"
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
    render_chat_layout_styles()
    msg_container = st.container(height=600)
    with msg_container:
        render_chat_history(mode)
        render_bottom_scroll_anchor()
    user_text = st.chat_input("像聊天一样直接说...")
    if user_text:
        with st.spinner("我先帮你判断方向，再整理成初稿..."):
            handle_user_message(active_api_key, user_text)
        st.rerun()


if __name__ == "__main__":
    main()
