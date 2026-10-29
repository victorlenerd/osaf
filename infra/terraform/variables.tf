variable "aws_region" {
  description = "AWS region for every resource (CloudFront certificates must be in us-east-1)."
  type        = string
  default     = "us-east-1"
}

variable "domain" {
  description = "Apex domain. The Route53 hosted zone is created for it."
  type        = string
  default     = "afefehub.com"
}

variable "vpc_id" {
  description = "Existing (default) VPC that hosts the ALB and the Fargate tasks."
  type        = string
  default     = "vpc-0cefd106eacf5df17"
}

variable "subnet_availability_zones" {
  description = "AZs whose default public subnets are used for the ALB and tasks. us-east-1e is excluded because Fargate is not available there."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d", "us-east-1f"]
}

variable "ecs_cluster_name" {
  description = "Name of the existing ECS cluster to run the backend service in."
  type        = string
  default     = "default"
}

variable "dns_delegated" {
  description = <<-EOT
    Set to true once afefehub.com's nameservers point at the Route53 zone created here
    (see output ns_update_command). Until then ACM certificates cannot validate, so the
    HTTPS listener, CloudFront distribution and the pieces that depend on them are not created.
  EOT
  type        = bool
  default     = false
}

variable "site_dns_target" {
  description = "Where apex + www A records point: 'lovable' (current landing page IP) or 'cloudfront' (the S3/CloudFront site built here)."
  type        = string
  default     = "lovable"

  validation {
    condition     = contains(["lovable", "cloudfront"], var.site_dns_target)
    error_message = "site_dns_target must be 'lovable' or 'cloudfront'."
  }

  validation {
    condition     = var.site_dns_target == "lovable" || var.dns_delegated
    error_message = "site_dns_target = \"cloudfront\" requires dns_delegated = true (the CloudFront distribution only exists after the nameserver cutover)."
  }
}

variable "lovable_ip" {
  description = "IPv4 address of the current Lovable landing page (used while site_dns_target = lovable)."
  type        = string
  default     = "185.158.133.1"
}

variable "zoho_dkim_value" {
  description = "Value of the zmail._domainkey TXT record served by GoDaddy today (Zoho Mail DKIM). Split into 255-char chunks automatically."
  type        = string
  default     = "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCZR4YMtEfwCI4p0vWLW/8THqD/Ap/WU5SND0UI6tm/Wb81+2fU2FfXEO8ssM3wAgsoKIhcDeRhEVIukDowGdVilz9AO5We4N5S1ncBy5TiGi6wzeWcyMONr0QUVvC70NADy6UfhFBRG7KTwJDkeX/uiaVPjnXK8Bw1U/mFQxpKRwIDAQAB"
}

variable "zoho_spf_selector" {
  description = "Zoho SPF macro selector label (the dc-xxxx._spfm subdomain GoDaddy serves today)."
  type        = string
  default     = "dc-8e814c8572._spfm"
}

variable "admin_principal_arns" {
  description = "IAM principals (besides the ECS task role) allowed es:ESHttp* on the OpenSearch domain."
  type        = list(string)
  default     = ["arn:aws:iam::748201447723:user/victorn"]
}

variable "opensearch_engine_version" {
  description = "OpenSearch engine version (latest 2.x available in us-east-1 at creation time)."
  type        = string
  default     = "OpenSearch_2.19"
}

variable "opensearch_instance_type" {
  description = "OpenSearch data node instance type."
  type        = string
  default     = "t3.small.search"
}

variable "backend_image" {
  description = "Container image for the backend task. Empty = <ecr repo url>:latest."
  type        = string
  default     = ""
}

variable "desired_count" {
  description = "Desired number of backend tasks. Keep 0 until an image has been pushed to ECR."
  type        = number
  default     = 0
}

variable "secret_names" {
  description = "SSM SecureString parameters created under /afefehub/prod/ (value CHANGEME, managed out of band) and injected into the task as secrets."
  type        = list(string)
  default = [
    "MODEL_API_KEY",
    "GOOGLE_PLACES_API_KEY",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_VERIFY_TOKEN",
    "META_APP_SECRET",
    "IG_COOKIES_B64",
  ]
}
