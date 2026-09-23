# Claude Code A10 模型考场

[2026-09-23 技术故障修复与事件覆盖](arena-technical-failure-repair.md)：修复丛林迷宫合作选项的无头音效异常；技术故障后保留最后正常检查点，并从原生事件池自动枚举回归范围。

每个模型通过 Claude Code 操作真实游戏引擎的 headless 适配器。裁判启动游戏、记录动作、保存存档，并从原生状态计算成绩。正式试题为 Ironclad、Silent、Defect、Necrobinder 各一个随机种子，难度均为 A10。同一场考试中所有模型使用相同的四个种子。

先对每个模型进行最多 **600 秒的连通性试跑**，共用另外一个 Ironclad 练习种子。试跑不计正式成绩。正式单局时限默认未设置，必须在试跑后确定秒数或明确选择不限时；未设置时启动正式赛会被拒绝。

## 使用

依赖已安装的游戏引擎、已构建的适配器、Python 3.9+、Claude Code。当前集成验证版本为 Claude Code 2.1.280；每场考试冻结版本号、引擎/依赖/英文文本、适配器、考场代码和统一提示词的 SHA-256。更新后应新建一场考试，不能混用版本。

```bash
./sts2 arena --exam /absolute/path/exam-01/exam.json init

# stdin 输入 oneliner，按 Ctrl-D 结束。内容被解析为数据，不执行 shell。
# 不要把真实 key 直接放在命令行参数或 shell 历史里。
./sts2 arena --private-dir /absolute/private/path register model-a

./sts2 arena --private-dir /absolute/private/path models
./sts2 arena --exam /absolute/path/exam-01/exam.json verify
./sts2 arena --exam /absolute/path/exam-01/exam.json \
  --private-dir /absolute/private/path pilot model-a

# 试跑后，由考场负责人确定正式每局上限；示例为 3600 秒。
./sts2 arena --exam /absolute/path/exam-01/exam.json set-limits --seconds 3600
./sts2 arena --exam /absolute/path/exam-01/exam.json \
  --private-dir /absolute/private/path run model-a --case all
./sts2 arena --exam /absolute/path/exam-01/exam.json report

# 或在第一次正式尝试前选择不限时，每个模型最多两局并发。
./sts2 arena --exam /absolute/path/exam-01/exam.json set-limits --unlimited --concurrency 2
./sts2 arena --exam /absolute/path/exam-01/exam.json \
  --private-dir /absolute/private/path batch model-a model-b model-c
```

可接受的 oneliner 结构：`ANTHROPIC_BASE_URL=... ANTHROPIC_API_KEY=... claude --model ...`，也支持 `ANTHROPIC_AUTH_TOKEN`、`export A=...; ...; claude --model ...`、`--effort`。只接受明确的模型名和一个认证值。所有提供的模型别名必须指向同一个参赛模型。API key 保持 `x-api-key`，auth token 保持 Bearer，二者不会互相转换。拒绝管道、命令替换、任意脚本和附加 Claude 权限参数。

每个模型与题目只能启动一次，目录已存在时拒绝覆盖。`--case all` 顺序运行四局，遇到未完成或故障就停下供检查。任何需要重测的技术事故都应明确记录，并使用新的考试目录；考场不会自动重开、恢复或补考。

`batch` 按模型分别排队，一局结束后补上该模型的下一个角色，包含异常结束的情况；不会重试失败题目。`batch.lock` 防止重复调度。单一总控每五秒更新 `progress.json`、`README.md` 和 `leaderboard.json`；每局分别写自己的记录与检查点。`batch.json` 保存总控 PID 和冻结配置，`summary.json` 保存最终汇总。SIGINT/SIGTERM 会停止补位并收尾活跃子进程；该中断不能计成游戏死亡。不限时只取消整局墙钟截止时间，单次引擎命令和供应商请求仍可超时并单独报错。

每局都会替换 `X-Session-Id` 为新的 UUID，保留其他自定义头。会话 UUID 与 Claude PID 写入该局 `run.json`，可用于核验隔离与进程清理。

## 成绩规则

1. 单角色先比较原生 `TotalFloor`，即跨幕累计进入的楼层数，包含死亡所在层。
2. 同层先区分通关与失败。通关者比较自身剩余 HP / 最大 HP，越高越好。
3. 同层失败比较最终战斗中敌方总剩余 HP / 总最大 HP，越低越好。分母包括该场战斗中出现的所有不同敌人，包括已击杀敌人与召唤物；已击杀者按原生当前 HP（通常为零）记录。非战斗死亡没有敌方 HP，相关血量并列不强行排序。
4. 总榜要求四个正式题目均自然胜败结束，依次比较楼层之和、通关数、血量得分之和。血量得分为通关时的自身比例、失败时的 `1−敌方比例`。缺失血量证据的同分组保留并列。各角色单榜同时保留。
5. 超时、接口失败、模型主动提前结束、引擎/考场故障独立标记，不计为游戏死亡，不进入正式排名。记录它们的最后楼层用于排查。

`get_run_metrics` 在原生命令执行后读取最终 HP，不使用上一条决策快照。例如已验证的机器人死亡回合，出牌前敌人 61/155，闪电和玻璃充能球回合结束伤害后为 **54/155**，裁判记录后者。该只读命令不改变现有决策 JSON 和存档格式。

## 运行约束与留档

Claude Code 每次使用新的空工作目录、独立 HOME 和配置目录。所有内置工具关闭，仅允许 `get_state`、`get_map`、`act` 三个 MCP 工具；禁用技能、用户/项目设置、浏览器集成与会话恢复。使用 `restricted`、`dontAsk` 和严格 MCP 配置，无需 `dangerously-skip-permissions`。API key 模式额外使用 `bare`；Bearer 模式保留正确认证方式。启动日志中的工具列表若与白名单不符，裁判终止该次运行。

模型不能通过这些工具执行 shell、读文件、访问其他模型、改种子、重开、载入存档或调用 debug 命令。此约束针对参赛模型获得的工具权限；它不是防恶意本地操作系统用户的安全沙箱。哈希用于发现配置漂移，不是第三方不可篡改公证。接口返回的模型标识也只能作为供应商自报信息，不能独立证明路由器背后的实际模型。

每次运行保留：

- `game.jsonl`：原生请求/响应与时间戳；`engine.log`：引擎诊断。
- `current.json`：最新状态、原生计分数据；`checkpoint.save`：每个动作后的精确检查点，供考场负责人审计。
- `claude.jsonl` / `claude.stderr.log`：脱敏的 Claude Code 输出。
- `run.json` / `result.json`：版本、时间限制、状态、工具调用数、原生分数、接口自报模型、usage 与 Claude 估算费用。第三方接口的真实账单以供应商为准。
- `leaderboard.json` / `README.md`：正式榜单及所有运行摘要。

密钥只存入指定 private 目录，配置文件权限 `0600`；不会进入公开报告或仓库。模型配置目录默认 `.arena-private`，已在 `.gitignore` 排除。异常日志会替换已知密钥原文。请不要把原始 provider 配置或 private 目录公开。

## 验证

```bash
./sts2 test -q
RUN_CLAUDE_MOCK=1 ./sts2 test -q tests/test_arena_claude_mock.py
```

第二条通过本地回环模拟 Anthropic 接口，启动**真实 Claude Code 与真实游戏引擎**，验证 API key/Bearer、三工具白名单、一次开局、实际游戏动作、存档、密钥脱敏、提前结束与超时分类。使用假密钥，没有实际参赛模型推理，也不产生模型游戏成绩。需要允许本地回环端口。

接口参考：[Claude Code CLI](https://code.claude.com/docs/en/cli-reference)、[Claude Code MCP](https://code.claude.com/docs/en/mcp)、[MCP stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)。
