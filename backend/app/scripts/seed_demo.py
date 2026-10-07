from ..database import initialize
from ..demo import seed_demo


def main():
    info = initialize()
    inserted = seed_demo()
    print(f"Database: {info['database']}")
    print(f"Collections ready: {len(info['collections'])}")
    print(f"Demo records inserted: {inserted}" if inserted else "Seed already exists; skipped")


if __name__ == "__main__":
    main()
