import os

# 国内访问 huggingface.co 常不稳定，默认走镜像（可设 HF_ENDPOINT 覆盖）
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import gradio as gr
import json
import uuid
from sentence_transformers import SentenceTransformer, util
import numpy as np

# ---------- 配置 ----------
FAQ_FILE = "faqs.json"          # 存储问答对的文件
UNANSWERED_FILE = "unanswered.json"  # 存储未答问题记录
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
LOCAL_MODEL_DIR = os.path.join("models", MODEL_NAME)  # 项目内本地副本，启动更快、可离线

def _hf_cache_dir():
    return os.path.join(
        os.path.expanduser("~"),
        ".cache",
        "huggingface",
        "hub",
        f"models--sentence-transformers--{MODEL_NAME}",
    )

def load_embedding_model():
    """优先项目本地目录 → Hugging Face 缓存 → 首次联网下载，并自动保存到项目目录。"""
    config_file = os.path.join(LOCAL_MODEL_DIR, "config.json")
    if os.path.isfile(config_file):
        print(f"从本地加载模型: {LOCAL_MODEL_DIR}")
        return SentenceTransformer(LOCAL_MODEL_DIR)

    if os.path.isdir(_hf_cache_dir()):
        print(f"从 Hugging Face 缓存加载模型（无需重新下载）")
    else:
        print(f"正在首次下载模型: {MODEL_NAME}（约 120MB，请保持网络畅通）")

    model = SentenceTransformer(MODEL_NAME)

    if not os.path.isfile(config_file):
        os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)
        model.save(LOCAL_MODEL_DIR)
        print(f"模型已保存到: {LOCAL_MODEL_DIR}，下次启动将直接本地加载")

    return model

try:
    model = load_embedding_model()
except Exception as e:
    raise RuntimeError(
        "嵌入模型加载失败，通常是网络无法访问 Hugging Face。\n"
        "请任选其一：\n"
        "  1. 重试（已默认使用镜像 https://hf-mirror.com）\n"
        "  2. 手动下载后离线使用：\n"
        f"     huggingface-cli download sentence-transformers/{MODEL_NAME} "
        f"--local-dir {LOCAL_MODEL_DIR}\n"
        "  3. 使用代理后再运行 python app.py\n"
        f"原始错误: {e}"
    ) from e

# ---------- 加载/保存 FAQ 数据 ----------
def load_faqs():
    if os.path.exists(FAQ_FILE):
        with open(FAQ_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        # 默认内置 FAQ（可直接修改或通过界面添加）
        default_faqs = [
            {"question": "如何操作离心机？", "answer": "先配平，转速不超过12000rpm，时间5分钟。离心后静置2分钟再开盖。", "source": "李师兄实验手册 2024"},
            {"question": "反应液变黄是什么原因？", "answer": "可能是氧化或副反应。检查氮气保护是否到位，或者温度过高。", "source": "王师姐笔记 2023"},
            {"question": "如何清洗石英比色皿？", "answer": "先用乙醇浸泡10分钟，再用去离子水冲洗，不可用超声。", "source": "实验室SOP V2.1"},
            {"question": "我们实验室常用的基片尺寸是多少？", "answer": "硅片常用10mm×10mm，玻璃片15mm×15mm。", "source": "课题组共享文档"},
            {"question": "做PL测试时需要注意什么？", "answer": "样品要干燥，避免杂质荧光，激发波长选355nm。", "source": "张师兄毕业论文"},
            {"question": "如何避免旋蒸时暴沸？", "answer": "开始旋转前先通大气，缓慢升温，加入沸石。", "source": "实验室安全指南"},
            {"question": "实验室购买耗材的流程？", "answer": "填写采购申请表，导师签字后交给管理员。", "source": "课题组管理规则"},
            {"question": "手套箱水氧指标多少以下可以进样？", "answer": "水<0.1ppm，氧<0.1ppm。", "source": "手套箱操作规范"},
            {"question": "我们组常用的电化学工作站型号？", "answer": "CHI660E，使用前需校准。", "source": "仪器登记表"},
            {"question": "如何清洗银电极？", "answer": "用氧化铝浆抛光，然后去离子水冲洗。", "source": "电化学组经验"}
        ]
        save_faqs(default_faqs)
        return default_faqs

def save_faqs(faqs):
    with open(FAQ_FILE, 'w', encoding='utf-8') as f:
        json.dump(faqs, f, ensure_ascii=False, indent=2)

def load_unanswered():
    if os.path.exists(UNANSWERED_FILE):
        with open(UNANSWERED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_unanswered(unanswered_list):
    with open(UNANSWERED_FILE, 'w', encoding='utf-8') as f:
        json.dump(unanswered_list, f, ensure_ascii=False, indent=2)

# 全局变量，启动时加载
faqs = load_faqs()
unanswered_questions = load_unanswered()

# 预计算所有问题的嵌入向量
def compute_embeddings(faqs):
    questions = [f["question"] for f in faqs]
    if questions:
        return model.encode(questions, convert_to_tensor=True)
    return None

faq_embeddings = compute_embeddings(faqs)

# ---------- 核心检索与自进化功能 ----------
def answer_question(query):
    """返回答案文本和置信度，如果未找到则返回 None"""
    global faqs, faq_embeddings
    if not faqs or faq_embeddings is None:
        return None, 0.0
    query_emb = model.encode(query, convert_to_tensor=True)
    similarities = util.cos_sim(query_emb, faq_embeddings)[0]
    best_idx = np.argmax(similarities.cpu().numpy())
    best_score = similarities[best_idx].item()
    if best_score < 0.5:
        return None, best_score
    best_faq = faqs[best_idx]
    return best_faq, best_score

def record_unanswered(question):
    """记录未答问题，供管理员后续补充"""
    global unanswered_questions
    if question not in unanswered_questions:
        unanswered_questions.append(question)
        save_unanswered(unanswered_questions)
        return f"✅ 已记录问题：“{question}”，管理员会尽快补充知识库。"
    else:
        return f"ℹ️ 问题：“{question}” 已在待补充列表中。"

def add_new_qa(question, answer, source):
    """动态添加新问答对，并更新向量索引"""
    global faqs, faq_embeddings
    new_item = {"question": question, "answer": answer, "source": source}
    faqs.append(new_item)
    save_faqs(faqs)
    # 重新计算全部嵌入（数据量小，直接重算）
    faq_embeddings = compute_embeddings(faqs)
    return f"✅ 已添加新知识：{question} → {answer} (来源：{source})"

# ---------- 意图识别（内部路由，不在 UI 展示分类） ----------
INTENTS = {
    "experiment": {
        "label": "做实验",
        "description": "实验室操作、仪器使用、实验步骤、故障排查、试剂耗材",
        "keywords": ["离心", "旋蒸", "手套箱", "电极", "反应", "实验", "仪器", "清洗", "PL", "耗材", "比色皿"],
    },
    "paper": {
        "label": "写论文",
        "description": "论文写作、摘要、引言、润色、参考文献、章节结构",
        "keywords": ["论文", "摘要", "引言", "润色", "参考文献", "章节", "abstract", "讨论", "方法", "投稿"],
    },
    "diary": {
        "label": "做日记",
        "description": "实验日记、记录现象、今日进展、失败复盘、周报",
        "keywords": ["日记", "今天", "记录", "现象", "心得", "复盘", "周报", "进展", "失败了"],
    },
}

INTENT_NAMES = list(INTENTS.keys())
INTENT_EMBEDDINGS = model.encode(
    [f"{INTENTS[k]['label']}：{INTENTS[k]['description']}" for k in INTENT_NAMES],
    convert_to_tensor=True,
)

APP_SUBTITLE = "内容由 AI 大师兄 生成"
INPUT_PLACEHOLDER = "发消息…"
EXAMPLE_PROMPTS = [
    "如何操作离心机？",
    "帮我写论文摘要",
    "总结今天实验现象",
    "反应液变黄怎么办？",
]
PERSON_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "person.png")
WELCOME_TEXT = "我是AI大师兄，有什么我可以帮你的吗？"

def detect_intent(message):
    """
    根据用户 Prompt 猜测意图（脚手架）。
    1. 关键词匹配（快、可解释）
    2. 语义向量相似度（复用现有 embedding 模型）
    后续可替换为 LLM 分类：把 message 发给大模型，让它返回 experiment/paper/diary。
    """
    scores = {name: 0 for name in INTENT_NAMES}
    for name, cfg in INTENTS.items():
        for kw in cfg["keywords"]:
            if kw in message:
                scores[name] += 1
    best_kw = max(scores, key=scores.get)
    if scores[best_kw] > 0:
        return best_kw

    query_emb = model.encode(message, convert_to_tensor=True)
    sims = util.cos_sim(query_emb, INTENT_EMBEDDINGS)[0]
    return INTENT_NAMES[int(np.argmax(sims.cpu().numpy()))]

DOUBAO_CSS = """
html, body { height: 100% !important; margin: 0 !important; overflow: hidden !important; }
.gradio-container {
    max-width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important;
}
.gradio-container > .main,
.gradio-container > .main > .wrap,
.gradio-container .contain {
    height: 100% !important;
    max-height: 100% !important;
    overflow: hidden !important;
    padding: 0 !important;
    margin: 0 !important;
}
.app-shell {
    height: 100vh !important;
    max-height: 100vh !important;
    gap: 0 !important;
    overflow: hidden !important;
    align-items: stretch !important;
    margin: 0 !important;
}
.app-shell > .gap { gap: 0 !important; height: 100% !important; }
.sidebar {
    background: #f5f6f8 !important;
    border-right: 1px solid #e8eaed !important;
    padding: 16px 10px !important;
    height: 100vh !important;
    max-height: 100vh !important;
    overflow-y: auto !important;
}
.main-panel {
    background: #ffffff !important;
    padding: 0 20px 8px !important;
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important;
    box-sizing: border-box !important;
}
.main-panel > .gap, .main-layout > .gap, .chat-body > .gap { gap: 0 !important; }
.main-panel .block { padding: 0 !important; margin: 0 !important; }
.brand { font-size: 22px; font-weight: 700; color: #1f2329; margin-bottom: 8px; }
.brand-sub { font-size: 12px; color: #8f959e; margin-bottom: 20px; }
.nav-btn button {
    width: 100% !important;
    justify-content: flex-start !important;
    border: none !important;
    background: transparent !important;
    color: #1f2329 !important;
    font-size: 14px !important;
    padding: 10px 12px !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}
.nav-btn button:hover { background: #eceef2 !important; }
.nav-btn-primary button { background: #ffffff !important; box-shadow: 0 1px 2px rgba(0,0,0,.06) !important; }
.section-label { font-size: 12px; color: #8f959e; margin: 18px 0 8px 4px; }
.main-layout {
    display: flex !important;
    flex-direction: column !important;
    height: 100% !important;
    max-height: 100vh !important;
    overflow: hidden !important;
    min-height: 0 !important;
    box-sizing: border-box !important;
}
.chat-header {
    padding: 8px 0 4px !important;
    border-bottom: none;
    margin: 0 !important;
    text-align: center;
    flex: 0 0 auto !important;
}
.chat-title { font-size: 15px !important; font-weight: 600; color: #1f2329; margin: 0; }
.chat-title p { margin: 0 !important; line-height: 1.3 !important; }
.chat-subtitle { font-size: 11px !important; color: #b0b4bb; margin: 2px 0 0 !important; text-align: center; }
.chat-subtitle p { margin: 0 !important; }
.chat-body {
    flex: 1 1 0 !important;
    display: flex !important;
    flex-direction: column !important;
    min-height: 0 !important;
    overflow: hidden !important;
}
.welcome-hero {
    flex: 1 1 0 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: flex-start !important;
    padding: min(5vh, 40px) 16px 16px !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    gap: 0 !important;
}
.welcome-greeting {
    font-size: 24px;
    font-weight: 600;
    color: #1f2329;
    margin: 16px 0 20px;
    line-height: 1.45;
    text-align: center !important;
    width: 100% !important;
    max-width: 560px;
}
.hero-img {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    margin: 0 !important;
    padding: 0 !important;
    flex: 0 0 auto !important;
}
.hero-img .wrap,
.hero-img .image-container,
.hero-img > div {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
    min-height: 0 !important;
    height: auto !important;
    justify-content: center !important;
}
.hero-img img {
    width: 180px !important;
    max-width: 180px !important;
    height: auto !important;
    object-fit: contain !important;
    border-radius: 0 !important;
    display: block !important;
    margin: 0 auto !important;
}
.welcome-greeting-wrap { width: 100% !important; display: flex !important; justify-content: center !important; }
.welcome-chips { justify-content: center !important; max-width: 720px; margin: 0 auto !important; width: 100% !important; }
.chat-scroll-wrapper {
    flex: 1 1 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
    display: flex !important;
    flex-direction: column !important;
    width: 100% !important;
}
.main-chat {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    flex: 1 1 0 !important;
    min-height: 0 !important;
    height: 100% !important;
    max-height: 100% !important;
    overflow: hidden !important;
}
.main-chat > .block {
    height: 100% !important;
    min-height: 0 !important;
    overflow: hidden !important;
}
.main-chat .wrapper.svelte-1wizwbi {
    height: 100% !important;
    min-height: 0 !important;
}
.main-chat .bubble-wrap.svelte-kpz1,
.main-chat [class*="bubble-wrap"] {
    height: 100% !important;
    max-height: 100% !important;
    overflow-y: auto !important;
    padding-top: 8px !important;
}
/* 占位层/加载层仅 opacity:0，仍会占满高度 → 顶部大空白 */
.main-chat .wrap.default.full.hide,
.main-chat .placeholder-content,
.main-chat .placeholder {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    flex: 0 0 0 !important;
}
.main-chat .message-wrap,
.main-chat [class*="message-wrap"] {
    justify-content: flex-start !important;
    margin-bottom: 0 !important;
}
.chat-body > .hide {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    flex: 0 0 0 !important;
    overflow: hidden !important;
}
.input-area {
    flex: 0 0 auto !important;
    padding: 6px 0 0 !important;
    margin: 0 !important;
}
.input-shell {
    border: 1px solid #e8eaed !important;
    border-radius: 14px !important;
    background: #fff !important;
    box-shadow: 0 1px 6px rgba(0,0,0,.04) !important;
    padding: 2px 6px 4px !important;
}
.input-shell textarea {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    font-size: 14px !important;
    min-height: 36px !important;
    padding: 8px 4px !important;
}
.input-row { align-items: center !important; gap: 6px !important; margin: 0 !important; }
.send-btn button {
    border-radius: 10px !important;
    min-width: 64px !important;
    height: 36px !important;
    padding: 0 12px !important;
    background: #3370ff !important;
    color: #fff !important;
    border: none !important;
}
.input-hint { display: none !important; }
.chip-row { gap: 8px !important; flex-wrap: wrap !important; margin-top: 8px; }
.chip-row button {
    border-radius: 999px !important;
    border: 1px solid #e8eaed !important;
    background: #f7f8fa !important;
    color: #646a73 !important;
    font-size: 13px !important;
    padding: 6px 14px !important;
    min-width: unset !important;
    box-shadow: none !important;
}
.chip-row button:hover { background: #eceef2 !important; color: #1f2329 !important; }
.history-list fieldset { border: none !important; padding: 0 !important; }
.history-list label {
    width: 100% !important;
    padding: 8px 12px !important;
    border-radius: 10px !important;
    font-size: 13px !important;
    color: #646a73 !important;
    margin: 2px 0 !important;
}
.history-list label:has(input:checked) {
    background: #ffffff !important;
    color: #1f2329 !important;
    box-shadow: 0 1px 2px rgba(0,0,0,.06) !important;
}
.history-empty {
    padding: 8px 12px;
    border-radius: 10px;
    color: #8f959e;
    font-size: 13px;
}
footer { display: none !important; }
"""

def message_text(content):
    """兼容 Gradio 6：content 可能是 str 或多模态 block 列表。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
        return " ".join(p for p in parts if p).strip()
    return str(content).strip()

def session_title(messages):
    for item in messages or []:
        if item.get("role") == "user":
            text = message_text(item.get("content")).replace("\n", " ")
            if text:
                return text[:20] + ("…" if len(text) > 20 else "")
    return "新对话"

def upsert_session(sessions, session_id, messages):
    sessions = list(sessions or [])
    messages = list(messages or [])
    if not messages:
        return sessions, session_id
    title = session_title(messages)
    sid = session_id or str(uuid.uuid4())
    record = {"id": sid, "title": title, "messages": messages}
    for i, item in enumerate(sessions):
        if item["id"] == sid:
            sessions[i] = record
            return sessions, sid
    sessions.insert(0, record)
    return sessions, sid

def history_update(sessions, current_id=None):
    sessions = sessions or []
    if not sessions:
        return gr.update(choices=[], value=None)
    choices = [(s["title"], s["id"]) for s in sessions]
    if current_id and any(s["id"] == current_id for s in sessions):
        return gr.update(choices=choices, value=current_id)
    return gr.update(choices=choices)

def get_session(sessions, session_id):
    for item in sessions or []:
        if item["id"] == session_id:
            return item
    return None

def chat_view(chat_history):
    """空对话显示欢迎页，有消息时显示聊天区。"""
    active = bool(chat_history)
    return (
        gr.update(visible=not active),
        gr.update(visible=active),
        gr.update(visible=active),
    )

def respond_experiment(message, chat_history):
    """做实验：沿用 FAQ 语义检索"""
    chat_history = list(chat_history or [])
    if message.startswith("/add "):
        parts = message[5:].split("|")
        if len(parts) >= 3:
            q, a, s = parts[0].strip(), parts[1].strip(), parts[2].strip()
            result = add_new_qa(q, a, s)
        else:
            result = "❌ 格式错误，请使用：/add 问题 | 答案 | 来源"
        chat_history.append({"role": "user", "content": message})
        chat_history.append({"role": "assistant", "content": result})
        return chat_history

    best_faq, score = answer_question(message)
    if best_faq is None:
        record_msg = record_unanswered(message)
        answer_text = (
            f"我暂时没有在知识库里找到合适答案（置信度 {score:.2f}）。\n\n"
            f"{record_msg}\n\n"
            f"💡 可用 `/add 问题 | 答案 | 来源` 直接补充知识。"
        )
    else:
        answer_text = (
            f"**{best_faq['answer']}**\n\n"
            f"📖 来源：{best_faq['source']}　·　置信度 {score:.2f}"
        )
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": answer_text})
    return chat_history

def respond_paper(message, chat_history, intent_label):
    chat_history = list(chat_history or [])
    chat_history.append({"role": "user", "content": message})
    chat_history.append({
        "role": "assistant",
        "content": (
            f"**{intent_label}**（AI 能力待接入）\n\n"
            f"收到：「{message}」\n\n"
            f"后续可接入：摘要生成、段落润色、章节大纲、参考文献整理。"
        ),
    })
    return chat_history

def respond_diary(message, chat_history, intent_label):
    chat_history = list(chat_history or [])
    chat_history.append({"role": "user", "content": message})
    chat_history.append({
        "role": "assistant",
        "content": (
            f"**{intent_label}**（AI 能力待接入）\n\n"
            f"收到：「{message}」\n\n"
            f"后续可接入：日记模板、现象归纳、失败复盘、周报汇总。"
        ),
    })
    return chat_history

def respond(message, chat_history, sessions, session_id):
    if not message or not message.strip():
        welcome_up, chat_up, title_vis = chat_view(chat_history)
        return (
            chat_history or [],
            gr.update(value=""),
            sessions,
            session_id,
            history_update(sessions, session_id),
            title_vis,
            welcome_up,
            chat_up,
        )
    try:
        intent = detect_intent(message)
        label = INTENTS[intent]["label"]
        if message.startswith("/add "):
            chat_history = respond_experiment(message, chat_history)
        elif intent == "paper":
            chat_history = respond_paper(message, chat_history, label)
        elif intent == "diary":
            chat_history = respond_diary(message, chat_history, label)
        else:
            chat_history = respond_experiment(message, chat_history)
        sessions, session_id = upsert_session(sessions, session_id, chat_history)
        title = session_title(chat_history)
    except Exception as e:
        chat_history = list(chat_history or [])
        chat_history.append({"role": "user", "content": message})
        chat_history.append({"role": "assistant", "content": f"处理出错：{e}"})
        sessions, session_id = upsert_session(sessions, session_id, chat_history)
        title = session_title(chat_history)
    welcome_up, chat_up, title_vis = chat_view(chat_history)
    return (
        chat_history,
        gr.update(value=""),
        sessions,
        session_id,
        history_update(sessions, session_id),
        gr.update(value=f"## {title}", visible=True),
        welcome_up,
        chat_up,
    )

def new_chat(chat_history, sessions, session_id):
    sessions, _ = upsert_session(sessions, session_id, chat_history)
    welcome_up, chat_up, title_vis = chat_view([])
    return (
        [],
        str(uuid.uuid4()),
        sessions,
        history_update(sessions, None),
        gr.update(value="## 新对话", visible=False),
        gr.update(value=""),
        welcome_up,
        chat_up,
    )

def load_history(selected_id, chat_history, sessions, session_id):
    if not selected_id:
        welcome_up, chat_up, title_vis = chat_view(chat_history)
        return chat_history, session_id, sessions, title_vis, gr.skip(), welcome_up, chat_up
    sessions, _ = upsert_session(sessions, session_id, chat_history)
    session = get_session(sessions, selected_id)
    if not session:
        welcome_up, chat_up, title_vis = chat_view(chat_history)
        return chat_history, session_id, sessions, title_vis, gr.skip(), welcome_up, chat_up
    messages = list(session["messages"])
    welcome_up, chat_up, title_vis = chat_view(messages)
    return (
        messages,
        session["id"],
        sessions,
        gr.update(value=f"## {session['title']}", visible=True),
        gr.update(value=""),
        welcome_up,
        chat_up,
    )

# ---------- 构建 Gradio 界面（豆包风格） ----------
with gr.Blocks(title="AI 大师兄", fill_width=True, fill_height=True) as demo:
    sessions_state = gr.State([])
    session_id_state = gr.State(str(uuid.uuid4()))

    with gr.Row(elem_classes=["app-shell"]):
        with gr.Column(scale=2, min_width=220, elem_classes=["sidebar"]):
            gr.HTML('<div class="brand">🧑‍🔬 AI 大师兄</div><div class="brand-sub">课题组智能助手</div>')
            btn_new = gr.Button("✏️  新对话", elem_classes=["nav-btn", "nav-btn-primary"])
            gr.HTML('<div class="section-label">历史对话</div>')
            history_radio = gr.Radio(
                choices=[],
                label=None,
                show_label=False,
                elem_classes=["history-list"],
            )
            history_empty = gr.HTML(
                '<div class="history-empty">暂无历史，发送消息或点「新对话」开始</div>',
                visible=True,
            )

        with gr.Column(scale=8, elem_classes=["main-panel", "main-layout"]):
            with gr.Column(elem_classes=["chat-header"]):
                chat_title = gr.Markdown("## 新对话", visible=False, elem_classes=["chat-title"])
                chat_subtitle = gr.Markdown(APP_SUBTITLE, elem_classes=["chat-subtitle"])

            with gr.Column(elem_classes=["chat-body"]):
                with gr.Column(visible=True, elem_classes=["welcome-hero"]) as welcome_hero:
                    gr.Image(
                        PERSON_IMAGE,
                        show_label=False,
                        interactive=False,
                        container=False,
                        elem_classes=["hero-img"],
                    )
                    gr.HTML(
                        f'<div class="welcome-greeting">{WELCOME_TEXT}</div>',
                        elem_classes=["welcome-greeting-wrap"],
                    )
                    example_buttons = []
                    with gr.Row(elem_classes=["chip-row", "welcome-chips"]):
                        for example in EXAMPLE_PROMPTS:
                            example_buttons.append((gr.Button(example, size="sm"), example))

                with gr.Column(visible=False, elem_classes=["chat-scroll-wrapper"]) as chat_panel:
                    chatbot = gr.Chatbot(
                        label=None,
                        show_label=False,
                        height="100%",
                        placeholder=None,
                        container=False,
                        elem_classes=["main-chat"],
                        layout="bubble",
                        autoscroll=True,
                    )

            with gr.Column(elem_classes=["input-area", "input-shell"]):
                with gr.Row(elem_classes=["input-row"]):
                    msg = gr.Textbox(
                        show_label=False,
                        placeholder=INPUT_PLACEHOLDER,
                        lines=1,
                        max_lines=4,
                        scale=9,
                        container=False,
                        submit_btn=False,
                    )
                    send_btn = gr.Button("发送", variant="primary", scale=1, elem_classes=["send-btn"])

    for btn, example in example_buttons:
        btn.click(lambda text=example: text, outputs=msg)

    def toggle_history_empty(sessions):
        return gr.update(visible=not bool(sessions))

    view_outputs = [welcome_hero, chat_panel]

    btn_new.click(
        new_chat,
        [chatbot, sessions_state, session_id_state],
        [chatbot, session_id_state, sessions_state, history_radio, chat_title, msg, *view_outputs],
    ).then(toggle_history_empty, [sessions_state], [history_empty])

    history_radio.change(
        load_history,
        [history_radio, chatbot, sessions_state, session_id_state],
        [chatbot, session_id_state, sessions_state, chat_title, msg, *view_outputs],
    )

    respond_outputs = [chatbot, msg, sessions_state, session_id_state, history_radio, chat_title, *view_outputs]
    msg.submit(
        respond,
        [msg, chatbot, sessions_state, session_id_state],
        respond_outputs,
    ).then(toggle_history_empty, [sessions_state], [history_empty])
    send_btn.click(
        respond,
        [msg, chatbot, sessions_state, session_id_state],
        respond_outputs,
    ).then(toggle_history_empty, [sessions_state], [history_empty])

demo.launch(
    share=os.environ.get("GRADIO_SHARE", "").lower() in ("1", "true", "yes"),
    theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
    css=DOUBAO_CSS,
)