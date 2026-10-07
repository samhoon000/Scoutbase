import asyncio
from ..config import settings
from ..diagnostics import provider_status


def main():
    print(f"Database name: {settings.database_name}")
    print(f"Demo mode: {settings.demo_mode}")
    for name, status in asyncio.run(provider_status()).items():
        print(f"{name}: {status}")


if __name__ == "__main__":
    main()
