#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import time


USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ

COLORS = {
    "reset": "\033[0m",
    "cyan": "\033[96m",
    "blue": "\033[94m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
}


def show(message, color="cyan"):
    prefix = COLORS[color] if USE_COLOR else ""
    suffix = COLORS["reset"] if USE_COLOR else ""
    print(f"{prefix}{message}{suffix}", flush=True)


def main():
    if not sys.platform.startswith("linux"):
        show("This program requires Linux.", "red")
        return 1

    if os.geteuid() != 0:
        show(
            "Please Run with sudo",
            "red",
        )
        return 1

    apt = shutil.which("apt")
    if apt is None:
        show("apt was not found in PATH.", "red")
        return 1

    steps = [
        ("Refresh package lists", [apt, "update"]),
        ("Upgrade the system", [apt, "full-upgrade", "-y"]),
        ("Remove unused dependencies", [apt, "autoremove", "-y"]),
    ]

    show("\n=== Kali Linux Post-Installation ===", "cyan")
    show(
        "Upgrades and cleanup may remove packages.",
        "yellow",
    )
    started = time.monotonic()

    try:
        for number, (title, command) in enumerate(steps, start=1):
            show(f"\n[{number}/{len(steps)}] {title}", "blue")
            show(f"$ {' '.join(command)}", "cyan")

            subprocess.run(command, check=True)

            show(f"{title}", "green")

    except subprocess.CalledProcessError as exc:
        show(
            f"\n Command exited with code {exc.returncode}. "
            "Remaining steps were not run.",
            "red",
        )
        return exc.returncode if exc.returncode > 0 else 1

    except KeyboardInterrupt:
        show(
            "\n Interrupted. Remaining steps were not run.",
            "yellow",
        )
        return 130

    except OSError as exc:
        show(f"\n Could not execute command: {exc}", "red")
        return 1

    elapsed = time.monotonic() - started
    show(f"\n All three tasks completed in {elapsed:.1f}s.", "green")
    return 0


if __name__ == "__main__":
    sys.exit(main())