import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import ceil
from zoneinfo import ZoneInfo

import boto3

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

INSTANCE_ID = os.environ["INSTANCE_ID"]
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "UTC"))
THRESHOLD_MB = float(os.environ.get("MONITOR_THRESHOLD_MB", 1))
WINDOW_HOURS = float(os.environ.get("MONITOR_WINDOW_HRS", 1.5))
PERIOD_SECONDS = int(os.environ.get("MONITOR_PERIOD_SECONDS", 900))
REQUIRED_POINTS = max(1, int(ceil((WINDOW_HOURS * 3600) / PERIOD_SECONDS)))

cloudwatch = boto3.client("cloudwatch")
ec2 = boto3.client("ec2")

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST"
}


def _response(status: int, data: dict) -> dict:
    return {
        "statusCode": status,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(data, ensure_ascii=False)
    }


def _instance_is_running() -> bool:
    status = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
    reservations = status.get("Reservations", [])
    instances = [instance for r in reservations for instance in r.get("Instances", [])]
    if not instances:
        return False
    return instances[0]["State"]["Name"] == "running"


def _collect_metrics(start: datetime, end: datetime) -> dict:
    totals = defaultdict(float)
    for metric_name in ("NetworkIn", "NetworkOut"):
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName=metric_name,
            Dimensions=[{"Name": "InstanceId", "Value": INSTANCE_ID}],
            StartTime=start,
            EndTime=end,
            Period=PERIOD_SECONDS,
            Statistics=["Sum"],
            Unit="Bytes"
        )
        for datapoint in response.get("Datapoints", []):
            totals[datapoint["Timestamp"]] += datapoint["Sum"]
    return totals


def handler(event, context):
    try:
        if not _instance_is_running():
            LOGGER.info("Instance not running. Skipping traffic evaluation.")
            return _response(200, {
                "message": "Instance is not in a running state. No action taken.",
                "timestampLocal": datetime.now(TIMEZONE).isoformat()
            })

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=WINDOW_HOURS)
        metrics = _collect_metrics(start_time, end_time)

        if not metrics:
            LOGGER.info("No traffic metrics available in window. Skipping auto-stop.")
            return _response(200, {
                "message": "No CloudWatch metrics found for evaluation window.",
                "timestampLocal": datetime.now(TIMEZONE).isoformat()
            })

        sorted_points = sorted(metrics.items(), key=lambda item: item[0])
        evaluation = []
        per_hour_factor = 3600 / PERIOD_SECONDS
        for timestamp, total_bytes in sorted_points:
            mb_transferred = total_bytes / (1024 * 1024)
            mb_per_hour = mb_transferred * per_hour_factor
            evaluation.append({
                "timestamp": timestamp.isoformat(),
                "megabytesPeriod": round(mb_transferred, 3),
                "megabytesPerHour": round(mb_per_hour, 3)
            })

        low_utilization = [item for item in evaluation if item["megabytesPerHour"] <= THRESHOLD_MB]
        valid_points = evaluation[-REQUIRED_POINTS:]
        should_stop = len(valid_points) >= REQUIRED_POINTS and all(item["megabytesPerHour"] <= THRESHOLD_MB for item in valid_points)

        LOGGER.info("Evaluation results: %s", evaluation)
        LOGGER.info("Low utilization periods: %s", low_utilization)

        if should_stop:
            LOGGER.info("Threshold satisfied. Issuing stop command.")
            ec2.stop_instances(InstanceIds=[INSTANCE_ID])
            return _response(200, {
                "message": "Traffic remained below threshold. Stop command issued.",
                "evaluation": evaluation,
                "thresholdMbPerHour": THRESHOLD_MB,
                "windowHours": WINDOW_HOURS,
                "requiredPoints": REQUIRED_POINTS,
                "timestampLocal": datetime.now(TIMEZONE).isoformat()
            })

        return _response(200, {
            "message": "Traffic above threshold. Instance remains running.",
            "evaluation": evaluation,
            "thresholdMbPerHour": THRESHOLD_MB,
            "windowHours": WINDOW_HOURS,
            "requiredPoints": REQUIRED_POINTS,
            "timestampLocal": datetime.now(TIMEZONE).isoformat()
        })
    except Exception as exc:
        LOGGER.exception("Traffic monitor failed: %s", exc)
        return _response(500, {
            "message": "Failed to evaluate traffic metrics.",
            "error": str(exc)
        })
