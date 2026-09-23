# A10 arena: Jungle Maze technical failures

The 2026-09-23 official batch encountered the same native exception in three
games. The owner voided the batch; its scores are excluded and all contestant
processes were stopped. No replacement seeds or paid model attempts were started
during this repair.

| Model | Character | Floor | HP at interruption | Trigger |
|---|---|---:|---:|---|
| deepseek-flash | Silent | 9 | 29/70 | Jungle Maze Adventure → Join Forces |
| deepseek-flash | Defect | 4 | 52/82 | Jungle Maze Adventure → Join Forces |
| glm-5.3-flash | Silent | 5 | 34/70 | Jungle Maze Adventure → Join Forces |

## Cause and repair

In v0.107.1, `JungleMazeAdventure.SafetyInNumbers` calls
`NDebugAudioManager.Instance.Play("hey.mp3", ...)` before awarding gold. IL
inspection confirms an unconditional `callvirt` at offset `0x0028` in the async
state machine. The audio singleton is absent without a Godot scene, so the call
throws `NullReferenceException` before `PlayerCmd.GainGold` runs.

The adapter replaces this one audio call with a static no-op that accepts the
null receiver. It preserves the native wait, gold calculation, RNG and event
completion instructions. The patch checks the method and call shape at startup
and fails visibly if a future engine changes them. Neither the installed Steam
DLL nor the CLI's already patched engine DLL is modified by this fix.

The arena now also preserves the last healthy checkpoint after a native technical
fault and writes the failing request/response into `fault.json`. Previously it
could overwrite the checkpoint with replay history containing a failed action.
The attempt remains frozen; this change does not introduce automatic recovery,
rerolls or gameplay retries.

## Event coverage

The previous hand-maintained event sweep omitted Jungle Maze Adventure. The
new read-only `list_events` command enumerates the installed engine's native
event pools: 57 ordinary events and 8 ancients in the tested version. This
diagnostic command is not exposed through the contestant MCP tools.

`scripts/sweep_events.py` probes each event with Ironclad, Silent, Defect and
Necrobinder at A10 in isolated native processes. It tries every initially
unlocked option, resolves later selections with a deterministic policy, and
checks an exact state/metrics checkpoint restore for every successful branch.

Results: **260 event entries, 556 successful branches and 556 exact checkpoint
restores; no native errors or exceptions in 1,373 engine/restore logs**.

Full regression: **172 tests passed in 368.43 seconds**, including real Claude
Code against a local mock provider. The only warning is the pre-existing
unregistered pytest `slow` marker. No paid model API was used.

These are synthetic coverage probes, not model scores. The sweep stops when an
event hands off to combat, and does not enumerate every follow-up combination,
seed, inventory or unlock condition. Separate existing regressions cover combat,
shops, all three acts, character mechanics and terminal scoring.

## Reproduce

```bash
./sts2 build
./sts2 test -q tests/test_arena_event_failures.py tests/test_arena_fault_checkpoint.py
python3 scripts/sweep_events.py --output /absolute/path/new-event-audit --workers 4
RUN_CLAUDE_MOCK=1 ./sts2 test -q
```

The three original action sequences are retained as regression fixtures. They
reproduce the failure before the fix, and afterward verify one gold award,
unchanged HP/deck/relics, map progression and exact checkpoint restoration.
Both Jungle Maze choices are also tested with all four contestant characters.
The Claude mock tests use a local fake provider and dummy credentials.
