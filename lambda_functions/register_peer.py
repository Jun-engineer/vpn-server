"""Lambda function to register WireGuard peers via SSM."""

import base64
import json
import logging
import os
import shlex
import textwrap
import time
from typing import Any, Dict, List

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
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
}


def _response(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _build_ssm_commands(public_key: str) -> List[str]:
    # Inline Python writes WireGuard peer configuration atomically and emits JSON.
    python_script = textwrap.dedent(
        r"""
import base64
import ipaddress
import json
import os
import pathlib
import subprocess
import tempfile

public_key = base64.b64decode(os.environ["PUBLIC_KEY_B64"]).decode("utf-8").strip()
wg_conf_path = os.environ.get("WG_CONF_PATH", "/etc/wireguard/wg0.conf")
client_subnet = ipaddress.ip_network(os.environ["CLIENT_SUBNET"], strict=False)
server_address = ipaddress.ip_address(os.environ["SERVER_ADDRESS"])
wg_interface = os.environ.get("WG_INTERFACE", "wg0")

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

result = {"alreadyExists": False, "assignedIp": None, "presharedKey": None}

if existing_peer:
    allowed = existing_peer["data"].get("AllowedIPs", "").split(",", 1)[0].strip()
    if allowed:
        result["assignedIp"] = allowed.split("/", 1)[0]
    result["alreadyExists"] = True
    result["presharedKey"] = existing_peer["data"].get("PreSharedKey")
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
    preshared_key = subprocess.run(
        ["wg", "genpsk"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with open(wg_conf_path, "a", encoding="utf-8") as fh:
        fh.write("\n[Peer]\n")
        fh.write(f"PublicKey = {public_key}\n")
        fh.write(f"AllowedIPs = {assigned_ip}/32\n")
        if preshared_key:
            fh.write(f"PreSharedKey = {preshared_key}\n")

    subprocess.run(
        ["wg", "set", wg_interface, "peer", public_key, "allowed-ips", f"{assigned_ip}/32"],
        check=True,
    )

    if preshared_key:
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write(preshared_key)
            temp_path = tmp.name
        try:
            subprocess.run(
                ["wg", "set", wg_interface, "peer", public_key, "preshared-key", temp_path],
                check=True,
            )
        finally:
            pathlib.Path(temp_path).unlink(missing_ok=True)

    result["assignedIp"] = assigned_ip
    result["presharedKey"] = preshared_key

try:
    server_public_key = subprocess.run(
        ["wg", "show", wg_interface, "public-key"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
except subprocess.CalledProcessError:
    server_public_key = ""

result["publicKey"] = public_key
result["serverPublicKey"] = server_public_key

print(json.dumps(result))
"""
    ).strip()

    encoded_script = base64.b64encode(python_script.encode("utf-8")).decode("ascii")
    encoded_key = base64.b64encode(public_key.strip().encode("utf-8")).decode("ascii")

    shell_script = textwrap.dedent(
        f"""
    /bin/bash <<'SCRIPT'
    set -euo pipefail
    export PUBLIC_KEY_B64='{encoded_key}'
    export WG_CONF_PATH={shlex.quote(WG_CONF_PATH)}
    export CLIENT_SUBNET={shlex.quote(CLIENT_SUBNET)}
    export SERVER_ADDRESS={shlex.quote(SERVER_ADDRESS)}
    export WG_INTERFACE={shlex.quote(WG_INTERFACE)}
    python3 - <<'PY'
    import base64
    code = base64.b64decode('{encoded_script}')
    exec(compile(code.decode('utf-8'), '<register_peer>', 'exec'), globals(), globals())
    PY
    SCRIPT
    """
    ).strip()

    return [shell_script]


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
            TimeoutSeconds=COMMAND_TIMEOUT,
        )
        command_id = command["Command"]["CommandId"]

        start = time.time()
        while True:
            try:
                invocation = ssm.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=INSTANCE_ID,
                )
            except ClientError as err:  # handle eventual consistency
                code = err.response.get("Error", {}).get("Code")
                if code == "InvocationDoesNotExist":
                    if time.time() - start > COMMAND_TIMEOUT:
                        raise TimeoutError("SSM command invocation not found before timeout")
                    time.sleep(2)
                    continue
                raise
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
                    "error": error_output or status,
                })
            output = invocation.get("StandardOutputContent") or "{}"
            break

        try:
            result = json.loads(output.strip().splitlines()[-1])
        except json.JSONDecodeError:
            LOGGER.error("Unable to parse SSM output: %s", output)
            return _response(500, {
                "message": "Unexpected response from registration command.",
                "rawOutput": output,
            })

        response_body = {
            "message": "Peer registered." if not result.get("alreadyExists") else "Peer already registered.",
            "assignedIp": result.get("assignedIp"),
            "presharedKey": result.get("presharedKey"),
            "alreadyExists": result.get("alreadyExists", False),
            "publicKey": public_key,
            "serverPublicKey": result.get("serverPublicKey"),
        }
        return _response(200, response_body)
    except (ClientError, TimeoutError) as exc:
        LOGGER.exception("Registration failed: %s", exc)
        return _response(500, {
            "message": "Failed to register peer.",
            "error": str(exc),
        })
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Unhandled error: %s", exc)
        return _response(500, {
            "message": "Unexpected error during registration.",
            "error": str(exc),
        })
