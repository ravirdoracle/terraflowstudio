terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = ">= 4.9.0" }
  }
}

resource "azurerm_virtual_network" "this" {
  name                = var.vnet_name
  address_space       = [var.address_space]
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_subnet" "oracle_delegated" {
  name                 = var.subnet_name
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.subnet_address_prefix]

  delegation {
    name = "Oracle.Database.networkAttachments"
    service_delegation {
      name = "Oracle.Database/networkAttachments"
      actions = [
        "Microsoft.Network/networkinterfaces/*",
        "Microsoft.Network/virtualNetworks/subnets/join/action",
      ]
    }
  }
}
