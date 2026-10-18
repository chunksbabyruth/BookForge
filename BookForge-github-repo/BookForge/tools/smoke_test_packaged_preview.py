"""Smoke-test PDF preview rendering in a packaged BookForge executable."""
import os
import subprocess
import sys
import tempfile

from PIL import Image


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_packaged_preview.py PATH_TO_BOOKFORGE_EXECUTABLE")

    executable = os.path.abspath(sys.argv[1])
    if not os.path.isfile(executable):
        raise SystemExit(f"Packaged executable not found: {executable}")

    with tempfile.TemporaryDirectory(prefix="bookforge-preview-smoke-") as temp:
        source = os.path.join(temp, "preview-smoke.txt")
        output = os.path.join(temp, "preview-smoke.png")
        with open(source, "w", encoding="utf-8") as f:
            f.write(
                "BookForge Preview Smoke Test\n\n"
                "Chapter 1: A Small Test\n\n"
                "This sample verifies that the packaged application can build a "
                "preview PDF and render the first page to an image on this OS.\n"
            )

        result = subprocess.run(
            [executable, "--preview-check", source, output],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(
                f"Packaged preview smoke test failed with exit code {result.returncode}."
            )

        if not os.path.isfile(output) or os.path.getsize(output) < 1000:
            raise SystemExit("Preview smoke test did not create a valid-sized PNG.")

        with Image.open(output) as image:
            image.verify()
        with Image.open(output) as image:
            width, height = image.size
            if width < 100 or height < 100:
                raise SystemExit(f"Preview image is unexpectedly small: {width}x{height}")
            print(f"PASS: packaged preview rendered {width}x{height} PNG on this OS.")


if __name__ == "__main__":
    main()
