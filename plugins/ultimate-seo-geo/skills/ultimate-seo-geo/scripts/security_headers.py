#!/usr/bin/env python3
"""
Check security headers relevant to SEO trust signals.

Validates HTTPS, HSTS, CSP, X-Frame-Options, X-Content-Type-Options,
Referrer-Policy, and Permissions-Policy.

Usage:
    python security_headers.py https://example.com
    python security_headers.py https://example.com --json
"""

import argparse
import json
import sys
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)


SECURITY_HEADERS = {
    "strict-transport-security": {
        "label": "HSTS (Strict-Transport-Security)",
        "weight": 20,
        "description": "Forces browsers to use HTTPS. Prevents downgrade attacks.",
        "recommendation": 'Add header: Strict-Transport-Security: max-age=31536000; includeSubDomains',
    },
    "content-security-policy": {
        "label": "Content-Security-Policy (CSP)",
        "weight": 15,
        "description": "Prevents XSS, clickjacking, and code injection.",
        "recommendation": "Add a Content-Security-Policy header restricting script/style sources.",
    },
    "x-frame-options": {
        "label": "X-Frame-Options",
        "weight": 10,
        "description": "Prevents clickjacking by controlling iframe embedding.",
        "recommendation": "Add header: X-Frame-Options: SAMEORIGIN",
    },
    "x-content-type-options": {
        "label": "X-Content-Type-Options",
        "weight": 10,
        "description": "Prevents MIME-type sniffing.",
        "recommendation": "Add header: X-Content-Type-Options: nosniff",
    },
    "referrer-policy": {
        "label": "Referrer-Policy",
        "weight": 10,
        "description": "Controls how much referrer info is shared.",
        "recommendation": "Add header: Referrer-Policy: strict-origin-when-cross-origin",
    },
    "permissions-policy": {
        "label": "Permissions-Policy",
        "weight": 10,
        "description": "Controls browser feature access (camera, microphone, geolocation).",
        "recommendation": "Add header: Permissions-Policy: camera=(), microphone=(), geolocation=()",
    },
}


def _issue(code: str, severity: str, finding: str, fix: str, evidence: str = "") -> dict:
    """One finding in the shape generate_report.py renders: what is wrong, what shows it, what to do.

    Each code is the one generate_report.py derived from this script's old one-line
    wording, so a --previous run from before the change still matches its findings.
    """
    issue = {"code": code, "severity": severity, "finding": finding, "fix": fix, "confidence": "Confirmed"}
    if evidence:
        issue["evidence"] = evidence
    return issue


def check_security_headers(url: str, timeout: int = 15) -> dict:
    """
    Check security headers for a URL.

    Args:
        url: URL to check
        timeout: Request timeout in seconds

    Returns:
        Dictionary with security header analysis
    """
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)

    result = {
        "url": url,
        "score": 0,
        "https": False,
        "headers_present": {},
        "headers_missing": {},
        "header_values": {},
        "issues": [],
        "recommendations": [],
        "error": None,
    }

    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; UltimateSEO/1.8)"
        }, allow_redirects=True)

        # Check HTTPS
        if resp.url.startswith("https://"):
            result["https"] = True
            result["score"] += 25
        else:
            result["issues"].append(_issue(
                "site-not-using-https", "critical", "Site is not served over HTTPS",
                "Serve every page over HTTPS and 301-redirect each HTTP URL to its HTTPS equivalent.",
                f"Final URL after redirects: {resp.url}"))
            result["recommendations"].append("Migrate to HTTPS and set up 301 redirects from HTTP")

        # Check each security header
        response_headers = {k.lower(): v for k, v in resp.headers.items()}

        for header_key, header_info in SECURITY_HEADERS.items():
            if header_key in response_headers:
                value = response_headers[header_key]
                result["headers_present"][header_info["label"]] = value
                result["header_values"][header_key] = value
                result["score"] += header_info["weight"]

                # Validate HSTS specifics
                if header_key == "strict-transport-security":
                    if "max-age=" in value.lower():
                        try:
                            max_age = int(value.lower().split("max-age=")[1].split(";")[0].strip())
                            if max_age < 31536000:
                                result["issues"].append(_issue(
                                    "hsts-max-age-is-s", "medium", f"HSTS max-age is {max_age}s, under one year",
                                    "Raise it: Strict-Transport-Security: max-age=31536000; includeSubDomains",
                                    f"Strict-Transport-Security: {value}"))
                        except (ValueError, IndexError):
                            result["issues"].append(_issue(
                                "hsts-max-age-invalid", "medium", "HSTS max-age is not a number, so browsers ignore the header",
                                "Set Strict-Transport-Security: max-age=31536000; includeSubDomains",
                                f"Strict-Transport-Security: {value}"))
                    if "includesubdomains" not in value.lower():
                        result["issues"].append(_issue(
                            "hsts-missing-includesubdomains-directive", "medium", "HSTS header has no includeSubDomains directive",
                            "Add includeSubDomains once every subdomain serves HTTPS: "
                            "Strict-Transport-Security: max-age=31536000; includeSubDomains",
                            f"Strict-Transport-Security: {value}"))
            else:
                result["headers_missing"][header_info["label"]] = header_info["description"]
                result["recommendations"].append(
                    f"{header_info['label']}: {header_info['recommendation']}"
                )

        # Cap score at 100
        result["score"] = min(result["score"], 100)

        # Summary issues
        # Missing hardening headers on an HTTPS site is the middle tier of every rubric
        # in references/ (technical-checklist.md, cite-domain-rating.md T02): the failing
        # tier is no HTTPS, which is reported above as critical.
        missing = [(info["label"], info["recommendation"]) for key, info in SECURITY_HEADERS.items()
                   if info["label"] in result["headers_missing"]]
        if missing:
            result["issues"].append(_issue(
                "security-headers-missing", "medium",
                f"{len(missing)} security header(s) missing: {', '.join(label for label, _ in missing)}",
                " ".join(rec if rec.endswith(".") else rec + "." for _, rec in missing),
                "Absent from the response headers of " + resp.url))

    except requests.exceptions.RequestException as e:
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description="Check security headers for SEO")
    parser.add_argument("url", help="URL to check")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    args = parser.parse_args()
    result = check_security_headers(args.url)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result["error"]:
        print(f"Error: {result['error']}")
        sys.exit(1)

    print(f"Security Headers — {result['url']}")
    print("=" * 50)

    # HTTPS status
    https_icon = "✅" if result["https"] else "🔴"
    print(f"{https_icon} HTTPS: {'Yes' if result['https'] else 'No'}")
    print(f"Security Score: {result['score']}/100")

    if result["headers_present"]:
        print(f"\n✅ Present ({len(result['headers_present'])}):")
        for header, value in result["headers_present"].items():
            print(f"  {header}: {value[:80]}")

    if result["headers_missing"]:
        print(f"\n❌ Missing ({len(result['headers_missing'])}):")
        for header, desc in result["headers_missing"].items():
            print(f"  {header}")
            print(f"    → {desc}")

    if result["issues"]:
        print(f"\nIssues:")
        for issue in result["issues"]:
            print(f"  [{issue['severity']}] {issue['finding']}")
            print(f"    Fix: {issue['fix']}")

    if result["recommendations"]:
        print(f"\nRecommendations:")
        for rec in result["recommendations"][:5]:
            print(f"  💡 {rec}")


if __name__ == "__main__":
    main()
