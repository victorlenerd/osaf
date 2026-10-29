# Afefehub infrastructure (Terraform)

Everything Afefehub runs on in AWS account `748201447723`, region `us-east-1`:

| Piece | Resource |
|---|---|
| DNS | Route53 hosted zone `afefehub.com` (Zoho MX/SPF/DKIM recreated), `api` → ALB, apex/`www` → Lovable or CloudFront |
| TLS | ACM certs `afefehub.com`+`www` (CloudFront) and `api.afefehub.com` (ALB), DNS validated |
| Site | S3 `afefehub-site-prod` behind CloudFront (OAC, extensionless → `.html` rewrite, 403/404 → `/404.html`) |
| Media | S3 `afefehub-media-prod`, private, `submissions/` expires after 30 days |
| Search | OpenSearch domain `afefehub-prod`, 1 × t3.small.search, 10 GB gp3, IAM access policy |
| Data | DynamoDB `afefehub` (PK/SK, GSI1, TTL `expires_at`) |
| Backend | ECR `afefehub-backend`, Fargate task 0.5 vCPU / 1 GB in cluster `default`, ALB `api.afefehub.com`, logs `/afefehub/backend` |
| Secrets | SSM SecureString `/afefehub/prod/*` (placeholders; real values set with the CLI) |

State lives in S3 bucket `afefehub-tfstate-748201447723` (key `afefehub/prod.tfstate`, S3 lockfile).

## Prerequisites

- Terraform ≥ 1.10, AWS CLI v2, Docker (for backend images)
- `AWS_PROFILE=prod` configured for account 748201447723 (`aws sts get-caller-identity`)

All commands below assume `export AWS_PROFILE=prod` and run from `infra/terraform/`.
From the repo root you can also use `make infra-init | infra-plan | infra-apply | infra-output`.

## 1. Bootstrap (once)

```bash
./bootstrap.sh   # creates the versioned, encrypted, private state bucket
terraform init
```

## 2. First apply (everything that does not need a validated certificate)

```bash
terraform apply
```

With `dns_delegated = false` (`terraform apply -var dns_delegated=false`) this creates the zone and its records,
S3 buckets, DynamoDB, OpenSearch (≈15–20 min), ECR, IAM, SSM placeholders, the
ALB with an HTTP listener that forwards to the backend, the task definition and
the service (pass `-var desired_count=0` while ECR is still empty). The two ACM certificates are requested and their
validation CNAMEs written into the zone, but they stay `PENDING_VALIDATION`
until the domain actually resolves through Route53.

## 3. Nameserver cutover (outward-facing: changes live DNS for afefehub.com)

The zone recreates exactly what GoDaddy serves today (Zoho MX, both SPF TXTs,
the `zmail._domainkey` DKIM key, apex/`www` → 185.158.133.1), so mail and the
landing page keep working after the switch. Check first:

```bash
terraform output nameservers
dig +short MX afefehub.com @$(terraform output -raw nameservers | head -1)   # expect the three Zoho MX hosts
```

Then switch the registrar (the domain is registered in Route53 Domains in this account):

```bash
terraform output -raw ns_update_command
# prints, with the real nameservers:
# AWS_PROFILE=prod aws route53domains update-domain-nameservers --region us-east-1 \
#   --domain-name afefehub.com --nameservers Name=ns-... Name=ns-... Name=ns-... Name=ns-...
```

Propagation takes minutes to a few hours (GoDaddy's TTLs are short). Verify with
`dig +short NS afefehub.com` from a public resolver.

## 4. Second apply (HTTPS + CloudFront)

Once `dig NS` shows the Route53 nameservers:

```bash
terraform apply
```

This waits for ACM to validate both certificates, then creates the HTTPS
listener (port 80 becomes a 301 redirect), the CloudFront distribution and the
site bucket policy. `dns_delegated` defaults to `true` since the cutover on
2026-10-29; only a rebuild from scratch needs the two-step sequence above.

## 5. Site cutover (Lovable → CloudFront)

Publish the static export first so the distribution has content:

```bash
terraform output -raw deploy_site
# (cd frontend && npm run build); aws s3 sync frontend/out s3://afefehub-site-prod/ --delete; invalidate
```

Then move the apex/`www` records with one variable:

```bash
terraform apply -var site_dns_target=cloudfront
```

`site_dns_target=lovable` rolls back. CloudFront serves `index.html` at `/`,
rewrites `/foo` → `/foo.html` and `/foo/` → `/foo/index.html`, and returns
`/404.html` for missing objects.

## 6. Secrets

Terraform creates each parameter with the value `CHANGEME` and never touches
the value again. Set the real ones:

```bash
for name in MODEL_API_KEY GOOGLE_PLACES_API_KEY WHATSAPP_ACCESS_TOKEN WHATSAPP_PHONE_NUMBER_ID WHATSAPP_VERIFY_TOKEN META_APP_SECRET; do
  aws ssm put-parameter --name /afefehub/prod/$name --type SecureString --overwrite --value "$(read -rs "?$name: " v; echo "$v")"
done
# optional, only if Instagram rate-limits anonymous yt-dlp downloads:
aws ssm put-parameter --name /afefehub/prod/IG_COOKIES_B64 --type SecureString --overwrite --value "$(base64 -i cookies.txt)"
```

The task reads them at start, so roll the service after changing one
(`aws ecs update-service ... --force-new-deployment`). `IG_COOKIES_B64` is left
as `CHANGEME` when unused; the backend treats that as unset.

## 7. Deploying the backend

```bash
terraform output -raw deploy_backend
```

which is:

```bash
export AWS_PROFILE=prod AWS_REGION=us-east-1
aws ecr get-login-password | docker login --username AWS --password-stdin 748201447723.dkr.ecr.us-east-1.amazonaws.com
docker build --platform linux/amd64 -t 748201447723.dkr.ecr.us-east-1.amazonaws.com/afefehub-backend:latest backend/
docker push 748201447723.dkr.ecr.us-east-1.amazonaws.com/afefehub-backend:latest
aws ecs update-service --cluster default --service afefehub-backend --force-new-deployment --desired-count 1
```

`desired_count` defaults to 1; if you scale with the CLI, keep Terraform in
agreement via `prod.auto.tfvars` or the next apply resets the count. Health check is `GET /healthz`.
The WhatsApp webhook URL to register in the Meta app is
`https://api.afefehub.com/webhooks/whatsapp` (path as implemented in `backend/`).

Useful:

```bash
aws logs tail /afefehub/backend --follow
aws ecs execute-command --cluster default --task <task-id> --container backend --interactive --command /bin/sh
```

## Variables

| Variable | Default | Purpose |
|---|---|---|
| `dns_delegated` | `true` | `false` only for a from-scratch rebuild before the NS cutover (skips cert validations, HTTPS listener, CloudFront) |
| `site_dns_target` | `lovable` | `cloudfront` moves apex/`www` to the S3 site (requires `dns_delegated`) |
| `desired_count` | `1` | Backend task count |
| `backend_image` | `""` → `<ecr>:latest` | Pin an image tag |
| `admin_principal_arns` | `user/victorn` | Extra IAM principals allowed on OpenSearch |
| `lovable_ip`, `zoho_dkim_value`, `zoho_spf_selector` | current GoDaddy values | DNS data |

## Notes

- Fargate is not offered in `us-east-1e`, so that AZ's default subnet is excluded (`subnet_availability_zones`).
- OpenSearch has fine-grained access control off; only the task role and
  `admin_principal_arns` can call it, with SigV4-signed requests.
- Monthly cost at idle is roughly: OpenSearch t3.small ≈ $26, ALB ≈ $17–20, one
  Fargate task ≈ $15, the rest pennies.
- `terraform destroy` works in reverse order; delete the state bucket by hand.
