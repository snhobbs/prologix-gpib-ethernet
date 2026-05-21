"""PyVISA-compatible resource for a single GPIB instrument via Prologix GPIB-Ethernet.

    with PrologixResource('192.168.1.10', gpib_address=16) as res:
        idn = res.query('*IDN?')
"""

from __future__ import annotations

from .plx_gpib_ethernet import PrologixGPIBEthernet


class PrologixResource:
    """write / read / query / close wrapper for one GPIB instrument. No PyVISA required.

    timeout is in milliseconds, matching the PyVISA convention.
    """

    def __init__(self, host: str, gpib_address: int, *, timeout_ms: int = 5000) -> None:
        self.timeout = timeout_ms
        self._gpib_address = gpib_address
        self._adapter = PrologixGPIBEthernet(host, timeout=min(3.0, timeout_ms / 1000))
        self._adapter.connect()
        # Override _setup() defaults: select address and enable auto-read
        self._adapter._send(f"++addr {gpib_address}")
        self._adapter._send("++auto 1")
        self._adapter._send("++eos 2")
        self._adapter._send("++eoi 1")
        self._adapter._send(f"++read_tmo_ms {timeout_ms}")

    def write(self, cmd: str) -> None:
        self._adapter._send(cmd)

    def read(self) -> str:
        # ++auto 1: adapter issues ++read eoi after each write, response arrives without prompting
        sock = self._adapter.socket
        sock.settimeout(self.timeout / 1000)
        buf = b""
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    break
        except TimeoutError:
            pass
        return buf.decode(errors="replace").rstrip("\r\n")

    def query(self, cmd: str) -> str:
        self.write(cmd)
        return self.read()

    def close(self) -> None:
        self._adapter.close()

    def __enter__(self) -> PrologixResource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"PrologixResource({self._adapter.host!r}, {self._gpib_address})"
