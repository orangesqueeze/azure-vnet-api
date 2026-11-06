terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    azuread = { source = "hashicorp/azuread", version = "~> 3.0" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

provider "azuread" {}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

locals {
  suffix       = random_string.suffix.result
  storage_name = substr("${var.base_name}${local.suffix}", 0, 24)
  app_name     = "${var.base_name}-${local.suffix}"
}

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
}

resource "random_uuid" "scope" {}

# Entra ID app registration = the API's audience
resource "azuread_application" "api" {
  display_name     = "${var.base_name}-api"
  sign_in_audience = "AzureADMyOrg"

  api {
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                         = random_uuid.scope.result
      value                      = "access_as_user"
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Access the VNet API"
      admin_consent_description  = "Call the VNet API as the signed-in user"
      user_consent_display_name  = "Access the VNet API"
      user_consent_description   = "Call the VNet API on your behalf"
    }
  }

  # identifier_uris is managed by azuread_application_identifier_uri below
  lifecycle {
    ignore_changes = [identifier_uris]
  }
}

resource "azuread_application_identifier_uri" "api" {
  application_id = azuread_application.api.id
  identifier_uri = "api://${azuread_application.api.client_id}"
}

resource "azuread_service_principal" "api" {
  client_id = azuread_application.api.client_id
}

# Lets `az login --scope` / `az account get-access-token` request the API scope without a consent prompt
resource "azuread_application_pre_authorized" "azure_cli" {
  application_id       = azuread_application.api.id
  authorized_client_id = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
  permission_ids       = [random_uuid.scope.result]
}

resource "azurerm_storage_account" "sa" {
  name                            = local.storage_name
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = azurerm_resource_group.rg.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
}

resource "azurerm_application_insights" "ai" {
  name                = "${var.base_name}-ai"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  application_type    = "web"
}

resource "azurerm_service_plan" "plan" {
  name                = "${var.base_name}-plan"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "Y1" # Consumption (serverless)
}

resource "azurerm_linux_function_app" "func" {
  name                       = local.app_name
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  service_plan_id            = azurerm_service_plan.plan.id
  storage_account_name       = azurerm_storage_account.sa.name
  storage_account_access_key = azurerm_storage_account.sa.primary_access_key
  https_only                 = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    minimum_tls_version                    = "1.2"
    application_insights_connection_string = azurerm_application_insights.ai.connection_string
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    AZURE_TENANT_ID                = data.azurerm_client_config.current.tenant_id
    API_CLIENT_ID                  = azuread_application.api.client_id
    AZURE_SUBSCRIPTION_ID          = var.subscription_id
    TARGET_RESOURCE_GROUP          = azurerm_resource_group.rg.name
    DEFAULT_LOCATION               = var.location
    TABLE_ENDPOINT                 = azurerm_storage_account.sa.primary_table_endpoint
  }

  depends_on = [azurerm_service_plan.plan]
}

# Managed identity permissions (no secrets in the app)
resource "azurerm_role_assignment" "network" {
  scope                = azurerm_resource_group.rg.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}

resource "azurerm_role_assignment" "table" {
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}
