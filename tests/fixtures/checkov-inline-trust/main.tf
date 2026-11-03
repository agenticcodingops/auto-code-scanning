# Synthetic resources: two approved skips and one finding in the trusted base.
resource "azurerm_key_vault" "unchanged" {
  #checkov:skip=CKV_AZURE_110:Reviewed fixture exception
  name = "unchangedvault"
  sku_name = "standard"
}

resource "azurerm_key_vault" "edited" {
  #checkov:skip=CKV_AZURE_110:Original fixture exception
  name = "editedvault"
  sku_name = "standard"
}

resource "azurerm_key_vault" "new" {
  name = "newvault"
  sku_name = "standard"
}

module "plain" {
  #checkov:skip=CKV_TF_1:Reviewed local module
  source = "./modules/b"
}

module "counted" {
  #checkov:skip=CKV_TF_1:Reviewed local module
  source = "./modules/b"
  count = 2
}
