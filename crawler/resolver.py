"""Connection-boundary DNS Resolver for SSRF and DNS Rebinding Prevention.

Validates resolved IP addresses directly at the Twisted network boundary,
ensuring that sockets are never opened to private, loopback, link-local,
or reserved IP addresses even under DNS rebinding attacks.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from scrapy.resolver import CachingThreadedResolver
from twisted.internet import defer
from twisted.internet.base import ReactorBase
from twisted.internet.error import DNSLookupError
from twisted.internet.interfaces import IAddress, IHostResolution, IResolutionReceiver, IResolverSimple
from zope.interface.declarations import implementer

from scraper import is_ip_allowed

logger = logging.getLogger(__name__)


@implementer(IResolverSimple)
class SafeCachingThreadedResolver(CachingThreadedResolver):
    """Twisted DNS Resolver enforcing IP safety policies at socket creation time."""

    def getHostByName(self, name: str, timeout: Sequence[int] = ()) -> defer.Deferred[str]:
        d = super().getHostByName(name, timeout)

        def _verify_ip(ip_str: str) -> str:
            if not is_ip_allowed(ip_str):
                logger.warning(
                    "[Connection Boundary Block] Destination '%s' resolved to forbidden IP (%s)",
                    name,
                    ip_str,
                )
                raise DNSLookupError(
                    f"Connection-boundary SSRF Block: Destination '{name}' resolved to private or restricted IP ({ip_str})"
                )
            return ip_str

        d.addCallback(_verify_ip)
        return d
