param(
    [string]$ConfigPath = "$PSScriptRoot\deploy.config.toml"
)

. "$PSScriptRoot\deploy-common.ps1"

$scriptName = "upload-prompts"

$config = Get-Config -Path $ConfigPath
$repoRoot = Get-RepoRoot
$storageAccountName = Get-StorageAccountName -Config $config
$container = $config.storage.prompts_container

$uploads = @(
    @{ Source = $config.paths.system_prompt_source;            Blob = $config.prompts.system_prompt_blob },
    @{ Source = $config.paths.user_prompt_source;              Blob = $config.prompts.user_prompt_blob },
    @{ Source = $config.paths.chunk_system_prompt_source;      Blob = $config.prompts.chunk_system_prompt_blob },
    @{ Source = $config.paths.chunk_user_prompt_source;        Blob = $config.prompts.chunk_user_prompt_blob },
    @{ Source = $config.paths.reconcile_system_prompt_source;  Blob = $config.prompts.reconcile_system_prompt_blob },
    @{ Source = $config.paths.reconcile_user_prompt_source;    Blob = $config.prompts.reconcile_user_prompt_blob },
    @{ Source = $config.paths.full_schema_source;              Blob = $config.schemas.full_blob_path },
    @{ Source = $config.paths.chunk_schema_source;             Blob = $config.schemas.chunk_blob_path }
)

foreach ($item in $uploads) {
    $source = Join-Path $repoRoot $item.Source
    $blob = $item.Blob
    if (-not (Test-Path $source)) {
        Write-Host "WARNING: Source file not found: $source" -ForegroundColor Yellow
        continue
    }
    Write-Step $scriptName "Uploading $($item.Source) -> $container/$blob"
    az storage blob upload `
        --account-name $storageAccountName `
        --container-name $container `
        --file $source `
        --name $blob `
        --overwrite `
        --auth-mode login `
        -o none
}

Write-Step $scriptName "All prompts and schemas uploaded to '$container' container in '$storageAccountName'."
