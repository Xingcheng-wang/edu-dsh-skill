# 知识盲区：记录、复习、转成进步

## 0. 一句话

盲区不是耻辱，是资产：记下来，定期复习；能解释、能应用、复习确认后，再转成进步记录。

## 1. 什么算盲区

- 用户明确说“这个我不懂 / 没学过 / 说不清 / 每次到这里就卡”。
- 做题或实践暴露出的重复缺口。
- 影响当前目标的先修缺口。

**不是所有错误都记**：偶发手误、一次口误、没兴趣的细节，不记。用户指定要记，就记。

## 2. 颗粒度：五类基本分类

| kind | 中文 | 说明 | 例子 |
|---|---|---|---|
| `concept` | 概念 | 是什么、定义、区别 | 极限的定义 |
| `principle` | 原理 | 为什么、因果、证明 | 为什么极限不要求该点有定义 |
| `skill` | 技能 | 怎么做、操作 | 用 ε-δ 写一个证明 |
| `method` | 方法 | 先做什么、流程 | 判断极限是否存在的一般步骤 |
| `boundary` | 边界 | 什么时候不成立、反例 | 什么时候不能用洛必达 |

- 不确定就问用户：“这个盲区更像概念、原理、技能、方法，还是边界？”
- 不要用“基础差 / 不熟”当颗粒度；那是判断，不是分类。

## 3. 状态机：按认识论环节

```
unknown（未识别）
   ↓
noticed（已发现）
   ↓ resolve --leap first
explained（能解释，第一次飞跃）
   ↓ resolve --leap second
applied（能应用，第二次飞跃）
   ↓ status --status verified（复习通过）
verified（已确认）
```

- **回退**：`verified` 复习失败 → `noticed`；`noticed` 重新不确定 → `unknown`。
- `status` 只能设 `unknown / noticed / verified`；`explained / applied` 必须走 `resolve`，并同时生成进步记录。
- **不能跳级**：`verified` 之前必须是 `applied`。
- `drop` 删除（不再追踪）；不要用删除假装解决。

## 4. 文件与格式

- 文件名：**`<学习主线>（主线）知识盲区.md`**，放在 `<EDU_HOME>/learner/`。
  - 例：`微积分（主线）知识盲区.md`、`网络（主线）知识盲区.md`。
- 数据：`<EDU_HOME>/learner/blindspots.jsonl`。
- 每条一个引用块，不用标题：

```markdown
> 2026-11-20 · bs-0001 · 概念 · 已发现
> 盲区：为什么极限不要求该点有定义
> 上下文：在导数定义那一步，他说不出为什么可以不管该点

> 2026-11-21 · bs-0001 · 概念 · 能解释
> 盲区：为什么极限不要求该点有定义
> 上下文：在导数定义那一步，他说不出为什么可以不管该点
> 关联进步：p-0003
```

- 解决后写 `关联进步：p-xxxx`；进步记录里同时写 `> 盲区：bs-xxxx`。
- 旧记录保留状态历史？当前只保留最新状态；状态变化写入 `updated`，避免文档膨胀。

## 5. 命令

```bash
blindspot --action add \
  --title "为什么极限不要求该点有定义" \
  --kind concept \
  --context "在导数定义那一步，他说不出为什么可以不管该点" \
  --topic calculus --node limits --consent outline

blindspot --action list [--status noticed|explained|applied|verified] [--json]
blindspot --action show [--json]
blindspot --action status --id bs-0001 --status noticed|unknown|verified --consent outline
blindspot --action resolve --id bs-0001 --leap first|second \
  --context "..." --summary "..." [--evidence "..."] --consent outline
blindspot --action drop --id bs-0001 --consent outline
```

- `resolve --leap first` → `explained`；`--leap second` → `applied`；同时创建进步记录。
- `drop` 删除盲区；已生成的进步记录保留（历史不抹掉）。

## 6. 定期复习

- 用 `blindspot list --status noticed` / `explained` / `applied` 找待复习项。
- 复习时先让他自己说/做，不要直接给答案；失败就把状态回退到 `noticed`，并更新 `updated`。
- 通过复习才设 `verified`；不要用“我讲过了”代替。
- `state` 显示未确认盲区（最多 5 条）；`doctor` 显示总数。

## 7. 和进步记录的联动

- **盲区 → 进步是必要过程**：`resolve` 必须带上下文、概述和飞跃，生成一条 progress 记录。
- 双向链接：盲区有 `progress_id`，进步记录有 `blindspot`。
- 删除盲区不删除进步记录；`forget --session` 会删除该会话新增的盲区，并清理死链（对应进步被删时，盲区回到 `noticed`）。

## 8. 反模式

- 把每个小错都记成盲区，数据库变成噪音。
- 颗粒度不清就硬填；不问用户。
- 跳级：`noticed` 直接 `verified`；没生成进步就标 `explained / applied`。
- 用删除假装解决。
- 把盲区数量当绩效、做排行榜。
- 复习时直接给答案，不让他先说。
- 记录“他很笨 / 基础差”这类人格判断。

## 9. 认知基本画像

四类记录拼起来，就是一个简单的本地数据库：

- **知识地图**：他在哪、下一步是什么。
- **知识盲区**：他还不会什么、什么颗粒度、复习到哪一步。
- **认知进步**：他会了什么、哪次飞跃、证据是什么。
- **状态与目标**：他想去哪、能投入多少。

不导出分数，只导出记录；不排名，只复习。

## 10. 一句话

> 盲区是待办的知识债，不是人格判决；能解释、能应用、复习确认后，转成进步记录。
