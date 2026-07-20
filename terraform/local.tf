resource "random_string" "sfx" {
  length  = 5
  upper   = false
  special = false
}

locals {
  name_base = "scstudy"

  rg_name  = "${local.name_base}-rg"
  acr_name = "${local.name_base}acr${random_string.sfx.result}"
  sa_name  = "${local.name_base}sa${random_string.sfx.result}"
  aci_name = "${local.name_base}-api"
  uai_name = "${local.name_base}-aci-id"
}
