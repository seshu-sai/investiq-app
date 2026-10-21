import socket
from pathlib import Path
import subprocess
import sys

import pytest

from run_server import create_listener


def test_listener_accepts_ipv4():
    with create_listener(0) as listener:
        port = listener.getsockname()[1]
        with socket.create_connection(('127.0.0.1', port), timeout=2) as client:
            connection, address = listener.accept()
            with connection:
                client.sendall(b'ping')
                assert connection.recv(4) == b'ping'


@pytest.mark.skipif(not socket.has_dualstack_ipv6(), reason='IPv6 not enabled on this host')
def test_same_listener_accepts_ipv6():
    with create_listener(0) as listener:
        port = listener.getsockname()[1]
        with socket.create_connection(('::1', port), timeout=2) as client:
            connection, address = listener.accept()
            with connection:
                client.sendall(b'ping')
                assert connection.recv(4) == b'ping'


def test_invalid_port_fails_before_starting_server():
    import os
    runner = Path(__file__).resolve().parents[1] / 'run_server.py'
    result = subprocess.run([sys.executable, str(runner)], env={**os.environ, 'PORT': '70000'},
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert 'PORT must be between 1 and 65535' in result.stderr
