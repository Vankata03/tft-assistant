"""Authenticated finite evidence at the shared replay/display boundary."""

import json
import pytest


def test_evidence_pages_authenticate_membership_without_expanding_other_branches():
    from tft_engine.evidence import EvidenceGraph

    original = {"options": [{"option_id": str(i), "paired": list(range(2000))}
                            for i in range(30)], "other": list(range(10000))}
    graph = EvidenceGraph.factor(original)
    encoded = graph.to_dict()
    restored = EvidenceGraph.from_dict(encoded)
    page = restored.page(path=("options",), cursor=0, limit=4, max_bytes=4096)
    assert page["total"] == 30
    assert page["next_cursor"] == 4
    assert len(json.dumps(page).encode()) <= 4096
    assert [row["path"] for row in page["items"]] == [
        ["options", i] for i in range(4)]
    assert restored.resolve(path=("options", 3)) == original["options"][3]
    root = encoded["objects"][encoded["root_id"]]["value"]
    other_id = root["other"]["$evidence"]
    encoded["objects"][other_id]["value"] = "changed"
    corrupted = EvidenceGraph.from_dict(encoded)
    assert corrupted.resolve(path=("options", 3)) == original["options"][3]
    with pytest.raises(ValueError, match="identity"):
        corrupted.resolve()
    with pytest.raises(ValueError):
        restored.resolve(path=("options", True))


def test_evidence_preserves_literal_reference_keys_and_rejects_root_tampering():
    from tft_engine.evidence import EvidenceGraph

    original = {"$literal": {"$evidence": "ordinary user value"}}
    graph = EvidenceGraph.factor(original, threshold=10)
    assert graph.resolve() == original
    assert graph.resolve(path=("$literal", "$evidence")) == "ordinary user value"
    encoded = graph.to_dict()
    encoded["objects"][encoded["root_id"]]["value"] = {"other": 1}
    with pytest.raises(ValueError, match="identity"):
        EvidenceGraph.from_dict(encoded).resolve()
    with pytest.raises(ValueError):
        EvidenceGraph.factor({"invalid": float("nan")})


def test_long_unicode_text_pages_reconstruct_without_truncation():
    from tft_engine.evidence import EvidenceGraph, canonical_bytes

    text = "\U0001f680 source text\n" * 500
    graph = EvidenceGraph.factor({"description": text})
    cursor, chunks = 0, []
    while cursor is not None:
        page = graph.page(path=("description",), cursor=cursor, limit=10, max_bytes=1024)
        assert page["kind"] == "string"
        assert len(canonical_bytes(page)) <= 1024
        chunks.extend(row["value"] for row in page["items"])
        cursor = page["next_cursor"]
    assert "".join(chunks) == text
    with pytest.raises(ValueError):
        graph.page(path=("../other-game",))
    with pytest.raises(ValueError):
        graph.page(cursor=True)
    with pytest.raises(ValueError):
        EvidenceGraph.from_dict({"v": True, "root_id": graph.root_id, "objects": {}})


def test_reference_storage_is_immutable_and_missing_members_fail_visibly():
    from tft_engine.evidence import EvidenceGraph

    graph = EvidenceGraph.factor({"large": list(range(1000))})
    with pytest.raises(TypeError):
        graph.objects[graph.root_id] = b"replacement"
    serialized = graph.to_dict()
    child = serialized["objects"][graph.root_id]["value"]["large"]["$evidence"]
    del serialized["objects"][child]
    with pytest.raises(ValueError, match="unavailable"):
        EvidenceGraph.from_dict(serialized).resolve(path=("large",))
