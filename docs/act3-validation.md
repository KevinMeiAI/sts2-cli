# Continuing the original saves through Act 3

Engine **v0.107.1**, Steam build **23811903**. Validation date **2026-09-22**.

## Actual outcomes

These are the same two Act 2 checkpoints documented in
[Act 2 validation](act2-validation.md). The assistant selected each route, event,
card, target and potion; the transport only forwarded JSON and logged replies.
No gameplay policy script, reroll, debug room entry, stat editing or resurrection
was used in either actual continuation. The Ironclad keeps its original A0;
the Necrobinder keeps A10.

| Character | Seed | Ascension | Start at Act 2 reward | Act 3 ending |
| --- | --- | --- | --- | --- |
| Ironclad | `6BMMPCFQAJ` | 0 | 16/83 HP | Queen defeated, floor 15, round 3; `victory: true`, **86/86 HP**, 98 gold, 35 cards |
| Necrobinder | `WWSC86QMRD` | 10 | 6/66 HP | Aeonglass reached, floor 15; died on round 8; `victory: false`, **0/66 HP**, 110 gold, 38 cards |

Native Ancient entry healed Ironclad to 83/83 and Necrobinder to 54/66.
Ironclad subsequently increased max HP with Feed. Necrobinder reached the last
rest at 10 HP, rested to 29, and Pantograph healed it to 54 when entering Aeonglass.
Its defeat is a gameplay result, not an engine crash or successful completion.

## Coverage

Ironclad: Tanx/Sai, Devoted Sculptor, War Historian Repy/Lantern Key → History
Course, shop, Relic Trader, Slippery Bridge, Grave of the Forgotten, Scrolls of
Biting, The Lost/The Forgotten, Battleworn Dummy, rest/upgrade and Queen.
The bridge was played without rewinding: seven Hold On payments cost 42 HP,
then Bash was removed. History Course's automatic True Grit correctly yielded a
card-selection prompt; start-of-turn attacks could also end combat. Queen covered
its summoned ally, Bound cards and late Frail/Weak/Vulnerable powers.

Necrobinder: Nonupeipe/Signet Ring, Devoted Sculptor, two shops, Membership Card
price recalculation, Reflections card downgrades/upgrades, Living Shield/Turret
Operator, Tinker Time, Fabricator and its summons, Potion Courier, Mecha Knight,
Relic Trader/Pantograph and Aeonglass. Tinker Time created a Skill with Energized
(8 base Block and 2 energy); it was actually played. Combat also covered full
hands, Soul draws, exhaust selection, Osty death/revival, Sacrifice, Doom,
Beating Remnant, Ghost Seed, Pagestorm, Shroud, Sleight of Flesh and Wither.

## Defects repaired

| Area | Evidence | Repair |
| --- | --- | --- |
| Event/final-combat reward suppression | Battleworn Dummy offered an ordinary card reward, 17 gold and a random potion despite its native encounter disabling ordinary rewards. | Respect `Encounter.ShouldGiveRewards`. Dummy gives only its selected native event reward; Queen ends directly in victory without invented ordinary boss loot. |
| Resuming an event after combat | Forcing a terminal combat to the map could discard the resumed parent's custom rewards or subsequent choices. | Resume the native parent asynchronously and retain pending prompts, only when the room stack has a parent and the native resume flag is set. |
| Upgraded event card names | Slippery Bridge exported `HEMOKINESIS.title+` / `RUPTURE.title+`. | Fall back to the localized base title plus the upgrade suffix after exact-key lookup fails. |
| Mad Science description and preview | Every variant exposed the same template and all numeric variables, without its chosen type/rider. Fresh upgrade previews lost that configuration. Related Violence attacks previewed one hit instead of three. | Export native `tinker_time` and `description_vars` selectors in deck, hand, rewards, bundles, selection and upgrade views; retain configuration in upgrade previews; use native Violence hit count. The Python display resolves the selected branches. |

The Mad Science JSON description intentionally remains a template, consistent
with other cards. Consumers combine `stats` with `description_vars`, or use the
explicit `tinker_time.card_type` / `tinker_time.rider` fields. Unselected numeric
variables are not additional effects. The interactive display renders, for
example, `Gain 8 Block. Gain 2E.` instead of unrelated branches.

All changes are adapter/client source changes. No new DLL patch was added. The
already setup-patched CLI engine retains SHA-256
`805c631cb6b400c5d5b18edb9f60ed54d797eb65fbc776a01162b50b6cafe724`.
The original game DLL remains
`e7ceb80669bfaf5c8fccabaa126ae2bb283aba514be5b5b55612579cfd285f18`.

## Evidence integrity and recovery

The erroneous Dummy reward checkpoint was preserved for diagnosis. The real run
resumed immediately before the faulty terminal action and repeated that same
`end_turn` after the fix. It returned to the map with **98 gold**, **35 cards** and
the single native event potion, Blessing of the Forge. The fake 17 gold, ordinary
card offer and ordinary potion RNG were discarded. No strategic decision was
replayed to seek a better result.

A development version of the parent-resume fix omitted the room-stack guard;
regression testing caught recursion on ordinary combat. It was corrected before
the real game resumed. This was a test failure during repair, not a retained
successful-run result.

The final fixtures contain **499 Ironclad** and **687 Necrobinder** commands,
including Acts 1 and 2. The Necrobinder fixture omits two older rejected command
names (`leave_shop`, `map_select`); its raw checkpoint retains all **689** commands.
The two Act 3 caller mistakes remain in the fixture: purchasing a potion with both
A10 slots occupied, and using an outdated potion index after the inventory
compacted. Both return explicit errors and are checked to leave state unchanged.
Neither is counted as an engine defect.

Both entire final states match the actual endings. Fresh-process loads also
verify the original checkpoint command histories. Mad Science's additional
presentation fields require a snapshot-schema update: original Necrobinder
snapshots are preserved as `*.pre-metadata.save`; current copies add only that
card's verified metadata. No commands, RNG inputs, HP, gold or deck composition
were changed. Final, pre-elite, pre-boss and final-turn copies restore exactly.
Discovery traces remain available separately from clean verification logs.

## Tests

- `test_act3_runs.py`: complete actual traces, boss rounds and both final outcomes;
  entire state equality; unchanged rejected requests; custom-card display;
  repeated state reads; exact terminal checkpoint reloads.
- `test_act3_events.py`: actual key/History Course/bridge/dummy route; all three
  native Dummy reward settings; Dummy timeout with no victory reward; exact saves.
- Separate synthetic English/Chinese Tinker Time tests generate Attack/Violence,
  check selectors and upgrade data, render the chosen description, and compare
  the 12 × 3 = 36 damage preview to actual enemy HP loss.
- Synthetic tests run in separate processes and are not part of either reported
  actual game. Full fixtures contain only `start_run` and `action` requests.

Final full-suite result: **120 passed**, one existing unregistered `slow` marker
warning, **262.04 seconds**. `git diff --check` and Python compilation also passed.
Build: **0 errors, 2 existing nullable warnings**.

## Boundaries

This validates two original routes and their outcomes, not all Act 3 branches or
bosses. Necrobinder did not defeat Aeonglass. Every Tinker Time rider is exported,
but only Energized and Violence have dedicated behavioral checks here. Other
characters, alternative Act 3 encounters and combinations still need coverage.
Trial's Reject → Double Down abandonment confirmation remains unsupported.
General conditional-card descriptions outside Mad Science and older snapshot
schema migration remain limitations; exact checkpoint validation stays strict.
