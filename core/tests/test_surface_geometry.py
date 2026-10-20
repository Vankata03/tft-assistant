"""Desktop geometry through capture snapshots/logs, distinct from Windows qualification."""
from datetime import UTC, datetime, timedelta
import pytest
from PIL import Image
from tft_capture.pipeline import CapturePipeline
from tft_capture.runner import CaptureRunner
from tft_capture.windows import CapturedFrame, CaptureUnavailable
from tft_core.storage import SessionStore


def test_positive_physical_origin_survives_capture_log_and_disappears_on_window_loss(tmp_path):
    now = datetime(2026, 10, 12, tzinfo=UTC)

    class WindowFrames:
        def __init__(self):
            self.lost = False
        def capture(self):
            if self.lost:
                raise CaptureUnavailable("Recorded window loss")
            return CapturedFrame(Image.new("RGB", (100, 50)), "positive-window", "wgc",
                                 desktop_bounds=(-1920, 40, -1820, 90), geometry_read_at=now)

    class RecordedOCR:
        source = "external-recorded-ocr"
        def read(self, image, *, region):
            return []

    logs = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=False)
    logs.start_game("123")
    source = WindowFrames()
    pipeline = CapturePipeline("123", ocr=RecordedOCR(), sink=logs, regions={"gold": (0, 0, 1, 1)})
    runner = CaptureRunner(source, pipeline)
    first = runner.step(timestamp=now)
    geometry = first["capture_geometry"]
    assert geometry["client_bounds"] == {"x": -1920, "y": 40, "width": 100, "height": 50}
    assert geometry["coordinate_space"] == "physical_pixels"
    assert geometry["read_at"] == now.isoformat()
    assert geometry["window_id"] == "positive-window"
    assert next(e for e in logs.read_events("123") if e["kind"] == "snapshot")["payload"]["capture_geometry"] == geometry
    source.lost = True
    lost = runner.step(timestamp=now + timedelta(seconds=1))
    assert lost["capture_geometry"] is None
    assert first["capture_geometry"] == geometry


def test_reviewed_profile_anchors_require_explicit_size_and_scale(tmp_path):
    import json
    from tft_capture.profile import load_profile
    profile = tmp_path / 'profile.json'
    rows = {'version':1,'regions':{'gold':[0,0,1,1]},
            'anchors':[{'kind':'shop','index':0,'x':0.2,'y':0.8,'width':0.1,'height':0.05}],
            'anchor_calibration':{'client_size':[100,50],'ui_scale':1.0}}
    profile.write_text(json.dumps(rows))
    loaded = load_profile(profile)
    assert loaded.surface['anchors'] == rows['anchors']
    assert loaded.surface['calibration'] == rows['anchor_calibration']
    assert loaded.surface['profile_sha256'] == loaded.sha256
    import pytest
    rows['anchors'][0]['x'] = 0.95
    profile.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match='anchor'):
        load_profile(profile)


def test_surface_geometry_is_mode_gated_and_baseline_omits_player_anchors(tmp_path):
    import asyncio, json
    from websockets.asyncio.client import connect
    from tft_core.messages import Hello, dump
    from tft_core.server import CoreServer

    async def scenario():
        logs = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=False)
        logs.start_game('123')
        server = CoreServer('geometry-token', sessions=logs)
        source = {'capture_geometry': {'window_id':'positive','coordinate_space':'physical_pixels',
                    'client_bounds':{'x':-1920,'y':40,'width':100,'height':50},
                    'read_at':'2026-10-12T00:00:00Z','source':'Win32-client-rectangle'},
                  'capture_layout':{'scale_source':'game-config','window_mode':'borderless','ui_scale':1.0,'read_at':'2026-10-12T00:00:00Z','config_sha256':'b'*64},
                  'surface_profile':{'profile_sha256':'a'*64,'calibration':{'client_size':[100,50],'ui_scale':1.0},
                    'anchors':[{'kind':'shop','index':0,'x':.2,'y':.8,'width':.1,'height':.05},
                               {'kind':'player','index':0,'x':.9,'y':.2,'width':.05,'height':.05}]}}
        server.publish_surface_geometry(source)
        async with server.listen() as listener:
            async with connect(f'ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}') as ws:
                await ws.send(dump(Hello(token='geometry-token')))
                await ws.recv(); await ws.recv()
                await ws.send(json.dumps({'v':1,'type':'request_surface_geometry'}))
                state=json.loads(await ws.recv())
                assert state['geometry']['client_bounds']['x']==-1920
                assert [a['kind'] for a in state['anchors']]==['shop']
                await ws.send(json.dumps({'v':1,'type':'set_session_mode','mode':'silent'}))
                assert json.loads(await ws.recv())['mode']=='silent'
                cleared=json.loads(await ws.recv())
                assert cleared['geometry'] is None and cleared['anchors']==[]
    asyncio.run(scenario())


def test_layout_configuration_observations_keep_their_own_age_and_revalidate_each_frame(tmp_path):
    from tft_capture.layout import HudLayout
    from tft_core.surface_geometry import captured_surface
    config = tmp_path/'game.cfg'
    config.write_text('[HUD]\nGlobalScale=1\n[General]\nWindowMode=2\n')
    layout = HudLayout.from_config(config)
    logs = SessionStore(tmp_path/'app', tmp_path/'config', live_installed=False)
    logs.start_game('123')
    class Frames:
        def capture(self):
            return CapturedFrame(Image.new('RGB',(100,50)), 'window', 'wgc',
                desktop_bounds=(40,20,140,70), geometry_read_at=datetime.now(UTC))
    class OCR:
        source='external-recorded'
        def read(self,image,*,region):return []
    pipeline=CapturePipeline('123',ocr=OCR(),sink=logs,layout=layout,regions={'gold':(0,0,1,1)},
        surface_profile={'profile_sha256':'a'*64,'calibration':{'client_size':[100,50],'ui_scale':1},
            'anchors':[{'kind':'shop','index':0,'x':.2,'y':.8,'width':.1,'height':.05}]})
    def checked():
        current=HudLayout.from_config(config)
        if current.window_mode not in {'windowed','borderless'} or current.ui_scale!=layout.ui_scale:
            raise CaptureUnavailable('Layout requires revalidation')
        return current
    runner=CaptureRunner(Frames(),pipeline,layout_provider=checked)
    first=runner.step()
    view,_=captured_surface(first)
    assert view.layout_read_at.isoformat()==first['capture_layout']['read_at']
    assert view.layout_source_sha256==first['capture_layout']['config_sha256']
    config.write_text('[HUD]\nGlobalScale=1\n[General]\nWindowMode=0\n')
    lost=runner.step()
    assert lost['capture_geometry'] is None
    assert lost['capture_layout']['read_at']==first['capture_layout']['read_at']
    assert captured_surface(lost)==(None,())


@pytest.mark.parametrize('scale_source,available', [('game-config', True), ('measured', True), ('probe-reference', False)])
def test_surface_geometry_requires_an_established_hud_scale(scale_source, available):
    from tft_core.surface_geometry import captured_surface
    source = {'capture_geometry': {'window_id':'positive','coordinate_space':'physical_pixels',
                'client_bounds':{'x':0,'y':0,'width':100,'height':50},
                'read_at':'2026-10-12T00:00:00Z','source':'Win32-client-rectangle'},
              'capture_layout':{'scale_source':scale_source,'window_mode':'windowed','ui_scale':1.0,'read_at':'2026-10-12T00:00:00Z','config_sha256':'b'*64},
              'surface_profile':{'profile_sha256':'a'*64,'calibration':{'client_size':[100,50],'ui_scale':1.0},
                'anchors':[{'kind':'shop','index':0,'x':.2,'y':.8,'width':.1,'height':.05}]}}
    assert (captured_surface(source)[0] is not None) is available
