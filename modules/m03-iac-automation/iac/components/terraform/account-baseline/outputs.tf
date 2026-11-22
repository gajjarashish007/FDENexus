output "ebs_encryption_by_default" {
  value = aws_ebs_encryption_by_default.this.enabled
}

output "access_analyzer_arn" {
  value = try(aws_accessanalyzer_analyzer.this[0].arn, null)
}
