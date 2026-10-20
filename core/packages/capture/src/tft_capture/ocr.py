"""External OCR adapters and locale-aware identity matching."""
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata


@dataclass(frozen=True)
class TextLine:
    text: str
    confidence: float = 1.0
    box: tuple[float, float, float, float] = (0, 0, 1, 1)


class NameCatalog:
    """Only return a known locale id when the best match is unambiguous."""
    def __init__(self, names: dict[str, dict[str, str]] | None = None):
        self.names = names or {}

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", text).casefold())

    def match(self, text: str, kind: str, *, minimum: float = 0.85, margin: float = 0.08) -> str | None:
        normalized = self.normalize(text)
        if not normalized:
            return None
        candidates = sorted(((SequenceMatcher(None, normalized, self.normalize(name)).ratio(), unit_id)
                             for unit_id, name in self.names.get(kind, {}).items()), reverse=True)
        if not candidates or candidates[0][0] < minimum:
            return None
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < margin:
            return None
        return candidates[0][1]


class DigitTemplates:
    """Read segmented game-font glyphs; uncertain matches produce no value."""
    source = "digit-templates"
    max_size_ratio = 1.5

    def __init__(self, templates: dict, *, minimum: float = .90, margin: float = .035):
        if not templates:
            raise ValueError("Digit templates are missing; supply calibrated game-font glyphs")
        self.minimum, self.margin = minimum, margin
        crops = {glyph: self._mask(image).crop(self._mask(image).getbbox())
                 for glyph, image in templates.items() if self._mask(image).getbbox()}
        self.templates = {glyph: crop.resize((20, 32)) for glyph, crop in crops.items()}
        # Normalizing to 20x32 hides size: a minus becomes a solid block. Glyphs
        # are only compared with templates of similar pixel size, so a glyph set
        # belongs to the client size it was cut at.
        self.sizes = {glyph: crop.size for glyph, crop in crops.items()}
        if not self.templates:
            raise ValueError("Digit templates contain no readable foreground")

    @staticmethod
    def _mask(image):
        return image.convert("L").point(lambda value: 255 if value >= 180 else 0)

    @classmethod
    def from_directory(cls, path):
        from pathlib import Path
        from PIL import Image
        path = Path(path)
        names = {**{digit: f"{digit}.png" for digit in "0123456789"}, "-": "minus.png", "/": "slash.png"}
        missing = [filename for filename in names.values() if not (path / filename).is_file()]
        if missing:
            raise ValueError(f"Calibrated digit templates missing in {path}: {', '.join(missing)}")
        return cls({glyph: Image.open(path / filename).copy() for glyph, filename in names.items()})

    def read(self, image, *, region):
        from PIL import ImageChops, ImageStat
        mask = self._mask(image)
        columns = [mask.crop((x, 0, x+1, mask.height)).getbbox() is not None for x in range(mask.width)]
        runs, start = [], None
        for index, occupied in enumerate(columns + [False]):
            if occupied and start is None:
                start = index
            elif not occupied and start is not None:
                runs.append((start, index))
                start = None
        text, confidence = "", 1.0
        for left, right in runs:
            glyph = mask.crop((left, 0, right, mask.height))
            glyph = glyph.crop(glyph.getbbox())
            size = glyph.size
            glyph = glyph.resize((20, 32))
            scores = sorted(((1-ImageStat.Stat(ImageChops.difference(glyph, template)).mean[0]/255, symbol)
                             for symbol, template in self.templates.items()
                             if all(1/self.max_size_ratio <= side/expected <= self.max_size_ratio
                                    for side, expected in zip(size, self.sizes[symbol]))), reverse=True)
            if not scores or scores[0][0] < self.minimum or len(scores) > 1 and scores[0][0]-scores[1][0] < self.margin:
                return []
            text += scores[0][1]
            confidence = min(confidence, scores[0][0])
        return [TextLine(text, confidence)] if text else []


class RapidOCRReader:
    """CPU-only RapidOCR with explicit local models, never mid-game downloads."""
    source = "rapidocr"

    def __init__(self, *, detector_path, recognizer_path, keys_path=None, language: str = "ch"):
        from pathlib import Path
        paths = [Path(detector_path), Path(recognizer_path)]
        if keys_path is not None:
            paths.append(Path(keys_path))
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise ValueError("OCR assets are missing; prepare the locale models before capture: " + ", ".join(missing))
        try:
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            from rapidocr import RapidOCR
        except ImportError as error:
            raise RuntimeError("RapidOCR is not installed; sync the capture package dependencies") from error
        if keys_path is None:
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 1
            metadata = onnxruntime.InferenceSession(str(paths[1]), options, providers=["CPUExecutionProvider"]).get_modelmeta().custom_metadata_map
            if "character" not in metadata:
                raise ValueError("Recognizer has no embedded dictionary; supply its keys_path before capture")
        self._engine = RapidOCR(params={"Det.model_path": str(paths[0]), "Rec.model_path": str(paths[1]),
            "Rec.rec_keys_path": str(keys_path) if keys_path is not None else None, "Rec.lang_type": language, "Global.use_cls": False,
            "Global.text_score": .75, "EngineConfig.onnxruntime.use_cuda": False,
            "EngineConfig.onnxruntime.use_dml": False, "EngineConfig.onnxruntime.use_coreml": False,
            "EngineConfig.onnxruntime.intra_op_num_threads": 2, "EngineConfig.onnxruntime.inter_op_num_threads": 1})

    @classmethod
    def from_bundled_models(cls):
        from pathlib import Path
        import rapidocr
        root = Path(rapidocr.__file__).parent / "models"
        return cls(detector_path=root / "PP-OCRv6_det_small.onnx", recognizer_path=root / "PP-OCRv6_rec_small.onnx")

    def read(self, image, *, region):
        import numpy as np
        result = self._engine(np.asarray(image.convert("RGB"))[:, :, ::-1])
        if result.txts is None or result.boxes is None or result.scores is None:
            return []
        width, height = image.size
        return [TextLine(str(text), float(score), (float(box[:, 0].min())/width, float(box[:, 1].min())/height,
                    float(box[:, 0].max())/width, float(box[:, 1].max())/height))
                for box, text, score in zip(result.boxes, result.txts, result.scores)]


class WindowsOCRReader:
    """Windows.Media.Ocr behind the same text boundary; run on the capture thread.

    Windows exposes no recognition scores. Its configured confidence is a
    conservative policy value, not a measured probability.
    """
    source = "windows-media-ocr"

    def __init__(self, locale: str, *, unscored_confidence: float = .5):
        import sys
        if sys.platform != "win32":
            raise RuntimeError("Windows.Media.Ocr requires Windows and its locale language pack")
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        self._engine = OcrEngine.try_create_from_language(Language(locale.replace("_", "-")))
        if self._engine is None:
            raise RuntimeError(f"Windows OCR language pack is unavailable for {locale}")
        self.confidence = unscored_confidence

    def read(self, image, *, region):
        import asyncio
        return asyncio.run(self._read(image))

    async def _read(self, image):
        from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.storage.streams import DataWriter
        writer = DataWriter()
        width, height = image.size
        writer.write_bytes(image.convert("RGBA").tobytes("raw", "BGRA"))
        bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8,
                                                        width, height, BitmapAlphaMode.IGNORE)
        try:
            result = await self._engine.recognize_async(bitmap)
            output = []
            for line in result.lines:
                words = list(line.words)
                if not words:
                    continue
                left = min(word.bounding_rect.x for word in words)
                top = min(word.bounding_rect.y for word in words)
                right = max(word.bounding_rect.x+word.bounding_rect.width for word in words)
                bottom = max(word.bounding_rect.y+word.bounding_rect.height for word in words)
                output.append(TextLine(line.text, self.confidence, (left/width, top/height, right/width, bottom/height)))
            return output
        finally:
            bitmap.close()
            writer.close()


class HybridOCR:
    """Digits first; text/OCR fallback records its actual provenance."""
    source = "hybrid-ocr"
    def __init__(self, digits, names, *, fallback=None):
        self.digits, self.names, self.fallback = digits, names, fallback
        self._sources = {}

    def source_for(self, region):
        return self._sources.get(region, self.source)

    def read(self, image, *, region):
        readers = [self.names]
        if region in {"gold", "hp", "level", "xp", "timer", "stage", "streak"}:
            readers.insert(0, self.digits)
        if self.fallback:
            readers.append(self.fallback)
        for reader in readers:
            try:
                lines = reader.read(image, region=region)
            except (RuntimeError, OSError, ValueError):
                continue
            if lines:
                self._sources[region] = reader.source
                return lines
        return []
