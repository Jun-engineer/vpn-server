# VPN Server Auto-Control Platform

This repository provisions an AWS-based automation stack that runs a WireGuard VPN server in the Tokyo region and exposes a lightweight Web UI for start, stop, and status operations, with an admin console for peer registration. Terraform creates the AWS resources, and the VPN can be started on demand at any time. Weekday midnight shutdown remains disabled. An opt-in 15-minute WireGuard peer-presence monitor is available, but **disabled by default** until every client is configured and verified with persistent keepalives.

## Solution Highlights
- **EC2 (default `t3a.small`)** launched from the configured AMI (`vpn_ami_id`, default `ami-0f52389a8648b923a`) with a 30 GB encrypted gp3 root volume and no additional user-data overrides.
- **Dedicated networking stack** (new VPC, single public subnet, internet gateway, and route table) plus an ENI with an Elastic IP to keep the VPN’s public address stable across reboots.
- **Managed SSH key pair** generated via Terraform and exposed as sensitive output for immediate download; the EC2 instance uses this key for admin access.
- **Lambda functions (Python 3.12)** handling start, stop, status, peer-registration, and network-monitor workflows.
- **API Gateway (REST)** exposing `/start`, `/stop`, `/status`, and `/register` endpoints locked behind an API key.
- **EventBridge Scheduler** keeps the weekday midnight shutdown **DISABLED**. The former low-traffic schedule has been replaced with an opt-in 1-minute WireGuard handshake check. It remains **DISABLED by default** until validated.
- **S3 + CloudFront** delivering a static HTML/CSS Web UI that interacts with the API.
- **Admin console** served at `admin.html` for trusted operators, with WireGuard peer registration alongside the server controls.
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
[Amazon EventBridge Scheduler] (weekday shutdown OFF; peer monitor opt-in)
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

   For an existing deployment, use its **existing Terraform state and variable values**. Do not initialize a new state or deploy over the existing stack with defaults that differ from production. If the retired `allowed_weekday_start_hour` or `allowed_weekday_end_hour` inputs were explicitly set in a variable file, environment, or CLI arguments, remove them before planning.

   **Important: merging this change does not update AWS.** Run `terraform plan` and `terraform apply` against the existing state. Verify that the change disables both `aws_scheduler_schedule.weekday_stop` and `aws_scheduler_schedule.monitor` in place; investigate any proposed EC2 replacement or unrelated changes before applying. If an immediate change is needed before Terraform can be applied, disable both schedules in the AWS EventBridge Scheduler console in `ap-northeast-1`, then reconcile with Terraform.

   After applying, verify the two schedules (adjust the names if `project_name` differs from its default):
   ```bash
   aws scheduler get-schedule --region ap-northeast-1 \
     --name vpn-server-tokyo-weekday-stop --query State --output text
   aws scheduler get-schedule --region ap-northeast-1 \
     --name vpn-server-tokyo-monitor --query State --output text
   ```
   With the default configuration, both print `DISABLED`. After intentionally enabling peer monitoring, the weekday schedule should print `DISABLED` and the monitor should print `ENABLED`. This does **not** start a currently stopped instance; use **Start VPN** when needed.

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
2. `index.html` displays **Start VPN**, **Stop VPN**, and **Check Status**. Terraform inserts the API Gateway invoke URL into both pages at deployment. The first request prompts for the **API key**, which is never included in the published files.
3. **Stop VPN** asks for confirmation on `index.html` because a shutdown disconnects all VPN devices. After confirming, use **Check Status** to verify that the server has stopped. The result panel also reports the outcome of start and status requests.
4. The browser saves the API key locally and shares it between the two pages on the same domain. Use **Forget saved API key** to clear it or enter a replacement.
5. Trusted operators can open `<cloudfront-domain>/admin.html` to access the server controls and register peers. The page prompts for the HTTP Basic credentials configured via `admin_basic_auth_username`/`admin_basic_auth_password`. The registration form returns the allocated `/32` IP and generated preshared key for the client configuration.

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
- **stop_instance**: Stops the instance only when explicitly invoked through the API/UI (or by a direct, authorized AWS action). The former weekday midnight schedule is disabled. Idempotent when already stopping or stopped.
- **check_status**: Reports instance state, IPs, and the latest EC2 system/instance status checks, marking the VPN as available only after both checks pass, with timestamps in Australia/Sydney time.
- **register_peer**: Accepts a WireGuard public key, allocates the next free `/32` in the configured client CIDR, updates `/etc/wireguard/wg0.conf` through AWS Systems Manager, and returns the assigned IP plus a generated preshared key.
- **monitor_traffic**: Checks WireGuard `latest-handshakes` over AWS Systems Manager once per minute **only if explicitly enabled**. After at least 15 minutes since the latest client handshake (or instance startup if no client has connected), it probes again, checks the EC2 instance is still the same running boot, and then requests stop. All errors skip shutdown.

## Shutdown policy

**Default: manual-only.** No midnight cutoff. No traffic-volume shutdown. An optional peer-presence policy is available with `enable_peer_auto_stop = true`, after client setup and verification as described below. All schedules remain Terraform-managed.

### Optional 15-minute automatic stop (requires client setup)

**Important limitation:** WireGuard is connectionless. The server **cannot tell that the VPN switch was turned OFF**. `wg show wg0 latest-handshakes` reports the last successful handshake, not the client's actual UI state. A client that is ON but silent can look disconnected and be interrupted. For this reason, the monitor is **off by default** and must NOT be enabled before configuring and testing **every** phone, laptop, and other client. Even with keepalives, mobile OS sleep/power-saving/network interruptions can suppress traffic; this is an approximation, never a guaranteed disconnect detector.

1. On **each client** (iOS WireGuard, Android, Windows, Mac), open its VPN tunnel configuration and add or verify the following option in the `[Peer]` block (the block that contains the **server** `PublicKey` and `Endpoint`, NOT the server's own configuration):

   ```ini
   [Peer]
   PublicKey = <server-public-key>
   Endpoint = <vpn-ip-or-domain>:51820
   AllowedIPs = 0.0.0.0/0
   PersistentKeepalive = 25
   ```

   This is only an illustrative excerpt; **keep the client's existing PublicKey, Endpoint, AllowedIPs, and other settings unchanged**. Save the configuration and reactivate its tunnel. For QR-imported profiles, edit the client profile itself; configuring the server cannot set a client's keepalive behavior.

2. Start the VPN server and keep a client connected **without browsing for more than 15 minutes**. In AWS Systems Manager Run Command, execute `wg show wg0 latest-handshakes` on the EC2 instance twice several minutes apart. The epoch timestamp of the connected peer should advance periodically. If it does not, **do not enable auto-stop**. Repeat for every client, including with the phone screen locked/backgrounded.
3. From the **existing production Terraform state and variable values**, opt in with `enable_peer_auto_stop = true` (for example, in a production `terraform.tfvars`) and leave `peer_auto_stop_idle_minutes = 15`. Run `terraform plan` first, confirm only intended in-place changes, and run `terraform apply`. Verify `vpn-server-tokyo-weekday-stop` stays `DISABLED`, and `vpn-server-tokyo-monitor` becomes `ENABLED`.
4. Test **all clients connected** (no stop), **all tunnels OFF** (stop roughly 15–16 minutes after the last successful handshake), **reconnection before cutoff** (no stop), and **SSM not available** (no stop). The stopped VPN can be restarted from the existing Web UI. The monitoring interval and SSM command latency mean the shutdown is **not an exact 15-minute deadline**.
5. If a connected device is incorrectly stopped, immediately set `enable_peer_auto_stop = false` and apply, or disable `vpn-server-tokyo-monitor` in the AWS EventBridge Scheduler console while investigating.

**Fail-safe protections:** no automatic stop during the first 15 minutes after EC2 starts; no stop when a recent handshake exists; a second independent SSM check and EC2 boot/state check before stop; no stop when a peer gets added/removed during the check; no stop after malformed output, missing WireGuard interface, SSM failures/timeouts, clock anomalies, or IAM errors; no private keys are retrieved in the probe. A brief reconnect **after** the last recheck and just before the AWS stop request can still race with shutdown; this is not a hard guarantee. Manual Start/Stop/Status and peer-registration continue to work.

**Operational note:** Keepalives generate small periodic packets and additional handshakes. If any client is configured to remain always-on and sends keepalives continuously, the instance will deliberately remain running (and billable). Disconnect the last client tunnel when finished if you want the 15-minute shutdown.


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
