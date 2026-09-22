# Ironclad Ascension 10: first-act validation

Game version: v0.107.1. Random seed: `5LBKZHX72A`. One manually directed
Codex run, with no reroll, debug commands, changed player stats, or scripted
combat policy. The scope was Act 1 only.

The run reached floor 17 and died against Vantom on turn 10, with the boss at
22/183 HP. It won seven normal encounters and one elite encounter beforehand.
Final player state: 0/72 HP, 91 gold, 23 cards, five relics. This is a defeat,
not a completed first act or a whole-game win.

## Previously reported defects repaired before the run

Commit `f09b19d` caches shop purchase metadata before the engine clears it,
checks actual purchase results, exposes sold-out slots without fake labels,
and adds explicit Twin Strike hit counts and damage-preview scope. Exact CLI
checkpoints record the initial state and command stream, replay on load, and
compare the final decision; they do not silently move a completed room back
to its preceding map node. Native Steam save files remain a separate format.

Validation before this run: 81 tests passed. The scripted smoke runner also
completed five runs per character (25 total) without fatal or unobserved errors;
all were ordinary defeats. These are robustness checks, not model gameplay or
win-rate evidence. An earlier A0 boss-reward checkpoint was preserved and its
exact restoration verified.

## Two further defects found and repaired after the run

1. **Event selection completion race.** Neow's Lead Paperweight selection
   returned an old event response before adding Ultimate Strike to the deck.
   Human pacing allowed the background task to finish; immediate command
   replay could diverge at command 5 and reject the checkpoint. The same stale
   response occurred after Self-Help Book and Brain Leech selections.
   The simulator now tracks the event task and waits for completion or the next
   real selection/combat decision, with a bounded timeout and surfaced errors.
   It does not infer completion from the ActionExecutor or a fixed sleep.
2. **Tear Asunder attack preview count.** `Repeat` is only its base hit count.
   At boss turn 6, `CalculatedHits=6` and damage was 7 per hit, but the API
   reported `repeat=1, total_damage=7`; the engine correctly dealt 42 damage.
   The preview now uses the resolved `CalculatedHits` value. Twin Strike also
   correctly reports two hits, including when Slippery limits actual HP loss.

The 180 original gameplay/read commands form a regression fixture. Replaying
with these fixes reproduces the original final result. Intended response
changes are limited to settled event responses and Tear Asunder previews.
Boss-turn-6 and terminal checkpoints both restore exactly. Checks of 104 card
plays, 96 energy transitions, 16 map moves, five selections, eight post-combat
heals, and three purchases found no invalid transitions. The original manual
trace reported no command errors or engine exception lines.

## Remaining information gaps

| Priority | Reproduction | Evidence and effect | Suggested fix |
| --- | --- | --- | --- |
| P2 | Self-Help Book, floor 3, command 22 | Event options expose `Enchantment1/2/3` as numeric zero, leaving the actual enchantment unknown before committing. The selected attack later received Sharp 2. | Serialize typed enchantment values with model ID/name instead of casting every event dynamic variable to an integer. |
| P2 | Shop, floor 9, command 77 | Stocked relic and potion descriptions contain `{Cards}`, `{Damage}`, or `{DexterityPower}` but omit effect variables. Price and availability are correct. Owned potion summaries do expose `DexterityPower=2`. | Include dynamic variables in stocked relic/potion entries, as in player inventory summaries. |
| P3 | Speed Potion, boss turn 3, command 149 | A player power is named `SPEED_POTION_POWER.title`, with a raw description key. Its temporary +5 Dexterity effect and expiration worked. | Resolve the power's actual localization key or provide an explicit fallback, without inventing a description. |

These display issues remain open. Preview damage is attack damage before final
HP-loss modifiers; it must not be treated as exact HP loss through Block or
Slippery. No live-game choices were revised during verification.

Final validation after the two follow-up fixes: **83 tests passed**. Pytest
reported one pre-existing unregistered `slow` marker warning. No tests failed.
