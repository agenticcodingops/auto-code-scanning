# Valid Azure Terraform - passes ALL security checks
# Fixture for testing that clean code produces exit 0 from all hooks

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

# --- Resource Group ---

resource "azurerm_resource_group" "secure" {
  name     = "test-secure-rg"
  location = "uksouth"

  tags = {
    Environment = "dev"
    Owner       = "security-team"
  }
}

# --- Storage Account (fully secured) ---

resource "azurerm_storage_account" "secure" {
  name                          = "testsecurestorage"
  resource_group_name           = azurerm_resource_group.secure.name
  location                      = azurerm_resource_group.secure.location
  account_tier                  = "Standard"
  account_replication_type      = "GRS"
  min_tls_version               = "TLS1_2"
  https_traffic_only_enabled    = true
  public_network_access_enabled = false

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 7
    }
  }

  network_rules {
    default_action = "Deny"
  }

  tags = {
    Environment = "dev"
    Owner       = "security-team"
  }
}

# --- Network Security Group (restricted) ---

resource "azurerm_network_security_group" "secure" {
  name                = "test-secure-nsg"
  location            = azurerm_resource_group.secure.location
  resource_group_name = azurerm_resource_group.secure.name

  security_rule {
    name                       = "allow-https-internal"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "10.0.0.0/8"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "deny-all-inbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = {
    Environment = "dev"
    Owner       = "security-team"
  }
}
