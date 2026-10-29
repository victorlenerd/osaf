# Placeholders only. Set real values out of band, e.g.
#   aws ssm put-parameter --name /afefehub/prod/MODEL_API_KEY --type SecureString --overwrite --value '...'
# Terraform ignores the value afterwards. Intelligent-Tiering lets IG_COOKIES_B64
# exceed the 4 KB Standard limit without a config change.
resource "aws_ssm_parameter" "secrets" {
  for_each = toset(var.secret_names)

  name        = "${local.ssm_prefix}/${each.key}"
  description = "afefehub prod secret ${each.key} (value managed outside Terraform)"
  type        = "SecureString"
  tier        = "Intelligent-Tiering"
  value       = "CHANGEME"

  lifecycle {
    ignore_changes = [value]
  }
}
