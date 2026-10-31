data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_vpc" "default" {
  id = var.vpc_id
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }
  filter {
    name   = "availability-zone"
    values = var.subnet_availability_zones
  }
}

data "aws_ecs_cluster" "default" {
  cluster_name = var.ecs_cluster_name
}

data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

locals {
  name       = "afefehub"
  env        = "prod"
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  www_domain   = "www.${var.domain}"
  api_domain   = "api.${var.domain}"
  site_domains = [var.domain, local.www_domain]
  site_url     = "https://${var.domain}"
  api_url      = "https://${local.api_domain}"

  media_bucket_name = "${local.name}-media-${local.env}"
  site_bucket_name  = "${local.name}-site-${local.env}"
  dynamo_table_name = local.name
  ecr_repo_name     = "${local.name}-backend"
  log_group_name    = "/${local.name}/backend"
  ssm_prefix        = "/${local.name}/${local.env}"

  # Built from the name (not the resource) so the task-role policy and the domain
  # access policy do not form a dependency cycle.
  opensearch_domain_name = "${local.name}-${local.env}"
  opensearch_domain_arn  = "arn:aws:es:${local.region}:${local.account_id}:domain/${local.opensearch_domain_name}"

  backend_image = var.backend_image != "" ? var.backend_image : "${aws_ecr_repository.backend.repository_url}:latest"

  backend_env = {
    AWS_REGION          = local.region
    DYNAMO_TABLE        = aws_dynamodb_table.main.name
    MEDIA_BUCKET        = aws_s3_bucket.media.bucket
    OPENSEARCH_ENDPOINT = aws_opensearch_domain.main.endpoint
    PUBLIC_SITE_URL     = local.site_url
    PUBLIC_API_URL      = local.api_url
    ENV                 = local.env
  }
}
