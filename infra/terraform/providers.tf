terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state. The bucket is created once by ./bootstrap.sh.
  # Credentials and profile come from the environment (AWS_PROFILE=prod).
  backend "s3" {
    bucket       = "afefehub-tfstate-748201447723"
    key          = "afefehub/prod.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "afefehub"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}
