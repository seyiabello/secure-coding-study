resource "azurerm_container_group" "api" {
  name                = local.aci_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  ip_address_type = "Public"
  dns_name_label  = local.aci_name
  os_type         = "Linux"

  # Pull images via managed identity — no ACR admin credentials needed
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aci_identity.id]
  }

  image_registry_credential {
    server                    = azurerm_container_registry.acr.login_server
    user_assigned_identity_id = azurerm_user_assigned_identity.aci_identity.id
  }

  container {
    name   = "api"
    image  = "${azurerm_container_registry.acr.login_server}/api:${var.image_tag}"
    cpu    = "2.0"
    memory = "4.0"

    environment_variables = {
      FRONTEND_ORIGIN = var.frontend_origin
    }

    secure_environment_variables = {
      OPENAI_API_KEY = var.openai_api_key
    }

    ports {
      port     = 8000
      protocol = "TCP"
    }

    # ChromaDB is baked into the image at build time (see Dockerfile + rag.ingest).
    # The corpus is static so no persistent volume is needed.

    # Session logs must survive container restarts during data collection.
    volume {
      name                 = "logs"
      mount_path           = "/app/backend/logs"
      share_name           = azurerm_storage_share.logs.name
      storage_account_name = azurerm_storage_account.sa.name
      storage_account_key  = azurerm_storage_account.sa.primary_access_key
    }
  }

  depends_on = [time_sleep.rbac_propagation]

  tags = var.tags
}
