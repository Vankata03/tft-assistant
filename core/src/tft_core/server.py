"""The localhost WebSocket between the core and the shell.

The shell connects to 127.0.0.1 and sends a Hello with the per-launch token it
gave the core in `TFT_CORE_TOKEN`. Connections that carry an Origin header (any
web page in a browser) are refused, and so are connections that do not say
Hello with the right token within five seconds.
"""

from .wire_json import evidence_wire_page
import asyncio
import hmac
import logging
import json
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError
from tft_capture.lcu import NOT_RUNNING, GameflowUpdate
from tft_data import DataError
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from tft_core.baseline import BaselineController
from tft_core.baseline.contracts import BaselineState
from tft_core.messages import (
    ErrorMessage,
    ReviewReady,
    ReviewNoticeShown,
    Gameflow,
    Hello,
    RequestBaselineState,
    SelectGuide,
    SessionMode,
    SessionModeState,
    SetSessionMode,
    SurfaceShown,
    UnsupportedVersion,
    dump,
    parse_ui_message,
)
from tft_core.delivery_queue import ClientWriter
from tft_core.storage import SessionStore
from tft_core.live_delivery import LiveDeliveryController
from tft_core.messages import RequestLiveState, RequestEvidencePage, LiveSurfaceShown, LivePreviewShown, EvidencePage, PinLine
from tft_core.messages import RequestSurfaceGeometry, SurfaceGeometryState
from contextlib import asynccontextmanager
from tft_core.io_worker import OwnedIO
from tft_core.review_queue import ReviewRequests
from tft_core.review_transport import ReviewTransport
from tft_core.messages import RequestReview,ReviewResponse,RequestReviewGames,ReviewGames
from tft_core.surface_geometry import captured_surface

log = logging.getLogger(__name__)

HELLO_TIMEOUT = 5.0
POLICY_VIOLATION = 1008


class CoreServer:
    def __init__(
        self,
        token: str,
        *,
        sessions: SessionStore | None = None,
        game_metadata: Callable[[str], dict] | None = None,
        baseline: BaselineController | None = None,
        managed_lifecycle: bool = False,
        review_service=None,
    ) -> None:
        self._token = token
        self._clients: set[ServerConnection] = set()
        self._writers = {}
        self._review_requests = {}
        self.io = OwnedIO()
        self._gameflow = NOT_RUNNING
        self.baseline = baseline or BaselineController()
        self._baseline_clients: set[ServerConnection] = set()
        self.sessions = sessions
        self.review = ReviewTransport(sessions,review_service)
        self._review_ready = None
        self._game_metadata = game_metadata or (lambda game_id: {})
        self._managed_lifecycle = managed_lifecycle
        self._mode = sessions.mode if sessions else SessionMode.SILENT
        self.live = LiveDeliveryController(sessions)
        self._live_clients: set[ServerConnection] = set()
        self._geometry_clients: set[ServerConnection] = set()
        self._geometry = None
        self._anchors = ()
        self._geometry_status = "Desktop geometry unavailable"

    def publish_surface_geometry(self, snapshot):
        try:
            self._geometry, self._anchors = captured_surface(snapshot)
            self._geometry_status = "Reviewed physical client geometry" if self._geometry else "Checked window geometry or profile anchors unavailable"
        except (ValueError, KeyError, TypeError) as error:
            self._geometry, self._anchors = None, ()
            self._geometry_status = f"Surface calibration unavailable: {error}"
        self._publish_geometry_state()

    def _geometry_state(self):
        if self._mode is SessionMode.SILENT:
            return SurfaceGeometryState(mode=self._mode, status="Silent game · overlay off")
        anchors = self._anchors
        if self._mode is SessionMode.BASELINE:
            anchors = tuple(row for row in anchors if row.kind in ('shop','level','par','augment','carousel','wisp','review'))
        return SurfaceGeometryState(mode=self._mode, geometry=self._geometry, anchors=anchors, status=self._geometry_status)

    def _publish_geometry_state(self):
        self._broadcast(self._geometry_clients, dump(self._geometry_state()))

    def publish_live(self, delivery) -> None:
        """Accept the optional advisor's public output; dispatch remains runtime-owned."""
        self.live.publish(delivery)
        self._publish_live_state()

    async def publish_live_async(self, delivery) -> None:
        """Runtime55 stages heavy file work off-loop; activation stays loop-owned."""
        prepared = self.live.prepare(delivery)
        reference = await self.io.call(self.live.persist,prepared,cooperative=True)
        self.live.activate(prepared,reference)
        self._publish_live_state()

    def observe_live_capture(self, snapshot, data) -> None:
        if self._mode is SessionMode.LIVE:
            self.live.observe(snapshot, data)
            self._publish_live_state()

    async def publish_review_ready(self,game_id):
        """Publish only a checked finished report, using that game's final mode."""
        if (not self.sessions or self.sessions.active_game_id
            or self._gameflow.phase in {'InProgress','Reconnect','PreEndOfGame'}):return None
        record=await self.io.call(self.review.ready,str(game_id))
        if record is None or self.sessions.active_game_id:return None
        self.review.permitted(str(game_id))
        now=datetime.now(UTC)
        elapsed=(now-datetime.fromisoformat(record['ended_at'])).total_seconds()
        if elapsed<0:raise ValueError('Review game-end timestamp is in the future')
        from uuid import uuid4
        ready=ReviewReady(**record,notice_id=uuid4().hex,ready_at=now,latency_seconds=elapsed,late=elapsed>30)
        self._review_ready=ready
        self._broadcast(self._clients,dump(ready))
        return ready

    async def review_notice_shown(self, message):
        ready = self._review_ready
        if (ready is None or not self.sessions or self.sessions.active_game_id
            or self._gameflow.phase in {'InProgress','Reconnect','PreEndOfGame'}
            or any(getattr(message,name)!=getattr(ready,name)
                   for name in ('game_id','report_id','evidence_id','job_id','notice_id'))):
            raise ValueError('Review notice is not the current finished report')
        now = datetime.now(UTC)
        if message.timestamp < ready.ready_at or not 0 <= (now-message.timestamp).total_seconds() <= 5:
            raise ValueError('Review notice timestamp is outside the visible receipt interval')
        current = await self.io.call(self.review.ready,message.game_id)
        if (current is None or any(current[name]!=getattr(ready,name)
                                  for name in ('game_id','report_id','evidence_id','job_id','mode'))
            or self._review_ready is not ready or self.sessions.active_game_id):
            raise ValueError('Review notice membership changed')
        elapsed = (message.timestamp-ready.ended_at).total_seconds()
        receipt = message.model_dump(mode='json') | {'received_at':now.isoformat(),
            'ended_at':ready.ended_at.isoformat(),'ready_at':ready.ready_at.isoformat(),
            'latency_seconds':elapsed,'late':elapsed>30,'mode':ready.mode}
        def persist(*,cancelled):
            return self.sessions.write_review_notice(message.game_id,receipt,
                cancelled=lambda: cancelled() or self._review_ready is not ready
                or self._gameflow.phase in {'InProgress','Reconnect','PreEndOfGame'})
        accepted = await self.io.call(persist,cooperative=True)
        if self._review_ready is not ready or self.sessions.active_game_id:
            return
        # First visible receipt determines notice latency; other surfaces stay durable.
        if ready.displayed_at is None:
            ready = ready.model_copy(update={'displayed_at':datetime.fromisoformat(accepted['timestamp']),
                'display_latency_seconds':accepted['latency_seconds'],'display_late':accepted['late']})
            self._review_ready = ready
        self._broadcast(self._clients,dump(ready))

    def publish_runtime_error(self,code,message) -> None:
        """Expose a runtime supervisor failure without changing lifecycle guards."""
        log.error("Runtime %s: %s",code,message)
        self._broadcast(self._clients,dump(ErrorMessage(code=code,message=message)))

    def publish_live_status(self) -> None:
        """Broadcast current cleared/paused state after a runtime-owned job error."""
        self._publish_live_state()

    def _publish_live_state(self) -> None:
        if self._live_clients:
            self._broadcast(self._live_clients, dump(self.live.state(self._mode)))

    def _broadcast(self, clients, encoded):
        key = json.loads(encoded)["type"]
        for client in clients:
            self._writers[client].publish(key, encoded)

    async def _send(self, client, encoded):
        await self._writers[client].send(encoded)

    @property
    def mode(self) -> SessionMode:
        return self._mode

    def refresh_idle_mode(self) -> None:
        """Adopt another process's durable selection only outside a game."""
        if (not self.sessions or self.sessions.active_game_id is not None
                or self._gameflow.phase in {"InProgress", "Reconnect", "PreEndOfGame"}):
            return
        mode = self.sessions.mode
        if mode == self._mode:
            return
        self._mode = mode
        if mode is not SessionMode.LIVE:
            self.live.clear("Live content suppressed by session mode")
        self._broadcast(self._clients, dump(self._mode_message()))
        self._publish_baseline_state()
        self._publish_live_state()
        self._publish_geometry_state()

    @asynccontextmanager
    async def listen(self, host: str = "127.0.0.1", port: int = 0):
        try:
            async with serve(self._handle,host,port,origins=[None],close_timeout=.25) as listener:
                yield listener
        finally:
            await self.shutdown_io()

    async def shutdown_io(self, *, timeout=.25):
        self.live.clear('Core shutting down · Live surfaces off')
        for jobs in tuple(self._review_requests.values()):await jobs.close()
        return await self.io.close(timeout=timeout)

    def publish_gameflow(self, update: GameflowUpdate) -> None:
        self._gameflow = update
        if update.phase in {"InProgress","Reconnect","PreEndOfGame"}:self._review_ready=None
        if self.sessions and not self._managed_lifecycle:
            try:
                if update.phase in {"InProgress", "Reconnect"}:
                    if update.game_id:
                        metadata = {}
                        if (
                            self.sessions.active_game_id != update.game_id
                            and not self.sessions.read_events(update.game_id)
                        ):
                            metadata = self._game_metadata(update.game_id)
                        self.sessions.start_game(update.game_id, **metadata)
                    else:
                        self._broadcast(
                            self._clients,
                            dump(
                                ErrorMessage(
                                    code="missing_game_id",
                                    message="LCU has not supplied a game id; capture cannot log this game yet",
                                )
                            ),
                        )
                elif update.phase in {"EndOfGame", "WaitingForStats"}:
                    self.sessions.end_game()
                elif update.phase in {"Lobby", "None"} and self.sessions.active_game_id:
                    self._log_game_ended_without_stats()
                    self.sessions.end_game()
            except Exception as error:  # noqa: BLE001 -- Storage/metadata failures must leave the connection usable.
                log.error("Session logging failed: %s", error)
                self._broadcast(
                    self._clients,
                    dump(
                        ErrorMessage(
                            code="session_storage_error",
                            message=f"Game logging is blocked: {error}",
                        )
                    ),
                )
            if self._mode != self.sessions.mode:
                self._mode = self.sessions.mode
                self._broadcast(self._clients, dump(self._mode_message()))
                self._publish_baseline_state()
        log.info(
            "Gameflow: client_running=%s phase=%s", update.client_running, update.phase
        )
        if self.sessions and self._managed_lifecycle:
            self._mode = self.sessions.mode
            self._broadcast(self._clients, dump(self._mode_message()))
            self._publish_baseline_state()
        self._broadcast(self._clients, dump(self._gameflow_message()))

    def _log_game_ended_without_stats(self) -> None:
        """Record the unobserved terminal span; placement stays unavailable.

        The span starts at the last logged capture (or the log's start when
        nothing was captured) and ends when the stats-less exit is detected.
        """
        events = self.sessions.read_events(self.sessions.active_game_id)
        start = next(
            (
                event["payload"]["captured_at"]
                for event in reversed(events)
                if event["kind"] == "snapshot"
            ),
            events[0]["timestamp"],
        )
        end = datetime.now(UTC).isoformat()
        self.sessions.append_event(
            "capture_gap",
            {"reason": "game_ended_without_stats", "start": start, "end": end},
            timestamp=end,
        )

    def publish_baseline(
        self,
        *,
        data=None,
        snapshot=None,
        faced=(),
        status="Capture OK",
        round_start=False,
        anchors=(),
        overlay_bounds=None,
        overlay_allowed=False,
    ) -> None:
        """Publish pinned data and permitted own capture fields; runtime wiring owns cadence."""
        try:
            self.baseline.update(
                data=data,
                snapshot=snapshot,
                faced=faced,
                status=status,
                round_start=round_start,
                anchors=anchors,
                overlay_bounds=overlay_bounds,
                overlay_allowed=overlay_allowed,
            )
        except DataError, ValidationError, KeyError, TypeError, ValueError:
            self.baseline.update(
                data=None,
                status="Capture status unavailable; invalid capture or calibrated surface fields",
            )
        self._publish_baseline_state()

    def _baseline_state(self) -> BaselineState:
        try:
            return self.baseline.state(self._mode)
        except (DataError, KeyError, TypeError, ValueError) as error:
            return BaselineState(
                mode=self._mode.value, status=f"Baseline data unavailable: {error}"
            )

    def _publish_baseline_state(self) -> None:
        if self._baseline_clients:
            self._broadcast(self._baseline_clients, dump(self._baseline_state()))

    def _mode_message(self) -> SessionModeState:
        available = (
            tuple(SessionMode)
            if not self.sessions or self.sessions.live_installed
            else (SessionMode.SILENT, SessionMode.BASELINE)
        )
        return SessionModeState(mode=self._mode, available_modes=available)

    def _gameflow_message(self) -> Gameflow:
        return Gameflow(
            client_running=self._gameflow.client_running, phase=self._gameflow.phase
        )

    async def _handle(self, ws: ServerConnection) -> None:
        if not await self._authenticate(ws):
            return
        self._writers[ws] = ClientWriter(ws)
        self._review_requests[ws] = ReviewRequests(lambda message:self._review_receive(ws,message))
        self._clients.add(ws)
        try:
            await self._send(ws, dump(self._gameflow_message()))
            await self._send(ws, dump(self._mode_message()))
            if self._review_ready and not (self.sessions and self.sessions.active_game_id):await self._send(ws,dump(self._review_ready))
            async for raw in ws:
                await self._receive(ws, raw)
        except ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            self._baseline_clients.discard(ws)
            self._live_clients.discard(ws)
            self._geometry_clients.discard(ws)
            await self._review_requests.pop(ws).close()
            await self._writers.pop(ws).close()

    async def _authenticate(self, ws: ServerConnection) -> bool:
        try:
            raw = await asyncio.wait_for(ws.recv(), HELLO_TIMEOUT)
            message = parse_ui_message(raw)
        except TimeoutError, ConnectionClosed, ValueError, ValidationError:
            message = None
        if isinstance(message, Hello) and hmac.compare_digest(
            message.token, self._token
        ):
            return True
        log.warning("Refused a WebSocket client without a valid hello")
        await ws.close(POLICY_VIOLATION, "hello required")
        return False

    async def _review_receive(self,ws,message):
        if isinstance(message, ReviewNoticeShown):
            try:
                await self.review_notice_shown(message)
            except (ValueError, OSError, KeyError, PermissionError) as error:
                await self._send(ws,dump(ErrorMessage(code='review_notice_rejected',message=str(error))))
            return
        if isinstance(message,RequestReviewGames):
            try:
                if self.sessions and self.sessions.active_game_id and self.sessions.mode is SessionMode.SILENT:
                    raise ValueError('Silent games suppress post-game surfaces')
                if self.review.service:
                    result = await self.io.call(self.review.service.games)
                else:
                    rows = await self.io.call(self.sessions.list_games) if self.sessions else []
                    result = {'games': [{name: (None if name == 'placement' and row['review_locked'] else row[name])
                        for name in ('game_id','date','mode','finished','review_locked','patch','placement')} for row in rows],
                        'aggregates': {}}
                if self.sessions and self.sessions.active_game_id and self.sessions.mode is SessionMode.SILENT:
                    raise ValueError('Review permissions changed')
                await self._send(ws,dump(ReviewGames(request_id=message.request_id,
                    games=tuple(result['games']), aggregates=result['aggregates'])))
            except (ValueError,KeyError,TypeError) as error:
                await self._send(ws,dump(ErrorMessage(code='review_request_rejected',request_id=message.request_id,message=str(error))))
            return
        if isinstance(message,RequestReview):
            try:
                keys={'page':('report_id','evidence_id','path','cursor','limit'),
                    'what_if':('report_id','evidence_id','moment_id','option_id'),
                    'tag':('report_id','evidence_id','moment_id','tag'),
                    'media':('name','cursor','limit'),'summary':(),'regenerate':()}
                arguments={name:getattr(message,name) for name in keys[message.operation]}
                value=await self.io.call(self.review.call,message.operation,message.game_id,**arguments)
                # Re-check session permissions after work completed off the socket loop.
                self.review.permitted(message.game_id)
                if message.operation=='page':value=evidence_wire_page(value)
                response=ReviewResponse(request_id=message.request_id,game_id=message.game_id,operation=message.operation,value=value)
                encoded=dump(response)
                if len(encoded.encode())>256*1024:raise ValueError('Review response exceeds its bounded transport budget')
                await self._send(ws,encoded)
            except (ValueError,KeyError,TypeError,OSError) as error:
                await self._send(ws,dump(ErrorMessage(code='review_request_rejected',message=str(error),request_id=message.request_id)))
            return
    async def _receive(self, ws: ServerConnection, raw: str | bytes) -> None:
        try:
            message = parse_ui_message(raw)
        except UnsupportedVersion as error:
            await self._send(ws,
                dump(ErrorMessage(code="unsupported_version", message=str(error)))
            )
            return
        except (ValueError, ValidationError) as error:
            await self._send(ws,
                dump(ErrorMessage(code="invalid_message", message=str(error)))
            )
            return
        if isinstance(message,(RequestReviewGames,RequestReview,ReviewNoticeShown)):
            try:self._review_requests[ws].submit(message)
            except ValueError as error:
                await self._send(ws,dump(ErrorMessage(code='review_request_rejected',request_id=getattr(message,'request_id',None),message=str(error))))
            return
        if isinstance(message, RequestBaselineState):
            self._baseline_clients.add(ws)
            await self._send(ws, dump(self._baseline_state()))
            return
        if isinstance(message, RequestLiveState):
            self._live_clients.add(ws)
            await self._send(ws, dump(self.live.state(self._mode)))
            return
        if isinstance(message, RequestSurfaceGeometry):
            self._geometry_clients.add(ws)
            await self._send(ws, dump(self._geometry_state()))
            return
        if isinstance(message, (RequestEvidencePage, LiveSurfaceShown, LivePreviewShown, PinLine)):
            try:
                if isinstance(message, RequestEvidencePage):
                    page = evidence_wire_page(self.live.page(message, self._mode))
                    await self._send(ws, dump(EvidencePage(request_id=message.request_id,
                        game_id=message.game_id, revision=message.revision, page=page)))
                elif isinstance(message, LivePreviewShown):
                    self.live.preview_shown(message, self._mode)
                elif isinstance(message, LiveSurfaceShown):
                    self.live.shown(message, self._mode)
                else:
                    self.live.pin_line(message, self._mode)
                    self._publish_live_state()
            except (ValueError, KeyError, TypeError) as error:
                await self._send(ws, dump(ErrorMessage(code="live_request_rejected", message=str(error), request_id=getattr(message, 'request_id', None))))
            return
        if isinstance(message, SelectGuide):
            if self._mode is not SessionMode.BASELINE:
                await self._send(ws,
                    dump(
                        ErrorMessage(
                            code="baseline_request_rejected",
                            message="Guide selection is available in Baseline mode only",
                        )
                    )
                )
                return
            try:
                self.baseline.select(message.guide_id)
            except DataError as error:
                await self._send(ws,
                    dump(ErrorMessage(code="guide_unavailable", message=str(error)))
                )
                return
            self._baseline_clients.add(ws)
            if self.sessions and self.sessions.active_game_id:
                self.sessions.append_event(
                    "guide_selection", {"guide_id": message.guide_id}
                )
            self._publish_baseline_state()
            return
        if isinstance(message, SurfaceShown):
            if self._mode is SessionMode.SILENT:
                await self._send(ws,
                    dump(
                        ErrorMessage(
                            code="surface_suppressed",
                            message="Silent mode suppresses all game content and voice",
                        )
                    )
                )
                return
            if self.sessions and self.sessions.active_game_id:
                self.sessions.append_event(
                    "ui_show",
                    {
                        "surface": message.surface,
                        "content_id": message.content_id,
                        "mode": self._mode.value,
                    },
                    timestamp=message.timestamp.isoformat(),
                )
            return
        if isinstance(message, SetSessionMode):
            ranks = {
                SessionMode.SILENT: 0,
                SessionMode.BASELINE: 1,
                SessionMode.LIVE: 2,
            }
            if (
                self._gameflow.phase in {"InProgress", "Reconnect", "PreEndOfGame"}
                and ranks[message.mode] > ranks[self._mode]
            ):
                await self._send(ws,
                    dump(
                        ErrorMessage(
                            code="mode_rejected",
                            message="A game can only move to a lower session mode",
                        )
                    )
                )
                return
            if self.sessions:
                try:
                    self.sessions.set_mode(message.mode)
                except ValueError as error:
                    await self._send(ws,
                        dump(ErrorMessage(code="mode_rejected", message=str(error)))
                    )
                    return
            self._mode = message.mode
            if self._mode is not SessionMode.LIVE:
                self.live.clear("Live content suppressed by session mode")
            log.info("Session mode: %s", self._mode)
            self._broadcast(self._clients, dump(self._mode_message()))
            self._publish_baseline_state()
            self._publish_live_state()
            self._publish_geometry_state()
