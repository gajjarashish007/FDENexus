variable "domain_name" {
  type = string
}

variable "private_zone" {
  type    = bool
  default = false
}

variable "vpc_id" {
  description = "Existing VPC for a private zone. Empty = the environment VPC."
  type        = string
  default     = ""
}

data "aws_vpc" "env" {
  count = var.private_zone ? 1 : 0
  id    = var.vpc_id == "" ? null : var.vpc_id
  tags = var.vpc_id != "" ? null : {
    "fde:environment" = var.environment_id
    "ManagedBy"       = "fde-nexus"
  }
}

resource "aws_route53_zone" "this" {
  name          = var.domain_name
  comment       = "FDE Nexus ${var.environment_id}"
  force_destroy = false

  dynamic "vpc" {
    for_each = var.private_zone ? [1] : []
    content {
      vpc_id = data.aws_vpc.env[0].id
    }
  }
}
