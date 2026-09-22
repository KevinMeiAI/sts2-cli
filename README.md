# sts2-cli

Fork of [wuhao21/sts2-cli](https://github.com/wuhao21/sts2-cli), maintained under
[KevinMeiAI](https://github.com/KevinMeiAI). The default `compat/v0.107.1` branch
contains tested fixes for terminal agents and the v0.107.1 game engine.
[Compatibility details and verification](docs/compatibility-v0.107.1.md).

本 Fork 的默认分支适配 **v0.107.1**，包含 agent 控制流程修复。
完成安装后，可以运行 `./sts2 menu`，或双击 `启动游戏.command` 进入中文菜单。

```bash
./sts2 setup         # first-time setup; requires the game, Python, and .NET SDK
./sts2 play          # interactive terminal game
./sts2 json          # persistent JSON stdin/stdout for coding agents
./sts2 bridge 9876   # HTTP commands on http://127.0.0.1:9876
```

The launcher uses a project-local `.runtime/dotnet` SDK when present, otherwise
the SDK on PATH or in `~/.dotnet-arm64` / `~/.dotnet`. No SDK or game DLLs are bundled.

<details open>
<summary><b>English</b></summary>

A CLI for Slay the Spire 2.

Runs the real game engine headless in your terminal through an adapter that replaces rendering and UI interactions. Everything is unlocked from the start: all characters, cards, relics, potions, and ascension levels — no timeline progression required. See the compatibility report for the tested version and coverage.

![demo](docs/demo_en.gif)

## Setup

Requirements:
- [Slay the Spire 2](https://store.steampowered.com/app/2868840/Slay_the_Spire_2/) on Steam
- [.NET 9+ SDK](https://dotnet.microsoft.com/download)
- Python 3.9+

```bash
git clone https://github.com/KevinMeiAI/sts2-cli.git
cd sts2-cli
./setup.sh      # copies DLLs from Steam → IL patches → builds
```

Or just run `python3 python/play.py` — it auto-detects and sets up on first run.

This branch is tested with **v0.107.1 (Steam build 23811903)**. After updating the
installed game in Steam, check adapter compatibility before rerunning `./sts2 setup`
to refresh the engine DLLs, patches, and official English/Chinese localization.
Other game versions may require code changes.

For a compatibility check, run `python3 python/play_full_run.py 5 Ironclad`
(repeat for Silent, Defect, Regent, and Necrobinder). A completed run reaches
victory or defeat; crashes, stalls, and timeouts return a nonzero exit code.

## Play

```bash
python3 python/play.py                        # interactive (Chinese)
python3 python/play.py --lang en              # interactive (English)
python3 python/play.py --ascension 10         # Ascension 10
python3 python/play.py --character Silent      # play as Silent
```

Type `help` in-game:

```
  help     — show help
  map      — show map
  deck     — show deck
  potions  — show potions
  relics   — show relics
  quit     — quit

  Map:     enter path number (0, 1, 2)
  Combat:  card index / e (end turn) / p0 (use potion)
  Reward:  card index / s (skip)
  Rest:    option index
  Event:   option index / leave
  Shop:    c0 (card) / r0 (relic) / p0 (potion) / rm (remove) / leave
```

## JSON Protocol

For programmatic control (AI agents, RL, etc.), communicate via stdin/stdout JSON:

```bash
dotnet run --project src/Sts2Headless/Sts2Headless.csproj
```

```json
{"cmd": "start_run", "character": "Ironclad", "seed": "test", "ascension": 0}
{"cmd": "action", "action": "play_card", "args": {"card_index": 0, "target_index": 0}}
{"cmd": "action", "action": "end_turn"}
{"cmd": "action", "action": "select_map_node", "args": {"col": 3, "row": 1}}
{"cmd": "action", "action": "skip_card_reward"}
{"cmd": "quit"}
```

Each command returns a JSON decision point (`map_select` / `combat_play` / `card_reward` / `rest_site` / `event_choice` / `shop` / `game_over`). All names are in English.

## Exact CLI checkpoints

`write_continue_save` and `quit` with a `path` now write a versioned CLI checkpoint.
It stores the concrete seed, game commands, engine fingerprint, and full expected
state. `load_save` replays those commands and verifies that the exact saved decision
was restored, including combat turns, pending card choices, and Boss rewards.
Engine mismatches and replay divergence are explicit errors. Restore takes time
proportional to the recorded commands. Existing native game saves remain readable.
These CLI checkpoint files are not Steam game save files.

```json
{"cmd":"get_state"}
{"cmd":"write_continue_save","path":"saves/act1.save"}
{"cmd":"load_save","path":"saves/act1.save"}
```

中文：现在可以在战斗、选牌或 Boss 奖励界面精确保存。读取时会重放并核对完整状态；
引擎不匹配或状态发生偏差会明确报错。此存档供 CLI 使用，不可放入 Steam 游戏存档目录。

Shop sold-out slots retain their index and `is_stocked: false`, with no fake name
or price. Clients should filter on `is_stocked`. Attack `damage_by_target` includes
`repeat` and `total_damage`; it previews attack damage before final HP-loss modifiers
such as Block and Slippery. It is not a promise of how much HP the target will lose.

## A10 event coverage and known limits

See [Act 2 continuation and fixes](docs/act2-validation.md) for the same saved
Ironclad A0 and Necrobinder A10 runs continued through their second boss, including
Crystal Sphere support and combat/reward compatibility fixes.

See [Silent / Necrobinder A10 validation](docs/a10-event-coverage.md) for manually
played first acts, the event-branch survey, repairs and remaining limitations.
Power summaries now expose live `vars` and `description_is_template`. Shop relics
and potions expose their effect variables; event string values remain strings.
Event options include `is_supported` and `unsupported_reason` separately from
the game's `is_locked`. Unsupported choices return `code: unsupported_interaction`
and `state_unchanged: true` before their effects run. Crystal Sphere's grid
minigame and Trial's abandon confirmation are not implemented yet.

中文：本轮已修复事件崩溃、状态说明、商店效果参数和飞靴地图选项；详见上方报告。
水晶球小游戏及审判的放弃确认尚未接入，CLI 会在执行效果前明确返回不支持。

## Game Logs

Every run is automatically logged to `logs/` as a JSONL file (one JSON per line), recording each game state and action with timestamps. Logs older than 7 days are cleaned up automatically.

```bash
python3 python/play.py --no-log    # disable logging
```

**When filing a bug report, please attach the relevant log file from `logs/`** — it contains the full step-by-step game state needed to reproduce the issue.

## Supported Characters

| Character | Status |
|---|---|
| Ironclad | Fully playable |
| Silent | Fully playable |
| Defect | Fully playable |
| Necrobinder | Fully playable |
| Regent | Fully playable |

## Architecture

```
Your code (Python / JS / LLM)
    │  JSON stdin/stdout
    ▼
src/Sts2Headless (C#)
    │  RunSimulator.cs
    ▼
sts2.dll (game engine, IL patched)
  + src/GodotStubs (replaces GodotSharp.dll)
  + Harmony patches (localization)
```

</details>

<details>
<summary><b>中文</b></summary>

杀戮尖塔2的命令行版本。

在终端里运行真实游戏引擎，通过适配层替代画面与界面交互。所有内容从一开始就全部解锁：全角色、全卡牌、全遗物、全药水、全渐进难度等级，无需时间线进度。已验证的版本与覆盖范围见兼容性报告。

![demo](docs/demo_zh.gif)

## 安装

需要：
- [Slay the Spire 2](https://store.steampowered.com/app/2868840/Slay_the_Spire_2/) (Steam)
- [.NET 9+ SDK](https://dotnet.microsoft.com/download)
- Python 3.9+

```bash
git clone https://github.com/KevinMeiAI/sts2-cli.git
cd sts2-cli
./setup.sh      # 从 Steam 复制 DLL → IL patch → 编译
```

或者直接运行 `python3 python/play.py`，首次会自动完成 setup。

本分支已验证 **v0.107.1（Steam 构建 23811903）**。通过 Steam 更新游戏后，
请先检查接口兼容性，再运行 `./sts2 setup`，同步游戏 DLL、补丁和官方中英文文本。
其他游戏版本可能需要修改适配代码。

可运行 `python3 python/play_full_run.py 5 Ironclad` 检查兼容性，并依次替换为
Silent、Defect、Regent、Necrobinder。“完成”指正常胜利或死亡；崩溃、卡住和超时
会返回非零退出码。

## 玩

```bash
python3 python/play.py                        # 中文交互模式
python3 python/play.py --lang en              # English
python3 python/play.py --ascension 10         # 渐进难度 10
python3 python/play.py --character Silent      # 选择静默猎手
```

游戏内输入 `help` 查看所有命令：

```
  help     — 帮助
  map      — 显示地图
  deck     — 查看牌组
  potions  — 查看药水
  relics   — 查看遗物
  quit     — 退出

  地图:    输入编号 (0, 1, 2)
  战斗:    输入卡牌编号 / e 结束回合 / p0 使用药水
  奖励:    输入卡牌编号 / s 跳过
  休息:    输入选项编号
  事件:    输入选项编号 / leave 离开
  商店:    c0 买卡 / r0 买遗物 / p0 买药水 / rm 移除 / leave 离开
```

## 角色支持

| 角色 | 状态 |
|---|---|
| 铁甲战士 (Ironclad) | 完全可玩 |
| 静默猎手 (Silent) | 完全可玩 |
| 故障机器人 (Defect) | 完全可玩 |
| 亡灵契约师 (Necrobinder) | 完全可玩 |
| 储君 (Regent) | 完全可玩 |

## JSON 协议

除了交互模式，也可以通过 stdin/stdout JSON 协议编程控制（写 AI agent、RL 训练等）：

```bash
dotnet run --project src/Sts2Headless/Sts2Headless.csproj
```

```json
{"cmd": "start_run", "character": "Ironclad", "seed": "test", "ascension": 0}
{"cmd": "action", "action": "play_card", "args": {"card_index": 0, "target_index": 0}}
{"cmd": "action", "action": "end_turn"}
{"cmd": "action", "action": "select_map_node", "args": {"col": 3, "row": 1}}
{"cmd": "action", "action": "skip_card_reward"}
{"cmd": "quit"}
```

每个命令返回一个 JSON decision point（`map_select` / `combat_play` / `card_reward` / `rest_site` / `event_choice` / `shop` / `game_over`），所有名称为英文。

## 游戏日志

每局游戏会自动记录到 `logs/` 目录下的 JSONL 文件中，包含每一步的游戏状态和操作，附带时间戳。超过 7 天的旧日志会自动清理。

```bash
python3 python/play.py --no-log    # 关闭日志
```

**提交 bug 报告时，请附上 `logs/` 中对应的日志文件** — 它包含了复现问题所需的完整游戏步骤。

## 架构

```
你的代码 (Python / JS / LLM)
    │  JSON stdin/stdout
    ▼
src/Sts2Headless (C#)
    │  RunSimulator.cs
    ▼
sts2.dll (游戏引擎, IL patched)
  + src/GodotStubs (替代 GodotSharp.dll)
  + Harmony patches (本地化)
```

</details>
