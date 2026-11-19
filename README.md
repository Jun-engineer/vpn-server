# VPN Server Auto-Control Platform

This repository provisions an AWS-based automation stack that runs a WireGuard VPN server in the Tokyo region and exposes a lightweight Web UI for start/status operations, peer registration, and automated monitoring. Terraform creates the AWS resources, and the VPN can be started on demand at any time. The scheduled weekday midnight shutdown and low-traffic shutdowns remain in effect.

## Solution Highlights
- **EC2 (default `t3a.small`)** launched from the configured AMI (`vpn_ami_id`, default `ami-0f52389a8648b923a`) with a 30 GB encrypted gp3 root volume and no additional user-data overrides.
- **Dedicated networking stack** (new VPC, single public subnet, internet gateway, and route table) plus an ENI with an Elastic IP to keep the VPN’s public address stable across reboots.
- **Managed SSH key pair** generated via Terraform and exposed as sensitive output for immediate download; the EC2 instance uses this key for admin access.
- **Lambda functions (Python 3.12)** handling start, stop, status, peer-registration, and network-monitor workflows.
- **API Gateway (REST)** exposing `/start`, `/status`, `/register`, and (optionally) `/stop` endpoints locked behind an API key.
- **EventBridge Scheduler** jobs for weekday midnight shutdown and 15-minute traffic monitoring, both timezone-aware for Australia/Sydney.
- **S3 + CloudFront** delivering a static HTML/CSS Web UI that interacts with the API.
- **Admin console** served at `admin.html` for trusted operators who need manual stop and WireGuard peer registration.
- **SNS notifications** fired whenever a manual start request is issued, with optional email subscriptions.
- **IAM** kept minimal: Lambda receives only the permissions required for EC2 control, monitoring, and Systems Manager commands, while the VPN instance is attached to an `AmazonSSMManagedInstanceCore` profile for remote peer management.

## Architecture
```
[S3 + CloudFront]  -->  Web UI
         |
         v
   [API Gateway] ---> [Lambda]
      |    \           | | | |
   |     > start_instance / stop_instance / check_status / register_peer / monitor_traffic
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
   - Ensure `wireguard_client_subnet` and `wireguard_server_address` reflect the addressing used in `/etc/wireguard/wg0.conf`; the peer registration Lambda relies on these values when allocating client IPs.
   - Confirm the selected AMI includes the AWS Systems Manager Agent (SSM Agent). Amazon Linux 2/2023 images ship with it enabled by default.
   - Set `admin_basic_auth_username` and `admin_basic_auth_password` to non-default values before deploying to production; these control the CloudFront basic-auth gate for `admin.html`.
   - Optionally populate `start_notification_emails` with the addresses that should receive SNS alerts when the VPN is started.

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
   If you supplied `start_notification_emails`, check your email for the SNS subscription confirmation message and confirm it to begin receiving alerts.

   For an existing deployment, use its existing Terraform state and variable values. If the retired `allowed_weekday_start_hour` or `allowed_weekday_end_hour` inputs were explicitly set in a variable file, environment, or CLI arguments, remove them before planning.

5. **Retrieve the API key value**
   From `terraform/`, Terraform outputs the API key ID, not the secret value. Use the AWS CLI profile and region for this deployment to fetch the key:
   ```bash
   VPN_API_KEY_ID="$(terraform output -raw api_key_id)" &&
     test -n "$VPN_API_KEY_ID" &&
     aws apigateway get-api-key --api-key "$VPN_API_KEY_ID" \
       --include-value --query value --output text
   ```
   The command prints the secret. Save it in a password manager and keep it out of logs and screenshots.

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
2. `index.html` displays Start/Status buttons at any time. Terraform inserts the API Gateway invoke URL into both pages at deployment. On first use the page asks for the **API key** only. The key itself is never included in the published files.
3. The result panel shows the response (e.g., “Server already running.” or “VPN warming up…”). The browser saves the key locally and shares it between the two pages on the same domain. Use **Forget saved API key** to clear it or enter a replacement.
4. Administrators can browse to `<cloudfront-domain>/admin.html` to stop the VPN manually and register peers. The WireGuard registration form returns the allocated `/32` IP and generated preshared key—copy them into the client configuration.
5. You will be prompted for the HTTP Basic credentials configured via `admin_basic_auth_username`/`admin_basic_auth_password`; share them (and the admin API key) only with trusted operators. Successful start requests emit an SNS notification (see Terraform outputs for the topic ARN).

## Running Tests

Install the development dependencies and execute the `pytest` suite from the repository root:

```bash
pip install -r requirements-test.txt
pytest
```

The tests rely on `moto` to mock AWS services and cover the start handler during and outside the former blackout hours, the no-op for an already running instance, and SNS notifications.

Run the Web UI tests from the repository root with `node --test tests/test_vpn_controller.cjs`. These use Node's built-in test runner and mock API responses without issuing requests to AWS.

## Lambda Behavior Summary
- **start_instance**: Starts the instance on request at any time and returns the resulting instance state.
- **stop_instance**: Stops the instance when invoked via API or at midnight on weekdays (Australia/Sydney by default). You can request a start again after it stops. Idempotent when the instance is already stopping or stopped.
- **check_status**: Reports instance state, IPs, and the latest EC2 system/instance status checks, marking the VPN as available only after both checks pass, with timestamps in Australia/Sydney time.
- **register_peer**: Accepts a WireGuard public key, allocates the next free `/32` in the configured client CIDR, updates `/etc/wireguard/wg0.conf` through AWS Systems Manager, and returns the assigned IP plus a generated preshared key.
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
