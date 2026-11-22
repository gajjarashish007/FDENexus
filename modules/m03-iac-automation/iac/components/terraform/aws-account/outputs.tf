output "account_id" {
  value = aws_organizations_account.this.id
}

output "access_role_arn" {
  value = "arn:aws:iam::${aws_organizations_account.this.id}:role/OrganizationAccountAccessRole"
}
