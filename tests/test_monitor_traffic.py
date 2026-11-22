"""Regression tests for safe 15-minute WireGuard peer-presence auto-stop."""

import base64
import importlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

PEER = base64.b64encode(b"A" * 32).decode("ascii")
OTHER_PEER = base64.b64encode(b"B" * 32).decode("ascii")
NOW = 1_800_000_000


class FakeEc2:
    def __init__(self, launch_age=3600):
        self.launch = NOW - launch_age
        self.state = "running"
        self.stops = []

    def describe_instances(self, InstanceIds):
        return {"Reservations": [{"Instances": [{
            "State": {"Name": self.state},
            "LaunchTime": datetime.fromtimestamp(self.launch, timezone.utc),
        }]}]}

    def stop_instances(self, InstanceIds):
        self.stops.append(InstanceIds)


class FakeSsm:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def send_command(self, **kwargs):
        assert kwargs["Parameters"]["commands"] == [
            "wg show wg0 latest-handshakes"
        ]
        self.calls += 1
        return {"Command": {"CommandId": str(self.calls)}}

    def get_command_invocation(self, **kwargs):
        value = self.outputs[self.calls - 1]
        if isinstance(value, Exception):
            raise value
        if value is None:
            return {"Status": "Failed"}
        return {"Status": "Success", "StandardOutputContent": value}


def read_body(response):
    assert response["statusCode"] == 200
    return json.loads(response["body"])


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("INSTANCE_ID", "i-01234567890123456")
    monkeypatch.setenv("WG_INTERFACE", "wg0")
    monkeypatch.setenv("AUTO_STOP_IDLE_SECONDS", "900")
    module = importlib.import_module("lambda_functions.monitor_traffic")
    module = importlib.reload(module)
    monkeypatch.setattr(module.time, "time", lambda: NOW)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    return module


def setup(monitor, monkeypatch, outputs, launch_age=3600):
    ec2 = FakeEc2(launch_age)
    ssm = FakeSsm(outputs)
    monkeypatch.setattr(monitor, "ec2", ec2)
    monkeypatch.setattr(monitor, "ssm", ssm)
    return ec2, ssm


def test_recent_handshake_keeps_instance_running(monitor, monkeypatch):
    ec2, ssm = setup(monitor, monkeypatch, [f"{PEER}\t{NOW-60}\n"])
    assert "retained" in read_body(monitor.handler({}, None))["message"]
    assert not ec2.stops
    assert ssm.calls == 1


def test_stale_handshake_stops_after_two_probes(monitor, monkeypatch):
    ec2, ssm = setup(monitor, monkeypatch,
                     [f"{PEER}\t{NOW-901}\n", f"{PEER}\t{NOW-901}\n"])
    assert "auto-stop requested" in read_body(monitor.handler({}, None))["message"]
    assert len(ec2.stops) == 1
    assert ssm.calls == 2


def test_recheck_detects_reconnection(monitor, monkeypatch):
    ec2, ssm = setup(monitor, monkeypatch,
                     [f"{PEER}\t{NOW-901}\n", f"{PEER}\t{NOW-3}\n"])
    assert "Peer became active" in read_body(monitor.handler({}, None))["message"]
    assert ssm.calls == 2
    assert not ec2.stops


def test_new_peer_registration_aborts_stop(monitor, monkeypatch):
    ec2, _ = setup(monitor, monkeypatch,
                   [f"{PEER}\t{NOW-901}\n",
                    f"{PEER}\t{NOW-901}\n{OTHER_PEER}\t0\n"])
    assert "configuration changed" in read_body(monitor.handler({}, None))["message"]
    assert not ec2.stops


def test_startup_grace_prevents_premature_shutdown(monitor, monkeypatch):
    ec2, ssm = setup(monitor, monkeypatch, [], launch_age=500)
    assert "grace" in read_body(monitor.handler({}, None))["message"]
    assert ssm.calls == 0
    assert not ec2.stops


def test_unconfigured_server_stops_after_grace(monitor, monkeypatch):
    ec2, ssm = setup(monitor, monkeypatch, ["", ""])
    read_body(monitor.handler({}, None))
    assert ssm.calls == 2
    assert len(ec2.stops) == 1


@pytest.mark.parametrize("bad_result", [None, "truncated_or_invalid"])
def test_failed_or_malformed_probe_fails_open(monitor, monkeypatch, bad_result):
    ec2, _ = setup(monitor, monkeypatch, [bad_result])
    assert "no action" in read_body(monitor.handler({}, None))["message"]
    assert not ec2.stops


def test_second_probe_failure_fails_open(monitor, monkeypatch):
    ec2, _ = setup(monitor, monkeypatch, [f"{PEER}\t0\n", None])
    assert "no action" in read_body(monitor.handler({}, None))["message"]
    assert not ec2.stops


def test_stopped_instance_is_never_stopped_again(monitor, monkeypatch):
    ec2, ssm = setup(monitor, monkeypatch, [])
    ec2.state = "stopped"
    assert read_body(monitor.handler({}, None))["state"] == "stopped"
    assert ssm.calls == 0


def test_future_handshake_fails_open(monitor, monkeypatch):
    ec2, _ = setup(monitor, monkeypatch, [f"{PEER}\t{NOW+1000}\n"])
    assert "no action" in read_body(monitor.handler({}, None))["message"]
    assert not ec2.stops


def test_launch_changed_during_recheck_does_not_stop(monitor, monkeypatch):
    ec2, ssm = setup(monitor, monkeypatch, ["", ""])
    original = monitor._handshakes

    def changed_boot():
        result = original()
        if ssm.calls == 2:
            ec2.launch = NOW - 1200
        return result

    monkeypatch.setattr(monitor, "_handshakes", changed_boot)
    assert "changed state" in read_body(monitor.handler({}, None))["message"]
    assert not ec2.stops


def test_idle_window_must_not_be_under_15_minutes(monitor):
    original = monitor.IDLE_SECONDS
    monitor.IDLE_SECONDS = 899
    try:
        with pytest.raises(ValueError):
            monitor._is_safe_to_stop(NOW - 3600, {PEER: NOW - 1000}, NOW)
    finally:
        monitor.IDLE_SECONDS = original
