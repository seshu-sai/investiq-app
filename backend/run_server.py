"""Listen on both address families so Railway private DNS can reach the API."""
import os
import socket
from contextlib import ExitStack

import uvicorn


def create_listener(port: int) -> socket.socket:
    if socket.has_dualstack_ipv6():
        sock = socket.create_server(('::', port), family=socket.AF_INET6,
                                    dualstack_ipv6=True, backlog=2048)
    else:
        sock = socket.create_server(('0.0.0.0', port), backlog=2048)
    sock.set_inheritable(True)
    return sock


def main():
    port = int(os.getenv('PORT', '8000'))
    internal_port = int(os.getenv('API_INTERNAL_PORT', '8000'))
    if not all(1 <= value <= 65535 for value in (port, internal_port)):
        raise ValueError('PORT must be between 1 and 65535; API_INTERNAL_PORT has the same range')
    # Keep the private proxy's stable port even if Railway assigns another
    # public service port. Both listeners run the same application.
    with ExitStack() as stack:
        listeners = [stack.enter_context(create_listener(value)) for value in sorted({port, internal_port})]
        families = 'IPv4 + IPv6' if listeners[0].family == socket.AF_INET6 else 'IPv4'
        print(f'InvestIQ listening on {families}, ports {sorted({port, internal_port})}', flush=True)
        config = uvicorn.Config('app.main:app', port=port, log_level='info')
        uvicorn.Server(config).run(sockets=listeners)


if __name__ == '__main__':
    main()
