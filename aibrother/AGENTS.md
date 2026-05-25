# 问师兄 — Agent 配置

用 NanoBot 加载以下技能，作为实验室智能助手：
- `skills/ask_senior` — 问师兄，实验室智能问答（实验/论文/汇报/日记）
- `skills/resource_manager` — 资源管理，导入和检索组会PPT、实验记录、文献笔记

使用方式：
```bash
# 设置 API key
export ANTHROPIC_API_KEY=sk-xxx

# 使用自定义 config 运行
nanobot --config aibrother/config.json
```
