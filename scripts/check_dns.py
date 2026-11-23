#!/usr/bin/env python3
"""Check whether each configured hostname has at least one DNS record."""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import dns.exception
import dns.resolver

CONFIG = Path(__file__).resolve().parents[1] / "sites.json"
RECORD_TYPES = ("A", "AAAA", "CNAME")


def load_hosts():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    hosts = set()
    for url in data.get("urls", []):
        host = urlparse(url).hostname
        if host:
            hosts.add(host.rstrip(".").lower())
    return sorted(hosts)


def check_host(host, resolver):
    found = []
    errors = []
    for record_type in RECORD_TYPES:
        try:
            answer = resolver.resolve(
                host, record_type, lifetime=5, raise_on_no_answer=False
            )
            if answer.rrset is not None:
                values = [item.to_text() for item in answer]
                found.append((record_type, values))
        except dns.resolver.NoAnswer:
            continue
        except dns.resolver.NXDOMAIN:
            errors.append(f"{record_type}: NXDOMAIN")
            break
        except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
            errors.append(f"{record_type}: {type(exc).__name__}")
        except dns.exception.DNSException as exc:
            errors.append(f"{record_type}: {type(exc).__name__}")

    return found, errors


def main():
    resolver = dns.resolver.Resolver()
    resolver.timeout = 3
    resolver.lifetime = 5

    hosts = load_hosts()
    if not hosts:
        print("No valid hostnames found in sites.json.", file=sys.stderr)
        return 2

    failed = []
    print(f"Checking {len(hosts)} unique hostnames; any A, AAAA, or CNAME record counts.\n")
    for host in hosts:
        records, errors = check_host(host, resolver)
        if records:
            summary = "; ".join(
                f"{kind}={', '.join(values)}" for kind, values in records
            )
            print(f"[OK]   {host}: {summary}")
        else:
            detail = "; ".join(errors) if errors else "no A, AAAA, or CNAME records"
            print(f"[FAIL] {host}: {detail}")
            failed.append(host)

    print(f"\nResult: {len(hosts) - len(failed)}/{len(hosts)} hostnames have DNS records.")
    if failed:
        print("Hostnames needing attention: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
