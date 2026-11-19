# 知识库（SQLite，并行 MVP）

## 0. 一句话

`knowledge.db` 是 v0.15 的**并行实验**：统一知识项、事件、复习、关系；旧的 `progress` / `blindspot` / JSONL 不动，随时可回退。

## 1. 为什么并行

- 旧命令已有 157 项测试，稳定；数据库是新路径，先不替换。
- `kb` 写 SQLite；旧的 `progress` / `blindspot` 仍写 JSONL。
- **不要双写**：同一段学习要么走 `kb`，要么走旧命令；两边都写会漂移。
- `kb import` 一次性导入旧数据；导入后以数据库为准，JSONL 只做导出/回退。

## 2. 数据模型

`<EDU_HOME>/learner/knowledge.db`：

```sql
items(id, title, domain, type, granularity, state, conditions, context,
      created, updated, last_reviewed, review_count, interval_days,
      ease, next_review)

item_disciplines(item_id, discipline)   -- 多学科
events(item_id, kind, context, evidence, date)
reviews(item_id, date, result, note)
links(from_id, to_id, rel)
```

- **一个知识项，多个事件**：盲区声明、第一次飞跃、第二次飞跃、复习都是 `events`。
- 不把同一知识存成“盲区表 + 进步表”两份。
- `links` 存先修、组成、对照、应用、类比。

## 3. 分类

- **学科 discipline**（至少一个）：math / cs / physics / chemistry / biology / engineering / language / humanities / social-science / arts / other；可加自定义。
- **领域 domain**：子领域路径，如 `calculus/limits`、`networking/transport`。
- **类型 type**：fact 事实 / concept 概念 / principle 原理 / procedure 程序 / method 方法 / meta 元认知。
- **粒度 granularity**：atom 原子 / cluster 组合 / meta 元。
- **阶段 state**：unpracticed 未实践 / perceptual 感性认识 / rational 理性认识 / practiced 实践检验 / consolidated 反复检验。
- **conditions**：适用条件、反例；“边界”是字段，不是类型。

## 4. 命令

```bash
kb --action init
kb --action import --discipline math --consent outline [--force]

kb --action add --title "TCP 三次握手" --discipline cs \
  --domain networking/transport --type principle --granularity atom \
  --state perceptual --context "刚看完抓包" --consent outline

kb --action list [--discipline cs] [--type principle] [--state rational] [--due] [--json]
kb --action show
kb --action review --id k-0001 --result pass|fail [--note "..."] --consent outline
kb --action due [--discipline math]
kb --action link --from k-0001 --to k-0002 --rel prereq --consent outline
kb --action export --to backup.json
```

- `show` 生成 `<EDU_HOME>/learner/knowledge.md`（表格视图）。
- `import` 读取 `blindspots.jsonl` / `progress.jsonl`；已有数据时必须 `--force`。
- 写操作都要 `--consent`；`list/show/due/export` 只读。

## 5. 复习

`kb review` 是**保持性检查**，不是新的飞跃：

- `pass`：只有 `practiced → consolidated`；其他阶段保持不变，只更新复习间隔；
- `fail`：回退一级（consolidated→practiced→rational→perceptual→unpracticed）；
- 字段：`review_count`、`last_reviewed`、`interval_days`、`ease`、`next_review`；
- `due` 查 `next_review <= today`；
- 不显示百分比、不排名。

## 6. 导入映射

| 旧字段 | 新字段 |
|---|---|
| blindspot kind concept/principle/skill/method | type concept/principle/procedure/method |
| blindspot kind boundary | type concept + `conditions="边界/适用条件（导入时待补）"` |
| status unknown/noticed | state unpracticed |
| status explained | state rational |
| status applied | state practiced |
| status verified | state consolidated |
| progress leap first/second | events first_leap/second_leap |
| progress.blindspot | 事件挂到对应 item，不新建 item |
| topic | domain（导入时暂用 topic；建议后续改成路径） |

- 所有导入项默认学科 `--discipline`（默认 `other`），可导入后改。
- 地图节点暂不导入；v0.16 再做。

## 7. 边界

- 不自动迁移；必须显式 `kb import`。
- 不替换旧命令；旧命令与 `kb` 不要双写。
- `forget --all` 会删除整个 `learner/`，包括 `knowledge.db`。
- `forget --session` 暂不同步 SQLite（数据库是并行实验）。
- SQLite 是二进制文件；用 `kb export` 备份为 JSON。
- 不做 Web UI、不做 FSRS、不做自动评分。

## 8. 下一步

- v0.16：把 `progress` / `blindspot` 切到 SQLite 适配层，JSONL 只做导出；
- 导入地图节点与先修关系；
- `forget --session` 同步 DB；
- 全局 `kb` 查询与画像视图。

## 9. 一句话

> 旧命令照常跑；新知识进 `knowledge.db`。一个知识项、多个事件、五维分类、可复习，不双写。
