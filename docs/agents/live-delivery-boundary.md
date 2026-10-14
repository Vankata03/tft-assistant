# Live delivery and runtime interfaces

This ticket 44 checkpoint supplies the optional advisor, core transport, durable evidence, capture geometry and runtime interfaces. Full ticket 44 remains open. Its renderer, charts, display latency and toast acknowledgement work is preserved separately; this checkpoint does not qualify Windows capture, voice, source data or end-to-end Live operation.

## Evaluation and publication

`tft_live.advisor.LiveAdvisor.evaluate(snapshot, history, data, mode=...)` accepts the shared `GameSnapshot` and `GameHistory`. It returns `LiveDelivery` in Live mode and `None` in other modes. Delivery contains finite display summaries and a lossless `EvidenceGraph`; the core does not import the optional Live package. `model_hash` identifies the canonical pinned Engine tunables, not the board-reader model pointer.

The runtime calls `CoreServer.observe_live_capture(snapshot, data)` on the socket loop for each current observation. Calling it with `(None, None)` while Live clears the delivery and pin and invalidates prepared publication. `publish_surface_geometry(snapshot)` accepts the capture's root geometry, layout and reviewed surface-profile fields. Missing metadata clears geometry rather than supplying a desktop origin.

The runtime awaits `CoreServer.publish_live_async(delivery)`. Summary validation and activation stay on the owner loop; graph file preparation runs on owned I/O workers. Durable activation checks the game, mode, data and controller epoch again. Mode changes, capture loss and accepted pin changes invalidate pending work. Synchronous `publish_live` remains available for offline callers.

`publish_live_status()` broadcasts a cleared or paused Live state. `publish_runtime_error(code, message)` logs a supervisor failure and sends the existing authenticated error message without changing capture, session or refresh guards.

## I/O and shutdown

Each core owns two daemon I/O workers and a queue of eight requests. Each authenticated socket owns one review consumer with eight pending requests. A slow review does not block a later mode command on that same connection. Expected file failures return correlated errors and preserve the consumer. State sends are awaited and unsent state revisions coalesce.

The runtime awaits `shutdown_io(timeout=.25)` before capture shutdown. It cancels queued requests, signals cooperative publication and joins workers only until the stated deadline. A native file operation cannot be forcibly stopped; a blocked worker remains a daemon, and cancellation prevents its later publication. The WebSocket close timeout is .25 seconds. These are software lifecycle limits, not measured target-device guarantees.

## Pin identity and time

Accepted pin commands reference a scored `(comp_id, line_id, seed)` and never provide a schedule. The seed is a decimal string. `server.live.pin_schedule` exposes the validated schedule. `pin_read_at` is the actual persisted `line_pin` timestamp. `pin_context` contains its game, data snapshot, acceptance revision, epoch, timestamp, schedule and reference. Unpin, clear, downgrade, detach and restart clear that state.

The runtime projects the pin only when its original receipt time is no later than the original capture time, with source `ui_pin`. It must not advance `captured_at`. The acceptance revision remains the original certificate when later display revisions replace the advice. Persistent UI choices are distinct from expiring HUD reads; ticket 55 supplies the shared Engine read rule.

## Protected review and evidence

`CoreServer(review_service=service)` uses the committed `ReviewService` routes for summaries, authenticated pages, already-scored what-if options and known-moment tags. Logged media uses `ReviewAccess`, separately from low-level capture and offline training media. Every request rechecks review locks; a Silent active game suppresses these surfaces.

`await publish_review_ready(game_id)` verifies the stored report graph and the finished game's final logged mode and end timestamp. It returns `ReviewReady` or `None` when suppressed. A final Silent mode suppresses the notice even if that game reached Live earlier. A later active game also suppresses a delayed notice. Readiness time and seconds since logged end are explicit; values above 30 seconds are marked late. Actual paint acknowledgement and late-event persistence remain unfinished surface work.

Paged wire copies convert integers outside JavaScript's safe range into decimal strings and add `integer_paths` relative to that response. Evidence membership paths are unchanged. Offline graph bytes and resolved values retain their original integer types.

## Geometry and qualification

Capture carries positively observed Win32 physical client bounds and their read time. UI scale and window mode carry their own configuration read time and SHA256. The worker revalidates configuration each tick; fresh bounds cannot refresh old layout evidence. Reviewed profile anchors include reference client dimensions and UI scale. The renderer must use native per-monitor physical-pixel-to-DIP conversion and hide stale, ambiguous or incompatible geometry.

The paired retained-artifact probe preserves 17,741,188 bytes of raw evidence with 1,491 graph records and a 1,959,988-byte durable graph. Owned asynchronous publication measured 62.09 ms cold and 30.42/30.03 ms warm; synchronous controls measured 31.16/38.69/37.42 ms. Summary transport was 18,608 bytes. The probe uses synthetic transport headers over retained Engine output; it does not measure game-change-to-screen latency. Factoring remains about one second and the complete Engine-plus-factoring path still exceeds the augment budget. Full-game resources, actual Windows geometry and voice, current source qualification and the historical native failure remain open in tickets 42, 48, 49, 50 and 55.
