resource "azurerm_key_vault" "example" {
  #checkov:skip=CKV_AZURE_110:Reviewed nested exception
  name = "fixturevault"
  sku_name = "standard"
}
