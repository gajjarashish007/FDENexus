variable "domain_name" {
  type = string
}

variable "subject_alternative_names" {
  type    = list(string)
  default = []
}

variable "validation" {
  description = "route53: create validation records in zone_domain. manual: you add the DNS records yourself."
  type        = string
  default     = "route53"
  validation {
    condition     = contains(["route53", "manual"], var.validation)
    error_message = "validation must be route53 or manual."
  }
}

variable "zone_domain" {
  description = "Public hosted zone that holds the validation records (route53 validation only)."
  type        = string
  default     = ""
}

locals {
  auto = var.validation == "route53"
}

resource "aws_acm_certificate" "this" {
  domain_name               = var.domain_name
  subject_alternative_names = var.subject_alternative_names
  validation_method         = "DNS"
  key_algorithm             = "RSA_2048"

  lifecycle {
    create_before_destroy = true
  }
}

data "aws_route53_zone" "this" {
  count        = local.auto ? 1 : 0
  name         = var.zone_domain
  private_zone = false
}

resource "aws_route53_record" "validation" {
  for_each = local.auto ? {
    for o in aws_acm_certificate.this.domain_validation_options : o.domain_name => o
  } : {}
  zone_id         = data.aws_route53_zone.this[0].zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  count                   = local.auto ? 1 : 0
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for r in aws_route53_record.validation : r.fqdn]
}
