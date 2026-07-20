output "resource_group_name" {
  value = azurerm_resource_group.rg.name
}

output "acr_login_server" {
  value = azurerm_container_registry.acr.login_server
}

output "api_fqdn" {
  value       = "http://${azurerm_container_group.api.fqdn}:8000"
  description = "Backend API base URL — set this as NEXT_PUBLIC_API_URL in Vercel"
}

output "storage_account_name" {
  value = azurerm_storage_account.sa.name
}

output "docker_push_commands" {
  value = <<-EOT
    az acr login --name ${azurerm_container_registry.acr.name}
    docker build -t ${azurerm_container_registry.acr.login_server}/api:latest .
    docker push ${azurerm_container_registry.acr.login_server}/api:latest
  EOT
  description = "Run these to push the backend image before terraform apply"
}
