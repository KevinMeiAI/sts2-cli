# A10 Silent / Necrobinder and event-branch validation

Engine: v0.107.1 (Steam build 23811903). Date: 2026-09-22.

## Manually directed runs

Each seed was rolled once. The current Codex assistant chose every route, event,
card and potion action. The transport only forwarded JSON and recorded responses;
it did not choose actions. Neither run used debug commands, changed player stats,
rerolled, or continued into Act 2.

| Character | Seed | Result | Final state |
| --- | --- | --- | --- |
| Silent | `K5H4W2Z8G5` | Defeat against Vantom, floor 17, turn 7 | 0/70 HP, 93 gold, 21 cards |
| Necrobinder | `WWSC86QMRD` | Defeated Vantom through Doom, floor 17, turn 8 | 22/66 HP, 192 gold, 21 cards; paused at Boss card reward |

Silent won seven normal combats. Its route covered Byrdonis Nest and hatching,
Morphic Grove's two-card transformation, Spoils Map, repeated Slippery Bridge
choices, and all three Winged Boots charges. Necrobinder won five normal combats,
two elites and the Boss. Its route covered Wellspring, The Legends Were True's
exit option, This or That's cursed relic, Sapphire Seed's heal/upgrade, and
Silver Crucible's empty treasure chest. Combat coverage included Osty, Doom,
Phrog Parasite's four-spawn transition, Bygone Effigy, Soul draws, Snecko Oil,
Skill Potion selection, temporary energy and card-cost affliction.

The Silent trace contains 223 gameplay/read commands and no command errors.
Necrobinder contains 207, including one caller mistake (`leave_shop`, an unknown
action); the successful 206 form its fixture. That rejected request had no game
effect. Both engine logs contained no exception/fatal/deadlock fallback lines.
These two runs are not win-rate evidence.

## Repairs

- Preserve string event variables (enchantment/curse names) and fractional effect
  variables. Expose stocked shop relic/potion variables before purchase.
- Resolve each power's actual title/description keys, including Speed Potion.
  Use live smart-description variables instead of generic example amounts:
  Shrink's infinite duration, Constrict damage, Retain Hand duration and Vulnerable
  percentage now agree with the live state. Select plural rules by output language,
  independent of the host's locale. Unhandled formats retain their template and set
  `description_is_template`, with `vars` available to the client.
- Include the engine's free-travel destinations in map choices while allowed;
  keep the Boss destination valid at the final grid row.
- Skip only cosmetic instructions in Dense Vegetation's Rest, Amalgamator's two
  merge actions, Punch Off's Nab and Trial's portrait/VFX setup. The v0.107.1 engine
  still performs healing, selection, card removal/addition, rewards, RNG and combat
  transitions. These fixes use in-memory Harmony patches; neither the existing
  setup-patched CLI engine copy nor Steam's original DLL changed on disk.
  Patches fail visibly if expected
  method/IL shapes change.
- Preserve Trial's per-page story variables and render its actual case narrative.
- Report unsupported Crystal Sphere and Trial abandonment interactions before
  executing them, rather than crashing after payment or other mutations.

## Synthetic coverage and boundaries

Separate debug sessions force **54 event types**, rotating Silent, Necrobinder,
Defect and Regent at A10 with 60 HP / 500 gold. They probe up to three initial
unlocked choices per event and resolve subsequent card/bundle/event choices using
a fixed policy. These include events normally restricted to later acts; this is
not a claim that all 54 occur in Act 1, or that every character/seed/branch was tested.
Combat handoffs stop at the first combat decision, not after winning that combat.

There are 108 available initial branches in this matrix. The initial expanded
sweep completed 101 and reproduced seven failures across four event types. Five
of those failures were repaired (two merge paths, Nab and two Trial entry paths).
Crystal Sphere's two paths are explicitly unsupported. Dense Vegetation's Rest
failure had already been repaired before that expanded sweep.

Final sweep: **106 completed branches, 2 explicitly unsupported branches, 54
unavailable option probes; 51 exact event checkpoint restores**. The full suite
passed **99 tests** (one existing unregistered `slow` marker warning). All four
saved manual runs, including the earlier Ironclad A0/A10 runs, restored exactly
with the final installed build.
Real-engine regression tests verify healed HP, both merged decks, Punch Off's
curse and relic, Trial choices/story, unchanged unsupported-action state, flight
choices, fractions/English/Chinese formatting, and exact checkpoint restoration.
The two complete manual command fixtures reproduce the original outcomes.

## Remaining limitations

| Priority | Issue | Current behavior / next work |
| --- | --- | --- |
| P1 | Crystal Sphere grid minigame | No CLI grid actions yet; both options return `unsupported_interaction` without gold/curse mutation. This event cannot currently be completed through the CLI. Implement its native cell/reveal/reward decision protocol. |
| P2 | Trial: Reject → Double Down | Opens an abandon confirmation UI in the game. CLI reports unsupported before mutation; Accept remains available. Needs an explicit confirm/cancel protocol. |
| P2 | X-cost metadata | Dirge is shown as numeric cost 0 in shop/card selection although its description says X. Expose an explicit X-cost flag consistently in every card view; do not interpret numeric 0 as free. |
| P3 | Rich text from custom power formatters | Some descriptions contain an energy-icon resource tag. Numeric variables remain available, but terminal rendering should translate the icon to text. |

An unavailable `SCROLL_BOXES` event ID in the preliminary survey was excluded:
Scroll Boxes is a relic in this engine, not an event failure. Optional/locked or
nonexistent option indices are counted as unavailable, not successful coverage.
Checkpoint rendering is verified against the adapter's current output schema;
older snapshots at changed presentation states may explicitly reject divergence.
