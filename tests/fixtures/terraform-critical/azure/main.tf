# CRITICAL-only Azure Terraform failure fixture
# Must trigger CRITICAL findings from trivy-iac-critical and checkov
# Expected: trivy-iac-critical=Exit1, trivy-iac-full=Exit1, checkov=Exit1

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.0.0"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "test" {
  name     = "test-critical-rg"
  location = "uksouth"
}

# CRITICAL: Storage account with public access and no HTTPS enforcement
# Trivy: AVD-AZU-0008 (CRITICAL) - Storage account has public network access
# Checkov: CKV_AZURE_3 (CRITICAL) - Ensure that storage account enables secure transfer
resource "azurerm_storage_account" "public" {
  name                          = "criticalinsecurestorage"
  resource_group_name           = azurerm_resource_group.test.name
  location                      = azurerm_resource_group.test.location
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  min_tls_version               = "TLS1_0"
  https_traffic_only_enabled    = false
  public_network_access_enabled = true
  allow_nested_items_to_be_public = true

  tags = {
    Environment = "test"
  }
}

# CRITICAL: NSG rule allowing SSH from anywhere
# Trivy: AVD-AZU-0051 (CRITICAL) - SSH access from internet
# Checkov: CKV_AZURE_9 (CRITICAL) - Ensure NSG does not allow SSH from internet
resource "azurerm_network_security_group" "open" {
  name                = "critical-open-nsg"
  location            = azurerm_resource_group.test.location
  resource_group_name = azurerm_resource_group.test.name

  security_rule {
    name                       = "allow-ssh-all"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-rdp-all"
    priority                   = 101
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = {
    Environment = "test"
  }
}
