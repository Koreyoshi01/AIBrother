# AIBrother — 问师兄

基于 **NanoBot + 分层知识库** 的实验室智能助手，支持四种场景：

| 场景 | 说明 | 示例 |
|------|------|------|
| 🧪 **做实验** | 试剂选择、配比、操作流程、故障排查 | "CO2吸收要用什么试剂？比例多少？" |
| 📄 **写论文** | 论文推荐、idea可行性评估、方向调研 | "帮我推荐一篇CO2捕获的前沿论文" |
| 📊 **做汇报** | 汇报结构、PPT组织建议 | "组会汇报应该怎么组织？" |
| 📝 **做日记** | 实验记录结构化整理与知识沉淀 | "我今天做了三组实验..." |

## 架构

```
aibrother/
├── skills/
│   └── ask_senior/SKILL.md    # 师兄人设 + 四种场景工作流
├── knowledge/                  # 分层知识库（纯 Markdown）
│   ├── lab_manual/             # 实验操作手册
│   ├── group_knowledge/        # 组内实验记录 + 问答历史
│   ├── papers/                 # 论文摘要
│   └── public/                 # 外部知识源
├── AGENTS.md                   # Agent 配置
├── SOUL.md                     # 角色人设
├── USER.md                     # 用户信息
├── memory/MEMORY.md            # 长期记忆
├── config.json                 # NanoBot 配置（含 API Key 占位）
├── demo.py                     # 四种场景演示脚本
└── README.md
```

**关键设计**：零自定义代码，所有逻辑通过 SKILL.md 指导 LLM 使用 NanoBot 内置工具（find_files、grep、read_file、web_search、web_fetch）实现分层知识检索。

## 快速开始

### 1. 安装 NanoBot

```bash
cd AIBrother
pip install -e .
```

### 2. 配置 API Key

```bash
export ANTHROPIC_API_KEY=sk-your-key-here
```

或者直接编辑 `aibrother/config.json`，在 `providers.anthropic.apiKey` 中填入 key。

如果使用 OpenAI 等其他 provider，同步修改 `agents.defaults.model` 字段。

### 3. 运行 Demo

```bash
# Windows 中文系统需 PYTHONUTF8=1 解决 .pth 文件编码问题
PYTHONUTF8=1 python aibrother/demo.py
```

## 分层检索流程

```
用户提问
  │
  ├─ 场景识别（做实验 / 写论文 / 做汇报 / 做日记）
  │
  ├─ 第1层：实验室手册    (knowledge/lab_manual/)
  ├─ 第2层：组内记录      (knowledge/group_knowledge/)
  ├─ 第3层：论文知识       (knowledge/papers/)
  ├─ 第4层：公开知识       (knowledge/public/)
  └─ 第5层：Web 搜索      (web_search)
       │
       └─ 整合 → 标注来源 → 输出回答
```

## 自定义知识库

在 `knowledge/` 目录下修改或添加 Markdown 文件：

- 操作手册放在 `lab_manual/`
- 实验记录和问答放在 `group_knowledge/`
- 论文摘要放在 `papers/`
- 外部链接放在 `public/`

Agent 在回答时会自动按优先级检索这些文件。

## 环境要求

- Python >= 3.11
- NanoBot == 0.2.0（已包含在 AIBrother 仓库中）
- API Key（Anthropic / OpenAI 等）
