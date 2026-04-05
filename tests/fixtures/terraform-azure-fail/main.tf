# WARNING: This file intentionally has Azure security issues for testing
# It should FAIL trivy-iac and checkov-terraform hooks
resource "azurerm_storage_account" "insecure" {
  name                     = "insecurestorage"
  resource_group_name      = "example-rg"
  location                 = "uksouth"
  account_tier             = "Standard"
  account_replication_type = "LRS"

  # Missing: HTTPS enforcement, TLS version, network rules
  enable_https_traffic_only = false
  min_tls_version           = "TLS1_0"
}

resource "azurerm_network_security_rule" "open_ssh" {
  name                        = "allow-ssh-all"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "*" # Open to the world
  destination_address_prefix  = "*"
  resource_group_name         = "example-rg"
  network_security_group_name = "example-nsg"
}
