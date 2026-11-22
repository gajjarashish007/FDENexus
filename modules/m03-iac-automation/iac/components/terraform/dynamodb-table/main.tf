variable "table_name" {
  type = string
}

variable "hash_key" {
  type = string
}

variable "hash_key_type" {
  type    = string
  default = "S"
  validation {
    condition     = contains(["S", "N", "B"], var.hash_key_type)
    error_message = "hash_key_type must be S, N or B."
  }
}

variable "range_key" {
  type    = string
  default = ""
}

variable "range_key_type" {
  type    = string
  default = "S"
  validation {
    condition     = contains(["S", "N", "B"], var.range_key_type)
    error_message = "range_key_type must be S, N or B."
  }
}

variable "billing_mode" {
  type    = string
  default = "PAY_PER_REQUEST"
  validation {
    condition     = contains(["PAY_PER_REQUEST", "PROVISIONED"], var.billing_mode)
    error_message = "billing_mode must be PAY_PER_REQUEST or PROVISIONED."
  }
}

variable "read_capacity" {
  type    = number
  default = 5
}

variable "write_capacity" {
  type    = number
  default = 5
}

variable "ttl_attribute" {
  type    = string
  default = ""
}

variable "point_in_time_recovery" {
  type    = bool
  default = true
}

variable "stream_enabled" {
  type    = bool
  default = false
}

locals {
  provisioned = var.billing_mode == "PROVISIONED"
}

resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = var.billing_mode
  hash_key     = var.hash_key
  range_key    = var.range_key == "" ? null : var.range_key

  read_capacity  = local.provisioned ? var.read_capacity : null
  write_capacity = local.provisioned ? var.write_capacity : null

  attribute {
    name = var.hash_key
    type = var.hash_key_type
  }

  dynamic "attribute" {
    for_each = var.range_key == "" ? [] : [var.range_key]
    content {
      name = attribute.value
      type = var.range_key_type
    }
  }

  dynamic "ttl" {
    for_each = var.ttl_attribute == "" ? [] : [var.ttl_attribute]
    content {
      attribute_name = ttl.value
      enabled        = true
    }
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  server_side_encryption {
    enabled = true
  }

  stream_enabled              = var.stream_enabled
  stream_view_type            = var.stream_enabled ? "NEW_AND_OLD_IMAGES" : null
  deletion_protection_enabled = local.is_production

  tags = { Name = var.table_name }
}
