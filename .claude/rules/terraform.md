---
paths:
  - "terraform/**"
---

# Terraform (AWS ECS Fargate)

`terraform/` is a single flat root module with one file per concern:

- `providers.tf`: `hashicorp/aws ~> 5.0`, locked to 5.100.0 in `.terraform.lock.hcl`. Sets `default_tags` Project / `Environment = "dev"` / `ManagedBy = "terraform"`.
- `variables.tf`: `aws_region` (default `eu-west-1`) and `project_name` (default `aegis-guard`).
- `ecr.tf`: a repository named `var.project_name`, with `force_delete = true` and a lifecycle policy that keeps the last 5 images.
- `network.tf`: the account's default VPC (`aws_default_vpc`) and its subnets.
- `security.tf`: the security group, with ingress on tcp/8000 and all egress.
- `iam.tf`: the ECS task execution role, with `AmazonECSTaskExecutionRolePolicy` attached.
- `logs.tf`: CloudWatch log group `/ecs/${var.project_name}`, 7-day retention.
- `ecs.tf`: the cluster, the Fargate task definition and the service.
  - The task definition runs `cpu = "256"` / `memory = "512"` and image `<ecr repo url>:latest` on port 8000 with awslogs. It sets no `environment` or `secrets`, so the container runs with the code defaults.
  - The service has `desired_count = 1` and a public IP.
- `outputs.tf`: `ecr_repository_url`, `vpc_id`, `security_group_id`.

## Conventions

- **Names** derive from `var.project_name`:
  - `-cluster`, `-task` (task family), `-service`, `-sg` and `-ecs-execution-role`.
  - The ECR repository and the container use the bare name, and the default VPC is tagged `${var.project_name}-default-vpc`.
  - HCL identifiers are snake_case.
- **Don't rename existing resources or reword existing `description` arguments.** Most renames force replacement, and changing an `aws_security_group` `description` replaces the group, so leave its current Spanish text as is. Comments are free to change.
- **Style**:
  - Policies and container definitions use `jsonencode()`.
  - Every variable and output has a `description`.
  - Commit with the `feat(infra): ...` scope.
- **Fargate sizes**: only fixed `cpu`/`memory` pairs are accepted. 256 → 512/1024/2048; 512 → 1024–4096; 1024 → 2048–8192; 2048 → 4096–16384. `validate` doesn't check this; a bad pair fails at `apply`. When you change one, set a valid partner and update the size comments.

## Commands (run from the repo root, with `-chdir=terraform`)

- **Offline, always fine**:
  - `terraform -chdir=terraform fmt -check -recursive` (drop `-check` to rewrite)
  - `terraform -chdir=terraform validate`
  - `terraform -chdir=terraform state list`
  - `terraform -chdir=terraform output`
- **Only when the user asks for that step in the current conversation** (`.claude/settings.json` makes them prompt):
  - `plan`, `apply`, `destroy`, `import` and `refresh` call AWS. The region comes from `var.aws_region`, default eu-west-1.
  - `init` reaches the registry.
  - `taint`/`untaint` and `state rm|mv|push|replace-provider` rewrite the state.
  - `show`, `state show|pull` and `console` print it.
  - Every `aws` CLI call reaches the account, in the CLI profile's region.
  - Never add `-auto-approve` unless the user explicitly asks for it.

## State

- The backend is local: there is no `backend` block, and `terraform/terraform.tfstate` is the only record of what's deployed.
- Never delete, move, hand-edit or commit `*.tfstate*`.
- `*.tfstate*`, `.terraform/` and `*.tfvars*` are gitignored, and Claude's file tools are denied the state and tfvars files. Inspect state with `state list` / `output`.

After you edit a `.tf` file, the post-edit hook runs `terraform fmt` on it. Run `terraform -chdir=terraform validate` before you finish.
