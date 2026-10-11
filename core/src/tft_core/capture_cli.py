"""Exercise automatic capture from recorded images with the real durable log sink."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from PIL import Image

from tft_capture.ocr import NameCatalog, RapidOCRReader
from tft_capture.pipeline import CapturePipeline
from tft_capture.profile import load_profile
from tft_core.storage import SessionStore


def main(argv=None, *, ocr=None):
    parser = argparse.ArgumentParser(prog='tft-capture')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='Automatically read recorded frames and write a game log')
    inspect.add_argument('--images', nargs='+', required=True)
    inspect.add_argument('--profile', required=True)
    inspect.add_argument('--game-id', required=True)
    inspect.add_argument('--log-root', type=Path, required=True)
    inspect.add_argument('--own-player')
    inspect.add_argument('--names', type=Path, help='Locale entity-name asset; no live-state values')
    inspect.add_argument('--start', help='Recorded sequence start; otherwise use each image modification time')
    inspect.add_argument('--interval', type=float, default=.25)
    inspect.add_argument('--models', type=Path, help='Verified versioned CPU reader model cache')
    inspect.add_argument('--model-pointer', type=Path, help='Reviewed portable model-version pointer')
    inspect.add_argument('--set-number', type=int)
    inspect.add_argument('--full-video', action='store_true')
    args = parser.parse_args(argv)
    pipeline = None
    try:
        if args.interval <= 0:
            raise ValueError('Frame interval must be positive')
        start = datetime.fromisoformat(args.start) if args.start else None
        if start and start.tzinfo is None:
            raise ValueError('Recorded sequence start requires a timezone')
        names = json.loads(args.names.read_text()) if args.names else {}
        unit_ids = {name: identity for identity, name in names.get('units', {}).items()}
        profile = load_profile(args.profile, unit_ids=unit_ids)
        reader = None
        if args.models:
            from tft_capture.board_reader import BoardReader
            if args.set_number is None or not unit_ids:
                raise ValueError('CPU models require the pinned set number and locale unit-name asset')
            reader = BoardReader.from_version(args.models, pointer=args.model_pointer,
                set_number=args.set_number, unit_ids=unit_ids, templates=profile.reader.items)
        profile = load_profile(args.profile, board_reader=reader,
            carousel_classifier=reader.units if reader else None, unit_ids=unit_ids)
        images = [(Path(path), Image.open(path).convert('RGB')) for path in args.images]
        recognizer = ocr or RapidOCRReader.from_bundled_models()
        logs = SessionStore(args.log_root, args.log_root/'config', live_installed=False)
        logs.start_game(args.game_id)
        logs.append_event('capture_profile', {'sha256': profile.sha256})
        video = None
        if args.full_video:
            from tft_capture.media import SegmentRecorder
            video = SegmentRecorder(logs)
            logs.set_media_mode('full_video')
        pipeline = CapturePipeline(args.game_id, ocr=recognizer, sink=logs, catalog=NameCatalog(names),
            visual_reader=profile.reader, regions=profile.regions, own_player_name=args.own_player, video=video,
            tracking_events=logs.read_events(args.game_id))
        snapshots = []
        for index, (path, image) in enumerate(images):
            timestamp = start+timedelta(seconds=index*args.interval) if start else datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            snapshots.append(pipeline.tick(image, timestamp=timestamp))
        pipeline.close(timestamp=timestamp)
        print(json.dumps({'snapshots': snapshots, 'game_id': args.game_id, 'profile_sha256': profile.sha256}, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        if pipeline:
            try:
                pipeline.close()
            except (OSError, ValueError, RuntimeError):
                pass  # The original failure is reported; recorder errors are also in the game log.
        print(json.dumps({'error': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
