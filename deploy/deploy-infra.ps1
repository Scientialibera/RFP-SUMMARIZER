param(
    [string]$ConfigPath = "$PSScriptRoot\deploy.config.toml"
)

. "$PSScriptRoot\deploy-common.ps1"

$scriptName = "deploy-infra"

# ===========================================================================
# Script-specific helpers (Graph, ARM, AD)
# ===========================================================================

function Invoke-GraphPatch {
    param([string]$ObjectId, [hashtable]$Body)
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        $Body | ConvertTo-Json -Depth 10 | Set-Content -Path $tmp -Encoding UTF8
        az rest --method PATCH --url "https://graph.microsoft.com/v1.0/applications/$ObjectId" --headers "Content-Type=application/json" --body "@$tmp" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Graph PATCH failed for $ObjectId." }
    } finally { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
}

function Invoke-ArmPut {
    param([string]$Url, [hashtable]$Body)
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        $Body | ConvertTo-Json -Depth 10 | Set-Content -Path $tmp -Encoding UTF8
        az rest --method PUT --url $Url --headers "Content-Type=application/json" --body "@$tmp" | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning "ARM PUT failed: $Url" }
    } finally { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
}

function Invoke-ArmPatch {
    param([string]$Url, [hashtable]$Body)
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        $Body | ConvertTo-Json -Depth 10 | Set-Content -Path $tmp -Encoding UTF8
        az rest --method PATCH --url $Url --headers "Content-Type=application/json" --body "@$tmp" | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning "ARM PATCH failed: $Url" }
    } finally { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
}

# ===========================================================================
# Load config
# ===========================================================================

$config = Get-Config -Path $ConfigPath

$subscriptionId = $config.azure.subscription_id
if ([string]::IsNullOrWhiteSpace($subscriptionId)) { $subscriptionId = az account show --query id -o tsv }
$tenantId = az account show --query tenantId -o tsv

$prefix   = $config.naming.prefix.ToLower()
$location = Select-Value $config.azure.location "eastus2"
$rg       = Select-Value $config.azure.resource_group_name "rg-$prefix"

$functionAppName    = Select-Value $config.naming.function_app_name    "func-$prefix"
$storageAccountName = Get-StorageAccountName -Config $config
$openAiAccount      = Select-Value $config.naming.openai_account_name  (Normalize-CogName -Prefix "aoai" -Value $prefix)
$acrName            = Select-Value $config.naming.acr_name             (Normalize-AcrName -Value $prefix)
$backendAppName     = Select-Value $config.naming.backend_app_name     "api-$prefix"
$frontendAppName    = Select-Value $config.naming.frontend_app_name    "web-$prefix"
$envName            = "cae-$prefix"

$sqlServerName  = Select-Value $config.naming.sql_server_name  "sql-$prefix"
$sqlDatabaseName = Select-Value $config.naming.sql_database_name "sqldb-$prefix"

$deployOpenAI  = [bool]$config.openai.deploy_openai_resources
$deployWebApps = [bool]$config.webapp.deploy_webapp_resources
$deploySql     = [bool]$config.sql.deploy_sql_resources
$outputMode    = $config.app_settings.output_mode   # "storage" or "sql"

$inputContainer     = $config.storage.input_container
$referenceContainer = $config.storage.reference_container
$outputContainer    = $config.storage.output_container
$promptsContainer   = $config.storage.prompts_container

Write-Step $scriptName "Configuration"
Write-Output "  Subscription:  $subscriptionId"
Write-Output "  Tenant:        $tenantId"
Write-Output "  RG:            $rg"
Write-Output "  Storage:       $storageAccountName"
Write-Output "  OpenAI:        $openAiAccount"
Write-Output "  Function App:  $functionAppName"
Write-Output "  ACR:           $acrName"
Write-Output "  Backend CA:    $backendAppName"
Write-Output "  Frontend CA:   $frontendAppName"
Write-Output "  SQL Server:    $sqlServerName (deploy=$deploySql)"
Write-Output "  Output Mode:   $outputMode"

az account set --subscription $subscriptionId

$executorObjectId = az ad signed-in-user show --query id -o tsv
if ([string]::IsNullOrWhiteSpace($executorObjectId)) { throw "Could not resolve signed-in user." }

# ===================================================================
# SECTION A - Core infrastructure (Storage, OpenAI, Function App)
# ===================================================================

# ---------------------------------------------------------------------------
# A1. Resource Group
# ---------------------------------------------------------------------------

Write-Step $scriptName "A1. Resource Group '$rg'"
$rgExists = az group exists --name $rg -o tsv
if ($rgExists -ne "true") { az group create --name $rg --location $location | Out-Null }
$rgScope = az group show --name $rg --query id -o tsv

# ---------------------------------------------------------------------------
# A2. Storage Account + containers
# ---------------------------------------------------------------------------

Write-Step $scriptName "A2. Storage Account '$storageAccountName'"
$storageExists = az storage account list --resource-group $rg --query "[?name=='$storageAccountName'] | length(@)" -o tsv
if ($storageExists -eq "0") {
    az storage account create --resource-group $rg --name $storageAccountName --location $location --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false | Out-Null
}
$storageScope = az storage account show --resource-group $rg --name $storageAccountName --query id -o tsv
$storageAccountUrl = "https://$storageAccountName.blob.core.windows.net"
Ensure-RoleAssignment -PrincipalId $executorObjectId -PrincipalType User -Scope $storageScope -Role "Storage Blob Data Owner"

foreach ($c in @($inputContainer, $referenceContainer, $outputContainer, $promptsContainer)) {
    $exists = az storage container exists --account-name $storageAccountName --name $c --auth-mode login --query exists -o tsv
    if ($exists -ne "true") { az storage container create --account-name $storageAccountName --name $c --auth-mode login | Out-Null }
}

# ---------------------------------------------------------------------------
# A3. Azure OpenAI
# ---------------------------------------------------------------------------

Write-Step $scriptName "A3. Azure OpenAI '$openAiAccount'"
if ($deployOpenAI) {
    $aoaiExists = az cognitiveservices account list --resource-group $rg --query "[?name=='$openAiAccount'] | length(@)" -o tsv
    if ($aoaiExists -eq "0") {
        az cognitiveservices account create --name $openAiAccount --resource-group $rg --kind OpenAI --sku S0 --location $location --custom-domain $openAiAccount | Out-Null
    }
    $deploymentName = $config.openai.deployment_name
    $depExists = az cognitiveservices account deployment list --name $openAiAccount --resource-group $rg --query "[?name=='$deploymentName'] | length(@)" -o tsv
    if ($depExists -eq "0") {
        az cognitiveservices account deployment create --name $openAiAccount --resource-group $rg --deployment-name $deploymentName --model-format OpenAI --model-name $config.openai.model_name --model-version $config.openai.model_version --sku-name $config.openai.deployment_sku_name --sku-capacity $config.openai.capacity | Out-Null
    }
}
$aoaiEndpoint = az cognitiveservices account show --resource-group $rg --name $openAiAccount --query properties.endpoint -o tsv
$aoaiScope    = az cognitiveservices account show --resource-group $rg --name $openAiAccount --query id -o tsv

# ---------------------------------------------------------------------------
# A4. Function App (Flex Consumption)
# ---------------------------------------------------------------------------

Write-Step $scriptName "A4. Function App '$functionAppName'"
$funcExists = az functionapp list --resource-group $rg --query "[?name=='$functionAppName'] | length(@)" -o tsv
if ($funcExists -eq "0") {
    az functionapp create --resource-group $rg --name $functionAppName --storage-account $storageAccountName --flexconsumption-location $location --runtime python --runtime-version 3.11 --functions-version 4 | Out-Null
}
az functionapp identity assign --resource-group $rg --name $functionAppName --identities [system] | Out-Null
$funcPrincipalId = az functionapp identity show --resource-group $rg --name $functionAppName --query principalId -o tsv

# ---------------------------------------------------------------------------
# A5. Function App RBAC
# ---------------------------------------------------------------------------

Write-Step $scriptName "A5. Function App RBAC"
Ensure-RoleAssignment -PrincipalId $funcPrincipalId -Scope $storageScope -Role "Storage Blob Data Contributor"
Ensure-RoleAssignment -PrincipalId $funcPrincipalId -Scope $aoaiScope    -Role "Cognitive Services OpenAI User"

# ---------------------------------------------------------------------------
# A6. Function App Settings
# ---------------------------------------------------------------------------

Write-Step $scriptName "A6. Function App Settings"
$appSettings = @(
    "AZURE_OPENAI_ENDPOINT=$aoaiEndpoint",
    "AZURE_OPENAI_MODEL=$($config.openai.deployment_name)",
    "AZURE_OPENAI_API_VERSION=$($config.openai.api_version)",
    "STORAGE_ACCOUNT_NAME=$storageAccountName",
    "STORAGE_ACCOUNT_URL=$storageAccountUrl",
    "RFP_CONTAINER=$inputContainer",
    "INPUT_CONTAINER=$inputContainer",
    "REFERENCE_CONTAINER=$referenceContainer",
    "OUTPUT_CONTAINER=$outputContainer",
    "CAPABILITIES_BLOB=$($config.capabilities.blob_name)",
    "PROMPTS_CONTAINER=$promptsContainer",
    "SYSTEM_PROMPT_BLOB=$($config.prompts.system_prompt_blob)",
    "USER_PROMPT_BLOB=$($config.prompts.user_prompt_blob)",
    "CHUNK_SYSTEM_PROMPT_BLOB=$($config.prompts.chunk_system_prompt_blob)",
    "CHUNK_USER_PROMPT_BLOB=$($config.prompts.chunk_user_prompt_blob)",
    "RECONCILE_SYSTEM_PROMPT_BLOB=$($config.prompts.reconcile_system_prompt_blob)",
    "RECONCILE_USER_PROMPT_BLOB=$($config.prompts.reconcile_user_prompt_blob)",
    "SCHEMA_BLOB_PATH=$($config.schemas.full_blob_path)",
    "CHUNK_SCHEMA_BLOB_PATH=$($config.schemas.chunk_blob_path)",
    "CHUNKING_ENABLED=$($config.app_settings.chunking_enabled)",
    "CHUNKING_MAX_TOKENS=$($config.app_settings.chunking_max_tokens)",
    "TOGGLE_TABLE=$($config.app_settings.toggle_table)",
    "TOGGLE_IMAGES=$($config.app_settings.toggle_images)",
    "MAX_ATTACHED_IMAGES=$($config.app_settings.max_attached_images)",
    "OUTPUT_MODE=$($config.app_settings.output_mode)",
    "UPLOAD_ASSETS=$($config.app_settings.upload_assets)",
    "SHAREPOINT_ENABLED=$($config.app_settings.sharepoint_enabled)"
)
az functionapp config appsettings set --resource-group $rg --name $functionAppName --settings $appSettings | Out-Null

# ===================================================================
# SECTION A7 - Azure SQL (conditional)
# ===================================================================

$sqlConnectionString = ""

if ($deploySql -or $outputMode -eq "sql") {

    Write-Step $scriptName "A7. Azure SQL Server '$sqlServerName'"

    $sqlExists = az sql server list --resource-group $rg --query "[?name=='$sqlServerName'] | length(@)" -o tsv
    if ($sqlExists -eq "0" -and $deploySql) {
        az sql server create `
          --name $sqlServerName `
          --resource-group $rg `
          --location $location `
          --enable-ad-only-auth `
          --external-admin-principal-type User `
          --external-admin-name (az ad signed-in-user show --query userPrincipalName -o tsv) `
          --external-admin-sid $executorObjectId | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to create SQL Server." }

        # Allow Azure services to connect
        az sql server firewall-rule create `
          --server $sqlServerName `
          --resource-group $rg `
          --name AllowAzureServices `
          --start-ip-address 0.0.0.0 `
          --end-ip-address 0.0.0.0 | Out-Null
    }

    Write-Step $scriptName "A7. Azure SQL Database '$sqlDatabaseName'"
    $dbExists = az sql db list --server $sqlServerName --resource-group $rg --query "[?name=='$sqlDatabaseName'] | length(@)" -o tsv
    if ($dbExists -eq "0" -and $deploySql) {
        $sqlSku = Select-Value $config.sql.sku "Basic"
        az sql db create `
          --server $sqlServerName `
          --resource-group $rg `
          --name $sqlDatabaseName `
          --edition $sqlSku `
          --max-size $config.sql.max_size_bytes | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to create SQL Database." }
    }

    $sqlFqdn = az sql server show --name $sqlServerName --resource-group $rg --query fullyQualifiedDomainName -o tsv
    $sqlConnectionString = "Server=$sqlFqdn;Database=$sqlDatabaseName;Authentication=Active Directory Default;"
    Write-Output "  SQL FQDN: $sqlFqdn"

    # Add SQL connection string to function app settings
    Write-Step $scriptName "A7. Adding SQL connection string to Function App"
    az functionapp config appsettings set --resource-group $rg --name $functionAppName --settings "SQL_CONNECTION_STRING=$sqlConnectionString" | Out-Null

    Write-Step $scriptName "A7. SQL schema init"
    $schemaFile = Join-Path $PSScriptRoot "assets" "sql" "init_schema.sql"
    if (Test-Path $schemaFile) {
        Write-Output "  Schema file: $schemaFile"
        Write-Output "  Run manually: sqlcmd -S $sqlFqdn -d $sqlDatabaseName -G -i `"$schemaFile`""
        Write-Output "  (Or use Azure Portal Query Editor with AD auth)"
    }

} else {
    Write-Step $scriptName "A7. SQL - skipped (output_mode='$outputMode', deploy_sql=$deploySql)"
}

# ===================================================================
# SECTION B - Web Viewer infrastructure (ACR, Container Apps, Auth)
# ===================================================================

if (-not $deployWebApps) {
    Write-Step $scriptName "webapp.deploy_webapp_resources = false - skipping Section B."
} else {

# ---------------------------------------------------------------------------
# B1. Provider registrations
# ---------------------------------------------------------------------------

Write-Step $scriptName "B1. Provider registrations"
Ensure-ProviderRegistered -Namespace "Microsoft.ContainerRegistry"
Ensure-ProviderRegistered -Namespace "Microsoft.App"

# ---------------------------------------------------------------------------
# B2. Azure Container Registry
# ---------------------------------------------------------------------------

Write-Step $scriptName "B2. Azure Container Registry '$acrName'"
$acrExists = az acr list --resource-group $rg --query "[?name=='$acrName'] | length(@)" -o tsv
if ($acrExists -eq "0") {
    az acr create --name $acrName --resource-group $rg --location $location --sku Basic --admin-enabled true | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create ACR." }
}
$acrLoginServer = az acr show --name $acrName --resource-group $rg --query loginServer -o tsv
$acrId          = az acr show --name $acrName --resource-group $rg --query id -o tsv
Write-Output "  Login server: $acrLoginServer"

# ---------------------------------------------------------------------------
# B3. Container Apps Environment
# ---------------------------------------------------------------------------

Write-Step $scriptName "B3. Container Apps Environment '$envName'"
$caeExists = az containerapp env list --resource-group $rg --query "[?name=='$envName'] | length(@)" -o tsv
if ($caeExists -eq "0") {
    az containerapp env create --name $envName --resource-group $rg --location $location | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Container Apps Environment." }
}

# ---------------------------------------------------------------------------
# B4. Backend Container App
# ---------------------------------------------------------------------------

$placeholderImage = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"

Write-Step $scriptName "B4. Backend Container App '$backendAppName'"
$beExists = az containerapp list --resource-group $rg --query "[?name=='$backendAppName'] | length(@)" -o tsv
if ($beExists -eq "0") {
    az containerapp create --name $backendAppName --resource-group $rg --environment $envName --image $placeholderImage --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --system-assigned | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create backend Container App." }
}
try { az containerapp identity assign --name $backendAppName --resource-group $rg --system-assigned 2>&1 | Out-Null } catch {}
$beMiId = az containerapp show --name $backendAppName --resource-group $rg --query "identity.principalId" -o tsv
Ensure-RoleAssignment -PrincipalId $beMiId -Scope $acrId -Role "AcrPull"
Ensure-RoleAssignment -PrincipalId $beMiId -Scope $storageScope -Role "Storage Blob Data Contributor"

# Configure registry on backend container app
try { az containerapp registry set --name $backendAppName --resource-group $rg --server $acrLoginServer --identity system 2>&1 | Out-Null } catch {}

$backendFqdn = az containerapp show --name $backendAppName --resource-group $rg --query "properties.configuration.ingress.fqdn" -o tsv
$backendUrl  = "https://$backendFqdn"
Write-Output "  Backend URL: $backendUrl"

# ---------------------------------------------------------------------------
# B5. Frontend Container App
# ---------------------------------------------------------------------------

Write-Step $scriptName "B5. Frontend Container App '$frontendAppName'"
$feExists = az containerapp list --resource-group $rg --query "[?name=='$frontendAppName'] | length(@)" -o tsv
if ($feExists -eq "0") {
    az containerapp create --name $frontendAppName --resource-group $rg --environment $envName --image $placeholderImage --ingress external --target-port 8080 --min-replicas 0 --max-replicas 1 --system-assigned | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create frontend Container App." }
}
try { az containerapp identity assign --name $frontendAppName --resource-group $rg --system-assigned 2>&1 | Out-Null } catch {}
$feMiId = az containerapp show --name $frontendAppName --resource-group $rg --query "identity.principalId" -o tsv
Ensure-RoleAssignment -PrincipalId $feMiId -Scope $acrId -Role "AcrPull"

try { az containerapp registry set --name $frontendAppName --resource-group $rg --server $acrLoginServer --identity system 2>&1 | Out-Null } catch {}

$frontendFqdn = az containerapp show --name $frontendAppName --resource-group $rg --query "properties.configuration.ingress.fqdn" -o tsv
$frontendUrl  = "https://$frontendFqdn"
Write-Output "  Frontend URL: $frontendUrl"

# ---------------------------------------------------------------------------
# B6. Azure AD App Registration - Backend API
# ---------------------------------------------------------------------------

Write-Step $scriptName "B6. Azure AD - Backend API app registration"
$beAppId = az ad app list --display-name $backendAppName --query "[0].appId" -o tsv
if ([string]::IsNullOrWhiteSpace($beAppId)) {
    $beAppId = az ad app create --display-name $backendAppName --sign-in-audience AzureADMyOrg --query appId -o tsv
}
$beObjectId    = az ad app show --id $beAppId --query id -o tsv
$identifierUri = "api://$beAppId"

$existingUris = az ad app show --id $beAppId --query "identifierUris" -o json | ConvertFrom-Json
if ($existingUris -notcontains $identifierUri) {
    az ad app update --id $beAppId --identifier-uris $identifierUri
}

# Expose scope: access_as_user
$existingScopes = az ad app show --id $beAppId --query "api.oauth2PermissionScopes" -o json | ConvertFrom-Json
$hasScope = $existingScopes | Where-Object { $_.value -eq "access_as_user" }
if (-not $hasScope) {
    $scopeId = [guid]::NewGuid().ToString()
    Invoke-GraphPatch -ObjectId $beObjectId -Body @{
        api = @{ oauth2PermissionScopes = @(
            @{
                adminConsentDescription = "Allow the frontend to access the RFP API on behalf of the signed-in user."
                adminConsentDisplayName = "Access RFP API"
                id = $scopeId; isEnabled = $true; type = "User"
                userConsentDescription = "Allow the app to access the RFP API on your behalf."
                userConsentDisplayName = "Access RFP API"
                value = "access_as_user"
            }
        )}
    }
    $existingScopes = az ad app show --id $beAppId --query "api.oauth2PermissionScopes" -o json | ConvertFrom-Json
}
$accessScopeId = ($existingScopes | Where-Object { $_.value -eq "access_as_user" }).id
$apiScope = "api://$beAppId/access_as_user"
Write-Output "  Backend App ID:  $beAppId"
Write-Output "  Scope ID:        $accessScopeId"

$beSp = az ad sp list --filter "appId eq '$beAppId'" --query "[0].id" -o tsv
if ([string]::IsNullOrWhiteSpace($beSp)) { $beSp = az ad sp create --id $beAppId --query id -o tsv }

# --- B6b. App Roles (Reader / Admin) ---
Write-Step $scriptName "B6b. App Roles on backend registration"
$readerRoleValue = Select-Value $config.auth.reader_role "RFP.Reader"
$adminRoleValue  = Select-Value $config.auth.admin_role  "RFP.Admin"

$existingRoles = az ad app show --id $beAppId --query "appRoles" -o json | ConvertFrom-Json
$hasReader = $existingRoles | Where-Object { $_.value -eq $readerRoleValue }
$hasAdmin  = $existingRoles | Where-Object { $_.value -eq $adminRoleValue }

if (-not $hasReader -or -not $hasAdmin) {
    $roles = @()
    if ($hasReader) {
        $roles += @{ id = $hasReader.id; displayName = $hasReader.displayName; description = $hasReader.description; isEnabled = $true; value = $readerRoleValue; allowedMemberTypes = @("User","Application") }
    } else {
        $roles += @{ id = [guid]::NewGuid().ToString(); displayName = "RFP Reader"; description = "Read-only access to RFP runs and results"; isEnabled = $true; value = $readerRoleValue; allowedMemberTypes = @("User","Application") }
    }
    if ($hasAdmin) {
        $roles += @{ id = $hasAdmin.id; displayName = $hasAdmin.displayName; description = $hasAdmin.description; isEnabled = $true; value = $adminRoleValue; allowedMemberTypes = @("User","Application") }
    } else {
        $roles += @{ id = [guid]::NewGuid().ToString(); displayName = "RFP Admin"; description = "Read and write access: modify prompts and schemas"; isEnabled = $true; value = $adminRoleValue; allowedMemberTypes = @("User","Application") }
    }
    Invoke-GraphPatch -ObjectId $beObjectId -Body @{ appRoles = $roles }
    Write-Output "  App Roles created: $readerRoleValue, $adminRoleValue"
} else {
    Write-Output "  App Roles already exist."
}

$readerRoleId = (az ad app show --id $beAppId --query "appRoles[?value=='$readerRoleValue'].id" -o tsv)
$adminRoleId  = (az ad app show --id $beAppId --query "appRoles[?value=='$adminRoleValue'].id" -o tsv)

# --- B6c. Assign App Roles ---
Write-Step $scriptName "B6c. Assigning App Roles"

function Ensure-AppRoleAssignment {
    param([string]$ServicePrincipalId, [string]$PrincipalId, [string]$RoleId, [string]$Label)
    $existing = az rest --method GET --url "https://graph.microsoft.com/v1.0/servicePrincipals/$ServicePrincipalId/appRoleAssignedTo" --query "value[?principalId=='$PrincipalId' && appRoleId=='$RoleId'] | length(@)" -o tsv 2>$null
    if ($existing -eq "0" -or [string]::IsNullOrWhiteSpace($existing)) {
        $tmpFile = [System.IO.Path]::GetTempFileName()
        try {
            @{ principalId = $PrincipalId; resourceId = $ServicePrincipalId; appRoleId = $RoleId } | ConvertTo-Json | Set-Content -Path $tmpFile -Encoding UTF8
            az rest --method POST --url "https://graph.microsoft.com/v1.0/servicePrincipals/$ServicePrincipalId/appRoleAssignedTo" --headers "Content-Type=application/json" --body "@$tmpFile" | Out-Null
            Write-Output "    Assigned $Label"
        } finally { Remove-Item -Force $tmpFile -ErrorAction SilentlyContinue }
    } else {
        Write-Output "    $Label already assigned"
    }
}

# Auto-assign deployer as Admin
Ensure-AppRoleAssignment -ServicePrincipalId $beSp -PrincipalId $executorObjectId -RoleId $adminRoleId -Label "Admin -> deployer"
# Also give deployer Reader (Admin implies reader in the app, but explicit is clearer)
Ensure-AppRoleAssignment -ServicePrincipalId $beSp -PrincipalId $executorObjectId -RoleId $readerRoleId -Label "Reader -> deployer"

# Assign configured reader users
$readerUsers = @()
if ($config.auth.reader_users) { $readerUsers = @($config.auth.reader_users) }
foreach ($userRef in $readerUsers) {
    $oid = az ad user show --id $userRef --query id -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($oid)) { $oid = az ad group show --group $userRef --query id -o tsv 2>$null }
    if (-not [string]::IsNullOrWhiteSpace($oid)) {
        Ensure-AppRoleAssignment -ServicePrincipalId $beSp -PrincipalId $oid -RoleId $readerRoleId -Label "Reader -> $userRef"
    } else { Write-Warning "Could not resolve user/group: $userRef" }
}

# Assign configured admin users
$adminUsers = @()
if ($config.auth.admin_users) { $adminUsers = @($config.auth.admin_users) }
foreach ($userRef in $adminUsers) {
    $oid = az ad user show --id $userRef --query id -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($oid)) { $oid = az ad group show --group $userRef --query id -o tsv 2>$null }
    if (-not [string]::IsNullOrWhiteSpace($oid)) {
        Ensure-AppRoleAssignment -ServicePrincipalId $beSp -PrincipalId $oid -RoleId $adminRoleId -Label "Admin -> $userRef"
        Ensure-AppRoleAssignment -ServicePrincipalId $beSp -PrincipalId $oid -RoleId $readerRoleId -Label "Reader -> $userRef"
    } else { Write-Warning "Could not resolve user/group: $userRef" }
}

# ---------------------------------------------------------------------------
# B7. Azure AD App Registration - Frontend SPA
# ---------------------------------------------------------------------------

Write-Step $scriptName "B7. Azure AD - Frontend SPA app registration"
$feAppId = az ad app list --display-name $frontendAppName --query "[0].appId" -o tsv
if ([string]::IsNullOrWhiteSpace($feAppId)) {
    $feAppId = az ad app create --display-name $frontendAppName --sign-in-audience AzureADMyOrg --query appId -o tsv
}
$feObjectId = az ad app show --id $feAppId --query id -o tsv

# SPA redirect URIs
Invoke-GraphPatch -ObjectId $feObjectId -Body @{
    spa = @{ redirectUris = @($frontendUrl, "$frontendUrl/", "http://localhost:5173", "http://localhost:5173/") }
}

# API permission to backend
$existingPerms = az ad app show --id $feAppId --query "requiredResourceAccess" -o json | ConvertFrom-Json
$hasBackendPerm = $existingPerms | Where-Object { $_.resourceAppId -eq $beAppId }
if (-not $hasBackendPerm) {
    Invoke-GraphPatch -ObjectId $feObjectId -Body @{
        requiredResourceAccess = @(@{ resourceAppId = $beAppId; resourceAccess = @(@{ id = $accessScopeId; type = "Scope" }) })
    }
}

$feSp = az ad sp list --filter "appId eq '$feAppId'" --query "[0].id" -o tsv
if ([string]::IsNullOrWhiteSpace($feSp)) { az ad sp create --id $feAppId | Out-Null }

try { az ad app permission admin-consent --id $feAppId 2>&1 | Out-Null } catch {}
Write-Output "  Frontend App ID: $feAppId"

# ---------------------------------------------------------------------------
# B8. Easy Auth on Backend Container App
# ---------------------------------------------------------------------------

Write-Step $scriptName "B8. Easy Auth on backend"
$authUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$rg/providers/Microsoft.App/containerApps/$backendAppName/authConfigs/current?api-version=2024-03-01"
Invoke-ArmPut -Url $authUrl -Body @{
    properties = @{
        platform = @{ enabled = $true }
        globalValidation = @{ unauthenticatedClientAction = "AllowAnonymous" }
        identityProviders = @{
            azureActiveDirectory = @{
                enabled = $true
                registration = @{ openIdIssuer = "https://login.microsoftonline.com/$tenantId/v2.0"; clientId = $beAppId }
                validation   = @{ allowedAudiences = @($identifierUri, $backendUrl) }
            }
        }
    }
}

# ---------------------------------------------------------------------------
# B9. CORS on Backend
# ---------------------------------------------------------------------------

Write-Step $scriptName "B9. CORS on backend"
$corsPatchUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$rg/providers/Microsoft.App/containerApps/${backendAppName}?api-version=2024-03-01"
Invoke-ArmPatch -Url $corsPatchUrl -Body @{
    properties = @{
        configuration = @{
            ingress = @{
                external = $true; targetPort = 8000
                corsPolicy = @{
                    allowedOrigins   = @($frontendUrl, "http://localhost:5173")
                    allowedMethods   = @("GET","POST","PUT","DELETE","OPTIONS")
                    allowedHeaders   = @("Authorization","Content-Type")
                    allowCredentials = $true
                }
            }
        }
    }
}

# ---------------------------------------------------------------------------
# B10. Save webapp-env.json for deploy-apps.ps1
# ---------------------------------------------------------------------------

Write-Step $scriptName "B10. Saving webapp-env.json"
$envFile = Join-Path $PSScriptRoot "webapp-env.json"
@{
    tenantId          = $tenantId
    subscriptionId    = $subscriptionId
    resourceGroup     = $rg
    acrName           = $acrName
    acrLoginServer    = $acrLoginServer
    envName           = $envName
    backendAppName    = $backendAppName
    frontendAppName   = $frontendAppName
    beAppId           = $beAppId
    feAppId           = $feAppId
    identifierUri     = $identifierUri
    apiScope          = $apiScope
    accessScopeId     = $accessScopeId
    backendUrl        = $backendUrl
    frontendUrl       = $frontendUrl
    storageAccountUrl = $storageAccountUrl
    outputContainer   = $outputContainer
    promptsContainer  = $promptsContainer
    readerRole        = $readerRoleValue
    adminRole         = $adminRoleValue
} | ConvertTo-Json -Depth 3 | Set-Content -Path $envFile -Encoding UTF8

} # end if deployWebApps

# ===================================================================
# Summary
# ===================================================================

Write-Step $scriptName "INFRASTRUCTURE DEPLOYMENT COMPLETE"
Write-Output ""
Write-Output "  Resource Group:    $rg"
Write-Output "  Storage Account:   $storageAccountName ($storageAccountUrl)"
Write-Output "  Azure OpenAI:      $openAiAccount ($aoaiEndpoint)"
Write-Output "  Function App:      $functionAppName"
Write-Output "  Output Mode:       $outputMode"
if ($sqlConnectionString) {
    Write-Output "  SQL Server:        $sqlServerName ($sqlFqdn)"
    Write-Output "  SQL Database:      $sqlDatabaseName"
}
if ($deployWebApps) {
    Write-Output ""
    Write-Output "  ACR:               $acrLoginServer"
    Write-Output "  Backend CA:        $backendAppName ($backendUrl)"
    Write-Output "  Frontend CA:       $frontendAppName ($frontendUrl)"
    Write-Output "  Backend App ID:    $beAppId"
    Write-Output "  Frontend App ID:   $feAppId"
    Write-Output "  API Scope:         $apiScope"
}
Write-Output ""
Write-Output "Next steps:"
Write-Output "  1. deploy/upload-prompts.ps1    - upload prompts & schemas to blob"
Write-Output "  2. deploy/deploy-function.ps1   - deploy function code + Event Grid"
Write-Output "  3. deploy/deploy-apps.ps1       - build images & deploy to Container Apps"
