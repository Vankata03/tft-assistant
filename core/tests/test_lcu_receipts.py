"""Read-only probe receipts preserve endpoint shapes without credentials."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import threading

import pytest


@pytest.mark.parametrize('payload_kind', ('valid', 'oversize', 'nonjson'))
def test_real_local_endpoint_receipts_preserve_status_time_and_redact_credentials(tmp_path, payload_kind):
    powershell = shutil.which('pwsh')
    if not powershell:
        pytest.skip('This operator workflow check requires PowerShell 7')
    secret = 'fixture-secret-auth'
    encoded = base64.b64encode(f'riot:{secret}'.encode()).decode()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('Authorization')))
            status = 200 if self.path.endswith('/session') else 404
            body = json.dumps({'gameData': {'gameId': 901, 'gameMode': 'TFT'},
                'token': secret, 'nested': {'note': encoded,
                    'clientSecret': 'fixture-client-credential',
                    'client_secret': 'fixture-snake-credential',
                    'SECRET': 'fixture-uppercase-credential',
                    'ClientSECRET': 'fixture-mixed-credential',
                    'secret': 'fixture-secret-field',
                    'displayName': 'preserved player label',
                    'Title': 'upper-case label', 'title': 'lower-case label'}, 'placements': [4]}).encode()
            if payload_kind == 'oversize':
                body = b'x' * 1048577
            elif payload_kind == 'nonjson':
                body = b'password=unknown-auth-material'
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    helper = Path(__file__).parents[2] / 'probe/lcu-receipts.ps1'
    driver = tmp_path / 'driver.ps1'
    driver.write_text('''param($Helper,$Out,$Base,$Token,$Encoded)
$ErrorActionPreference='Stop'
. $Helper
Save-LcuReceipts -Base $Base -Headers @{Authorization="Basic $Encoded"} -Secrets @($Token,$Encoded) -OutputRoot $Out | ConvertTo-Json -Depth 10
''')
    try:
        result = subprocess.run([powershell, '-NoProfile', '-File', str(driver),
            str(helper), str(tmp_path / 'receipts'), f'http://127.0.0.1:{server.server_port}',
            secret, encoded], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        receipts = json.loads(result.stdout)
        assert [r['status'] for r in receipts] == [200, 404]
        assert all(r['requested_at'] and r['received_at'] for r in receipts)
        assert [r[0] for r in requests] == ['/lol-gameflow/v1/session', '/lol-end-of-game/v1/tft-eog-stats']
        assert all(r[1] == f'Basic {encoded}' for r in requests)
        outputs = ''.join(p.read_text() for p in (tmp_path / 'receipts').rglob('*') if p.is_file())
        assert secret not in outputs and encoded not in outputs
        assert secret not in result.stdout + result.stderr and encoded not in result.stdout + result.stderr
        for credential in ('fixture-client-credential', 'fixture-snake-credential',
                'fixture-uppercase-credential', 'fixture-mixed-credential', 'fixture-secret-field'):
            assert credential not in outputs + result.stdout + result.stderr
        if payload_kind == 'valid':
            payload = json.loads(Path(receipts[0]['body_file']).read_text())
            assert payload['gameData'] == {'gameId': 901, 'gameMode': 'TFT'}
            assert payload['placements'] == [4]
            assert payload['token'] == '[redacted]'
            assert payload['nested']['displayName'] == 'preserved player label'
            assert payload['nested']['Title'] == 'upper-case label'
            assert payload['nested']['title'] == 'lower-case label'
            for key in ('clientSecret', 'client_secret', 'SECRET', 'ClientSECRET', 'secret'):
                assert payload['nested'][key] == '[redacted]'
        else:
            reason = 'payload_limit' if payload_kind == 'oversize' else 'payload_not_json'
            assert all(r['unavailable_reason'] == reason and r['body_file'] is None for r in receipts)
            assert 'unknown-auth-material' not in outputs
    finally:
        server.shutdown()
        server.server_close()
