# Random A10 Defect run and metadata regressions

Engine **v0.107.1**, Steam build **23811903**; validated **2026-09-22**.

## Actual run

One seed, **`8J7GIO83BN`**, was generated with Python `secrets`. The assistant
selected every route, card, target, potion and event. The transport only forwarded
JSON and logged replies. The actual run used no debug commands, automated combat
policy, strategic rewinds, stat editing, resurrection or rerolls.

| Stage | Outcome |
| --- | --- |
| Act 1 / Overgrowth | Vantom defeated on floor 17, round 10; **7/75 HP**, 165 gold. |
| Act 2 entrance / Pael | Native A10 Ancient healing restored HP to **61/75**. Chose Pael's Tears. |
| Act 2 / Hive | Natural defeat at Entomancer, floor 14, round 4; **0/75 HP**, 198 gold, 30 cards. |

The run visited 16 combats (15 wins, one defeat), three shops and seven named
events including Neow and Pael. It did not reach the Act 2 boss or Act 3. In the
final turn the enemy intended 4×8 damage; Dualcast provided 10 Block and Frost
plus Plating brought it to 13. With 12 HP, this was insufficient. No crash or
engine exception caused the loss. Deck dilution and insufficient defense are
play-quality limitations, not successful full-run completion.

## Coverage

- All five orb types: Lightning, Frost, Dark, Glass and Plasma. Empty queues,
  full-queue evocation, temporary Focus, Dark accumulation, Glass decay and Plasma
  energy were observed in the real run.
- Dualcast, delayed Lightning Rod, doubled Loop/Thunder through Signal Boost,
  Echo Form, Hologram selection, FTL drawing and Unceasing Top.
- Akabeko with multi-hit Gunk Up, Vantom's Slippery, Weak/Frail/Vulnerable, attack
  cost changes, multiple enemy index changes and start-of-turn combat wins.
- Shop purchases, potion-created card selection, card removal, Meal Ticket
  healing, Thieving Hopper's card theft and return.
- Unrest Site (heal/curse), This or That? (curse/relic), Pael's Tears,
  Amalgamator (combine two Strikes), The Lost Wisp (gold), Bugslayer (Exterminate).

## Repairs

| Problem | Evidence and repair |
| --- | --- |
| Empty orb queue hides capacity | Actual Dualcast emptied the queue and removed both fields. Export `orbs: []` and `orb_slots` while the Defect has no orbs, including zero capacity. A separate native Bulk Up test covers zero slots. |
| X-cost cards resemble free cards | Actual Tempest reward exposed `cost: 0`. Add `costs_x: true` in hand, deck, rewards, shops, selections, bundles and upgrade previews. Retain numeric `cost` / `card_cost` for existing clients. Python renders **X**. Native tests verify Tempest consumes the remaining energy, including X=0. |
| Upgraded cards lack a clear marker | Actual Gunk Up reward had damage 5 and no upgrade preview, but no `upgraded` flag. Export the native boolean consistently. Python displays `+` and resolves `IfUpgraded` branches, including upgrade-only clauses. |
| Orb effects omitted | Passive/evoke numbers alone did not explain Glass decay, Dark targeting or Plasma timing. Export localized descriptions using the native live values and `description_is_template`. Plasma uses text energy units instead of Godot image paths. |
| Uproar previews one hit | Offered during the run; confirmed separately against native `OnPlay` and a controlled combat. Preview its two direct hits. Any automatically played follow-up card remains outside this direct-attack preview. |
| Debug-injected relic has no owner | Found only in isolated tests: `set_player(relics=['CRACKED_CORE'])` caused a null-reference error on combat entry. Assign the mutable relic's owner, as already done for injected potions. This did not affect the actual run. |

Shop upgrade previews also use the card's energy cost rather than its gold price.
JSON card names stay compatible; clients use `upgraded` instead of parsing names.
Orb index 0 is the next orb to evoke. The existing `damage_scope` caveat still
applies to attack previews: Block, Slippery and indirect effects can alter HP loss.

## Replay and checkpoint integrity

The checked-in fixture contains **330** game commands. Two malformed action
requests lacked nested `args`; these are caller mistakes, preserved in the trace
and verified to leave the pending reward unchanged. All other commands completed.
The original transport log contains 342 requests including reads, saves and quit.

The entire original trace was replayed. Every pre-existing reply field matched;
only the documented additive metadata changed. The game DLL hash and command
histories were unchanged. All eight Defect checkpoints and eight previously
published canonical checkpoints were migrated by verified replay and loaded in
fresh processes. Original snapshots were retained locally as backups. No
checkpoint equality or engine-hash validation was weakened. Historical diagnostic
snapshots retain their original schema and may require the same verified migration.

Fixtures for earlier Act 2/3 runs were updated only with verified additive card
metadata; their gameplay expectations remain unchanged.

## Verification

- Build: **0 errors, 2 existing nullable warnings**.
- All **130 test cases** passed across the full run and focused rechecks. The
  full run completed with 127 passed and three stale test expectations; after
  correcting the two Act 2 snapshots and allowing for native automatic selection
  of a sole upgradable card, the three targeted cases passed. No production code
  changed between the full run and these rechecks.
- The installed copy independently passed all **10 Defect tests** (20.27 seconds),
  including the complete real-run fixture and exact terminal restore.
- One existing unregistered pytest `slow` marker warning remains.
- Original reply-by-reply replay: pass. Eight Defect and eight previous canonical
  checkpoints: exact fresh-process restore passes.

The real run and controlled tests are separate. Synthetic tests may set a deck,
HP, relic or room to isolate a mechanic; none of those commands occurs in the
actual 330-command fixture. Not all Defect builds, event branches, elite fights,
Act 2 bosses or Act 3 content have been covered by this run.

Changes are source/client fixes. The setup-patched CLI engine remains SHA-256
`805c631cb6b400c5d5b18edb9f60ed54d797eb65fbc776a01162b50b6cafe724`;
the original DLL remains
`e7ceb80669bfaf5c8fccabaa126ae2bb283aba514be5b5b55612579cfd285f18`.
