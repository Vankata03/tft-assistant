from tests.test_harness_baseline import baseline_fixture

import pytest

from tft_core.messages import SessionMode
from tft_core.storage import SessionStore


def store(tmp_path, **kwargs):
    return SessionStore(tmp_path / "app", tmp_path / "config", **kwargs)


def test_sessions_log_snapshots_and_recover_downgraded_mode(tmp_path):
    first = store(tmp_path, live_installed=True)
    assert first.mode is SessionMode.SILENT
    first.set_mode(SessionMode.LIVE)
    first.start_game("123", patch="18.3", data_snapshot_id="data-a", model_version="reader-a")
    snapshot = {"timestamp": 12, "fields": {"gold": {"value": 27, "timestamp": 11, "source": "digits"}}}
    first.append_event("snapshot", snapshot, timestamp="2026-10-06T12:00:00Z")
    first.set_mode(SessionMode.BASELINE)
    with pytest.raises(ValueError, match="downgrade"):
        first.set_mode(SessionMode.LIVE)
    restarted = store(tmp_path, live_installed=True)
    restarted.start_game("123", patch="18.3", data_snapshot_id="data-b", model_version="reader-b")
    assert restarted.mode is SessionMode.BASELINE
    events = restarted.read_events("123")
    assert [event["kind"] for event in events] == ["game_start", "snapshot", "mode_change", "capture_gap"]
    assert events[1]["payload"] == snapshot
    assert events[0]["payload"]["data_snapshot_id"] == "data-a"
    restarted.end_game(placement=4)
    assert restarted.list_games()[0]["mode"] == "live"
    assert restarted.list_games()[0]["placement"] == 4


def test_crash_tail_is_recovered_without_losing_committed_events(tmp_path):
    first = store(tmp_path, live_installed=True)
    first.start_game("456", patch="18.3")
    first.append_event("fight_result", {"opponent": "Player", "result": "loss", "hp_lost": 7})
    with first.log_path("456").open("ab") as output:
        output.write(b'{"v":1,"seq":2,"kind":"snapshot","pay')
    restarted = store(tmp_path, live_installed=True)
    restarted.start_game("456")
    restarted.append_event("snapshot", {"gold": 12})
    restarted.end_game(placement=8)
    (tmp_path / "app" / "index.sqlite3").write_bytes(b"corrupt disposable index")
    recovered = store(tmp_path, live_installed=True)
    assert [e["kind"] for e in recovered.read_events("456")] == ["game_start", "fight_result", "capture_gap", "snapshot", "game_end"]
    assert recovered.list_games()[0]["placement"] == 8


def test_run_freezes_baseline_unlocks_reviews_and_numbers_same_set_live_games(tmp_path):
    session = store(tmp_path, live_installed=True)
    session.start_game("100", set_id="18", timestamp="2026-10-05T12:00:00Z")
    session.end_game(placement=3)
    assert session.list_games()[0]["review_locked"] is True
    baseline = baseline_fixture(sessions=session, at="2026-10-06T12:00:00Z")
    session.start_run(baseline, set_id="18", timestamp="2026-10-06T12:00:00Z")
    assert session.mode is SessionMode.LIVE
    assert session.run["baseline"] == baseline
    assert session.list_games()[0]["review_locked"] is False
    with pytest.raises(ValueError, match="already"):
        session.start_run(baseline, set_id="18")
    for i in range(11):
        session.start_game(str(200+i), set_id="18", queue_id=1100, timestamp="2026-10-07T12:00:00Z")
        session.end_game(placement=4)
    session.start_game("400", set_id="19", timestamp="2026-12-02T12:00:00Z")
    session.end_game(placement=4)
    session.rebuild_index()
    games = {g["game_id"]: g for g in session.list_games()}
    assert (games["210"]["run_number"], games["210"]["block"], games["210"]["pinned"]) == (11, 2, True)
    assert games["400"]["run_number"] is None
    public = SessionStore(tmp_path / "public", tmp_path / "public-config", live_installed=False)
    assert public.mode is SessionMode.BASELINE
    with pytest.raises(ValueError, match="not installed"):
        public.set_mode(SessionMode.LIVE)


def test_lossless_keyframes_media_cap_keep_logs_and_pinned_run_media(tmp_path):
    from io import BytesIO
    from PIL import Image

    session = store(tmp_path, live_installed=True)
    session.start_game("501", set_id="18", timestamp="2026-10-05T12:00:00Z")
    image = Image.new("RGB", (4, 4), (19, 42, 201))
    old_frame = session.write_keyframe(image, reason="shop_after_roll")
    session.end_game()
    session.start_run(baseline_fixture(sessions=session, at="2026-10-06T12:00:00Z"), set_id="18", timestamp="2026-10-06T12:00:00Z")
    session.start_game("502", set_id="18", queue_id=1100, timestamp="2026-10-07T12:00:00Z")
    pinned_frame = session.write_keyframe(image, reason="augment_offer")
    session.end_game()
    decoded = Image.open(BytesIO(session.read_media("502", pinned_frame)))
    assert decoded.convert("RGB").tobytes() == image.tobytes()
    report = session.enforce_media_cap(0)
    assert report["over_cap"] is True
    assert session.read_media("501", old_frame) is None
    assert session.read_media("502", pinned_frame) is not None
    assert session.read_events("501")[1]["payload"]["reason"] == "shop_after_roll"


def test_replay_cache_dirty_versions_and_review_locks(tmp_path):
    session = store(tmp_path, live_installed=True)
    session.start_game("600", data_snapshot_id="data-a")
    session.end_game()
    session.write_replay_cache("600", [{"decision_id": "4-2", "choice": "save"}], engine_version="abc", tunables_hash="t1", data_snapshot_id="data-a")
    session.write_review("600", {"moments": [{"decision_id": "4-2"}]}, engine_version="abc", data_snapshot_id="data-a")
    with pytest.raises(PermissionError, match="locked"):
        session.read_review("600")
    with pytest.raises(PermissionError, match="locked"):
        session.set_review_tag("600", "4-2", "disagree")
    session.rebuild_index()
    assert session.read_replay_cache("600", engine_version="abc", tunables_hash="t1", data_snapshot_id="data-a") == [{"decision_id": "4-2", "choice": "save"}]
    assert session.read_replay_cache("600", engine_version="abc+dirty", tunables_hash="t1", data_snapshot_id="data-a") is None
    session.start_run(baseline_fixture(sessions=session), set_id="18")
    session.set_review_tag("600", "4-2", "disagree")
    session.write_review("600", {"moments": []}, engine_version="def", data_snapshot_id="data-a")
    assert session.read_review("600")["tags"] == {"4-2": "disagree"}
    assert session.read_review("600")["engine_version"] == "def"


def test_capture_writers_preserve_order_and_media_setting_survives_restart(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    session = store(tmp_path, live_installed=True)
    assert session.media_mode == "keyframes"
    session.set_media_mode("full_video")
    session.start_game("700")
    with ThreadPoolExecutor(max_workers=4) as writers:
        list(writers.map(lambda n: session.append_event("snapshot", {"capture_tick": n}), range(40)))
    session.end_game()
    recovered = store(tmp_path, live_installed=True)
    events = recovered.read_events("700")
    assert [e["seq"] for e in events] == list(range(42))
    assert sorted(e["payload"]["capture_tick"] for e in events if e["kind"] == "snapshot") == list(range(40))
    assert recovered.media_mode == "full_video"


def test_crash_during_first_event_can_reattach(tmp_path):
    session = store(tmp_path, live_installed=True)
    path = session.log_path("800")
    path.parent.mkdir()
    path.write_bytes(b'{"v":1,"seq":0,"kind":"game_start"')
    recovered = store(tmp_path, live_installed=True)
    recovered.start_game("800", patch="18.3")
    recovered.append_event("snapshot", {"gold": 10})
    assert [e["kind"] for e in recovered.read_events("800")] == ["game_start", "capture_gap", "snapshot"]


def test_detach_preserves_unfinished_identity_and_mode_for_later_reattach(tmp_path):
    session = store(tmp_path, live_installed=False)
    session.start_game("123", patch="test.1", data_snapshot_id="old-pin", model_version="old-model")
    session.set_mode("silent")
    header = session.read_events("123")[0]
    session.detach_game("123", reason="different_positive_tft_game")
    assert session.active_game_id is None
    assert session.read_events("123")[0] == header
    assert not any(event["kind"] == "game_end" for event in session.read_events("123"))
    assert session.list_games()[0]["finished"] is False
    session.start_game("456", data_snapshot_id="new-pin")
    assert session.mode.value == "baseline"
    session.detach_game("456", reason="recovery")
    session.start_game("123", data_snapshot_id="replacement-must-not-win")
    assert session.mode.value == "silent"
    assert session.read_events("123")[0] == header
    assert sum(event["kind"] == "game_start" for event in session.read_events("123")) == 1
    with pytest.raises(ValueError, match="active game"):
        session.detach_game("456", reason="wrong-owner")
