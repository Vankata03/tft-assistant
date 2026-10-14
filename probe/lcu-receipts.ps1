# Read-only LCU payload receipts. Credentials stay in memory; files are private probe artifacts.
function Protect-LcuPayload($Value) {
    if ($Value -is [System.Collections.IDictionary]) {
        $safe = [ordered]@{}
        foreach ($key in $Value.Keys) {
            if ($key -match '(?i)token|authorization|password|api.?key|encryption.?key|credential') {
                $safe[$key] = '[redacted]'
            } else { $safe[$key] = Protect-LcuPayload $Value[$key] }
        }
        return $safe
    }
    if ($Value -is [array]) {
        return ,@($Value | ForEach-Object { Protect-LcuPayload $_ })
    }
    return $Value
}

function Save-LcuReceipts {
    param([string]$Base, [hashtable]$Headers, [string[]]$Secrets, [string]$OutputRoot)
    $uri = [Uri]$Base
    if ($uri.Host -ne '127.0.0.1' -or $uri.Scheme -notin @('http','https') -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/') {
        throw 'LCU receipts require a local loopback base URL'
    }
    $null = New-Item -ItemType Directory -Force -Path $OutputRoot
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.ServerCertificateCustomValidationCallback = [System.Net.Http.HttpClientHandler]::DangerousAcceptAnyServerCertificateValidator
    $client = [System.Net.Http.HttpClient]::new($handler)
    try {
        foreach ($endpoint in @('/lol-gameflow/v1/session','/lol-end-of-game/v1/tft-eog-stats')) {
            $receipt = [ordered]@{ endpoint=$endpoint; requested_at=[DateTimeOffset]::UtcNow.ToString('o'); status=0; received_at=$null; body_file=$null; unavailable_reason=$null; credentials_redacted=$true }
            $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, "$Base$endpoint")
            $response = $null
            $stream = $null
            $cancellation = [System.Threading.CancellationTokenSource]::new(3000)
            try {
                foreach ($name in $Headers.Keys) { $null = $request.Headers.TryAddWithoutValidation($name, $Headers[$name]) }
                $response = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead, $cancellation.Token).GetAwaiter().GetResult()
                $receipt.status = [int]$response.StatusCode
                $stream = $response.Content.ReadAsStreamAsync($cancellation.Token).GetAwaiter().GetResult()
                $buffer = [byte[]]::new(8192)
                $body = [System.IO.MemoryStream]::new()
                try {
                    do {
                        $count = $stream.ReadAsync($buffer, 0, $buffer.Length, $cancellation.Token).GetAwaiter().GetResult()
                        if ($body.Length + $count -gt 1048576) { throw 'payload_limit' }
                        $body.Write($buffer, 0, $count)
                    } while ($count -gt 0)
                    $text = [Text.Encoding]::UTF8.GetString($body.ToArray())
                } finally { $body.Dispose() }
                foreach ($secret in @($Secrets) + @($Headers.Values)) {
                    if ($secret) { $text = $text.Replace($secret, '[redacted]') }
                }
                try {
                    $safe = Protect-LcuPayload (ConvertFrom-Json -InputObject $text -AsHashtable -Depth 100 -ErrorAction Stop)
                    $text = ConvertTo-Json -InputObject $safe -Depth 100
                } catch { $receipt.unavailable_reason = 'payload_not_json' }
                if (-not $receipt.unavailable_reason) {
                    $name = $endpoint.Trim('/').Replace('/','_') + '.' + [Guid]::NewGuid().ToString('N') + '.json'
                    $receipt.body_file = Join-Path $OutputRoot $name
                    Set-Content -LiteralPath $receipt.body_file -Value $text -Encoding utf8
                }
            } catch {
                # Exception text can contain request credentials. Store a fixed reason only.
                $receipt.body_file = $null
                $receipt.unavailable_reason = if ($_.Exception.Message -eq 'payload_limit') { 'payload_limit' } else { 'request_or_capture_failed' }
            } finally {
                $receipt.received_at = [DateTimeOffset]::UtcNow.ToString('o')
                if ($stream) { $stream.Dispose() }
                if ($response) { $response.Dispose() }
                $request.Dispose()
                $cancellation.Dispose()
            }
            ($receipt | ConvertTo-Json -Compress) | Add-Content -LiteralPath (Join-Path $OutputRoot 'receipts.jsonl')
            [pscustomobject]$receipt
        }
    } finally { $client.Dispose(); $handler.Dispose() }
}
