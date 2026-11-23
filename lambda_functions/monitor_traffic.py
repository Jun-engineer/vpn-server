"""Fail-safe WireGuard peer-presence monitor.

WireGuard does not expose a reliable tunnel disconnect event. Clients must set
PersistentKeepalive = 25 for a fresh handshake to represent tunnel presence.
This monitor is deliberately opt-in in Terraform until client configuration is
verified. Any error fails open (the instance stays running).
"""

import json
import logging
import os
import re
import shlex
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

INSTANCE_ID = os.environ["INSTANCE_ID"]
WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")
IDLE_SECONDS = int(os.environ.get("AUTO_STOP_IDLE_SECONDS", "900"))
# SSM SendCommand.TimeoutSeconds has an AWS API minimum of 30 seconds.
# Bound Lambda-side polling separately: two checks + recheck delay must fit
# within the Lambda's 60-second timeout, and probe failures must fail open.
SSM_COMMAND_DELIVERY_TIMEOUT_SECONDS = 30
SSM_POLL_TIMEOUT_SECONDS = 20
SSM_POLL_SECONDS = 1
RECHECK_DELAY_SECONDS = 5

ec2 = boto3.client("ec2")
ssm = boto3.client("ssm")


def _response(message, **details):
    return {"statusCode": 200, "body": json.dumps({"message": message, **details})}


def _instance():
    reservations = ec2.describe_instances(InstanceIds=[INSTANCE_ID]).get("Reservations", [])
    instances = [item for reservation in reservations for item in reservation.get("Instances", [])]
    if len(instances) != 1:
        raise ValueError("Expected exactly one VPN EC2 instance")
    instance = instances[0]
    launch_time = instance["LaunchTime"]
    if launch_time.tzinfo is None:
        raise ValueError("EC2 LaunchTime must be timezone-aware")
    return instance["State"]["Name"], launch_time.timestamp()


def _handshakes():
    """Read only peer public keys and latest handshake epochs via SSM.

    Never fetch 'wg show dump': that command includes the server private key.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", WG_INTERFACE):
        raise ValueError("Invalid WireGuard interface name")

    command = ssm.send_command(
        InstanceIds=[INSTANCE_ID],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": [
            f"wg show {shlex.quote(WG_INTERFACE)} latest-handshakes"
        ]},
        TimeoutSeconds=SSM_COMMAND_DELIVERY_TIMEOUT_SECONDS,
    )
    command_id = command["Command"]["CommandId"]
    deadline = time.monotonic() + SSM_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            result = ssm.get_command_invocation(
                CommandId=command_id, InstanceId=INSTANCE_ID
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "InvocationDoesNotExist":
                raise
            time.sleep(SSM_POLL_SECONDS)
            continue

        status = result.get("Status")
        if status == "Success":
            return _parse_handshakes(result.get("StandardOutputContent", ""))
        if status in {"Failed", "Cancelled", "TimedOut", "Cancelling"}:
            raise RuntimeError(f"SSM WireGuard probe failed: {status}")
        if status not in {"Pending", "InProgress", "Delayed"}:
            raise RuntimeError(f"Unknown SSM invocation status: {status}")
        time.sleep(SSM_POLL_SECONDS)
    raise TimeoutError("SSM WireGuard probe timed out")


def _parse_handshakes(output):
    """Return peer latest-handshake epochs; refuse incomplete or malformed output."""
    if len(output) > 16000:
        raise ValueError("WireGuard probe response unexpectedly large")
    handshakes = {}
    for line in output.splitlines():
        columns = line.split()
        if len(columns) != 2:
            raise ValueError("Malformed wg latest-handshakes output")
        public_key, raw_timestamp = columns
        # WireGuard keys are 44-character base64 strings.
        if not re.fullmatch(r"[A-Za-z0-9+/]{43}=", public_key):
            raise ValueError("Unexpected WireGuard public key")
        if public_key in handshakes or not raw_timestamp.isdecimal():
            raise ValueError("Duplicate peer or malformed handshake timestamp")
        handshakes[public_key] = int(raw_timestamp)
    return handshakes


def _is_safe_to_stop(launch_epoch, handshakes, now_epoch):
    """Use the most recent handshake or launch as the earliest safe cutoff.

    Assumes *all* active clients send keepalives; without them, silence is NOT
    proof of disconnection. Refuse to act on future or suspicious timestamps.
    """
    if launch_epoch > now_epoch or IDLE_SECONDS < 900:
        raise ValueError("Invalid launch time or auto-stop idle window")
    last_seen = launch_epoch
    for stamp in handshakes.values():
        if stamp > now_epoch + 60:
            raise ValueError("Future WireGuard handshake timestamp")
        if stamp > 0:
            last_seen = max(last_seen, stamp)
    return now_epoch - last_seen >= IDLE_SECONDS


def handler(event, context):
    try:
        state, started = _instance()
        if state != "running":
            return _response("VPN is not running; no action", state=state)

        now = time.time()
        if now - started < IDLE_SECONDS:
            return _response("Start/restart grace period; no action")

        first = _handshakes()
        if not _is_safe_to_stop(started, first, time.time()):
            LOGGER.info("VPN peer presence or startup grace detected; retaining instance.")
            return _response("Recent peer handshake; instance retained", peerCount=len(first))

        # Two independent, successful probes before destructive action.
        time.sleep(RECHECK_DELAY_SECONDS)
        second = _handshakes()
        state_again, started_again = _instance()
        if state_again != "running" or started_again != started:
            return _response("Instance changed state during probe; no action")
        if set(second) != set(first):
            return _response("Peer configuration changed during probe; no action")
        if not _is_safe_to_stop(started, second, time.time()):
            return _response("Peer became active during recheck; no action")

        LOGGER.warning("No recent WireGuard handshakes for at least %s seconds; stopping %s",
                       IDLE_SECONDS, INSTANCE_ID)
        ec2.stop_instances(InstanceIds=[INSTANCE_ID])
        return _response("VPN auto-stop requested after idle interval",
                         peerCount=len(second), idleSeconds=IDLE_SECONDS)
    except Exception:
        # A missing SSM agent, WireGuard failure, clock skew, IAM error,
        # malformed output, or Lambda timeout must never stop a live VPN.
        LOGGER.exception("Unable to safely determine peer presence; skipping auto-stop")
        return _response("WireGuard presence check unavailable; no action")
