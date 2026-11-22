# Network placement. Default: the VPC and subnets built by the environment's vpc component (found by tag).
# Existing VPC: set vpc_id and subnet_ids (the portal fills them when an account's existing VPC is imported).

variable "vpc_id" {
  description = "Existing VPC to use. Empty = the environment VPC (tag fde:environment)."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Subnets to use, overriding the tagged public/private subnets."
  type        = list(string)
  default     = []
}

data "aws_vpc" "env" {
  id = var.vpc_id == "" ? null : var.vpc_id
  tags = var.vpc_id != "" ? null : {
    "fde:environment" = var.environment_id
    "ManagedBy"       = "fde-nexus"
  }
}

data "aws_subnets" "private" {
  count = length(var.subnet_ids) > 0 ? 0 : 1
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.env.id]
  }
  tags = {
    "fde:subnet-tier" = "private"
  }
}

data "aws_subnets" "public" {
  count = length(var.subnet_ids) > 0 ? 0 : 1
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.env.id]
  }
  tags = {
    "fde:subnet-tier" = "public"
  }
}

locals {
  private_subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.private[0].ids
  public_subnet_ids  = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.public[0].ids
}
