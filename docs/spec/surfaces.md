# Advice surfaces

Part of the [MVP spec](../spec.md). Sources: [Policy stance and feature modes](../../issues/008-policy-stance-and-modes.md), [Advice surface UX](../../issues/026-advice-surface-ux.md), [Stack and runtime](../../issues/025-stack-and-runtime.md), [Positioning decisions](../../issues/022-positioning-decisions.md), [Post-game review scope](../../issues/015-post-game-review-scope.md), [Evaluation harness](../../issues/027-evaluation-harness.md).

The design was chosen from a prototype: variant D of `prototype/advice-surfaces/index.html` on the branch `prototype/advice-surface-ux`. Run `python -m http.server 8765` from the repository root on that branch and open `/prototype/advice-surfaces/index.html?variant=D`. All advice in it is mocked over real probe frames.

## Surfaces

Three surfaces follow the same mode rules ([spec.md](../spec.md#modes-and-policy)). The overlay and second screen are two windows of one Electron, TypeScript and React app. Surfaces show the Engine's ranked advice list and never re-rank it.

- **Overlay.** A transparent window over the game that anchors each piece of advice to the game element it concerns: shop slots, the level bar, the Buy XP button, player-list rows, augment cards and carousel units. Its tags, chips and frames are kept small.
- **Second screen.** An ordinary window for the other monitor, a cockpit that shows everything at once without tabs: current advice with reasons, the Line projection, the Game plan, the target layout and the opponent table. After a game it shows the post-game review.
- **Voice.** Electron `speechSynthesis` with the Windows OneCore voices, behind a small text-to-speech interface so a local neural voice (Piper) can replace it later.

## Content per phase

| Phase | Overlay, Live mode | Overlay, Baseline mode | Second screen | Voice, Live mode |
| --- | --- | --- | --- | --- |
| Planning | Buy and Buy Wisp tags on shop slots, level chip, Line chip, target-layout arrows, scout eye | "In Guide" highlights on shop slots, Wisp worth tag, Guide plan chip, XP-aware leveling hint, win chance per player-list row | Cockpit; in Baseline mode the Guide, its layouts, win chance and opponents faced | Anti-dive or anti-AoE on, pivot call, the scout line tied to them |
| Roll-down | Roll-down tracker, Buy tags after every roll | "In Guide" highlights | Cockpit, with Lines held until the roll-down ends | "Roll down to N", once |
| Augment selection | Placement delta on each card, Take on the best, Reroll on the options to reroll | Tier letter per card, "in Guide" tag | Augment comparison with deltas, or tiers in Baseline mode | "Take X", with the reroll note |
| Carousel | Numbered rings 1 and 2 on units | Guide priority chip | Carousel reasons | "Carousel: take X" |
| Combat | One chip previewing the next planning phase's call | The Guide's step for the next stage | Win chance against the current opponent | Silent |
| Game end | "Review ready" toast | "Review ready" toast | Post-game review | Silent |

Baseline mode's win chance per player-list row depends on opponent sightings, which is open ([Baseline mode and opponent sightings](../../issues/031-baseline-mode-and-opponent-sightings.md)).

## Voice rules

- Live mode speaks only big moments: the augment pick, the carousel pick, an anti-dive or anti-AoE adjustment turning on, a pivot call and the start of a roll-down. It also says "scout X" when an anti-dive or anti-AoE decision depends on that opponent's sighting.
- Shop buys, holding gold and ordinary scout prompts are never spoken. Low-confidence advice is never spoken.
- Baseline mode reads the Guide's step for the stage at round start, and nothing else.
- The post-game review has no voice summary.

## Opponents

- The overlay marks a player-list row only when that opponent is due a scout: the sighting is 3 or more rounds old, or the opponent was never scouted, and the opponent is likely to be the next one (about 13 % or more). The mark is a small pulsing eye with the sighting age. It clears when the player scouts that opponent.
- The second screen shows win chance, sighting age, traits and threat tags for every opponent. A freshness bar per opponent is green for a sighting from this or the last round, amber for 2 to 3 rounds, and red for 4 or more or never.

## Lines

- The overlay shows a Line chip on the level bar with the advised or pinned Line's name and expected placement. Clicking it opens the candidate Lines, one row each; a click pins or unpins one.
- When another Line beats the pin by more than the Line margin, the chip turns amber and names that Line and its gain, without voice.
- The second screen draws the full projection: level steps per Line with roll-down points, gold, the hit probability at each roll-down and expected HP. Lines can be pinned and unpinned there too.
- There is no pin hotkey in v1.

## Roll-down mode

- A roll-down starts when the advised Line rolls down now, or when the player rolls twice within about 2 s. It ends when the player stops rolling for about 3 s or reaches the gold floor. These thresholds are UX settings, not Engine tunables.
- During it, capture reads only the shop strip at about 15 Hz, and the overlay shows the roll-down tracker above the shop: the gold floor, the rolls left, the chance of hitting the key units by the floor, and copy pips per key unit, marked when the unit is in the current shop. Buy tags update after every roll. Tracker counts come from purchase tracking.
- The gold floor is fixed when the roll-down starts. Lines are recomputed when it ends or a key unit hits, not on every roll.

## Positioning display

The target layout is shown on the board with move arrows for units whose hex the board reader knows, and a target hex without an arrow for units known only to purchase tracking ([sub-engines.md](sub-engines.md#positioning)). Baseline mode shows the Guide's own final and interim layouts.

## Low confidence and paused advice

- When a stale field pauses a sub-engine, its advice is replaced in place by a grey dashed tag naming the field, such as "paused · gold unread", so a silent coach can be told apart from a broken one. The second screen shows a banner with the field and how long it has been unread, and greys the paused rows.
- Low-confidence advice, such as a board on which purchase tracking and the board reader disagree, still shows, with dashed outlines and arrows and a "?" after the unit. The second screen says what disagrees.
- If the core restarts mid-game, the second screen shows a "coach restarting" state and the overlay hides advice older than the restart.
- On exclusive fullscreen the second screen shows a warning and the overlay stays off.

## Latency budgets

Each budget runs from the change in the game to the advice on screen.

| Advice | Budget |
| --- | --- |
| Roll-down shop buys and tracker | 0.25 s after the new shop settles (shop strip read 0.15 s, analytic shop call 0.02 s, render 0.02 s) |
| Shop and Wisp calls in normal planning | 0.5 s after the shop changes |
| Level and Line | 2 s after a gold, XP or HP change; the previous call stays until replaced |
| Target layout | 2.5 s after the player's last move (the board must first settle for about 2 s) |
| Augment pick | 2 s after the offer |
| Carousel pick | 3 s after the carousel opens |
| Win chance and sightings | 1 s after a scouted board is read |
| Review ready | 30 s after the game ends |

Advice that misses its budget still shows and is logged as late. Advice whose decision has already passed (the shop changed, the augment was picked) is dropped and logged as too late, and counts as not shown.

## Input

- The overlay is click-through by default (`setIgnoreMouseEvents(true, {forward: true})`). Only two widgets take clicks: the Line chip, and the "Review ready" toast, which brings the second-screen window forward on the review.
- Hovering any advice tag for about 400 ms shows its template reason in a tooltip above the element, never over it.
- Advice has no dismiss control; the follow rate already measures ignored advice.
- One hotkey toggles the whole overlay. Its default key is left to the build.
- The UI reports each piece of advice it showed, with surface and timestamp, to the core for the game log.

## Silent games

During a silent game the overlay, second screen and voice show nothing, and the game's review stays closed until the Live-mode run starts ([review-and-harness.md](review-and-harness.md#silent-games)).

## Post-game review layout

The review opens on demand in the second-screen window after the "Review ready" toast; its content and layout are in [review-and-harness.md](review-and-harness.md#post-game-review) and drawn in the prototype's Game end phase.
