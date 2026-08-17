[CmdletBinding()]
param(
    [string]$ComposeFile = "docker-compose.yml",
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Run this helper from Windows PowerShell/PowerShell, not from WSL."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composePath = Join-Path $repoRoot $ComposeFile
if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
    throw "Compose file not found: $composePath"
}

$storagePaths = [ordered]@{
    KB_MCP_DATA_PATH = Join-Path $repoRoot ".docker-data\mcp"
    KB_QDRANT_STORAGE_PATH = Join-Path $repoRoot ".docker-data\qdrant"
    KB_NEO4J_DATA_PATH = Join-Path $repoRoot ".docker-data\neo4j\data"
}

$previousValues = @{}
try {
    foreach ($entry in $storagePaths.GetEnumerator()) {
        $previousValues[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, "Process")
        New-Item -ItemType Directory -Force -Path $entry.Value | Out-Null
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }

    & docker compose --project-directory $repoRoot -f $composePath config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose config validation failed"
    }

    $upArgs = @("compose", "--project-directory", $repoRoot, "-f", $composePath, "up", "-d")
    if (-not $NoBuild) {
        $upArgs += "--build"
    }
    & docker @upArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed"
    }

    Write-Host "Persistent storage bind-mounted from:"
    foreach ($entry in $storagePaths.GetEnumerator()) {
        Write-Host "  $($entry.Key)=$($entry.Value)"
    }
}
finally {
    foreach ($entry in $storagePaths.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $previousValues[$entry.Key], "Process")
    }
}
