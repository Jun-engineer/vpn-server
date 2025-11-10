# VPN Server Auto-Control Platform

This repository provisions an AWS-based automation stack that runs a WireGuard VPN server in the Tokyo region and exposes a lightweight Web UI for controlled start, stop, and monitoring operations. Terraform creates every AWS resource, while Lambda functions implement the control logic that enforces weekday restrictions and low-traffic shutdowns.

## Solution Highlights
- **EC2 (default `t3a.small`)** launched from the configured AMI (`vpn_ami_id`, default `ami-0f52389a8648b923a`) with a 30 GB encrypted gp3 root volume and no additional user-data overrides.
- **Dedicated networking stack** (new VPC, single public subnet, internet gateway, and route table) plus an ENI with an Elastic IP to keep the VPN’s public address stable across reboots.
- **Managed SSH key pair** generated via Terraform and exposed as sensitive output for immediate download; the EC2 instance uses this key for admin access.
- **Lambda functions (Python 3.12)** handling start, stop, status, and network-monitor workflows.
- **API Gateway (REST)** exposing `/start`, `/stop`, `/status` endpoints locked behind an API key.
- **EventBridge Scheduler** jobs for weekday midnight shutdown and 15-minute traffic monitoring, both timezone-aware for Australia/Sydney.
- **S3 + CloudFront** delivering a static HTML/CSS Web UI that interacts with the API.
- **IAM** scoped to Lambda only—no IAM role is attached to the VPN instance, and Lambda logging permissions are removed to avoid CloudWatch log charges.

## Architecture
```
[S3 + CloudFront]  -->  Web UI
         |
         v
   [API Gateway] ---> [Lambda]
      |    \           | | | |
      |     > start_instance / stop_instance / check_status / monitor_traffic
      v
[Amazon EventBridge Scheduler]  (scheduled stop + traffic checks)
      |
      v
[EC2 WireGuard VPN]
```

## Prerequisites
- Terraform ≥ 1.5.x
- AWS CLI configured with credentials that can create IAM, EC2, Lambda, API Gateway, CloudFront, and S3 resources in `ap-northeast-1`.
- Optional: `direnv` or shell tooling to export Terraform variables.

## Repository Layout
```
terraform/            # Terraform configuration for the entire stack
lambda_functions/     # Python source for Lambda handlers
web/                  # Static assets for the Web UI served via CloudFront
```

## Deployment Steps
1. **Review security defaults**
   - Update `terraform/network.tf` to restrict SSH and WireGuard ingress to trusted IP ranges.
   - Adjust `timezone_name`, `vpn_instance_type`, `public_subnet_cidr`, or `vpn_private_ip` variables if you need a different layout. Ensure the instance type matches the AMI architecture.

2. **Initialize Terraform**
   ```bash
   cd terraform
   terraform init
   ```

3. **Inspect the plan**
   ```bash
   terraform plan \
     -var "project_name=vpn-auto-control" \
     -var "web_bucket_name=<optional-custom-bucket>"
   ```

4. **Apply the configuration**
   ```bash
   terraform apply
   ```
   Confirm the run and wait until all resources finish provisioning. The outputs include the API invoke URL, the CloudFront domain, and the EC2 instance ID.

5. **Retrieve the API key value**
   Terraform outputs the API key ID, not the actual secret value. To fetch it:
   ```bash
   aws apigateway get-api-key \
     --api-key <api_key_id_from_outputs> \
     --include-value
   ```

6. **Download the SSH private key**
   ```bash
   terraform output --raw ssh_private_key_pem > ../vpn-server-tokyo-key.pem
   chmod 600 ../vpn-server-tokyo-key.pem
   ```

7. **Verify WireGuard**
   - SSH into the EC2 instance using the Elastic IP output and complete any WireGuard peer configuration.
   - Confirm the existing WireGuard setup from your AMI works as expected.

## Web UI Configuration
1. Browse to the CloudFront domain from the Terraform output.
2. If it is a weekday between 00:00 and 13:00 Australia/Sydney, you will be shown `unavailable.html`, which explains the downtime and automatically refreshes once access returns.
3. Outside the restricted window (including all weekend hours), `index.html` displays Start/Stop/Status buttons. On the first click the page prompts for:
   - **API base URL** (for example, `https://<api-id>.execute-api.ap-northeast-1.amazonaws.com/prod`).
   - **API key** copied from API Gateway.
4. After the prompts, the request runs and the response appears in plain text (e.g., “Server already running.” or “VPN warming up…”). Details are saved to `localStorage`; use **Reset saved API details** to reconfigure.

## Lambda Behavior Summary
- **start_instance**: Enforces the Australia/Sydney weekday restriction (no manual starts between 00:00–13:00 local time). Returns the resulting instance state.
- **stop_instance**: Stops the instance when invoked via API or the scheduled weekday midnight rule. Idempotent when the instance is already stopping or stopped.
- **check_status**: Reports instance state, IPs, and the latest EC2 system/instance status checks, marking the VPN as available only after both checks pass, with timestamps in Australia/Sydney time.
- **monitor_traffic**: Runs every 15 minutes via EventBridge Scheduler, evaluates combined `NetworkIn`/`NetworkOut` for the trailing 1.5 hours, and stops the instance if sustained traffic ≤ 1 MB/hour.

## Cleanup
To remove all resources, run:
```bash
cd terraform
terraform destroy
```
Note that the S3 bucket is emptying automatically (`force_destroy = true`), but you should still confirm the bucket is no longer needed.

## Next Steps & Hardening Ideas
- Integrate Amazon Cognito or IAM authorizers for stronger authentication instead of API keys.
- Parameterize allowed ingress CIDR blocks and WireGuard settings.
- Add notifications (e.g., Amazon SNS) when automated stops occur.
- Introduce automated tests for the Lambda handlers (e.g., using `pytest` with moto).
