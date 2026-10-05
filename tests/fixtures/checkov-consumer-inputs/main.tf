# Synthetic scan fixture; no provider installation or remote modules are needed.
# The long alias chains exercise the duplicate-edge render limit in Checkov 3.3.19.
# At its default (4), CKV_AZURE_35/36 fail; with 20, both resolve and pass.
locals {
  default_action_0 = "Deny"
  bypass_0         = ["AzureServices"]
  default_action_1 = local.default_action_0
  bypass_1         = local.bypass_0
  default_action_2 = local.default_action_1
  bypass_2         = local.bypass_1
  default_action_3 = local.default_action_2
  bypass_3         = local.bypass_2
  default_action_4 = local.default_action_3
  bypass_4         = local.bypass_3
  default_action_5 = local.default_action_4
  bypass_5         = local.bypass_4
  default_action_6 = local.default_action_5
  bypass_6         = local.bypass_5
  default_action_7 = local.default_action_6
  bypass_7         = local.bypass_6
  default_action_8 = local.default_action_7
  bypass_8         = local.bypass_7
  default_action_9 = local.default_action_8
  bypass_9         = local.bypass_8
  default_action_10 = local.default_action_9
  bypass_10         = local.bypass_9
  default_action_11 = local.default_action_10
  bypass_11         = local.bypass_10
  default_action_12 = local.default_action_11
  bypass_12         = local.bypass_11
  default_action_13 = local.default_action_12
  bypass_13         = local.bypass_12
  default_action_14 = local.default_action_13
  bypass_14         = local.bypass_13
  default_action_15 = local.default_action_14
  bypass_15         = local.bypass_14
  default_action_16 = local.default_action_15
  bypass_16         = local.bypass_15
  default_action_17 = local.default_action_16
  bypass_17         = local.bypass_16
  default_action_18 = local.default_action_17
  bypass_18         = local.bypass_17
  default_action_19 = local.default_action_18
  bypass_19         = local.bypass_18
  default_action_20 = local.default_action_19
  bypass_20         = local.bypass_19
  default_action_21 = local.default_action_20
  bypass_21         = local.bypass_20
  default_action_22 = local.default_action_21
  bypass_22         = local.bypass_21
  default_action_23 = local.default_action_22
  bypass_23         = local.bypass_22
  default_action_24 = local.default_action_23
  bypass_24         = local.bypass_23
  default_action_25 = local.default_action_24
  bypass_25         = local.bypass_24
  default_action_26 = local.default_action_25
  bypass_26         = local.bypass_25
  default_action_27 = local.default_action_26
  bypass_27         = local.bypass_26
  default_action_28 = local.default_action_27
  bypass_28         = local.bypass_27
  default_action_29 = local.default_action_28
  bypass_29         = local.bypass_28
  default_action_30 = local.default_action_29
  bypass_30         = local.bypass_29
  default_action_31 = local.default_action_30
  bypass_31         = local.bypass_30
  default_action_32 = local.default_action_31
  bypass_32         = local.bypass_31
  default_action_33 = local.default_action_32
  bypass_33         = local.bypass_32
  default_action_34 = local.default_action_33
  bypass_34         = local.bypass_33
  default_action   = local.default_action_34
  bypass           = local.bypass_34
}

resource "azurerm_storage_account" "rendered" {
  name                     = "scanfixturestorage"
  resource_group_name      = "fixture"
  location                 = "uksouth"
  account_tier             = "Standard"
  account_replication_type = "LRS"

  network_rules {
    default_action = local.default_action
    bypass         = local.bypass
  }
}

resource "azurerm_key_vault" "inline_skip" {
  #checkov:skip=CKV_AZURE_110:Deliberate inline skip to verify SARIF filtering
  name                = "scanfixturevault"
  resource_group_name = "fixture"
  location            = "uksouth"
  sku_name            = "standard"
}
