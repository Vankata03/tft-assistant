"""Rate-limit checkpoints through real client requests and external clocks."""
import pytest

from tft_data.models import DataError
from tft_data.riot import HTTPResponse, RiotClient


def test_request_interrupted_after_dispatch_still_counts_after_client_restart(tmp_path):
    key, checkpoint = tmp_path/'key', tmp_path/'pacing.json'
    key.write_text('fixture-key')
    elapsed, sleeps = [0.0], []
    def sleep(seconds):
        sleeps.append(seconds)
        elapsed[0] += seconds
    def http(url, headers):
        if '/ids?' in url:
            return HTTPResponse(200, {'X-App-Rate-Limit': '2:120'}, ['EUN1_901'])
        raise DataError('Fixture transport interrupted after dispatch')
    options = dict(key_path=key, pacing_path=checkpoint, transport=http,
                   clock=lambda: elapsed[0], sleep=sleep)
    client = RiotClient(**options)
    client.owner_puuid = 'owner'
    client.match_ids()
    with pytest.raises(DataError, match='interrupted after dispatch'):
        client.match('EUN1_901')
    restarted = RiotClient(**options)
    restarted.owner_puuid = 'owner'
    assert restarted.match_ids() == ('EUN1_901',)
    assert any(delay >= 120 for delay in sleeps)


@pytest.mark.parametrize('raw', ['{}', '{"schema_version":true}', '{"schema_version":1,"saved_at":NaN,"rows":[]}'])
def test_corrupted_pacing_checkpoint_rejects_before_external_http(tmp_path, raw):
    checkpoint = tmp_path/'pacing.json'
    checkpoint.write_text(raw)
    requests = []
    with pytest.raises(DataError, match='pacing checkpoint invalid'):
        RiotClient(pacing_path=checkpoint, transport=lambda *args: requests.append(args))
    assert requests == []
    assert checkpoint.read_text() == raw
