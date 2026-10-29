output "route53_zone_id" {
  value = aws_route53_zone.main.zone_id
}

output "nameservers" {
  description = "Route53 nameservers for the zone. afefehub.com must be switched to these (see ns_update_command)."
  value       = aws_route53_zone.main.name_servers
}

output "ns_update_command" {
  description = "Run this (after review) to move afefehub.com DNS from GoDaddy to Route53. Outward-facing: it changes live DNS for the domain."
  value       = "AWS_PROFILE=prod aws route53domains update-domain-nameservers --region us-east-1 --domain-name ${var.domain} --nameservers ${join(" ", [for ns in aws_route53_zone.main.name_servers : "Name=${ns}"])}"
}

output "api_url" {
  value = local.api_url
}

output "alb_dns_name" {
  description = "Direct ALB hostname (plain HTTP works before the cutover)."
  value       = aws_lb.api.dns_name
}

output "site_url" {
  value = local.site_url
}

output "cloudfront_distribution_id" {
  description = "Null until dns_delegated = true."
  value       = one(aws_cloudfront_distribution.site[*].id)
}

output "cloudfront_domain_name" {
  value = one(aws_cloudfront_distribution.site[*].domain_name)
}

output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "dynamo_table" {
  value = aws_dynamodb_table.main.name
}

output "opensearch_endpoint" {
  value = aws_opensearch_domain.main.endpoint
}

output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "ecs_service" {
  value = "${data.aws_ecs_cluster.default.cluster_name}/${aws_ecs_service.backend.name}"
}

output "log_group" {
  value = aws_cloudwatch_log_group.backend.name
}

output "ssm_parameter_prefix" {
  value = local.ssm_prefix
}

output "deploy_backend" {
  description = "Build, push and roll the backend."
  value       = <<-EOT
    export AWS_PROFILE=prod AWS_REGION=${local.region}
    aws ecr get-login-password | docker login --username AWS --password-stdin ${local.account_id}.dkr.ecr.${local.region}.amazonaws.com
    docker build --platform linux/amd64 -t ${aws_ecr_repository.backend.repository_url}:latest backend/
    docker push ${aws_ecr_repository.backend.repository_url}:latest
    aws ecs update-service --cluster ${data.aws_ecs_cluster.default.cluster_name} --service ${aws_ecs_service.backend.name} --force-new-deployment --desired-count 1
  EOT
}

output "deploy_site" {
  description = "Publish the Next.js static export to the site bucket (after dns_delegated = true)."
  value       = <<-EOT
    export AWS_PROFILE=prod
    (cd frontend && npm run build)
    aws s3 sync frontend/out s3://${aws_s3_bucket.site.bucket}/ --delete
    aws cloudfront create-invalidation --distribution-id ${coalesce(one(aws_cloudfront_distribution.site[*].id), "<cloudfront_distribution_id>")} --paths '/*'
  EOT
}
