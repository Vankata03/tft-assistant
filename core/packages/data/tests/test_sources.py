"""Public source contracts using captured external-service response shapes."""

import io
import json
from datetime import UTC, datetime

from tft_data.sources import HTTPSource, MemorySource


TIERS_URL = "https://example.invalid/augments_tiers"
DONOR_URL = "https://example.invalid/unit_items_processed"


def external_responses(monkeypatch, responses):
    """Replace only network I/O; source parsing and qualification remain real."""

    def open_response(request, **kwargs):
        return io.BytesIO(json.dumps(responses[request.full_url]).encode())

    monkeypatch.setattr("urllib.request.urlopen", open_response)


def test_tier_metadata_belongs_to_tier_payload_and_donor_is_only_a_hint(monkeypatch):
    # Metadata excerpt from the checked 2026-10-10 primary responses. The tier
    # body has no patch/cohort; the donor describes a different publication.
    tiers = {
        "updated": 1791641438134,
        "tft_set": "TFTSet18",
        "tier_list_set": "TFTSet18",
        "queue_id": 1100,
        "content": {
            "updated_at": "2026-10-10T05:21:29.598Z",
            "created_at": "2026-08-07T19:49:57.225Z",
        },
    }
    donor = {
        "updated": 1791641414471,
        "region_patch_adjustment": {
            "global_patch": {
                "patch": "18.4",
                "b_patch_version": "b",
                "external_patch": "18.4",
            }
        },
    }
    external_responses(monkeypatch, {TIERS_URL: tiers, DONOR_URL: donor})
    source = HTTPSource(
        "metatft_augment_tiers",
        "enrichment",
        TIERS_URL,
        DONOR_URL,
        provider="metatft",
    )

    metadata = source.metadata()

    assert metadata.updated_at == datetime(2026, 10, 10, 14, 10, 38, 134000, UTC)
    assert metadata.patch is None
    assert metadata.identity == {
        "tft_set": "TFTSet18",
        "tier_list_set": "TFTSet18",
        "queue_id": 1100,
    }
    assert metadata.publication["content_updated_at"] == "2026-10-10T05:21:29.598Z"
    assert metadata.donor_hint["patch"] == "18.4"
    assert metadata.donor_hint["updated_at"] == "2026-10-10T14:10:14.471000+00:00"
    assert source.fetch() == tiers


def test_cached_owned_metadata_cannot_gain_a_fixture_patch():
    source = MemorySource(
        "metatft",
        "enrichment",
        "invented.patch",
        datetime(2026, 10, 11, tzinfo=UTC),
        {
            "updated": 1791641438134,
            "tft_set": "TFTSet18",
            "tier_list_set": "TFTSet18",
            "queue_id": 1100,
            "global_augment_tiers": {},
        },
    )
    metadata = source.metadata()
    assert metadata.patch is None
    assert not metadata.qualified
    assert metadata.updated_at == datetime(2026, 10, 10, 14, 10, 38, 134000, UTC)


def test_confirmed_metadata_preserves_its_own_revision_and_cohort(monkeypatch):
    revision = {"patch": "18.4", "b_patch_version": "b", "external_patch": "18.4"}
    body = {
        "updated": 1791641414471,
        "region_patch_adjustment": {"global_patch": revision},
        "filters": {"minimum_rank": "DIAMOND", "regions": "all"},
    }
    external_responses(monkeypatch, {DONOR_URL: body})
    source = HTTPSource(
        "units",
        "statistics",
        DONOR_URL,
        provider="metatft",
        required_cohort={"minimum_rank": "DIAMOND", "regions": "all"},
    )

    metadata = source.metadata()

    assert metadata.qualified and metadata.patch == "18.4"
    assert metadata.identity["global_patch"] == revision
    assert metadata.cohort == {"minimum_rank": "DIAMOND", "regions": "all"}
    assert metadata.donor_hint == {}


def test_invalid_owned_filters_fail_visibly_instead_of_crashing(monkeypatch):
    import pytest
    from tft_data.models import DataError

    external_responses(
        monkeypatch,
        {DONOR_URL: {"patch": "18.4", "updated": 1791641414471, "filters": None}},
    )
    source = HTTPSource(
        "units",
        "statistics",
        DONOR_URL,
        provider="metatft",
        required_cohort={"minimum_rank": "DIAMOND", "regions": "all"},
    )
    with pytest.raises(DataError, match="metadata"):
        source.metadata()


def test_provider_enum_and_requested_query_do_not_become_observed_cohort(monkeypatch):
    url = "https://example.invalid/units?rank=DIAMOND&regions=all"
    external_responses(
        monkeypatch,
        {
            url: {
                "patch": "18.4",
                "updated_at": "2026-10-10T14:10:38+00:00",
                "aperture": {"rankGroup": 1, "gameType": 0, "queue": 1100},
            }
        },
    )
    source = HTTPSource(
        "tactics.tools",
        "statistics",
        "https://example.invalid/units",
        query={"rank": "DIAMOND", "regions": "all"},
        expected_filters={"rankGroup": 1},
        required_cohort={"minimum_rank": "DIAMOND", "regions": "all"},
    )
    metadata = source.metadata()
    assert not metadata.qualified
    assert metadata.filters["rankGroup"] == 1
    assert metadata.cohort == {"minimum_rank": None, "regions": None}
    assert "regions" in "; ".join(metadata.qualification_reasons)


def test_invalid_donor_does_not_supply_or_replace_primary_identity(monkeypatch):
    external_responses(
        monkeypatch,
        {
            TIERS_URL: {"patch": "18.4", "updated": 1791641438134},
            DONOR_URL: {"patch": "invented.patch"},
        },
    )
    metadata = HTTPSource(
        "tiers", "enrichment", TIERS_URL, DONOR_URL, provider="metatft"
    ).metadata()
    assert metadata.qualified and metadata.patch == "18.4"
    assert metadata.updated_at == datetime(2026, 10, 10, 14, 10, 38, 134000, UTC)
    assert metadata.donor_hint["error"]


def test_offline_provider_identity_without_timestamp_cannot_use_fixture_freshness():
    import pytest
    from tft_data.models import DataError

    source = MemorySource(
        "metatft",
        "enrichment",
        "invented.patch",
        datetime(2026, 10, 11, tzinfo=UTC),
        {"tft_set": "TFTSet18", "queue_id": 1100, "global_augment_tiers": {}},
    )
    with pytest.raises(DataError, match="metadata"):
        source.metadata()


def test_offline_tactics_publication_without_patch_cannot_use_fixture_identity():
    source = MemorySource(
        "tactics.tools",
        "statistics",
        "invented.patch",
        datetime(2026, 10, 11, tzinfo=UTC),
        {
            "props": {
                "pageProps": {
                    "statsData": {"lastUpdated": 1791641438},
                    "aperture": {"rankGroup": 1},
                }
            }
        },
    )
    metadata = source.metadata()
    assert metadata.patch is None and not metadata.qualified
    assert metadata.updated_at == datetime(2026, 10, 10, 14, 10, 38, tzinfo=UTC)
    assert metadata.filters["rankGroup"] == 1


def test_opaque_patch_enum_is_preserved_without_inventing_a_label(monkeypatch):
    external_responses(
        monkeypatch,
        {
            DONOR_URL: {
                "patch": {"_0": 16200},
                "updated_at": "2026-10-10T14:10:38+00:00",
            }
        },
    )
    metadata = HTTPSource("units", "statistics", DONOR_URL).metadata()
    assert metadata.patch is None and not metadata.qualified
    assert metadata.identity["patch"] == {"_0": 16200}


def test_invalid_cohort_configuration_cannot_treat_unknown_values_as_goals(tmp_path):
    import pytest
    from tft_data.models import DataError
    from tft_data.source_config import SourceConfiguration

    manifest = tmp_path / "sources.toml"
    manifest.write_text("""schema_version=1
[statistics]
minimum_rank=false
regions="all"
[refresh]
sources=[]
[sources]
""")
    with pytest.raises(DataError, match="cohort"):
        SourceConfiguration.load(manifest)
