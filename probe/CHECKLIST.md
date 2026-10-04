# Probe game checklist

Companion to `probe.ps1` for the ticket "Probe live game data sources in a real TFT game". The script records port 2999, the client phase and a screenshot of the game's monitor every 10 seconds on its own. This list covers what it cannot see.

**Manual screenshots**: press **Win+PrtScn**. The script copies every capture taken during the run from `Pictures\Screenshots` (and Game Bar captures from `Videos\Captures`) into its output folder when it stops.

## Screenshots to take (Win+PrtScn)

- [ ] Planning phase with HUD, shop, board and bench all visible, with a **Wisp in the shop**.
- [ ] The shop **right after buying a Wisp**.
- [ ] One or two **scouted opponent boards**, with the bench if it shows.
- [ ] An **augment offer before and after a reroll**, with the reroll buttons visible.
- [ ] One **carousel**, while the units are still close enough to read their items.
- [ ] The **item bench** holding components and, if you get one, a special item (emblem, artifact, Radiant, support item, Reforger, anvil).
- [ ] The **opening encounter** screen at the start of the game.

## Facts to note

Write them in a reply after the game; times and rounds are enough.

**Rules the simulator takes as defaults**

- [ ] PvE rounds: does a PvE round keep, break or ignore a win or loss streak?
- [ ] Gold dropped by orbs in each PvE round you see (1-2, 1-3, 1-4, 2-7, 3-7, 4-7).
- [ ] Wisp shop: does the 4-champion shop alternate per round or per roll? What does the shop show after a Wisp is bought?
- [ ] Wisp offers: does low gold seem to limit which Wisps are offered?
- [ ] Which opening encounter the lobby got.

**Damage**

- [ ] On two or three lost rounds: the HP you lost, and the number and star levels of the opponent's surviving units.

**Items**

- [ ] A finished item stays on its unit until the unit is sold (items return to the item bench) or a Magnetic Remover is used.
- [ ] A single component can sit on a unit and gives its stats; a second component combines in place.
- [ ] Which special item kinds appeared and how they show on the item bench.

**Augments**

- [ ] Offers at 2-1, 3-2 and 4-2.
- [ ] All three options in one offer share a tier (silver, gold or prismatic).
- [ ] Each option can be rerolled once, for free.
- [ ] Selection timer: about 43 s for the first offer and 58 s for the others.

## Display mode

- [ ] Note whether the game runs in fullscreen, borderless or windowed mode. Automatic screenshots of an exclusive-fullscreen game can come out black.
