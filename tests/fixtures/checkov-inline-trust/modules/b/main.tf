resource "azurerm_key_vault" "unchanged" {
  #checkov:skip=CKV_AZURE_110:Reviewed fixture exception
  name = "unchangednestedvault"
  sku_name = "standard"
}

resource "azurerm_key_vault" "edited" {
  #checkov:skip=CKV_AZURE_110:Original fixture exception
  name = "editednestedvault"
  sku_name = "standard"
}

resource "azurerm_key_vault" "new" {
  name = "newnestedvault"
  sku_name = "standard"
}
