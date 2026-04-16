from lineup_bot import run_check as run_lineup_check
from pitcher_bot import run_check as run_pitcher_check


def main():
    try:
        print("Running lineup bot...")
        run_lineup_check()
    except Exception as e:
        print(f"Lineup bot failed: {e}")

    try:
        print("Running pitcher bot...")
        run_pitcher_check()
    except Exception as e:
        print(f"Pitcher bot failed: {e}")


if __name__ == "__main__":
    main()
