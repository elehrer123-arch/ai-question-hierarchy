#!/usr/bin/env python3
"""Sampled external-link checker. Not run at build time (external URLs have
transient failures); run manually or from the weekly discovery session:
    python3 scripts/linkcheck.py [N]
Checks N random stream URLs (default 40) and reports non-2xx/3xx results."""
import json, random, sys, urllib.request

n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
data = json.load(open("data/recent.json"))
urls = sorted({it["url"] for q in data["questions"].values()
               for it in q.get("items", []) + q.get("ledger", [])})
sample = random.sample(urls, min(n, len(urls)))
bad = []
for u in sample:
    try:
        req = urllib.request.Request(u, method="HEAD",
                                     headers={"User-Agent": "Mozilla/5.0 (link check)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                bad.append((u, resp.status))
    except Exception as e:
        bad.append((u, str(e)[:60]))
print(f"checked {len(sample)} of {len(urls)} URLs; {len(bad)} problems")
for u, why in bad:
    print(" -", u, "|", why)
