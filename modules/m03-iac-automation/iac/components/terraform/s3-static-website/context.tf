# Shared inputs, tags and AWS provider for every FDE Nexus component.
# This file is identical in every component directory (copied from components/terraform/_shared_context.tf).

variable "region" {
  description = "AWS region for this stack."
  type        = string
}

variable "assume_role_arn" {
  description = "Role to assume in the target account. Empty uses the caller's credentials (instance role)."
  type        = string
  default     = ""
}

variable "external_id" {
  description = "External ID required by the target role trust policy, if any."
  type        = string
  default     = ""
}

variable "environment_id" {
  description = "FDE Nexus environment name. Also the Atmos stack name."
  type        = string
}

variable "tier" {
  description = "sandbox, development, staging or production."
  type        = string
  validation {
    condition     = contains(["sandbox", "development", "staging", "production", "management"], var.tier)
    error_message = "tier must be sandbox, development, staging, production or management."
  }
}

variable "team" {
  type = string
}

variable "owner" {
  type    = string
  default = ""
}

variable "request_id" {
  type    = string
  default = ""
}

variable "extra_tags" {
  type    = map(string)
  default = {}
}

locals {
  is_production = var.tier == "production"
  base_tags = merge(var.extra_tags, {
    "fde:environment" = var.environment_id
    "fde:tier"        = var.tier
    "Team"            = var.team
    "Owner"           = var.owner
    "RequestId"       = var.request_id
    "ManagedBy"       = "fde-nexus"
  })
}

provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.assume_role_arn == "" ? [] : [1]
    content {
      role_arn     = var.assume_role_arn
      external_id  = var.external_id == "" ? null : var.external_id
      session_name = "fde-nexus-${var.environment_id}"
    }
  }

  default_tags {
    tags = local.base_tags
  }
}
