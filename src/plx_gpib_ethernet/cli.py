"""Prologix GPIB-Ethernet command-line interface."""

from __future__ import annotations

import sys

import click

from .discovery import discover_prologix, scan_gpib_idn
from .resource import PrologixResource


@click.group()
def main() -> None:
    """Prologix GPIB-Ethernet command-line interface."""


@main.command()
@click.option(
    "--local-ip",
    default=None,
    metavar="LOCAL_IP",
    help=(
        "IP address of a local network interface to search from "
        "(auto-detected when omitted). Must be an address assigned to this "
        "machine — not a router or remote host."
    ),
)
@click.option(
    "--udp-timeout",
    default=2.0,
    show_default=True,
    help="Seconds to wait for UDP broadcast replies.",
)
@click.option(
    "--tcp-timeout",
    default=0.5,
    show_default=True,
    help="Per-host TCP connect timeout for fallback sweep.",
)
def scan(local_ip: str | None, udp_timeout: float, tcp_timeout: float) -> None:
    """Discover Prologix GPIB-ETHERNET adapters on the local subnet."""
    click.echo("Scanning for Prologix GPIB-ETHERNET adapters...")
    try:
        devices = discover_prologix(
            local_ip=local_ip, udp_timeout=udp_timeout, tcp_timeout=tcp_timeout
        )
    except OSError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    if not devices:
        click.echo("No Prologix adapters found.")
        return

    click.echo(f"Found {len(devices)} adapter(s):\n")
    for dev in devices:
        click.echo(f"  {dev['ip']:<16}  {dev['version']}")


@main.command()
@click.argument("host")
@click.option(
    "-a", "--addr", "gpib_addr",
    required=True, type=int, metavar="GPIB_ADDR",
    help="GPIB address of the instrument (0–30).",
)
@click.option("--timeout", default=5000, show_default=True, help="Read timeout in ms.")
def idn(host: str, gpib_addr: int, timeout: int) -> None:
    """Query *IDN? from a GPIB instrument via a Prologix adapter at HOST."""
    try:
        with PrologixResource(host, gpib_addr, timeout_ms=timeout) as res:
            click.echo(res.query("*IDN?"))
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)


@main.command(name="idn-scan")
@click.argument("host")
@click.option("--start", "addr_start", default=0, show_default=True, type=int,
              help="First GPIB address to probe.")
@click.option("--end", "addr_end", default=30, show_default=True, type=int,
              help="Last GPIB address to probe.")
@click.option("--timeout", default=1.0, show_default=True,
              help="Per-address timeout in seconds.")
def idn_scan(host: str, addr_start: int, addr_end: int, timeout: float) -> None:
    """Scan GPIB addresses on a Prologix adapter at HOST with *IDN?."""
    click.echo(f"Scanning GPIB addresses {addr_start}–{addr_end} on {host}...")
    try:
        results = scan_gpib_idn(
            host, addr_start=addr_start, addr_end=addr_end, per_addr_timeout=timeout
        )
    except OSError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    if not results:
        click.echo("No instruments found.")
        return

    click.echo(f"\nFound {len(results)} instrument(s):\n")
    for r in results:
        click.echo(f"  GPIB {r['addr']:<3}  {r['idn']}")


@main.command()
@click.argument("host")
@click.argument("scpi")
@click.option(
    "-a", "--addr", "gpib_addr",
    required=True, type=int, metavar="GPIB_ADDR",
    help="GPIB address of the instrument (0–30).",
)
@click.option(
    "-q", "--query", "do_query",
    is_flag=True, default=False,
    help="Read a response after sending (for query commands ending in ?).",
)
@click.option("--timeout", default=5000, show_default=True, help="Read timeout in ms.")
def query(host: str, scpi: str, gpib_addr: int, do_query: bool, timeout: int) -> None:
    """Send a raw SCPI command or query. Commands ending in '?' auto-read a response."""
    try:
        with PrologixResource(host, gpib_addr, timeout_ms=timeout) as res:
            if do_query or scpi.strip().endswith("?"):
                click.echo(res.query(scpi))
            else:
                res.write(scpi)
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)


__all__ = ["main", "scan", "idn", "idn_scan", "query"]
