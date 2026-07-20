terraform {
  # State lives in a bootstrap storage account that is NOT managed by this config.
  # It survives terraform destroy so the next provision starts with known state.
  #
  # One-time bootstrap (run once, manually):
  #   az group create --name scstudy-bootstrap --location uksouth
  #   az storage account create --name scstudytfstate \
  #     --resource-group scstudy-bootstrap --sku Standard_LRS --min-tls-version TLS1_2
  #   az storage container create --name tfstate --account-name scstudytfstate
  backend "azurerm" {
    resource_group_name  = "scstudy-bootstrap"
    storage_account_name = "scstudytfstate"
    container_name       = "tfstate"
    key                  = "terraform.tfstate"
  }
}
