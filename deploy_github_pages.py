from pathlib import Path
from urllib.parse import quote
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
API = "https://api.github.com"


def env(name, default=None):
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise SystemExit(f"Missing environment variable: {name}")
    return value


def request(method, path, token, data=None, ok=(200, 201, 202, 204)):
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "viet-ha-memory-deployer",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            text = response.read().decode("utf-8")
            return None if not text else json.loads(text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        if exc.code in ok:
            return None
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code}\n{text}") from exc


def optional_request(method, path, token, data=None):
    try:
        return request(method, path, token, data=data)
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


def repo_exists(owner, repo, token):
    return optional_request("GET", f"/repos/{owner}/{repo}", token) is not None


def create_repo(repo, token, private=False):
    return request("POST", "/user/repos", token, {
        "name": repo,
        "private": private,
        "auto_init": True,
        "description": "Viet Ha memory website",
    })


def get_file_sha(owner, repo, path, token):
    encoded = quote(path, safe="/")
    result = optional_request("GET", f"/repos/{owner}/{repo}/contents/{encoded}?ref=main", token)
    return result.get("sha") if result else None


def upload_file(owner, repo, local_path, repo_path, token):
    content = base64.b64encode(local_path.read_bytes()).decode("ascii")
    data = {
        "message": f"Update {repo_path}",
        "content": content,
        "branch": "main",
    }
    sha = get_file_sha(owner, repo, repo_path, token)
    if sha:
        data["sha"] = sha
    encoded = quote(repo_path, safe="/")
    request("PUT", f"/repos/{owner}/{repo}/contents/{encoded}", token, data=data)


def enable_pages(owner, repo, token):
    data = {"source": {"branch": "main", "path": "/docs"}}
    try:
        request("POST", f"/repos/{owner}/{repo}/pages", token, data=data, ok=(201, 204, 409))
    except RuntimeError as exc:
        if "HTTP 409" not in str(exc):
            raise
        request("PUT", f"/repos/{owner}/{repo}/pages", token, data=data)


def main():
    token = env("GITHUB_TOKEN")
    repo = env("GITHUB_REPO", "viet-ha-memory")
    private = os.environ.get("GITHUB_PRIVATE", "false").lower() == "true"
    user = request("GET", "/user", token)
    owner = os.environ.get("GITHUB_OWNER") or user["login"]

    if not DOCS.exists():
        raise SystemExit("Missing docs directory. Run: python export_static.py")

    if not repo_exists(owner, repo, token):
        if owner != user["login"]:
            raise SystemExit("Repository does not exist. Create org repos manually or set GITHUB_OWNER to your username.")
        create_repo(repo, token, private=private)
        time.sleep(3)

    files = [path for path in DOCS.rglob("*") if path.is_file()]
    for index, path in enumerate(files, 1):
        repo_path = path.relative_to(ROOT).as_posix()
        print(f"[{index}/{len(files)}] {repo_path}")
        upload_file(owner, repo, path, repo_path, token)

    readme = ROOT / "README.md"
    if readme.exists():
        upload_file(owner, repo, readme, "README.md", token)

    enable_pages(owner, repo, token)
    print("")
    print("Deployment complete.")
    print(f"Repository: https://github.com/{owner}/{repo}")
    print(f"Pages:      https://{owner}.github.io/{repo}/")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
