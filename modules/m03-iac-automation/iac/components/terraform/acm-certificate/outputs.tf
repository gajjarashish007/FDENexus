output "certificate_arn" {
  value = aws_acm_certificate.this.arn
}

output "validation_records" {
  description = "Add these records yourself when validation = manual."
  value = [for o in aws_acm_certificate.this.domain_validation_options : {
    name  = o.resource_record_name
    type  = o.resource_record_type
    value = o.resource_record_value
  }]
}
