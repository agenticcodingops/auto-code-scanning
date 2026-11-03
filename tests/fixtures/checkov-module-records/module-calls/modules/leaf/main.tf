resource "azurerm_key_vault" "example" {
  name = "fixturevault"
  sku_name = "standard"
}
