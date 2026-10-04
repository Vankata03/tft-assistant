---
id: 26
title: "Advice surface UX"
labels: [wayfinder:prototype]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

What does each surface (the in-game overlay, the second-screen window and voice callouts) show in each mode and game phase, and how does advice compete for the player's attention? The owner wants the coach graphical and interactive, not only text. In Live mode the econ advice carries a per-Line projection and lets the player pin a Line ("Econ, level and roll Line simulation"), so the surfaces need a way to show and pick Lines within a planning phase. Mode rules per surface are settled in "Policy stance and feature modes".

Decide, with a rough prototype to react to:

- What goes on the overlay versus the second screen versus voice, per game phase (planning, combat, augment selection, carousel).
- The latency budget per phase. Capture reads a change within about 250–500 ms ("Game-state capture route"), and augment advice must show within about 2 s of the offer.
- How each opponent's sighting age is shown, and whether the coach prompts the player to scout an opponent whose board is old.
- How low-confidence fields (stale reads, a board that purchase tracking and vision disagree on) show to the player.

## Comments

### 2026-10-04 — claude-code

Input from "Post-game review scope": the review opens on demand in the second-screen window after a "review ready" notification at game end, with no voice. Its content is settled; its layout belongs here. The top of the review holds placement, estimated cost per category, follow rate, a Game plan timeline, a Line chart (actual against recommended and pinned Lines) and a fight strip (win chance against result). Below it come the top 5 moments as cards (round, category, the player's choice, the Engine's choice, estimated cost, template reason, shown-advice status, keyframe), each expanding to the options the Engine scored; the full round timeline; and a debug tab. A cross-game list shows each game's placement, total estimated cost and worst category.

### 2026-10-04 — claude-code

Input from "Positioning decisions": positioning advice is a target layout for the whole board, issued once per planning phase after the board has settled for about 2 s, and re-issued only when the recommended board changes or an anti-dive or anti-AoE adjustment turns on or off. Units whose current hex is known get a move arrow; a unit known only to purchase tracking shows its target hex without one. Each adjustment carries a template reason. Voice speaks only when an anti-dive or anti-AoE adjustment turns on. Baseline mode shows only the Guide's own final and interim layouts.

### 2026-10-04 — claude-code

Input from "Stack and runtime": the overlay and the second-screen window are two windows of one Electron, TypeScript and React app, and voice uses Electron's `speechSynthesis` with the Windows OneCore voices. The overlay is click-through by default; single widgets can take clicks when hovered, and a hotkey hides the whole overlay. Which widgets are interactive is decided here. The overlay is excluded from screen capture, so OBS, Discord and Game Bar recordings do not show it. The game must run borderless or windowed; on exclusive fullscreen the second screen shows a warning and the overlay stays off. If the core restarts mid-game, the second screen shows a "coach restarting" state and the overlay hides advice older than the restart. The UI reports each piece of advice it showed, with surface and timestamp, to the core for the game log.

### 2026-10-04 — claude-code (resolution)

Resolved with the owner by reacting to a prototype. The prototype is on the throwaway branch `prototype/advice-surface-ux` as `prototype/advice-surfaces/index.html`. To run it, start `python -m http.server 8765` from the repository root and open `/prototype/advice-surfaces/index.html?variant=D`. Variant D is the chosen design; variants A to C are the alternatives it was picked from. All advice in it is mocked over real probe frames.

- **Layout.** The overlay anchors each piece of advice to the game element it concerns (variant A): shop slots, the level bar, the Buy XP button, player-list rows, augment cards and carousel units. Its tags, chips and frames are kept small. The second screen is a cockpit that shows everything at once, without tabs (variant C): current advice with reasons, the Line projection, the Game plan, the target layout and the opponent table.
- **Opponents.** The overlay marks a player-list row only when that opponent is due a scout: its sighting is 3 or more rounds old, or it was never scouted, and it is likely to be the next opponent (about 13 % or more). The mark is a small pulsing eye with the sighting age. It clears when the player scouts that opponent. Win chance, sighting age, traits and threat tags for every opponent stay on the second screen, where a freshness bar per opponent is green for a sighting from this or the last round, amber for 2 to 3 rounds, and red for 4 or more or never.
- **Voice.** Voice speaks only big moments: the augment pick, the carousel pick, an anti-dive or anti-AoE adjustment turning on, a pivot call and the start of a roll-down. It also says "scout X" when an anti-dive or anti-AoE decision depends on that opponent's sighting. Shop buys, holding gold and ordinary scout prompts are never spoken. In Baseline mode, voice reads the Guide's step for the stage at round start and nothing else.
- **Lines.** The overlay shows a Line chip on the level bar with the advised or pinned Line's name and expected placement. Clicking it opens the candidate Lines, one row each, and a click pins or unpins one. When another Line beats the pin by more than the Line margin, the chip turns amber and names that Line and its gain, without voice. The second screen draws the full projection: level steps per Line with roll-down points, gold, the hit probability at each roll-down and expected HP. Lines can be pinned and unpinned there too. There is no pin hotkey in v1.
- **Low confidence.** When a stale field pauses a sub-engine, its advice is replaced in place by a grey dashed tag that names the field, such as "paused · gold unread", so a silent coach can be told apart from a broken one. The second screen shows a banner with the field and how long it has been unread, and greys the paused rows. Advice with low confidence, such as a board on which purchase tracking and the board reader disagree, still shows, with dashed outlines and arrows and a "?" after the unit. It is never spoken. The second screen says what disagrees.
- **Roll-down mode.** A roll-down starts when the advised Line rolls down now or when the player rolls twice within about 2 s. It ends when the player stops rolling for about 3 s or reaches the gold floor. During it, capture reads only the shop strip at about 15 Hz, and the overlay shows a roll-down tracker above the shop: the gold floor, the rolls left, the chance of hitting the key units by the floor, and copy pips for each key unit, marked when the unit is in the current shop. Buy tags update after every roll. Tracker counts come from purchase tracking. The gold floor is fixed when the roll-down starts; Lines are recomputed when it ends or a key unit hits, not on every roll.
- **Latency budget.** Each budget runs from the change in the game to the advice on screen.

  | Advice | Budget |
  |---|---|
  | Roll-down shop buys and tracker | 0.25 s after the new shop settles (shop strip read 0.15 s, analytic shop call 0.02 s, render 0.02 s) |
  | Shop and Wisp calls in normal planning | 0.5 s after the shop changes |
  | Level and Line | 2 s after a gold, XP or HP change; the previous call stays until replaced |
  | Target layout | 2.5 s after the player's last move (the board must first settle for about 2 s) |
  | Augment pick | 2 s after the offer |
  | Carousel pick | 3 s after the carousel opens |
  | Win chance and sightings | 1 s after a scouted board is read |
  | Review ready | 30 s after the game ends |

  Advice that misses its budget still shows and is logged as late. Advice whose decision has already passed, because the shop changed or the augment was picked, is dropped and logged as too late.
- **Mouse.** Hovering any advice tag for about 400 ms shows its template reason in a tooltip placed above the element, never over it. Only two overlay widgets take clicks: the Line chip and the "Review ready" toast, which brings the second-screen window forward on the review. Advice has no dismiss control; the follow rate already measures ignored advice. One hotkey toggles the whole overlay; its default key is left to the build.
- **Content per phase and surface.**

  | Phase | Overlay, Live mode | Overlay, Baseline mode | Second screen | Voice, Live mode |
  |---|---|---|---|---|
  | Planning | Buy and Buy Wisp tags on shop slots, level chip, Line chip, target-layout arrows, scout eye | "In Guide" highlights on shop slots, Wisp worth tag, Guide plan chip, XP-aware leveling hint, win chance per player-list row | Cockpit; in Baseline mode the Guide, its layouts, win chance and opponents faced | Anti-dive or anti-AoE on, pivot call, the scout line tied to them |
  | Roll-down | Roll-down tracker, Buy tags after every roll | "In Guide" highlights | Cockpit, with Lines held until the roll-down ends | "Roll down to N", once |
  | Augment selection | Placement delta on each card, Take on the best, Reroll on the options to reroll | Tier letter per card, "in Guide" tag | Augment comparison with deltas, or tiers in Baseline mode | "Take X", with the reroll note |
  | Carousel | Numbered rings 1 and 2 on units | Guide priority chip | Carousel reasons | "Carousel: take X" |
  | Combat | One chip previewing the next planning phase's call | The Guide's step for the next stage | Win chance against the current opponent | Silent |
  | Game end | "Review ready" toast | "Review ready" toast | Post-game review | Silent |

  The review's layout is the one given by "Post-game review scope", drawn in the prototype's Game end phase.

Input posted to "Game-state capture route" (the shop-strip capture rate during a roll-down) and "Evaluation harness" (late and too-late advice). Glossary terms Overlay, Second screen, Callout and Roll-down tracker added to `CONTEXT.md`. No new tickets.

### 2026-10-04 — claude-code

Input from "Evaluation harness": each review moment card on the second screen carries an agree, disagree or unsure tag for the owner. Tags are stored in the review store, keyed by game and decision point, not in the game log, and survive review regeneration. The harness reports the disagree rate; it never gates on it. During a silent game the overlay, second screen and voice show nothing, and the silent game's review stays closed until the Live-mode run starts.
