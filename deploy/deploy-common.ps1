# deploy-common.ps1 - Shared helper functions for all deploy scripts.
# Dot-source from each script:  . "$PSScriptRoot\deploy-common.ps1"

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Get-Config {
    param([string]$Path)
    if (-not (Test-Path $Path)) { throw "Config file not found: $Path" }
    $json = python -c "import json, pathlib, tomllib; p=pathlib.Path(r'$Path'); print(json.dumps(tomllib.loads(p.read_text(encoding='utf-8'))))"
    if ($LASTEXITCODE -ne 0) { throw "Failed to parse config file: $Path" }
    return $json | ConvertFrom-Json
}

function Select-Value {
    param([string]$Configured, [string]$Default)
    if ([string]::IsNullOrWhiteSpace($Configured)) { return $Default }
    return $Configured
}

function Write-Step {
    param(
        [string]$ScriptName,
        [string]$Message
    )
    Write-Host "`n[$ScriptName] $Message" -ForegroundColor Cyan
}

function Get-RepoRoot {
    return (Resolve-Path "$PSScriptRoot\..").Path
}

function Get-StorageAccountName {
    param([object]$Config)
    $name = $Config.naming.storage_account_name
    if ([string]::IsNullOrWhiteSpace($name)) {
        $normalized = ($Config.naming.prefix.ToLower() -replace "[^a-z0-9]", "")
        if ($normalized.Length -lt 3) { $normalized = $normalized + "123" }
        if ($normalized.Length -gt 22) { $normalized = $normalized.Substring(0, 22) }
        $name = "st$normalized"
    }
    return $name
}

function Normalize-CogName {
    param([string]$Prefix, [string]$Value)
    $n = ($Value.ToLower() -replace "[^a-z0-9-]", "")
    if ($n.Length -gt 18) { $n = $n.Substring(0, 18) }
    return "$Prefix-$n"
}

function Normalize-AcrName {
    param([string]$Value)
    $n = ($Value.ToLower() -replace "[^a-z0-9]", "")
    if ($n.Length -gt 47) { $n = $n.Substring(0, 47) }
    return "acr$n"
}

function Ensure-RoleAssignment {
    param(
        [string]$PrincipalId,
        [string]$Scope,
        [string]$Role,
        [string]$PrincipalType = "ServicePrincipal"
    )
    $count = az role assignment list --assignee-object-id $PrincipalId --scope $Scope --query "[?roleDefinitionName=='$Role'] | length(@)" -o tsv
    if ($LASTEXITCODE -ne 0) { throw "Failed to query role assignments for '$Role'." }
    if ($count -eq "0") {
        Write-Host "    Assigning '$Role'."
        az role assignment create --assignee-object-id $PrincipalId --assignee-principal-type $PrincipalType --role $Role --scope $Scope | Out-Null
    } else {
        Write-Host "    '$Role' already assigned."
    }
}

function Ensure-ProviderRegistered {
    param([string]$Namespace)
    $state = az provider show --namespace $Namespace --query registrationState -o tsv 2>$null
    if ($state -ne "Registered") {
        Write-Host "    Registering provider '$Namespace'..."
        az provider register --namespace $Namespace --wait | Out-Null
    }
}
