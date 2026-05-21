from __future__ import annotations

import concurrent.futures
import ipaddress
import os
import socket
from typing import Optional

_PORT = 1234
_DISCOVERY_PORT = 3040


def _make_discovery_packet() -> bytes:
    """12-byte Prologix NetFinder UDP discovery packet.

    Format reverse-engineered from netfinder.exe:
      0x00–0x01  0x5A 0x00  – command byte + reserved
      0x02–0x03  random 16-bit transaction ID (big-endian)
      0x04–0x07  0xFF FF FF FF  – broadcast target IP
      0x08–0x09  0xFF FF
      0x0A–0x0B  0x00 00
    """
    return b"\x5a\x00" + os.urandom(2) + b"\xff\xff\xff\xff\xff\xff\x00\x00"


def _local_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def _discover_udp(local_ip: str, timeout: float) -> list[dict]:
    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    broadcast = str(network.broadcast_address)

    found: list[dict] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        try:
            sock.bind((local_ip, 0))
        except OSError as e:
            raise OSError(
                f"Cannot bind to {local_ip!r} — must be a local interface address, "
                f"not a remote host."
            ) from e
        sock.sendto(_make_discovery_packet(), (broadcast, _DISCOVERY_PORT))
        try:
            while True:
                data, addr = sock.recvfrom(1024)
                found.append(
                    {"ip": addr[0], "version": data.decode(errors="replace").strip()}
                )
        except socket.timeout:
            pass
    return found


def _probe_tcp(host: str, timeout: float) -> Optional[dict]:
    try:
        with socket.create_connection((host, _PORT), timeout=timeout) as s:
            s.sendall(b"++ver\n")
            s.settimeout(timeout)
            response = s.recv(256).decode(errors="replace").strip()
            if "Prologix" in response:
                return {"ip": host, "version": response}
    except OSError:
        pass
    return None


def _discover_tcp(local_ip: str, timeout: float, workers: int) -> list[dict]:
    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    hosts = [str(h) for h in network.hosts()]

    found: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe_tcp, h, timeout): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            if result:
                found.append(result)
    return found


def discover_prologix(
    local_ip: Optional[str] = None,
    *,
    udp_timeout: float = 2.0,
    tcp_timeout: float = 0.5,
    tcp_workers: int = 64,
) -> list[dict]:
    """Find Prologix adapters on the subnet. UDP broadcast first, TCP sweep fallback.

    Returns list of dicts with 'ip' and 'version' keys.
    """
    if local_ip is None:
        local_ip = _local_ip()
    found = _discover_udp(local_ip, udp_timeout)
    if not found:
        found = _discover_tcp(local_ip, tcp_timeout, tcp_workers)
    return found


def scan_gpib_idn(
    host: str,
    *,
    addr_start: int = 0,
    addr_end: int = 30,
    per_addr_timeout: float = 1.0,
) -> list[dict]:
    """Probe each GPIB address with *IDN?. Returns list of dicts with 'addr' and 'idn' keys."""
    found: list[dict] = []

    with socket.create_connection((host, _PORT), timeout=per_addr_timeout) as s:

        def _send(cmd: str) -> None:
            s.sendall((cmd + "\n").encode())

        _send("++mode 1")
        _send("++auto 0")
        _send("++eos 2")
        _send("++eoi 1")

        for addr in range(addr_start, addr_end + 1):
            _send(f"++addr {addr}")
            _send("*IDN?")
            _send("++read eoi")
            s.settimeout(per_addr_timeout)
            buf = b""
            try:
                while b"\n" not in buf:
                    chunk = s.recv(256)
                    if not chunk:
                        break
                    buf += chunk
                line = buf.decode(errors="replace").strip()
                if line:
                    found.append({"addr": addr, "idn": line})
            except socket.timeout:
                pass

    return found
