import json
import subprocess
from typing import Any


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return result.stderr.strip()
    return result.stdout.strip()


def main() -> None:
    print("gcloud project:", run(["gcloud", "config", "get-value", "project"]))
    print("gcloud account:", run(["gcloud", "config", "get-value", "account"]))
    token = run(["gcloud", "auth", "application-default", "print-access-token"])
    print("adc access token:", "ok" if token and "ERROR" not in token else token)
    quota = run(["gcloud", "auth", "application-default", "set-quota-project", "relays-cloud"])
    print("quota project set:", quota)
    api = run(
        [
            "gcloud",
            "services",
            "list",
            "--enabled",
            "--filter=vertex-ai.googleapis.com",
            "--format=json",
        ]
    )
    try:
        api_data: list[dict[str, Any]] = json.loads(api)
        print("vertex ai api enabled:", "yes" if api_data else "no")
    except json.JSONDecodeError:
        print("vertex ai api check:", api)


if __name__ == "__main__":
    main()
