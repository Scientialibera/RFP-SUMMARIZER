param(
    [string]$ConfigPath = "$PSScriptRoot\deploy.config.toml"
)

. "$PSScriptRoot\deploy-common.ps1"

$scriptName = "upload-test-files"

$config = Get-Config -Path $ConfigPath
$repoRoot = Get-RepoRoot
$storageAccountName = Get-StorageAccountName -Config $config

# ---- 1. Capabilities PDF -> reference container ----

$capSource = Join-Path $repoRoot $config.test_docs.capabilities_source
$capBlob   = $config.capabilities.blob_name
$refContainer = $config.storage.reference_container

if (-not (Test-Path $capSource)) {
    Write-Host "WARNING: Capabilities PDF not found: $capSource" -ForegroundColor Yellow
} else {
    Write-Step $scriptName "Uploading capabilities: $($config.test_docs.capabilities_source) -> $refContainer/$capBlob"
    az storage blob upload `
        --account-name $storageAccountName `
        --container-name $refContainer `
        --file $capSource `
        --name $capBlob `
        --overwrite `
        --auth-mode login `
        -o none
}

# ---- 2. Test RFP PDF -> uploads container (triggers processing) ----

$rfpSource     = Join-Path $repoRoot $config.test_docs.rfp_source
$rfpBlobName   = Split-Path $rfpSource -Leaf
$inputContainer = $config.storage.input_container

if (-not (Test-Path $rfpSource)) {
    Write-Host "WARNING: Test RFP not found: $rfpSource" -ForegroundColor Yellow
} else {
    Write-Step $scriptName "Uploading test RFP: $($config.test_docs.rfp_source) -> $inputContainer/$rfpBlobName"
    Write-Host "  (This will trigger the Azure Function via Event Grid)" -ForegroundColor Yellow
    az storage blob upload `
        --account-name $storageAccountName `
        --container-name $inputContainer `
        --file $rfpSource `
        --name $rfpBlobName `
        --overwrite `
        --auth-mode login `
        -o none
}

Write-Step $scriptName "Test files uploaded."
