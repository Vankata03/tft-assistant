"""Bounded background video encoding with explicit frame times and durable segments.

FFmpeg's concat demuxer carries variable frame durations; completed MP4 files
are handed to SessionStore. Capture must close this recorder before ending the
active game, so the final segment can still be indexed in that game's log.
"""
from datetime import datetime
from pathlib import Path
from queue import Queue, Full
import shutil
import subprocess
import tempfile
import threading


class SegmentRecorder:
    def __init__(self, sink, *, executable=None, segment_seconds=5, queue_size=16):
        self.sink = sink
        self.executable = executable or shutil.which('ffmpeg')
        if not self.executable:
            raise ValueError('Full video requires a configured FFmpeg executable')
        if segment_seconds <= 0 or queue_size < 1:
            raise ValueError('Video segment duration and queue capacity must be positive')
        self.segment_seconds = segment_seconds
        self.queue = Queue(queue_size)
        self.closed = False
        self.error = None
        self.worker = threading.Thread(target=self._run, name='tft-video-encoder', daemon=True)
        self.worker.start()

    def submit(self, image, timestamp):
        if self.closed:
            raise ValueError('Video recorder is closed')
        if self.error:
            raise RuntimeError(self.error)
        try:
            self.queue.put_nowait(('frame', image.copy(), timestamp))
        except Full:
            self.sink.append_event('video_gap', {'reason': 'encoder_queue_full'}, timestamp=timestamp.isoformat())

    def flush(self):
        if not self.closed:
            self.queue.put(('flush', None, None))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.queue.put(('close', None, None))
        self.worker.join()
        if self.error:
            raise RuntimeError(self.error)

    def _run(self):
        frames = []
        with tempfile.TemporaryDirectory(prefix='tft-video-') as directory:
            root = Path(directory)
            while True:
                kind, image, timestamp = self.queue.get()
                try:
                    if kind == 'frame':
                        if frames and (image.size != frames[0][2] or (timestamp-frames[0][0]).total_seconds() >= self.segment_seconds):
                            self._encode(root, frames)
                            frames = []
                        path = root / f'{len(frames)}.png'
                        image.convert('RGB').save(path)
                        frames.append((timestamp, path, image.size))
                    else:
                        if frames:
                            self._encode(root, frames)
                            frames = []
                        if kind == 'close':
                            return
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    self.error = f'Video encoding failed: {error}'
                    frames = []
                    self.sink.append_event('media_status', {'state': 'unavailable', 'error': self.error}, timestamp=timestamp.isoformat() if timestamp else None)
                    if kind == 'close':
                        return
                finally:
                    self.queue.task_done()

    def _encode(self, root, frames):
        # Relative numeric filenames avoid shell quoting and concat path injection.
        lines = []
        for index, (timestamp, path, _) in enumerate(frames):
            duration = (frames[index+1][0]-timestamp).total_seconds() if index+1 < len(frames) else .25
            if duration <= 0:
                raise ValueError('Video frame timestamps must increase')
            lines.extend((f"file '{path.name}'", f'duration {duration:.9f}'))
        lines.append(f"file '{frames[-1][1].name}'")
        manifest = root / 'frames.txt'
        manifest.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        output = root / 'segment.mp4'
        result = subprocess.run([self.executable, '-v', 'error', '-y', '-f', 'concat', '-safe', '1',
            '-i', str(manifest), '-fps_mode', 'vfr', '-c:v', 'libx264', '-preset', 'veryfast',
            '-crf', '18', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', str(output)], capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip())
        path = self.sink.write_video(output.read_bytes(), timestamp=frames[0][0].isoformat())
        self.sink.append_event('video_segment', {'path': path, 'start': frames[0][0].isoformat(),
            'end': frames[-1][0].isoformat(), 'frame_timestamps': [frame[0].isoformat() for frame in frames]},
            timestamp=frames[0][0].isoformat())
