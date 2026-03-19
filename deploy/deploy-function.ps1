param(
    [string]$ConfigPath = "$PSScriptRoot\deploy.config.toml"
)

. "$PSScriptRoot\deploy-common.ps1"

$scriptName = "deploy-function"

function Ensure-FunctionIndexed {
    param(
        [string]$SubscriptionId,
        [string]$ResourceGroup,
        [string]$FunctionAppName,
        [string]$FunctionName
    )
    Write-Step $scriptName "Waiting for function '$FunctionName' to be indexed by the host..."
    $deadline = (Get-Date).AddMinutes(5)
    do {
        $listed = az functionapp function list `
          --name $FunctionAppName `
          --resource-group $ResourceGroup `
          --query "[?contains(name, '$FunctionName')] | length(@)" -o tsv 2>$null
        if ($listed -gt 0) {
            Write-Step $scriptName "Function '$FunctionName' is indexed."
            return
        }
        Start-Sleep -Seconds 10
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for function '$FunctionName' to be indexed."
}

function Ensure-EventSubscriptionAzureFunction {
    param(
        [string]$SourceResourceId,
        [string]$EventSubscriptionName,
        [string]$SubjectBeginsWith,
        [string]$FunctionResourceId
    )

    $deadline = (Get-Date).AddMinutes(5)
    do {
        az eventgrid event-subscription create `
          --name $EventSubscriptionName `
          --source-resource-id $SourceResourceId `
          --included-event-types Microsoft.Storage.BlobCreated `
          --subject-begins-with $SubjectBeginsWith `
          --endpoint-type azurefunction `
          --endpoint $FunctionResourceId | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 10
    } while ((Get-Date) -lt $deadline)

    throw "Failed to create Event Grid subscription '$EventSubscriptionName' with Azure Function endpoint."
}

# ---------------------------------------------------------------------------
# Load config and derive names
# ---------------------------------------------------------------------------

$config = Get-Config -Path $ConfigPath
$repoRoot = Get-RepoRoot
$functionDir = Join-Path $repoRoot "azure-function"

$subscriptionId = $config.azure.subscription_id
if ([string]::IsNullOrWhiteSpace($subscriptionId)) { $subscriptionId = az account show --query id -o tsv }

$prefix = $config.naming.prefix.ToLower()
$resourceGroup = Select-Value $config.azure.resource_group_name "rg-$prefix"
$functionAppName = Select-Value $config.naming.function_app_name "func-$prefix"
$storageAccountName = Get-StorageAccountName -Config $config
$inputContainer = $config.storage.input_container

# ---------------------------------------------------------------------------
# 1. Deploy function code (must run from azure-function directory)
# ---------------------------------------------------------------------------

Write-Step $scriptName "Deploying function code to '$functionAppName'..."
Push-Location $functionDir
try {
    func azure functionapp publish $functionAppName --python
} finally {
    Pop-Location
}
Write-Step $scriptName "Function deployment complete."

# ---------------------------------------------------------------------------
# 2. Create Event Grid subscription for blob trigger
# ---------------------------------------------------------------------------

Ensure-ProviderRegistered -Namespace "Microsoft.EventGrid"

$functionName = "RfpBlobTrigger"
Ensure-FunctionIndexed `
    -SubscriptionId $subscriptionId `
    -ResourceGroup $resourceGroup `
    -FunctionAppName $functionAppName `
    -FunctionName $functionName

$sourceResourceId = az storage account show `
    --name $storageAccountName `
    --resource-group $resourceGroup `
    --query id -o tsv

$eventSubName = "evg-rfp-upload-created"
$eventSubCount = az eventgrid event-subscription list `
    --source-resource-id $sourceResourceId `
    --query "[?name=='$eventSubName'] | length(@)" -o tsv

$functionResourceId = "/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Web/sites/$functionAppName/functions/$functionName"

if ($eventSubCount -ne "0") {
    Write-Step $scriptName "Deleting existing Event Grid subscription '$eventSubName'..."
    az eventgrid event-subscription delete `
        --name $eventSubName `
        --source-resource-id $sourceResourceId | Out-Null
    Start-Sleep -Seconds 5
}

Write-Step "Creating Event Grid subscription '$eventSubName'..."
Ensure-EventSubscriptionAzureFunction `
    -SourceResourceId $sourceResourceId `
    -EventSubscriptionName $eventSubName `
    -SubjectBeginsWith "/blobServices/default/containers/$inputContainer/blobs/" `
    -FunctionResourceId $functionResourceId

Write-Step $scriptName "Event Grid subscription ensured."
Write-Step $scriptName "Deployment complete. Upload an RFP PDF to '$inputContainer' to trigger processing."
