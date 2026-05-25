---
name: resource_manager
description: 资源导入与检索：当用户上传、导入、整理、归档组会PPT、实验记录、已读论文或要求查询已导入资源时使用
---

# 资源导入与检索

此 skill 只处理资源库相关任务，不替代 `ask_senior` 的实验、论文、汇报、日记回答风格。

## 触发场景

当用户表达以下意图时使用本 skill：

- 上传文件并要求导入、整理、归档、建索引、保存到资源库
- 指出某个本地文件属于组会 PPT、实验记录、已读论文
- 要查询“已经导入的资源”“已有资料”“资源索引”
- 要根据已导入资料找 tag、关键结论、摘要、来源文件

## 资源分类

- `group_meeting_ppt`：组会 PPT、汇报材料、组会讨论记录、导师反馈整理
- `experiment_records`：实验记录、实验日志、原始操作记录、阶段结果、失败排查
- `read_papers`：已读论文、文献笔记、论文摘要、阅读历史、文献调研材料

若用户没有明确分类，根据文件名和上下文判断；仍然无法判断时，再简短询问用户。

## 工具使用

导入资源时调用：

```text
aibrother_import_resource(path, category, title?, status?)
```

检索资源时调用：

```text
aibrother_search_resources(query?, category?, limit?)
```

导入完成后回复用户：

- 资源类别
- 标题
- 自动 tag
- 最重要结论
- 摘要 md 路径
- 原文件副本路径
- 说明 `RESOURCE_INDEX.md` 和 `resources.jsonl` 已更新

如果正文无法抽取，明确说明“需要人工补充摘要或检查文件格式”，不要假装已经读懂文件内容。

## 与其他 skill 的配合

回答实验、论文、汇报问题时，如果用户提到“已有资料、导入资源、上次组会、已读文章、实验记录”，先用 `aibrother_search_resources` 查资源索引，再按对应业务 skill 继续组织答案。

本 skill 不直接修改前端，也不创建 RAG 向量库；它只维护可被前端和未来 RAG 复用的文件索引。
