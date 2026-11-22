variable "fs_name" {
  type = string
}

variable "performance_mode" {
  type    = string
  default = "generalPurpose"
  validation {
    condition     = contains(["generalPurpose", "maxIO"], var.performance_mode)
    error_message = "performance_mode must be generalPurpose or maxIO."
  }
}

variable "throughput_mode" {
  type    = string
  default = "elastic"
  validation {
    condition     = contains(["elastic", "bursting"], var.throughput_mode)
    error_message = "throughput_mode must be elastic or bursting."
  }
}

variable "transition_to_ia" {
  type    = string
  default = "AFTER_30_DAYS"
}

variable "backup" {
  type    = bool
  default = true
}

resource "aws_efs_file_system" "this" {
  creation_token   = "${var.environment_id}-${var.fs_name}"
  encrypted        = true
  performance_mode = var.performance_mode
  throughput_mode  = var.throughput_mode

  lifecycle_policy {
    transition_to_ia = var.transition_to_ia
  }

  tags = { Name = "${var.environment_id}-${var.fs_name}" }
}

resource "aws_efs_backup_policy" "this" {
  file_system_id = aws_efs_file_system.this.id
  backup_policy {
    status = var.backup ? "ENABLED" : "DISABLED"
  }
}

resource "aws_security_group" "efs" {
  name_prefix = "${var.environment_id}-${var.fs_name}-efs-"
  description = "NFS from the environment VPC"
  vpc_id      = data.aws_vpc.env.id
  tags        = { Name = "${var.environment_id}-${var.fs_name}-efs" }
}

resource "aws_vpc_security_group_ingress_rule" "nfs" {
  security_group_id = aws_security_group.efs.id
  ip_protocol       = "tcp"
  from_port         = 2049
  to_port           = 2049
  cidr_ipv4         = data.aws_vpc.env.cidr_block
}

resource "aws_efs_mount_target" "this" {
  for_each        = toset(local.private_subnet_ids)
  file_system_id  = aws_efs_file_system.this.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}
