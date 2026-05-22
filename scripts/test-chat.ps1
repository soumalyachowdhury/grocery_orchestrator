param(
    [string]$Message = "Can you get my customer details for 2016588874?",
    [string]$Url = "http://127.0.0.1:8000/api/chat"
)

$ErrorActionPreference = "Stop"

$Body = @{
    message = $Message
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json" -Body $Body

