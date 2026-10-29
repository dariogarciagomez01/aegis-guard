# Milestone 8 Objective
Deploy the Aegis Guard gateway to AWS by provisioning its infrastructure as code with Terraform and running it on ECS Fargate. This milestone moves the proxy from a local Docker Compose stack to a publicly reachable, observable cloud service while keeping costs bounded and the environment fully reproducible, and it is measured by a successful `/health` check, CloudWatch logs, and a Locust run against the deployed endpoint.

### 1. Core Dependencies and Technical Justification
To deploy and operate the gateway in the cloud without adding any production dependency to the Python application, we introduce the following industry-standard tools:

1. **Terraform**
   - *What it is:* A declarative infrastructure-as-code tool that describes cloud resources in `.tf` files and reconciles them against a state file.
   - *Why we use it:* The whole environment can be created with `apply` and removed with `destroy`, so the deployment is repeatable and reviewable in Git. Clicking through the AWS console would leave no record of what exists and no safe way to tear it down.
2. **Amazon ECR and ECS Fargate**
   - *What it is:* ECR is AWS's private container registry; Fargate runs containers on demand without managing servers.
   - *Why we use it:* Our `Dockerfile` already produces an immutable image, so the gateway runs unchanged. Fargate avoids operating EC2 instances or a Kubernetes cluster, which would be disproportionate for a single stateless service.
3. **Amazon CloudWatch Logs**
   - *What it is:* AWS's managed log store, fed by the container's standard output.
   - *Why we use it:* The gateway already emits one JSON log line per request (Milestone 6), so no code changes are needed to make requests searchable in the cloud.
4. **AWS Budgets**
   - *What it is:* An account-level cost alert that emails us when spending reaches or is forecast to reach a threshold.
   - *Why we use it:* Fargate and public IPs bill by the hour. An alert is the safety net that catches a forgotten deployment before it becomes a surprise invoice.
5. **AWS Systems Manager Parameter Store (SecureString)**
   - *What it is:* A managed, encrypted key-value store for configuration and secrets.
   - *Why we use it:* `OPENAI_API_KEY` must never live in the image, the Terraform files or the public repository. Parameter Store injects it into the task at start-up, at a lower cost than AWS Secrets Manager.

### 2. Architectural Design and Pattern Justification
As we move from a local stack to a shared cloud environment, we must prevent two systemic traps: **Bill Shock** (resources that keep charging after the experiment ends) and **Configuration Drift** (an environment that can no longer be recreated because it was changed by hand).

#### The Problem We Avoid: Bill Shock and Configuration Drift
A Fargate task with a public IP runs and bills until someone stops it. Without a budget alert and a mandatory `destroy` step, a finished demo keeps costing money. Likewise, a service tuned manually in the console cannot be reproduced or audited. We solve this by defining every resource in Terraform, alerting on spend before the first `apply`, and ending the milestone with a full teardown.

- **Step 1: Cost Guardrail and Plan Review**
  Before any resource exists, a monthly AWS Budget with an email alert is created in the account, and `terraform plan` is read resource by resource to confirm exactly what will be created and where.
- **Step 2: Image Registry First** (`terraform/ecr.tf`)
  The ECS service points to `<ecr_url>:latest`, so the repository must exist and contain an image before the service is created. ECR is applied first, the image is built and pushed, and only then is the rest applied.
- **Step 3: Cloud-Safe Task Configuration** (`terraform/ecs.tf`, `terraform/iam.tf`)
  The container cannot reach the local Ollama daemon, so in AWS the gateway is configured with `DISABLE_SEMANTIC_CACHE=true` and serves `gpt-*` models through OpenAI. `OPENAI_API_KEY` is read from Parameter Store through a scoped permission added to the task execution role. The SQLite database lives in the container's ephemeral storage and is seeded at start-up; this is accepted for a demonstration deployment and documented as a limitation.
- **Step 4: Network Exposure** (`terraform/security.tf`)
  The security group opens port 8000 to the internet. This is acceptable for a short-lived demo because the completions route requires a Bearer API key and the deployment is destroyed after testing. The `/health`, `/metrics` and `/docs` routes are unauthenticated, which is a known limitation of the demo.
- **Step 5: Verification and Teardown**
  The deployed service is checked through `/health` and the CloudWatch log stream, load-tested with the existing Locust script, documented with an architecture diagram, and removed with `terraform destroy`.

### 3. Technical Execution Roadmap
The implementation sequence inside the repository will follow these exact steps:

1. **task 8.1: billing alarm and terraform plan review**
   Creates the monthly AWS Budget alert in the console, confirms the target account and region, and runs `terraform plan` on `feature/aws-terraform-deployment`, documenting what each of the planned resources does.
2. **task 8.2: ECR repository and image push**
   Applies only the ECR resources, builds the image from the existing `Dockerfile` for the Fargate CPU architecture, and pushes it to the repository defined in `terraform/ecr.tf`.
3. **task 8.3: task configuration, secrets and database**
   Configures `terraform/ecs.tf` and `terraform/iam.tf` with the environment variables, the Parameter Store secret and the start-up seeding, and adds the matching placeholders and notes to `.env.example` and `docs/DEPLOYMENT.md`.
4. **task 8.4: full apply and cloud verification**
   Applies the remaining resources, retrieves the task's public IP, and verifies `GET /health`, an authenticated request and the JSON log lines in the CloudWatch log group `/ecs/aegis-guard`.
5. **task 8.5: locust load test against the deployment**
   Executes `locustfile.py` against the public endpoint and records latency and HTTP 429 behaviour next to the local benchmark.
6. **task 8.6: architecture diagram, readme and destroy**
   Writes the AWS section of the README and `docs/DEPLOYMENT.md` with an architecture diagram and the load-test results, then runs `terraform destroy` and confirms that no billable resources remain.
