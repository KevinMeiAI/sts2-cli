# KevinMeiAI fork: STS2 v0.107.1

This fork is based on upstream commit `084d1aa3d8e118ca7ce8d8774ad16d6be9c92367`.
The `compat/v0.107.1` branch targets **game v0.107.1, Steam build 23811903,
game commit 59260271**. The upstream `main` branch targets a newer engine;
do not assume the compatibility branch supports v0.111.0.

## Changes

- Report card-action outcomes from the engine, allowing Feral to return a played
  Claw to the same hand slot without producing a false failure.
- Return end-of-turn retention prompts to the caller instead of treating them
  as a deadlock. A genuinely stalled turn now returns an error, not a defeat.
- Validate card-selection counts and indices. Batch play respects multi-card
  prompts such as Room Full of Cheese.
- Capture event options before dispatching background work and observe completed
  task failures.
- Resolve the HTTP bridge's project and SDK paths and use the copied game DLLs.
- Read the engine dependency manifest so older engines do not repeatedly try
  to install the nonexistent Sentry.Godot dependency.
- Use the v0.107.1 damage API and optional initialization for newer assembly metadata.

## Verification

Validated on 2026-09-22 using macOS ARM64, .NET SDK 9.0.318 / runtime 9.0.20,
and Python 3.14.7:

- 74 pytest tests passed, including regressions for Feral, Well-Laid Plans,
  required two-card selection, and legacy dependencies.
- Five deterministic runs per character, using seeds `run_1` through `run_5`.
- All 25 reached a normal game-over state. Final logs contained no forced
  game-over fallback, unobserved task exception, or fatal/protocol error.
- All 25 runs were defeats with the simple batch policy. These checks establish
  tested execution compatibility, not a winning policy or exhaustive coverage.
- JSON stdin/stdout, localhost HTTP bridge, and the Chinese menu were exercised.
- The Steam installation's original engine DLL remained unchanged.

| Character | Completed | Wins |
|---|---:|---:|
| Ironclad | 5/5 | 0/5 |
| Silent | 5/5 | 0/5 |
| Defect | 5/5 | 0/5 |
| Regent | 5/5 | 0/5 |
| Necrobinder | 5/5 | 0/5 |

## Reproduce

Install the matching game, a .NET 9+ SDK, and Python 3.9+ first.
Game DLLs and machine-specific SDKs are not distributed in this repository.

```bash
./sts2 setup
python3 -m venv .venv
.venv/bin/python -m pip install pytest
./sts2 test -q
for character in Ironclad Silent Defect Regent Necrobinder; do
    ./sts2 check 5 "$character" || exit 1
done
```

Inspect stderr logs as well as the completed-run count. The inherited nullable
compiler warnings and unregistered pytest `slow` marker are non-failing warnings.

## 中文说明

本分支针对 v0.107.1（Steam 构建 23811903），经过 74 项测试及五个角色共 25 局验证。
自动测试策略全部战败，正常结束不代表通关。对局使用本机正版游戏引擎的副本，
没有游戏画面，也不会接管 Steam 游戏窗口。

Steam 更新游戏后，需要重新确认接口兼容性，再运行 `./sts2 setup` 并复测。
通用错误修复和 v0.107.1 专属兼容修改分别保存为独立提交，便于后续向上游贡献。

## First-act follow-up fixes

A manually played Ironclad run (`6BMMPCFQAJ`, ascension 0) exposed purchase
feedback and checkpoint bugs missed by the initial batch policy. The follow-up
fixes cache purchase receipt data, observe purchase results, represent sold-out
slots explicitly, and export Twin Strike hit counts. CLI checkpoints now replay
recorded commands and compare the complete saved state before reporting success.

Validation: 81 pytest tests passed, including the recorded first act, duplicate
purchases, full potion capacity, combat/pending-choice/Boss-reward checkpoints,
engine mismatch, replay divergence, and failed-save behavior. The required five
runs per each of the five characters also completed (25 defeats, no diagnostic
errors). These batch runs remain execution checks, not model-driven gameplay.
