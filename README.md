# edu-dsh

> 一个把对话变成“老师教一个具体的人”的 Agent Skill。
> 唯一目标：**提升用户的能力**，而不是把内容讲完。

- 版本：0.1.0
- 运行环境：Python 3.10+，仅标准库
- 形态：Agent Skill（`SKILL.md` + 5 份参考 + 1 个本地 CLI + 冒烟测试）
- 许可：MIT

---

## 一、它是什么

开启之后，模型的目标函数从“输出最像答案的回答”换成“让这个人的能力往上走一点”。

每一轮结束时，只问三个问题：

- 他多会了什么？
- 他多做了什么？
- 他还想不想继续？

回答只是手段。用户没变，回答再漂亮也是零分。

## 二、它不是什么

- 不是课程生成器，不是讲义机；
- 不是任务发布器，不是作业批改；
- 不是测评系统（不给分、不排名、不报“掌握度”）；
- 不是固定教学脚本（没有“先 A 后 B 再 C”）；
- 不是学习风格匹配、人格画像、积分体系。

这些不是道德姿态，是**目标函数的正确性条件**：一旦把它们当成目标，就会得到一个“动作全对、用户没变”的系统。

## 三、三层设计

```
不变量（3 条）      增量 / 主权 / 诚实
判断层（8 张卡）    邀请、演示、预测、对比、追问、直接教、一起做、停
记忆层（本地文件）  profile / state / glossary / sessions / deltas
```

- **不变量**写在 `SKILL.md`，任何情况不破。
- **判断层**写在 `references/moves.md`：每张卡有“何时用 / 怎么做 / 风险 / 何时停”。一次只选一张。
- **记忆层**由 `scripts/edu_dsh.py` 维护：目标、会什么、卡在哪、术语、会话、每轮增量。没有它，“个性化”就只是一句口号。

## 四、快速开始

```bash
git clone https://github.com/Xingcheng-wang/edu-dsh-skill.git ~/.claude/skills/edu-dsh
python ~/.claude/skills/edu-dsh/scripts/edu_dsh.py init
python ~/.claude/skills/edu-dsh/scripts/edu_dsh.py doctor
```

然后对 Agent 说“用教育模式……”，或使用 `/edu-dsh`。

第一次对话，模型会先问一句记录偏好（不记 / 只记概要 / 记原话），默认只记概要。

```
你：我想弄懂为什么 RL 里的 PPO 要 clip
老师：先别背公式。你手上有个策略，更新太猛会怎样？……
```

## 五、工作区

默认 `~/.edu-dsh`，可用 `EDU_HOME` 覆盖。

```
<EDU_HOME>/
├── config.json
├── learner/
│   ├── profile.md       # 他是谁、想做什么、怎么学
│   ├── state.json       # 目标、能做什么、卡在哪、下一个动作
│   └── glossary.md      # 已解释过的术语
├── notes/               # 长笔记、网页缓存
├── sessions/NNNN-YYYY-MM-DD-topic.md
├── deltas.jsonl         # 每轮：会了什么 / 做了什么 / 还想继续
└── backup/              # forget 前自动备份
```

## 六、命令

```bash
edu_dsh.py init / doctor / state / records
edu_dsh.py goal  --add "..." | --drop 1 | --list          --consent outline
edu_dsh.py cap   --add --statement "能解释 X" --basis "..." --confidence medium
edu_dsh.py question --add "为什么 Y？"
edu_dsh.py glossary --add --term ZPD --full "..." --plain "..." --example "..."
edu_dsh.py note  --topic calculus/limits --summary "..." --next "..."
edu_dsh.py delta --learned "..." --did "..." --want "..."
edu_dsh.py export --to ~/edu-backup.zip
edu_dsh.py forget --session 0001 [--apply] | --all [--apply]
edu_dsh.py config [--set retrieval_mode=local]
```

- 所有写操作都带 `--consent`；`off` 时 CLI 直接拒绝写入。
- `forget` 默认预览，`--apply` 才删除，删前自动备份。
- 会话编号单调递增，删除后不复用。
- 非法 `retrieval_mode` 自动回退 `local`（失败关闭，不是失败放行）。

## 七、评测：只看用户侧

| 因变量 | 观测什么 | 不能拿什么充数 |
|---|---|---|
| 会了什么 | 换场景能用、能找错、能说边界 | 复述定义、点头 |
| 做了什么 | 他自己动手的产物 | 模型代做、只看一遍 |
| 还想继续 | 主动追新问题、回到旧问题 | 被悬念勾住、礼貌说想 |

单条回复测不了学习，测量单位是**会话**和**会话序列**。
红线（一票否决）：`local` 联网、编造来源、未经同意存原话、评分/排名/打卡、机械任务、用户说停还追问、传播 neuromyth。

跑冒烟测试：

```bash
python tests/selftest.py     # 42 项：同意门槛、编号、备份、导出、失败关闭
```

## 八、和上一版（education-mode v0.8）的区别

不是改参数，是砍结构：

| 上一版 | edu-dsh | 为什么 |
|---|---|---|
| 20 条硬规则 | 3 条不变量 | 全是“硬”等于没有硬 |
| 54 个“必须出现”用例 | 3 个用户侧因变量 + 7 条红线 | 测模型动作 ≠ 测用户变化 |
| 5 个模式文件 + 7 个教学法文件 | 1 张路由表 + 8 张动作卡 + 1 份学习机制 | 判断力靠示例和判据，不靠文件数 |
| 强制理论大纲、强制术语表 | 大纲不强制（可只在对话/笔记里）；术语表保留但由 CLI 去重 | 产物服务于教学，不是教学服务于产物 |
| 1961 行 CLI + BM25 索引 | 870 行单文件 CLI，无索引（本地文件直接读） | 记忆要的是“记住这个人”，不是“建一个检索系统” |
| `outline` 同意级别仍写理解状态 | `off` 硬拒绝；`outline` 只写转述 | 同意级别必须可执行，不能靠自觉 |

## 九、文件

```
edu-dsh/
├── SKILL.md                 # 入口：目标函数、不变量、自检、失败的样子
├── references/
│   ├── learning.md          # 人怎么学 + 怎么会“看起来学会”
│   ├── moves.md             # 8 张动作卡
│   ├── state.md             # 工作区、命令、同意、降级
│   ├── examples.md          # 3 个好对话 + 2 个坏对话
│   └── eval.md              # 用户侧评测协议
├── scripts/edu_dsh.py       # 记忆、同意、导出、遗忘
└── tests/selftest.py        # 端到端冒烟
```

## 十、限制

- 不内置向量检索：本地资料直接交给宿主的文件工具读。
- 非多模态：看不到图、表格截图、扫描页；不假装看过。
- 记忆的质量取决于记下来的东西；没记的，下次就不知道。
- `--consent` 是模型必须传的参数：它能挡住“off 还写”，但挡不住模型编造一个 outline。
- 教学不能被完全自动化。这个 skill 是脚手架，不是流水线。

## License

[MIT](LICENSE)
