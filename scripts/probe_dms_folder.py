"""Probe DMS SharePoint folder listing and download mechanisms."""

import re
import sys
from pathlib import Path

import requests
from requests_negotiate_sspi import HttpNegotiateAuth

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FOLDER_1405 = (
    "https://dms.orchidpharmed.com/OneDrive/Supply%20Chain/"
    "Supply%20Chain%20Team_DMS/%D8%AA%D8%AD%D9%88%DB%8C%D9%84%20%D8%A8%D9%87%20%"
    "D9%BE%D8%AE%D8%B4%20%D9%87%D8%A7%20.49/1405"
)
BASE = "https://dms.orchidpharmed.com"


def main() -> None:
    auth = HttpNegotiateAuth()

    rest_candidates = [
        (
            BASE
            + "/OneDrive/_api/web/GetFolderByServerRelativeUrl("
            + "'/OneDrive/Supply Chain/Supply Chain Team_DMS/"
            + "\u062a\u062d\u0648\u06cc\u0644 \u0628\u0647 \u067e\u062e\u0634 \u0647\u0627 .49/1405')"
            + "/Files"
        ),
        FOLDER_1405 + "/_api/web/lists",
    ]

    print("=== REST API probes ===")
    for url in rest_candidates:
        try:
            response = requests.get(
                url,
                auth=auth,
                headers={"Accept": "application/json;odata=verbose"},
                timeout=30,
            )
            print(f"status={response.status_code} url={url[:90]}...")
            if response.status_code == 200:
                print(response.text[:800])
        except Exception as exc:
            print(f"error: {exc}")
        print()

    print("=== HTML folder page ===")
    response = requests.get(FOLDER_1405, auth=auth, timeout=30)
    print(f"status={response.status_code} length={len(response.text)}")
    html = response.text

    for pattern_name, pattern in [
        ("xlsx_href", r'href="([^"]+\.xlsx)"'),
        ("file_ref", r"FileRef['\"]?\s*[:=]\s*['\"]([^'\"]+)"),
        ("listdata", r"ListData\s*=\s*(\{)"),
        ("download_aspx", r"download\.aspx[^\"']+"),
    ]:
        matches = re.findall(pattern, html, re.I)
        print(f"{pattern_name}: {len(matches)} matches")
        for match in matches[:3]:
            line = str(match)[:150]
            sys.stdout.buffer.write((f"  {line}\n").encode("utf-8", errors="replace"))

    ctx_match = re.search(r"ctx\.ListData\s*=\s*(\{.*?\});", html, re.S)
    if ctx_match:
        snippet = ctx_match.group(1)[:2000]
        sys.stdout.buffer.write(b"ctx.ListData snippet:\n")
        sys.stdout.buffer.write(snippet.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")

    print("\n=== Download test ===")
    hrefs = re.findall(r'href="([^"]+\.xlsx)"', html, re.I)
    if hrefs:
        test_href = hrefs[0]
        if test_href.startswith("/"):
            download_url = BASE + test_href
        elif test_href.startswith("http"):
            download_url = test_href
        else:
            download_url = FOLDER_1405.rsplit("/", 1)[0] + "/" + test_href
        dl = requests.get(download_url, auth=auth, timeout=60)
        print(f"download status={dl.status_code} bytes={len(dl.content)}")
        print(f"content-type={dl.headers.get('Content-Type', '')}")


if __name__ == "__main__":
    main()
