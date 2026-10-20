"""BookForge update check. No window code here.

Asks GitHub for the newest *published* release of BookForge and compares its version with this one.
It only reads the release's version number, notes and web page address: nothing is downloaded, installed
or run. Works the same on Windows, macOS and Linux (Python's own urllib; the certifi certificates are used
when available, so the packaged apps can make secure connections too).
"""
import json
import re
import ssl
import urllib.error
import urllib.request

REPO = "chunksbabyruth/BookForge"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
TIMEOUT = 8


class UpdateError(Exception):
    """A problem checking for updates, with a message meant for the user."""


def parse_version(text):
    """'v1.6.0' / '1.6' / 'BookForge 1.6.1' -> (1, 6, 0) / (1, 6, 0) / (1, 6, 1); None if there's no number."""
    m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text or "")
    if not m:
        return None
    return tuple(int(g or 0) for g in m.groups())


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def _contexts():
    """Secure connection settings to try: certifi's certificates first (packaged apps), then the system's."""
    out = []
    try:
        import certifi
        out.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    out.append(ssl.create_default_context())
    return out


def _get(url, app_version, timeout):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"BookForge/{app_version} (update check)",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    last = None
    for ctx in _contexts():
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read(2_000_000)
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as e:
            last = e
            if isinstance(getattr(e, "reason", None), ssl.SSLError):
                continue                       # try the next set of certificates
            raise
        except ssl.SSLError as e:
            last = e
            continue
    raise last


def fetch_latest(app_version, url=API_URL, timeout=TIMEOUT):
    """The newest published release: {'version', 'tag', 'name', 'url', 'notes', 'date'}.
    Raises UpdateError with a plain message when it can't be found out."""
    try:
        raw = _get(url, app_version, timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("No BookForge releases have been published yet.") from e
        if e.code in (403, 429):
            raise UpdateError("GitHub is limiting how often it can be asked right now. Please try again in "
                              "an hour, or look at the releases page.") from e
        raise UpdateError(f"GitHub answered with an error ({e.code}). Please try again later.") from e
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ssl.SSLError):
            raise UpdateError("A secure connection to GitHub couldn't be made (the computer's security "
                              "certificates may be out of date).") from e
        raise UpdateError("GitHub couldn't be reached. Check your internet connection and try again.") from e
    except (TimeoutError, OSError) as e:
        raise UpdateError("GitHub couldn't be reached. Check your internet connection and try again.") from e
    try:
        data = json.loads(raw.decode("utf-8"))
        tag = str(data.get("tag_name") or "")
    except Exception as e:
        raise UpdateError("GitHub's answer couldn't be read. Please try again later.") from e
    if not parse_version(tag):
        raise UpdateError("The newest release has no version number BookForge understands.")
    page = str(data.get("html_url") or RELEASES_PAGE)
    if not page.startswith("https://github.com/"):
        page = RELEASES_PAGE                   # only ever open GitHub's own pages
    return {"version": ".".join(map(str, parse_version(tag))), "tag": tag, "name": str(data.get("name") or tag),
            "url": page, "notes": str(data.get("body") or "").strip(),
            "date": str(data.get("published_at") or "")[:10]}


def check(app_version, url=API_URL, timeout=TIMEOUT):
    """(newer?, release info) - see fetch_latest."""
    info = fetch_latest(app_version, url, timeout)
    return is_newer(info["tag"], app_version), info


def plain_notes(md, limit=6000):
    """Release notes (Markdown) as readable plain text for the update window."""
    t = (md or "").replace("\r\n", "\n")
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), t)
    t = re.sub(r"(?<!\w)[*_](\S.*?\S|\S)[*_](?!\w)", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", t)
    t = re.sub(r"^\s*[-*+]\s+", "• ", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t if len(t) <= limit else t[:limit].rsplit("\n", 1)[0] + "\n..."
