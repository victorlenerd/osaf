data "aws_iam_policy_document" "opensearch_access" {
  statement {
    sid     = "AllowTaskRoleAndAdmins"
    effect  = "Allow"
    actions = ["es:ESHttp*"]

    principals {
      type        = "AWS"
      identifiers = concat([aws_iam_role.task.arn], var.admin_principal_arns)
    }

    resources = ["${local.opensearch_domain_arn}/*"]
  }
}

resource "aws_opensearch_domain" "main" {
  domain_name    = local.opensearch_domain_name
  engine_version = var.opensearch_engine_version

  cluster_config {
    instance_type            = var.opensearch_instance_type
    instance_count           = 1
    dedicated_master_enabled = false
    zone_awareness_enabled   = false
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = 10
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  software_update_options {
    auto_software_update_enabled = true
  }

  # Public endpoint, no VPC, fine-grained access control off: access is
  # governed purely by this IAM resource policy (requests must be SigV4-signed).
  access_policies = data.aws_iam_policy_document.opensearch_access.json
}
