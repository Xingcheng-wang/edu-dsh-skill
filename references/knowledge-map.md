# 知识地图：让他知道“现在在哪”

地图是导航，不是课表。
它回答三个问题：**我们在哪？上游是什么？下游是什么？**

## 1. 什么时候建

- 系统学习、精读、技能训练**第一次进入**时；或用户说“帮我理清这个领域”。
- 好奇心模式**不建全图**：只给一行微地图（上游 → 当前 → 下游）。
- 用户不想建，就不建——地图是工具，不是门槛。

## 2. 粒度

- **5–9 个节点**，一个节点约一次会话能碰。超过 12 个，拆图或裁剪。
- 节点分两类：`trunk`（主干，必须经过）和 `branch`（侧枝，可以晚点或跳过）。
- 节点分四种：`concept`（概念）、`skill`（技能）、`method`（方法）、`problem`（问题/案例）。

不要把“第一章、第二章”当节点——那是目录，不是知识结构。
好节点长这样：「极限」「导数」「链式法则」「用导数解释优化」。

## 3. co-create：不要单方面画图

1. **提草案**：先给 5–9 个节点，一句话说明每个为什么在这。
2. **问三句**：「缺什么？」「哪个不该在这？」「你想先走哪条？」
3. **改**：按他的回答增删、调整顺序、标主干/侧枝。
4. **落盘**：`map new` → `map add` → `map link` → `map position`；然后给他看一版 `map.md`。

示例对话：

> 我：我先把微积分拆成五个节点：函数、极限、导数、积分、微分方程。极限是导数的入口，积分是导数的逆运算。缺什么吗？
> 他：我想先学导数，为了做优化。
> 我：那我们把「优化」加成一个侧枝，主干顺序不变，但你可以先从导数进——只是极限那块会欠着，遇到时我提醒你。这样行吗？

## 4. 状态词表（描述，不是分数）

| 状态 | 意思 |
|---|---|
| `unseen` | 还没碰过 |
| `touched` | 见过、听过，但没自己做过 |
| `practicing` | 正在练，能做一部分 |
| `can-do` | 能自己做出来、能解释、能迁移 |

没有 0–3 分，没有百分比，没有掌握度。

## 5. 边

- `prereq`：from 是 to 的先修（`functions → limits`）。
- `part-of`：from 是 to 的一部分。
- `contrast`：易混对照（`极限 ↔ 连续`），渲染时单独列。

## 6. 渲染（`map.md`）

```md
# 知识地图：微积分
方向：理解变化与累积

你在这里：极限 —— 导数的入口
上游：函数
下游：导数
下一步：用 epsilon-N 说清楚

## 主干
[ ] 函数
  [~] 极限   ← 你在这里
    [ ] 导数

## 侧枝 / 对照
- 极限 ↔ 连续

## 开放问题
- 为什么极限不要求该点有定义？（极限）
```

规则：不显示完成率、剩余数量、进度条；`position` 只标「你在这里」。

## 7. 每轮一句话 + 会话后更新

- 每轮开头（或切入正题时）一句：
  > 我们在「微积分」的「极限」——它上游是函数，下游是导数。
- 会话结束按实际进展更新：
  - 他能自己做出来了 → `map status --status can-do`
  - 只是见过 → `touched`
  - 位置换了 → `map position --node ... --why ... --next ...`
  - 新问题 → `question --add ... --node ...`

**按兴趣推进，不按地图顺序推进。** 他想跳，就跳；提醒先修，但不拦。

## 8. 三个例子

**微积分**：函数 → 极限 → 导数 → 积分；侧枝：优化、微分方程；对照：极限 vs 连续。

**FPGA**：数字逻辑 → Verilog → 时序 → 状态机 → 上板调试；侧枝：综合与约束；对照：阻塞 vs 非阻塞赋值。

**读论文**：问题 → 方法 → 证据 → 结论 → 局限；侧枝：相关工作；对照：本文 vs 基线。

## 9. 反模式

- 把地图当课表：显示完成率、剩余节点、催进度。
- 把地图倒给用户当待办：那不是地图，是作业。
- 建全学科地图：太大，没人看。
- 模型单方面定图：用户没有所有权。
- 用地图阻止跑题：「你还没学完这个」。
- 地图长期不更新：位置永远是第一天。

## 10. 命令速查

```bash
map --action new      --topic calculus --title 微积分 [--goal "..."] --consent outline
map --action add      --topic calculus --node limits --title 极限 [--kind concept] [--role trunk] --consent outline
map --action link     --topic calculus --from functions --to limits [--rel prereq] --consent outline
map --action status   --topic calculus --node limits --status practicing --consent outline
map --action position --topic calculus --node limits --why "导数的入口" --next "..." --consent outline
map --action drop     --topic calculus [--node limits] --consent outline
map --action show     [--topic calculus] [--json]
```
