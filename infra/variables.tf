variable "subscription_id" {
  type        = string
  description = "Azure subscription ID"
}

variable "resource_group_name" {
  type    = string
  default = "rg-vnet-api"
}

variable "location" {
  type    = string
  default = "westus2"
}

variable "base_name" {
  type        = string
  default     = "vnetapi"
  description = "Lowercase alphanumeric prefix (max 11 chars)"
}
