param(
    [string]$Version = '25.3.2'
)
$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$sandbox = Join-Path $workspace '.tmp/testops-sandbox'
$vendor = Join-Path $workspace '.tmp/testops-vendor'
$revision = 'bc3f0c5c57773392112a4d46306f404dad7bd401'
if ($Version -notmatch '^[0-9]+(\.[0-9]+){2,3}$') { throw 'Invalid TestOps version' }
if (Test-Path -LiteralPath (Join-Path $sandbox '.env')) {
    throw 'Sandbox already prepared. Existing credentials are preserved; use its compose commands.'
}
if (-not (Test-Path -LiteralPath $vendor)) {
    git clone https://github.com/qameta/testops-deploy-compose.git $vendor
    if ($LASTEXITCODE -ne 0) { throw 'Cannot download official deployment configuration' }
}
$actual = (git -C $vendor rev-parse HEAD).Trim()
if ($actual -ne $revision) {
    throw "Vendor revision differs from $revision; review it before preparing this sandbox."
}
if (git -C $vendor status --porcelain) { throw 'Vendor checkout has local changes' }
New-Item -ItemType Directory -Force -Path $sandbox | Out-Null
Copy-Item -LiteralPath (Join-Path $vendor 'testops-demo/docker-compose.yml') -Destination $sandbox
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'compose.override.yaml') -Destination $sandbox
$settings = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $vendor 'testops-demo/env-example')) {
    if ($line -match '^([A-Z0-9_]+)=(.*)$') { $settings[$Matches[1]] = $Matches[2] }
}
function New-SandboxSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes)
}
foreach ($key in @(
    'DEMO_INSTANCE_JWT_SECRET', 'DEMO_INSTANCE_CRYPTO_PASSWORD',
    'DEMO_INSTANCE_REDIS_PASS', 'DEMO_INSTANCE_TESTOPS_DB_PASS',
    'DEMO_INSTANCE_RABBIT_PASS', 'RABBIT_ERLANG_COOKIE',
    'DEMO_INSTANCE_S3_ACCESS_KEY', 'DEMO_INSTANCE_S3_SECRET_KEY'
)) { $settings[$key] = New-SandboxSecret }
$settings['RELEASE_TO_DEPLOY'] = $Version
$settings['DEMO_INSTANCE_HOST'] = 'localhost:18080'
$settings['DEMO_INSTANCE_PORT'] = '18080'
$settings['FIRST_ADMIN_EMAIL'] = 'admin@testence.local'
$settings['TZ'] = 'Europe/Moscow'
$settings['SMTP_HOST'] = 'mailpit'
$settings['SMTP_PORT'] = '1025'
$settings['SMTP_USERNAME'] = ''
$settings['SMTP_PASSWORD'] = ''
$settings['SMTP_MAIL_FROM'] = 'testops@testence.local'
$settings['SMTP_AUTH'] = 'false'
$settings['SMTP_STARTTLS_ENABLE'] = 'false'
$settings['SMTP_STARTTLS_REQUIRED'] = 'false'
$settings['SMTP_SSL_TRUST'] = ''
$settings['COMPOSE_PROJECT_NAME'] = 'testence-testops-sandbox'
$encoding = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines(
    (Join-Path $sandbox '.env'),
    [string[]]@($settings.Keys | Sort-Object | ForEach-Object { "$_=$($settings[$_])" }),
    $encoding
)
docker compose --project-directory $sandbox -f (Join-Path $sandbox 'docker-compose.yml') -f (Join-Path $sandbox 'compose.override.yaml') config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed; credentials have been preserved for diagnosis' }
Write-Output "Prepared $sandbox (official revision $revision). Credentials are stored only in ignored .env."
Write-Output 'Next: obtain a trial license and registry access, then start using the README commands.'
