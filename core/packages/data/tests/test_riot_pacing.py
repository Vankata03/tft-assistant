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


@pytest.mark.parametrize('raw', ['{}', '{"schema_version":true}', '{"schema_version":1,"saved_at":NaN,"rows":[]}',
    '{"schema_version":1,"saved_at":10,"rows":[],"cooldowns":{"europe":NaN}}',
    '{"schema_version":1,"saved_at":10,"rows":[],"cooldowns":{"europe":true}}',
    '{"schema_version":1,"saved_at":10,"rows":[],"cooldowns":{"europe":9}}'])
def test_corrupted_pacing_checkpoint_rejects_before_external_http(tmp_path, raw):
    checkpoint = tmp_path/'pacing.json'
    checkpoint.write_text(raw)
    requests = []
    with pytest.raises(DataError, match='pacing checkpoint invalid'):
        RiotClient(pacing_path=checkpoint, transport=lambda *args: requests.append(args))
    assert requests == []
    assert checkpoint.read_text() == raw


@pytest.mark.parametrize('rollback', [False, True])
def test_retry_after_survives_interrupted_sleep_and_client_restart(tmp_path, rollback):
    key, checkpoint = tmp_path/'key', tmp_path/'pacing.json'
    key.write_text('fixture-key')
    now, requests = [10.0], []
    class ChildTerminated(BaseException):
        pass
    def http(url, headers):
        requests.append(now[0])
        return HTTPResponse(429, {'Retry-After': '120'}, None) if len(requests) == 1 else HTTPResponse(200, {}, [])
    def interrupted_sleep(delay):
        raise ChildTerminated()
    def sleep(delay):
        now[0] += delay
    options = dict(key_path=key, pacing_path=checkpoint, transport=http, clock=lambda: now[0])
    first = RiotClient(**options, sleep=interrupted_sleep)
    first.owner_puuid = 'owner'
    with pytest.raises(ChildTerminated):
        first.match_ids()
    if rollback:
        now[0] = 0.0
    restarted_at = now[0]
    second = RiotClient(**options, sleep=sleep)
    second.owner_puuid = 'owner'
    assert second.match_ids() == ()
    assert requests[-1] - restarted_at >= 120
