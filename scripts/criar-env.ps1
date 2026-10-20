$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
function Segredo([int]$n) { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count $n | ForEach-Object { [char]$_ }) }
$linhas = (Get-Content (Join-Path $raiz ".env.example")) `
  -replace "^DB_PASSWORD=.*", "DB_PASSWORD=$(Segredo 40)" `
  -replace "^APP_SECRET_KEY=.*", "APP_SECRET_KEY=$(Segredo 60)"
[IO.File]::WriteAllLines((Join-Path $raiz ".env"), $linhas)
Write-Host "Arquivo .env criado com senha do banco e chave secreta aleatorias."
