$ErrorActionPreference = 'Stop'
$body = @{
  token = 'postal-local'
  event_type = 'collection_log'
  event_time = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
  confidence = 1.0
  payload = @{
    message = 'TEST: New item added to your collection log: Twisted bow'
    name = 'Twisted bow'
  }
} | ConvertTo-Json -Depth 5

$r = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8787/api/game-events' -ContentType 'application/json' -Body $body
Write-Host "Bridge OK. Event ID: $($r.event_id)" -ForegroundColor Green
Write-Host "Refresh the Postal AutoClip dashboard and check the RuneLite game-event bridge panel."
