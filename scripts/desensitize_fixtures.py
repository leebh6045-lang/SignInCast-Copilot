"""Mask personal data in recorded fixtures (run after `--record`, before commit)."""

from pathlib import Path

from app.business.desensitize import desensitize_dir


def main() -> None:
    count = desensitize_dir(Path("data/fixtures/http"))
    print(f"已脱敏 {count} 个 fixture")


if __name__ == "__main__":
    main()
