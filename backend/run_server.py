import socket
import uvicorn

HOST = "::"
PORT = 8000

sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((HOST, PORT))
sock.listen(2048)
sock.set_inheritable(True)

print(f"InvestIQ listening on IPv4 + IPv6, port {PORT}", flush=True)

config = uvicorn.Config(
    "app.main:app",
    fd=sock.fileno(),
    log_level="info",
)
server = uvicorn.Server(config)
server.run()
