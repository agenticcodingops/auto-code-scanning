#!/usr/bin/env python3
"""Report hand-kept pins; never edit pins, merge PRs, or close issues (Python 3.11+)."""
import argparse
from datetime import datetime, timedelta, timezone
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from safe_io import assert_safe_path

MARKER = "<!-- pin-freshness:rolling-report:v1 -->"
REPORT_AUTHOR = "github-actions[bot]"
API = "https://api.github.com"
VERSION = re.compile(r"v?(\d+(?:\.\d+)*)(?:\+[0-9A-Za-z.-]+)?$")
REPOSITORY = re.compile(r"[\w.-]+/[\w.-]+$")


def version(value):
    """Stable numeric releases only; reject prereleases rather than misorder them."""
    match = VERSION.fullmatch(value.strip())
    if not match:
        raise ValueError(f"unsupported stable version: {value}")
    parts = [int(part) for part in match[1].split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def normalized(value):
    # Python prerequisite constants use tuples; minimum spellings may omit patch zero.
    return re.sub(r",\s*", ".", value.strip().rstrip(", "))


def safe_file(root, relative):
    """Only literal checkout-relative files, with no links/reparse points."""
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("file must be a POSIX relative path")
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(p in {"..", ".git"} or ":" in p for p in path.parts):
        raise ValueError("file must stay inside the checkout")
    root = assert_safe_path(root).resolve()
    result = assert_safe_path(root / relative)
    result.resolve().relative_to(root)
    if not result.is_file():
        raise ValueError(f"not a regular file: {relative}")
    return result


def load_manifest(root, relative):
    data = json.loads(safe_file(root, relative).read_text(encoding="utf-8"))
    if set(data) - {"$schema", "pins"} or not isinstance(data.get("pins"), list) or not data["pins"]:
        raise ValueError("manifest requires a nonempty pins array")
    ids = set()
    for pin in data["pins"]:
        if not isinstance(pin, dict) or set(pin) - {
            "id", "locations", "source", "policy", "precondition", "review_reason", "mirrors"
        }:
            raise ValueError("invalid pin entry")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", pin.get("id", "")) or pin["id"] in ids:
            raise ValueError("pin ids must be unique lowercase identifiers")
        ids.add(pin["id"])
        if pin.get("policy", "exact") not in {"exact", "minimum", "manual"}:
            raise ValueError(f"{pin['id']}: invalid policy")
        if pin.get("policy") == "manual" and not pin.get("review_reason"):
            raise ValueError("manual entries require review_reason")
        if not isinstance(pin.get("locations"), list) or not pin["locations"]:
            raise ValueError("each pin requires locations")
        mirror_locations = []
        for mirror in pin.get("mirrors", []):
            if set(mirror) != {"id", "locations"} or not re.fullmatch(r"[a-z0-9-]+", mirror["id"]):
                raise ValueError("invalid integrity mirror")
            if not isinstance(mirror["locations"], list) or not mirror["locations"]:
                raise ValueError("integrity mirrors require locations")
            mirror_locations.extend(mirror["locations"])
        for location in pin["locations"] + mirror_locations:
            if set(location) != {"file", "pattern"} or not isinstance(location["file"], str):
                raise ValueError("locations require file and pattern")
            pattern = re.compile(location["pattern"], re.MULTILINE)
            if "value" not in pattern.groupindex:
                raise ValueError("patterns require a named value group")
        source = pin.get("source", {})
        if source.get("type") in {"github_releases", "github_tags"}:
            if set(source) - {"type", "repo", "tag_pattern"} or not REPOSITORY.fullmatch(source.get("repo", "")):
                raise ValueError("invalid upstream repository")
            pattern = re.compile(source.get("tag_pattern", r"v?(?P<version>\d+(?:\.\d+)*)"))
            if "version" not in pattern.groupindex:
                raise ValueError("tag patterns require a named version group")
        elif source.get("type") == "pypi":
            if set(source) != {"type", "package"} or not re.fullmatch(r"[\w.-]+", source.get("package", "")):
                raise ValueError("invalid PyPI package")
        else:
            raise ValueError("unsupported upstream source")
    return data["pins"]


def extract(root, pin):
    values, failures = [], []
    for location in pin["locations"]:
        try:
            text = safe_file(root, location["file"]).read_text(encoding="utf-8")
            matches = list(re.finditer(location["pattern"], text, re.MULTILINE))
            if not matches:
                raise ValueError("pattern matched no values")
            for match in matches:
                value = normalized(match["value"])
                if not value:
                    raise ValueError("pattern extracted an empty value")
                values.append((location["file"], text.count("\n", 0, match.start("value")) + 1, value))
        except (OSError, ValueError, UnicodeError, re.error) as exc:
            # Path names are manifest-relative; OS exception text may expose a local path.
            failures.append(f"{pin['id']} ({location['file']}): {type(exc).__name__}: extraction failed" +
                            (f" ({exc})" if isinstance(exc, ValueError) else ""))
    return values, failures


def http_reason(exc):
    # The API's own message says why (rate limit, access policy); the status code alone does not.
    try:
        message = json.loads(exc.read(4096).decode("utf-8", errors="replace")).get("message")
    except (OSError, ValueError, AttributeError):
        return ""
    return f" ({' '.join(str(message).split())[:200]})" if message else ""


class Client:
    def __init__(self, token):
        self.token = token
        self.cache = {}

    def request(self, url, method="GET", data=None, anonymous=False):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc not in {"api.github.com", "pypi.org"}:
            raise ValueError("unsupported API origin")
        headers = {"User-Agent": "pin-freshness", "Accept": "application/json"}
        if parsed.netloc == "api.github.com":
            headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
            if self.token and not anonymous:
                headers["Authorization"] = f"Bearer {self.token}"
        payload = None if data is None else json.dumps(data).encode("utf-8")
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        # Do not forward the GitHub credential across redirects, including future API redirects.
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            reason = http_reason(exc)
            # An upstream org's IP allow list rejects tokens from hosted runners even for its public
            # repositories; an anonymous read is not subject to it and can reach only public data.
            if (exc.code == 403 and "IP allow list" in reason and method == "GET" and data is None
                    and self.token and not anonymous):
                return self.request(url, method, data, anonymous=True)
            raise ValueError(f"{parsed.netloc}: HTTP {exc.code}{reason}") from None
        except urllib.error.URLError:
            raise ValueError(f"{parsed.netloc}: network lookup failed") from None

    def pages(self, path):
        rows = []
        for page in range(1, 101):
            separator = "&" if "?" in path else "?"
            batch = self.request(f"{API}{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise ValueError("expected an API list")
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise ValueError("API pagination exceeded 100 pages; result is incomplete")

    def upstream(self, source):
        key = json.dumps(source, sort_keys=True)
        if key in self.cache:
            cached = self.cache[key]
            if isinstance(cached, Exception):
                raise cached
            return cached
        try:
            result = self._upstream(source)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.cache[key] = exc
            raise
        self.cache[key] = result
        return result

    def _upstream(self, source):
        candidates, revisions = [], {}
        if source["type"] == "pypi":
            package = source["package"]
            data = self.request(f"https://pypi.org/pypi/{package}/json")
            for name, files in data["releases"].items():
                if files and any(not f.get("yanked", False) for f in files):
                    try:
                        candidates.append((version(name), name, f"https://pypi.org/project/{package}/{name}/"))
                    except ValueError:
                        continue  # prerelease/non-numeric releases are deliberately excluded
        else:
            repo = source["repo"]
            kind = "releases" if source["type"] == "github_releases" else "tags"
            pattern = re.compile(source.get("tag_pattern", r"v?(?P<version>\d+(?:\.\d+)*)"))
            for row in self.pages(f"/repos/{repo}/{kind}"):
                if row.get("draft") or row.get("prerelease"):
                    continue
                tag = row["tag_name"] if kind == "releases" else row["name"]
                match = pattern.fullmatch(tag)
                if not match:
                    continue
                name = match["version"]
                try:
                    parsed = version(name)
                except ValueError:
                    continue
                route = "releases/tag" if kind == "releases" else "tree"
                url = f"https://github.com/{repo}/{route}/{urllib.parse.quote(tag, safe='')}"
                candidates.append((parsed, name, url))
                if kind == "tags":
                    sha = row["commit"]["sha"]
                    # Major aliases and exact tags can identify the same commit.
                    if sha not in revisions or version(revisions[sha]) < parsed:
                        revisions[sha] = name
        if not candidates:
            raise ValueError("no stable numeric upstream releases found")
        latest = max(candidates)
        return latest[1], latest[2], revisions


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def stale_prs(client, repository, now):
    result = []
    for pr in client.pages(f"/repos/{repository}/pulls?state=open"):
        labels = {label["name"].lower() for label in pr["labels"]}
        login = pr["user"]["login"].lower()
        dependency = "dependencies" in labels or login in {
            "dependabot[bot]", "dependabot-preview[bot]", "renovate[bot]", "dependabot", "renovate",
            "app/dependabot", "app/renovate"
        }
        created = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
        if dependency and now - created > timedelta(days=7):
            result.append(pr)
    return sorted(result, key=lambda pr: pr["created_at"])


def md(value):
    # Upstream titles and manifest notes must not inject HTML, links or mentions into the issue.
    value = html.escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    return re.sub(r"([\\`*_[\]#|@])", r"\\\1", value)


def drift_line(label, observed, keep=3):
    # Group repeated locations by value so one stray copy stands out; summarize only the largest group.
    groups = {}
    for file, line, value in dict.fromkeys(observed):
        groups.setdefault(value, []).append(f"{md(file)}:{line}")
    majority = max(groups, key=lambda value: len(groups[value]))
    parts = []
    for value, places in groups.items():
        if value == majority and len(places) > keep:
            parts.append(f"{len(places)} locations = {md(value)} (for example {places[0]})")
        else:
            parts.extend(f"{place} = {md(value)}" for place in places)
    return f"- **{md(label)}**: " + "; ".join(parts)


def ordered(values):
    # Numeric order for readers; the raw string breaks ties such as 1.0 and 1.0.0 deterministically.
    return sorted(values, key=lambda value: (version(value), value))


def report(root, pins, client, repository, now):
    outdated, drift, failures, manual, floors = [], [], [], [], []
    for pin in pins:
        for mirror in pin.get("mirrors", []):
            observed, errors = extract(root, {**mirror, "id": pin["id"] + "/" + mirror["id"]})
            failures.extend(errors)
            if len({value for _, _, value in observed}) > 1:
                drift.append(drift_line(f"{pin['id']}/{mirror['id']}", observed))
        values, errors = extract(root, pin)
        failures.extend(errors)
        raw = {item[2] for item in values}
        def record_drift(distinct):
            if len(distinct) > 1:
                drift.append(drift_line(pin["id"], values))
        policy = pin.get("policy", "exact")
        note = f" Precondition: {md(pin['precondition'])}" if pin.get("precondition") else ""
        if policy == "manual":
            record_drift(raw)
            manual.append(f"- **{pin['id']}**: {md(pin['review_reason'])}.{note}")
            continue
        try:
            latest, url, revisions = client.upstream(pin["source"])
            current = set()
            for value in raw:
                if re.fullmatch(r"[0-9a-f]{40}", value):
                    if value not in revisions:
                        raise ValueError("pinned commit has no stable upstream tag")
                    value = revisions[value]
                current.add(value)
            record_drift({version(value) for value in current})
            old = ordered(value for value in current if version(value) < version(latest))
            if policy == "minimum":
                floors.append(f"- **{pin['id']}**: minimum {md(', '.join(ordered(current)))}; "
                              f"[latest {md(latest)}]({url}). Compatibility decision; no automatic bump.{note}")
            elif old:
                outdated.append(f"- **{pin['id']}**: {md(', '.join(old))} → **{md(latest)}** "
                                f"([release]({url})).{note}")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            # Still surface local disagreement if upstream is unavailable.
            numeric = {version(value) for value in raw if VERSION.fullmatch(value)}
            hashes = {value for value in raw if re.fullmatch(r"[0-9a-f]{40}", value)}
            record_drift(numeric if numeric else hashes)
            failures.append(f"{pin['id']}: {type(exc).__name__}: {exc}")
    try:
        stale = [f"- [#{pr['number']}]({pr['html_url']}) {md(pr['title'])} — opened {md(pr['created_at'])}"
                 for pr in stale_prs(client, repository, now)]
    except (ValueError, OSError, KeyError, TypeError) as exc:
        failures.append(f"dependency PR lookup: {type(exc).__name__}: {exc}")
        stale = []
    lines = [MARKER, "# Pin freshness", "", f"Checked {now.strftime('%Y-%m-%d %H:%M:%S UTC')}; "
             f"{len(pins)} manifest entries.", "", "Report only: review release notes and preconditions before changing pins."]
    for title, rows in [("Outdated pins", outdated), ("Cross-file drift", drift),
                        ("Lookup and extraction failures", [f"- {md(f)}" for f in failures]),
                        ("Dependency-update PRs open longer than 7 days", stale),
                        ("Compatibility floors", floors), ("Manual review selections", manual)]:
        lines.extend(["", f"## {title}", "", *(rows or ["None."])])
    return "\n".join(lines) + "\n", bool(failures)


def upsert_issue(client, repository, title, body, author=REPORT_AUTHOR):
    creator = urllib.parse.quote(author, safe="")
    issues = [issue for issue in client.pages(f"/repos/{repository}/issues?state=all&creator={creator}")
              if "pull_request" not in issue
              and (issue.get("user") or {}).get("login") == author
              and MARKER in (issue.get("body") or "").splitlines()]
    if len(issues) > 1:
        raise ValueError("multiple rolling-issue markers found; refusing an ambiguous update")
    payload = {"title": title, "body": body}
    if issues:
        # Preserve open/closed state; never close or reopen an operator-managed issue.
        return client.request(f"{API}/repos/{repository}/issues/{issues[0]['number']}", "PATCH", payload)
    return client.request(f"{API}/repos/{repository}/issues", "POST", payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=".github/pin-freshness.json")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--issue-title", default="Weekly pin freshness")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        if not REPOSITORY.fullmatch(args.repository):
            raise ValueError("--repository must be owner/repo")
        pins = load_manifest(args.root, args.manifest)
        client = Client(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", ""))
        body, failed = report(args.root, pins, client, args.repository, datetime.now(timezone.utc))
        print(body, end="")
        if not args.dry_run:
            if not client.token:
                raise ValueError("GITHUB_TOKEN is required to write the rolling issue")
            author = REPORT_AUTHOR
            if os.environ.get("GITHUB_ACTIONS") != "true":
                # A local personal token creates user-owned issues, not workflow-bot issues.
                author = client.request(f"{API}/user")["login"]
                if not isinstance(author, str) or not re.fullmatch(r"[\w-]+(?:\[bot\])?", author):
                    raise ValueError("cannot determine the authenticated issue author")
            upsert_issue(client, args.repository, args.issue_title, body, author=author)
        return 1 if failed else 0
    except (OSError, ValueError, KeyError, TypeError, re.error) as exc:
        print(f"pin freshness failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
