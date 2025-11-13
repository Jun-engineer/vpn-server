import json
import logging
import os
import time
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

ssm = boto3.client("ssm")

INSTANCE_ID = os.environ["INSTANCE_ID"]
CLIENT_SUBNET = os.environ["CLIENT_SUBNET_CIDR"]
SERVER_ADDRESS = os.environ["SERVER_ADDRESS"]
WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")
WG_CONF_PATH = os.environ.get("WG_CONF_PATH", "/etc/wireguard/wg0.conf")
COMMAND_TIMEOUT = int(os.environ.get("SSM_COMMAND_TIMEOUT_SECONDS", "60"))
DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST"
}


def _response(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(payload, ensure_ascii=False)
    }


def _escape_heredoc(value: str) -> str:
    # Heredoc with single quotes prevents interpretation; ensure terminator not present
    return value.replace("EOF", "EOX")


def _build_ssm_commands(public_key: str) -> list[str]:
    sanitized_key = _escape_heredoc(public_key.strip())
    wg_conf = _escape_heredoc(WG_CONF_PATH)
    client_subnet = _escape_heredoc(CLIENT_SUBNET)
    server_address = _escape_heredoc(SERVER_ADDRESS)
    wg_interface = _escape_heredoc(WG_INTERFACE)

    python_script = """import ipaddress
import json
import os
import subprocess
import tempfile
import pathlib

public_key = os.environ[\"PUBLIC_KEY\"].strip()
wg_conf_path = os.environ.get(\"WG_CONF_PATH\", "/etc/wireguard/wg0.conf")
client_subnet = ipaddress.ip_network(os.environ[\"CLIENT_SUBNET\"], strict=False)
server_address = ipaddress.ip_address(os.environ[\"SERVER_ADDRESS\"])
wg_interface = os.environ.get(\"WG_INTERFACE\", \"wg0\")

if not public_key:
    raise SystemExit("Missing public key")

sections = []
current = None
with open(wg_conf_path, "r", encoding="utf-8") as fh:
    for raw in fh:
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if current is not None:
                sections.append(current)
            current = {"type": stripped.strip("[]"), "lines": [raw], "data": {}}
        else:
            if current is None:
                continue
            current["lines"].append(raw)
            if "=" in stripped:
                key, value = map(str.strip, stripped.split("=", 1))
                current["data"][key] = value
if current is not None:
    sections.append(current)

existing_peer = None
used_ips = {server_address}
for section in sections:
    if section["type"].lower() != "peer":
        continue
    if section["data"].get("PublicKey") == public_key:
        existing_peer = section
    allowed_line = section["data"].get("AllowedIPs")
    if allowed_line:
        first_entry = allowed_line.split(",", 1)[0].strip()
        network = ipaddress.ip_network(first_entry, strict=False)
        if network.prefixlen == 32:
            used_ips.add(network.network_address)
        else:
            for host in network.hosts():
                used_ips.add(host)

result = {
    "alreadyExists": False,
    "assignedIp": None,
    "presharedKey": None
}

if existing_peer:
    assigned = existing_peer["data"].get("AllowedIPs", "").split(",", 1)[0].strip()
    result["alreadyExists"] = True
    if assigned:
        result["assignedIp"] = assigned.split("/")[0]
    preshared = existing_peer["data"].get("PreSharedKey")
    result["presharedKey"] = preshared
else:
    available_ip = None
    for host in client_subnet.hosts():
        if host == server_address or host in used_ips:
            continue
        available_ip = host
        break
    if available_ip is None:
        raise SystemExit(json.dumps({"error": "No available client IP addresses"}))

    assigned_ip = str(available_ip)
    preshared_key = subprocess.run(["wg", "genpsk"], check=True, capture_output=True, text=True).stdout.strip()

    with open(wg_conf_path, "a", encoding="utf-8") as fh:
        fh.write("\n[Peer]\n")
        fh.write(f"PublicKey = {public_key}\n")
        fh.write(f"AllowedIPs = {assigned_ip}/32\n")
        if preshared_key:
            fh.write(f"PreSharedKey = {preshared_key}\n")

    subprocess.run(["wg", "set", wg_interface, "peer", public_key, "allowed-ips", f"{assigned_ip}/32"], check=True)

    if preshared_key:
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write(preshared_key)
            temp_path = tmp.name
        try:
            subprocess.run(["wg", "set", wg_interface, "peer", public_key, "preshared-key", temp_path], check=True)
        finally:
            pathlib.Path(temp_path).unlink(missing_ok=True)

    result["assignedIp"] = assigned_ip
    result["presharedKey"] = preshared_key

print(json.dumps(result))
"""

    script = f"""
set -euo pipefail
export PUBLIC_KEY=$(cat <<'EOF'
{sanitized_key}
EOF
)
export WG_CONF_PATH='{wg_conf}'
export CLIENT_SUBNET='{client_subnet}'
export SERVER_ADDRESS='{server_address}'
export WG_INTERFACE='{wg_interface}'
python3 <<'PY'
{python_script}
PY
"""
    return [script]


def handler(event, context):
    try:
        if event.get("httpMethod") == "OPTIONS":
            return _response(200, {"message": "OK"})

        if event.get("httpMethod") != "POST":
            return _response(405, {"message": "Method Not Allowed"})

        try:
            payload = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _response(400, {"message": "Request body must be valid JSON."})

        public_key = (payload.get("publicKey") or "").strip()
        if not public_key:
            return _response(400, {"message": "publicKey is required."})
        if len(public_key) < 32:
            return _response(400, {"message": "publicKey appears invalid."})

        commands = _build_ssm_commands(public_key)
        LOGGER.info("Sending registration command via SSM")
        command = ssm.send_command(
            InstanceIds=[INSTANCE_ID],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": commands},
            TimeoutSeconds=COMMAND_TIMEOUT
        )
        command_id = command["Command"]["CommandId"]

        start = time.time()
        while True:
            invocation = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=INSTANCE_ID
            )
            status = invocation.get("Status")
            if status in {"Pending", "InProgress", "Delayed"}:
                if time.time() - start > COMMAND_TIMEOUT:
                    raise TimeoutError("SSM command timed out")
                time.sleep(2)
                continue
            if status != "Success":
                error_output = invocation.get("StandardErrorContent")
                LOGGER.error("SSM command failed: %s", error_output)
                return _response(500, {
                    "message": "Failed to register peer.",
                    "error": error_output or status
                })
            output = invocation.get("StandardOutputContent") or "{}"
            break

        try:
            result = json.loads(output.strip().splitlines()[-1])
        except json.JSONDecodeError:
            LOGGER.error("Unable to parse SSM output: %s", output)
            return _response(500, {
                "message": "Unexpected response from registration command.",
                "rawOutput": output
            })

        response_body = {
            "message": "Peer registered." if not result.get("alreadyExists") else "Peer already registered.",
            "assignedIp": result.get("assignedIp"),
            "presharedKey": result.get("presharedKey"),
            "alreadyExists": result.get("alreadyExists", False)
        }
        return _response(200, response_body)
    except (ClientError, TimeoutError) as exc:
        LOGGER.exception("Registration failed: %s", exc)
        return _response(500, {
            "message": "Failed to register peer.",
            "error": str(exc)
        })
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Unhandled error: %s", exc)
        return _response(500, {
            "message": "Unexpected error during registration.",
            "error": str(exc)
        })
