param(
    [ValidateSet("all","backend","frontend")]
    [string]$Target = "all"
)

. "$PSScriptRoot\deploy-common.ps1"

$scriptName = "deploy-apps"

# Fix Windows charmap encoding issue with az acr build log streaming
$env:PYTHONIOENCODING = "utf-8"

# Load saved env from deploy-infra.ps1
$envFile = Join-Path $PSScriptRoot "webapp-env.json"
if (-not (Test-Path $envFile)) { throw "Run deploy-infra.ps1 first to create $envFile" }
$wenv = Get-Content $envFile -Raw | ConvertFrom-Json

$rg              = $wenv.resourceGroup
$acrName         = $wenv.acrName
$acrLoginServer  = $wenv.acrLoginServer
$backendAppName  = $wenv.backendAppName
$frontendAppName = $wenv.frontendAppName
$tenantId        = $wenv.tenantId
$beAppId         = $wenv.beAppId
$feAppId         = $wenv.feAppId
$apiScope        = $wenv.apiScope
$backendUrl      = $wenv.backendUrl

$repoRoot = Get-RepoRoot
$tag = Get-Date -Format "yyyyMMddHHmmss"

Write-Step $scriptName "Configuration"
Write-Output "  ACR:      $acrLoginServer"
Write-Output "  Backend:  $backendAppName"
Write-Output "  Frontend: $frontendAppName"
Write-Output "  Tag:      $tag"
Write-Output "  Repo:     $repoRoot"

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

if ($Target -eq "all" -or $Target -eq "backend") {
    Write-Step $scriptName "Building backend image in ACR"
    $backendDockerfile = [System.IO.Path]::Combine($repoRoot, "api", "Dockerfile")
    $runId = az acr build `
      --registry $acrName `
      --resource-group $rg `
      --image "${backendAppName}:${tag}" `
      -f $backendDockerfile `
      --no-logs `
      --query "id" -o tsv `
      $repoRoot
    if ($LASTEXITCODE -ne 0) { throw "Backend image build failed to queue." }
    $beRunShort = ($runId.Split('/'))[-1]
    Write-Output "  Build queued: $beRunShort"
    Write-Output "  Polling for completion..."
    do {
        Start-Sleep -Seconds 10
        $status = az acr task show-run --registry $acrName --resource-group $rg --run-id $beRunShort --query status -o tsv
        Write-Output "    Status: $status"
    } while ($status -eq "Running" -or $status -eq "Queued")
    if ($status -ne "Succeeded") { throw "Backend image build failed with status: $status" }

    Write-Step $scriptName "Updating backend Container App"
    az containerapp update `
      --name $backendAppName `
      --resource-group $rg `
      --image "$acrLoginServer/${backendAppName}:${tag}" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Backend container app update failed." }

    Write-Step $scriptName "Setting backend env vars"
    $storageUrl = $wenv.storageAccountUrl
    $outContainer = $wenv.outputContainer
    $promptsCont = $wenv.promptsContainer
    $readerRole = $wenv.readerRole
    $adminRole = $wenv.adminRole
    az containerapp update `
      --name $backendAppName `
      --resource-group $rg `
      --set-env-vars "STORAGE_ACCOUNT_URL=$storageUrl" "OUTPUT_CONTAINER=$outContainer" "PROMPTS_CONTAINER=$promptsCont" "AUTH_ENABLED=true" "READER_ROLE=$readerRole" "ADMIN_ROLE=$adminRole" | Out-Null

    Write-Output "  Backend updated."
}

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

if ($Target -eq "all" -or $Target -eq "frontend") {
    Write-Step $scriptName "Building frontend image in ACR (VITE env vars baked in)"
    $frontendDockerfile = [System.IO.Path]::Combine($repoRoot, "frontend", "Dockerfile")
    $feRunId = az acr build `
      --registry $acrName `
      --resource-group $rg `
      --image "${frontendAppName}:${tag}" `
      -f $frontendDockerfile `
      --build-arg "VITE_TENANT_ID=$tenantId" `
      --build-arg "VITE_CLIENT_ID=$feAppId" `
      --build-arg "VITE_API_CLIENT_ID=$beAppId" `
      --build-arg "VITE_API_SCOPE=$apiScope" `
      --build-arg "VITE_API_BASE_URL=$backendUrl" `
      --no-logs `
      --query "id" -o tsv `
      $repoRoot
    if ($LASTEXITCODE -ne 0) { throw "Frontend image build failed to queue." }
    $feRunShort = ($feRunId.Split('/'))[-1]
    Write-Output "  Build queued: $feRunShort"
    Write-Output "  Polling for completion..."
    do {
        Start-Sleep -Seconds 10
        $feStatus = az acr task show-run --registry $acrName --resource-group $rg --run-id $feRunShort --query status -o tsv
        Write-Output "    Status: $feStatus"
    } while ($feStatus -eq "Running" -or $feStatus -eq "Queued")
    if ($feStatus -ne "Succeeded") { throw "Frontend image build failed with status: $feStatus" }

    Write-Step $scriptName "Updating frontend Container App"
    az containerapp update `
      --name $frontendAppName `
      --resource-group $rg `
      --image "$acrLoginServer/${frontendAppName}:${tag}" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Frontend container app update failed." }

    Write-Output "  Frontend updated."
}

Write-Step $scriptName "DEPLOYMENT COMPLETE"
Write-Output "  Backend:  $backendUrl"
Write-Output "  Frontend: $($wenv.frontendUrl)"
