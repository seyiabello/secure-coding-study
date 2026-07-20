data "azurerm_client_config" "current" {}

# User-assigned managed identity for ACI — created before the container so it
# can be referenced in image_registry_credential at provision time
resource "azurerm_user_assigned_identity" "aci_identity" {
  name                = local.uai_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  tags                = var.tags
}

# Allow the ACI identity to pull images from ACR
resource "azurerm_role_assignment" "aci_acr_pull" {
  principal_id         = azurerm_user_assigned_identity.aci_identity.principal_id
  role_definition_name = "AcrPull"
  scope                = azurerm_container_registry.acr.id
}

# Wait for RBAC to propagate before ACI tries to pull the image
resource "time_sleep" "rbac_propagation" {
  depends_on      = [azurerm_role_assignment.aci_acr_pull]
  create_duration = "30s"
}
