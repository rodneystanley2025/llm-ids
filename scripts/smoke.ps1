$ErrorActionPreference = "Stop"

Invoke-RestMethod http://localhost:8000/health | Out-Host

Invoke-RestMethod -Method Post http://localhost:8000/v1/events `
  -ContentType "application/json" `
  -Body '{"session_id":"smoke","turn_id":1,"role":"user","content":"hello"}' | Out-Host

Invoke-RestMethod http://localhost:8000/v1/sessions/smoke | Out-Host
