output "function_app_name" {
  value = azurerm_linux_function_app.func.name
}

output "api_url" {
  value = "https://${azurerm_linux_function_app.func.default_hostname}/api"
}

output "api_client_id" {
  value = azuread_application.api.client_id
}
