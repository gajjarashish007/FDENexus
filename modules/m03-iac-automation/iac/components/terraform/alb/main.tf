variable "lb_name" {
  type = string
}

variable "scheme" {
  type    = string
  default = "internet-facing"
  validation {
    condition     = contains(["internet-facing", "internal"], var.scheme)
    error_message = "scheme must be internet-facing or internal."
  }
}

variable "certificate_domain" {
  description = "Domain of an issued ACM certificate in this region. Empty means HTTP only."
  type        = string
  default     = ""
}

variable "target_port" {
  type    = number
  default = 80
}

variable "health_check_path" {
  type    = string
  default = "/"
}

variable "idle_timeout" {
  type    = number
  default = 60
}

locals {
  internal  = var.scheme == "internal"
  https     = var.certificate_domain != ""
  ingress   = local.internal ? data.aws_vpc.env.cidr_block : "0.0.0.0/0"
  subnets   = local.internal ? local.private_subnet_ids : local.public_subnet_ids
  full_name = substr("${var.environment_id}-${var.lb_name}", 0, 32)
}

data "aws_acm_certificate" "this" {
  count       = local.https ? 1 : 0
  domain      = var.certificate_domain
  statuses    = ["ISSUED"]
  most_recent = true
}

resource "aws_security_group" "alb" {
  name_prefix = "${local.full_name}-alb-"
  description = "ALB ${local.full_name}"
  vpc_id      = data.aws_vpc.env.id
  tags        = { Name = "${local.full_name}-alb" }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.alb.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = local.ingress
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  count             = local.https ? 1 : 0
  security_group_id = aws_security_group.alb.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = local.ingress
}

resource "aws_vpc_security_group_egress_rule" "vpc" {
  security_group_id = aws_security_group.alb.id
  ip_protocol       = "tcp"
  from_port         = var.target_port
  to_port           = var.target_port
  cidr_ipv4         = data.aws_vpc.env.cidr_block
}

resource "aws_lb" "this" {
  name                       = local.full_name
  load_balancer_type         = "application"
  internal                   = local.internal
  subnets                    = local.subnets
  security_groups            = [aws_security_group.alb.id]
  idle_timeout               = var.idle_timeout
  drop_invalid_header_fields = true
  enable_deletion_protection = local.is_production
}

resource "aws_lb_target_group" "this" {
  name_prefix = "fde-"
  port        = var.target_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = data.aws_vpc.env.id

  health_check {
    path                = var.health_check_path
    matcher             = "200-399"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 15
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = local.https ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }

  dynamic "default_action" {
    for_each = local.https ? [] : [1]
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.this.arn
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = local.https ? 1 : 0
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = data.aws_acm_certificate.this[0].arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}
