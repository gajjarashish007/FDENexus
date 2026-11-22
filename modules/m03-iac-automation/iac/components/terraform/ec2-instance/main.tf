variable "instance_name" {
  type = string
}

variable "os" {
  type = string
  validation {
    condition     = contains(["amazon-linux", "ubuntu", "windows"], var.os)
    error_message = "os must be amazon-linux, ubuntu or windows."
  }
}

variable "instance_type" {
  type = string
}

variable "volume_gb" {
  type    = number
  default = 20
}

variable "subnet_tier" {
  type    = string
  default = "private"
  validation {
    condition     = contains(["private", "public"], var.subnet_tier)
    error_message = "subnet_tier must be private or public."
  }
}

variable "allowed_ports" {
  type    = list(number)
  default = []
}

variable "allowed_cidr" {
  description = "Source CIDR for allowed_ports. Empty means the VPC CIDR."
  type        = string
  default     = ""
}

variable "key_name" {
  type    = string
  default = ""
}

variable "user_data" {
  type    = string
  default = ""
}

locals {
  ssm_parameters = {
    "amazon-linux" = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
    "ubuntu"       = "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
    "windows"      = "/aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base"
  }
  subnet_ids  = var.subnet_tier == "public" ? local.public_subnet_ids : local.private_subnet_ids
  source_cidr = var.allowed_cidr == "" ? data.aws_vpc.env.cidr_block : var.allowed_cidr
}

data "aws_ssm_parameter" "ami" {
  name = local.ssm_parameters[var.os]
}

resource "aws_security_group" "this" {
  name_prefix = "${var.environment_id}-${var.instance_name}-"
  description = "FDE Nexus instance ${var.instance_name}"
  vpc_id      = data.aws_vpc.env.id
  tags        = { Name = "${var.environment_id}-${var.instance_name}" }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "ports" {
  for_each          = toset([for p in var.allowed_ports : tostring(p)])
  security_group_id = aws_security_group.this.id
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
  cidr_ipv4         = local.source_cidr
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.this.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# Session Manager access instead of open SSH.
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name_prefix        = substr("${var.environment_id}-${var.instance_name}-", 0, 38)
  path               = "/fde-nexus/"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "this" {
  name_prefix = substr("${var.environment_id}-${var.instance_name}-", 0, 38)
  path        = "/fde-nexus/"
  role        = aws_iam_role.this.name
}

resource "aws_instance" "this" {
  ami                         = data.aws_ssm_parameter.ami.value
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_ids[0]
  vpc_security_group_ids      = [aws_security_group.this.id]
  iam_instance_profile        = aws_iam_instance_profile.this.name
  key_name                    = var.key_name == "" ? null : var.key_name
  user_data                   = var.user_data == "" ? null : var.user_data
  associate_public_ip_address = var.subnet_tier == "public"
  monitoring                  = local.is_production

  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.volume_gb
    encrypted   = true
  }

  tags        = { Name = var.instance_name }
  volume_tags = merge(local.base_tags, { Name = var.instance_name })

  lifecycle {
    ignore_changes = [ami]
  }
}
