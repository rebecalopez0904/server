<#
Usage (from repository root):
  .\server\scripts\reset_business_data.ps1

Reads database settings from .\server\.env and runs
.\server\scripts\reset_business_data.sql using mysql.
#>

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Values,
        [Parameter(Mandatory = $true)]
        [string[]]$Keys,
        [string]$Default = ''
    )

    foreach ($key in $Keys) {
        if ($Values.ContainsKey($key) -and -not [string]::IsNullOrWhiteSpace($Values[$key])) {
            return $Values[$key]
        }
    }

    return $Default
}

$serverDir = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $serverDir '.env'
$sqlPath = Join-Path $PSScriptRoot 'reset_business_data.sql'

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing env file: $envPath"
}

if (-not (Test-Path -LiteralPath $sqlPath)) {
    throw "Missing SQL file: $sqlPath"
}

$envValues = @{}
Get-Content -LiteralPath $envPath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#') -or $line -notmatch '^[A-Za-z_][A-Za-z0-9_]*=') {
        return
    }

    $parts = $line -split '=', 2
    $key = $parts[0].Trim()
    $value = if ($parts.Count -gt 1) { $parts[1].Trim() } else { '' }

    if (
        (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) -and
        ($value.Length -ge 2)
    ) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    $envValues[$key] = $value
}

$dbHost = Get-EnvValue -Values $envValues -Keys @('DB_HOST', 'MYSQL_HOST')
$dbPort = Get-EnvValue -Values $envValues -Keys @('DB_PORT', 'MYSQL_PORT') -Default '3306'
$dbUser = Get-EnvValue -Values $envValues -Keys @('DB_USER', 'DB_USERNAME', 'MYSQL_USER')
$dbPassword = Get-EnvValue -Values $envValues -Keys @('DB_PASSWORD', 'MYSQL_PASSWORD')
$dbName = Get-EnvValue -Values $envValues -Keys @('DB_NAME', 'DB_DATABASE', 'MYSQL_DATABASE')

$missing = @()
if ([string]::IsNullOrWhiteSpace($dbHost)) { $missing += 'DB_HOST' }
if ([string]::IsNullOrWhiteSpace($dbUser)) { $missing += 'DB_USER' }
if ([string]::IsNullOrWhiteSpace($dbName)) { $missing += 'DB_NAME' }

if ($missing.Count -gt 0) {
    throw "Missing required env values in ${envPath}: $($missing -join ', ')"
}

$mysqlArgs = @(
    "--host=$dbHost"
    "--port=$dbPort"
    "--user=$dbUser"
    "$dbName"
)

$previousMysqlPwd = if (Test-Path Env:MYSQL_PWD) { $env:MYSQL_PWD } else { $null }

try {
    if (-not [string]::IsNullOrEmpty($dbPassword)) {
        $env:MYSQL_PWD = $dbPassword
    }

    $mysqlProcess = Start-Process -FilePath 'mysql' -ArgumentList $mysqlArgs -NoNewWindow -Wait -PassThru -RedirectStandardInput $sqlPath
    if ($mysqlProcess.ExitCode -ne 0) {
        throw "mysql exited with code $($mysqlProcess.ExitCode)."
    }

    Write-Host "Business-data reset script finished successfully."
}
finally {
    if ($null -eq $previousMysqlPwd) {
        Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue
    }
    else {
        $env:MYSQL_PWD = $previousMysqlPwd
    }
}
