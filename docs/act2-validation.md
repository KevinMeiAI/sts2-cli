# Continuing the saved runs through Act 2

Engine: **v0.107.1**, Steam build **23811903**. Date: **2026-09-22**.

## Actual runs

The same assistant manually chose each route, event option, card, target and
potion. The JSON transport only forwarded requests and recorded responses. These
are continuations of two existing Act 1 wins, with their original seeds and
ascensions. No seed reroll, debug room entry, stat editing or automated playing
policy was used in either real run. Both stop at the **Act 2 Boss card reward**;
neither entered Act 3.

| Character | Seed | Ascension | Act 1 checkpoint HP | Act 2 result |
| --- | --- | --- | --- | --- |
| Necrobinder | `WWSC86QMRD` | 10 | 22/66 | Kaiser Crab defeated on floor 16, round 10; **6/66 HP**, 96 gold, 27 cards |
| Ironclad | `6BMMPCFQAJ` | 0 (original difficulty) | 58/80 | Kaiser Crab defeated on floor 16, round 9; **16/83 HP**, 230 gold, 31 cards |

Necrobinder visited Darv/Astrolabe, two shops, Colossal Flower, Crystal Sphere,
rest sites and a treasure room. Combat included Tunneler, Bowlbugs, The Obscura,
Exoskeletons and Kaiser Crab. Crystal Sphere used the paid option and three
manually chosen big reveals; no prize was fully uncovered.

Ironclad visited Pael, Spirit Grafter, Field of Man-Sized Holes, Self-Help Book,
Colorful Philosophers, The Lantern Key, a shop and rest sites. It obtained Silent
cards, used Goopy/Swift/Perfect Fit enchantments, won the Mysterious Knight event
fight and Decimillipede elite, and used Feed to raise max HP to 83. Combat also
covered Exoskeletons and Ovicopter's eggs/minions. Perfect Fit does not guarantee
an opening-hand draw; the native shuffle hook excludes initial shuffling. This
was checked, not changed.

These two successes are **not win-rate evidence**. They both rolled Hive/Kaiser
Crab and do not cover every Act 2 route, boss, character or event branch.

## Defects found and repaired

| Area | Observed problem | Repair and verification |
| --- | --- | --- |
| Act transition healing | Adapter healing followed by native Ancient healing granted excess HP; the adapter also rounded differently. Necrobinder went 22 → 58 → 64. | Remove the duplicate heal. The native A10 transition remains at 22 HP until Ancient entry, then heals to **57** once. A0 heals 58 → 80. Exact snapshots before/inside Ancient and repeated reads are tested. |
| Ancient navigation | Initial map choices allowed bypassing the Ancient and its native transition behavior. | Require the starting Ancient, reject skipping/re-entry without changing state. |
| Crystal Sphere | Both options were previously explicitly unsupported. | Implement the native minigame's fog grid, small/big reveal actions, payment/curse branches and asynchronous completion. Tests check hidden-content non-disclosure, invalid actions, unchanged rejected states and exact mid-grid/final saves. |
| Kaiser Crab initialization/death | Missing `CanvasItem.SetVisible` and scene/audio singleton dependencies stopped startup/death. A startup failure was even misclassified as victory and granted rewards. | Add the missing stub; replace only scene background/animation/audio methods. Preserve native power setup, attacks, facing, rage, damage and kills. Require native `CombatRoom.IsPreFinished` before granting rewards or allowing `proceed`. Verify two real wins and a separate synthetic boss lifecycle test. |
| Decimillipede final death | Death VFX referenced missing `Node.GetIndex(bool)`, interrupting the final lethal card. | Add the stub API; preserve native segment death, revival and combat completion. Replay verifies an actual segment revival and subsequent victory. |
| The Lantern Key reward | The event's special card reward was silently ignored, while ordinary gold/cards/potions worked. | Collect native `SpecialCardReward` alongside other fixed rewards. Verify exactly one Lantern Key in the deck, unchanged repeated reads and exact restoration. |
| Attack previews | Pull from Below showed a hit at zero calculated hits; Osty damage was omitted; Dagger Spray lacked its second hit; Spite always displayed its maximum hit count. | Preserve zero calculated values, export Osty damage, account for fixed two-hit attacks and use Spite's native HP-loss predicate. Compare previews against actual damage and test Rattle as a nonregression case. |
| Failed checkpoint retry | Retrying a divergent restore in the same process could hang on leftover singleton tasks. | Reject further commands (except quit) with a clear fresh-process instruction after a replay failure. Pre-replay validation errors remain retryable. |
| Boss labels | Encounter-only boss names could leak an unresolved `.name` key. | Fall back to the encounter title in state/map output. |

Fixes are in adapter source, Godot stubs and in-memory Harmony patches. This work
did not modify the Steam game DLL or the already setup-patched CLI engine DLL.
The CLI engine SHA-256 remains
`805c631cb6b400c5d5b18edb9f60ed54d797eb65fbc776a01162b50b6cafe724`.

## Recovery and evidence boundaries

Discovery traces and failed checkpoints were preserved separately. Technical
restarts returned to the same checkpoint immediately before the faulty operation,
then replayed the same gameplay decision. The duplicate-heal discovery was
restarted from the unchanged Act 1 checkpoint. The fake boss reward was discarded;
the successful Necrobinder boss battle began from its genuine pre-boss map state.
The Crystal Sphere entry snapshot received only the new support flags needed for
its changed presentation schema; HP, gold, deck and gameplay commands were not
edited. A first presentation migration omitted a null field and correctly failed
strict equality; a fresh process with the correct schema restored it.

The successful command fixtures contain **372 Ironclad** and **420 Necrobinder**
requests, including their original Act 1 commands. Two rejected caller typos
(`leave_shop` from Act 1 and `map_select` from Act 2) were removed only from the
Necrobinder regression fixture; the original save retains all 422 requests. An
incorrect `load_continue_save` caller request also failed harmlessly before the
correct `load_save` command was used. These are distinguished from engine defects.

`tests/test_act2_runs.py` replays both full fixtures without debug commands,
compares the entire final state to the actual saved snapshot, checks boss rounds,
HP/gold, and restores an exact checkpoint in a separate process. Independent
fresh-process checks of both actual final save files also succeeded. Final full
route/checkpoint replay logs contain no engine exception, timeout or deadlock.
Discovery logs intentionally still contain the reproduced failures.

Synthetic tests use altered state only in separate test processes. For example,
the isolated Kaiser Crab lifecycle test uses 1000 HP and a controlled deck; it is
not either reported real run.

Final full suite: **111 passed**, one existing unregistered `slow` marker warning,
214.91 seconds. The build succeeded with nine existing nullable/inheritance/event
warnings and no errors. `git diff --check` and Python compilation also passed.

## Crystal Sphere JSON protocol

`decision: "crystal_sphere"` exports width, height, remaining divinations, tool
names and rows of cells. Hidden cells contain only `x`, `y`, `hidden`. Revealed
cells may include `item_type`; no hidden item location/extent is exported.

```json
{"cmd":"action","action":"crystal_sphere_reveal","args":{"x":5,"y":5,"tool":"big"}}
```

`small` reveals one cell; `big` reveals its 3×3 neighborhood. Both cost one native
divination. The event owns item placement, RNG, fog, reward effects and completion.
A final reveal may yield a normal `card_reward` decision before returning to the
map. The interactive Python client also renders this grid.

## Remaining limitations

- Trial's Reject → Double Down abandonment confirmation remains explicitly
  unsupported. Event continuation paths beyond those exercised here are not
  claimed as covered.
- Some X-cost card views still lack an explicit X-cost flag. Some custom power
  descriptions retain engine energy-icon markup.
- Card-selection views can omit enchantment metadata; combat views expose it.
  Crystal Sphere's visible item categories currently use native type names.
- Checkpoints enforce the engine hash and exact output schema. A presentation
  change can reject an older snapshot; failed replay requires a fresh process.
- Act 3, including Lantern Key's next-act event, remains untested in these runs.
