#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


TARGETS = (
    "sleep.target",
    "suspend.target",
    "hibernate.target",
    "hybrid-sleep.target",
    "suspend-then-hibernate.target",
)

CONFIG_PATH = Path("/etc/systemd/sleep.conf.d/99-disable-sleep.conf")

CONFIG_TEXT = (
    "[Sleep]\n"
    "AllowSuspend=no\n"
    "AllowHibernation=no\n"
    "AllowHybridSleep=no\n"
    "AllowSuspendThenHibernate=no\n"
)

VMWARE_SETTING = 'suspend.disabled = "TRUE"'


class Console:
    COLORS = {
        "cyan": "\033[36m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "red": "\033[31m",
        "dim": "\033[2m",
        "reset": "\033[0m",
    }

    def __init__(self, enabled):
        self.enabled = enabled

    def write(self, text="", color=None, stream=None):
        stream = stream or sys.stdout
        if self.enabled and color:
            text = f"{self.COLORS[color]}{text}{self.COLORS['reset']}"
        print(text, file=stream, flush=True)

    def step(self, number, title):
        self.write(f"\n[{number}/4] {title}", "cyan")

    def success(self, text):
        self.write(f"Done {text}", "green")

    def warning(self, text):
        self.write(f"Warning {text}", "yellow")

    def error(self, text):
        self.write(f"Error {text}", "red", stream=sys.stderr)


def run_command(arguments):
    result = subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"Exit status: {result.returncode}"
        )
        raise RuntimeError(
            f"Command failed: {' '.join(arguments)}\n{details}"
        )
    return result


def preflight():
    if sys.platform != "linux":
        raise RuntimeError("Run this program inside the Kali Linux guest.")

    if os.geteuid() != 0:
        raise RuntimeError(
            "Administrator privileges are required.\n"
            "Run: sudo python3 Force_disable_sleep.py"
        )

    if shutil.which("systemctl") is None:
        raise RuntimeError("systemctl was not found.")

    if not Path("/run/systemd/system").is_dir():
        raise RuntimeError("A running systemd environment was not detected.")

    if CONFIG_PATH.is_symlink():
        raise RuntimeError(
            f"Refusing to replace a symbolic link: {CONFIG_PATH}"
        )

    if CONFIG_PATH.exists() and not CONFIG_PATH.is_file():
        raise RuntimeError(
            f"The configuration path is not a regular file: {CONFIG_PATH}"
        )


def write_drop_in(console):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if CONFIG_PATH.exists():
        if CONFIG_PATH.read_bytes() == CONFIG_TEXT.encode("utf-8"):
            console.success("The requested drop-in already exists unchanged.")
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = CONFIG_PATH.with_name(
            f"{CONFIG_PATH.name}.{timestamp}.bak"
        )
        shutil.copy2(CONFIG_PATH, backup)
        console.success(f"Existing configuration backed up to: {backup}")

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CONFIG_PATH.parent,
            prefix=".disable-sleep-",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(CONFIG_TEXT)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        temporary_path.chmod(0o644)
        os.replace(temporary_path, CONFIG_PATH)
        console.success(f"Configuration written to: {CONFIG_PATH}")

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    for line in CONFIG_TEXT.splitlines():
        console.write(f"    {line}", "dim")


def verify(console):
    failures = []

    for target in TARGETS:
        result = subprocess.run(
            ["systemctl", "show", target, "--property=LoadState", "--value"],
            capture_output=True,
            text=True,
            check=False,
        )

        state = result.stdout.strip() or "unknown"

        if result.returncode == 0 and state == "masked":
            console.success(f"{target:<32} masked")
        else:
            detail = result.stderr.strip()
            console.error(
                f"{target:<32} {state}"
                + (f" — {detail}" if detail else "")
            )
            failures.append(target)

    if CONFIG_PATH.read_bytes() == CONFIG_TEXT.encode("utf-8"):
        console.success("Drop-in contents match the requested configuration.")
    else:
        failures.append(str(CONFIG_PATH))
        console.error("Drop-in contents do not match.")

    if failures:
        raise RuntimeError(
            "Verification failed for: " + ", ".join(failures)
        )


def show_vmware_instructions(console):
    console.step(4, "VMware host-side instructions")
    console.warning(
        "The guest script does not modify the host's .vmx file."
    )

    instructions = (
        "1. Shut down Kali completely; do not suspend the VM.",
        "2. Locate the VM folder on the host.",
        "3. Back up the VM's .vmx file.",
        "4. Open the original .vmx file in a text editor.",
        "5. Add the following line, or update its existing occurrence:",
    )

    for instruction in instructions:
        console.write(f"    {instruction}")

    console.write(f"\n       {VMWARE_SETTING}\n", "cyan")
    console.write("    6. Save the .vmx file and start the VM again.")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Mask systemd sleep targets, write the requested sleep "
            "configuration, and verify the result."
        )
    )
    colors = parser.add_mutually_exclusive_group()
    colors.add_argument(
        "--color",
        action="store_true",
        help="Force ANSI color output.",
    )
    colors.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output.",
    )
    args = parser.parse_args()

    use_color = not args.no_color and (
        args.color
        or (sys.stdout.isatty() and "NO_COLOR" not in os.environ)
    )
    console = Console(use_color)

    console.write("=" * 64, "cyan")
    console.write("Kali Linux Guest | Disable Suspend and Hibernation", "cyan")
    console.write("=" * 64, "cyan")

    try:
        preflight()

        console.step(1, "Block the five systemd sleep targets")
        console.write(
            "$ systemctl mask " + " ".join(TARGETS),
            "dim",
        )
        result = run_command(["systemctl", "mask", *TARGETS])

        for output in (result.stdout.strip(), result.stderr.strip()):
            if output:
                console.write(output, "dim")

        console.success("Target masking command completed.")

        console.step(2, "Create the sleep configuration drop-in")
        write_drop_in(console)

        console.step(3, "Verify target states and configuration")
        verify(console)

        show_vmware_instructions(console)

        console.write()
        console.success("All requested guest-side checks passed.")
        console.write(
            "No suspend test, shutdown, or reboot was performed.",
            "dim",
        )
        return 0

    except (OSError, RuntimeError) as exc:
        console.error(str(exc))
        console.warning(
            "The procedure stopped. Any changes already completed remain "
            "in place; automatic rollback was not performed."
        )
        return 1

    except KeyboardInterrupt:
        console.warning(
            "\nInterrupted. Any changes already completed remain in place."
        )
        return 130


if __name__ == "__main__":
    sys.exit(main())