from __future__ import annotations

from typing import Dict, Optional

from browser_cookies_windows import find_default_profile, read_hoyolab_tokens_from_profile, taskkill_browser


def mask(v: str) -> str:
    if not v:
        return "(empty)"
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:4]}...{v[-4:]}"


def pause_exit(enabled: bool) -> None:
    if not enabled:
        return
    try:
        input("Press Enter to exit...")
    except (EOFError, KeyboardInterrupt):
        pass


def _load_hoyolab_tokens_from_default_profile(browser: str, profile_directory: Optional[str], kill_browser: bool) -> Dict[str, str]:
    prof = find_default_profile(browser, profile_directory)
    print(f"browser: {prof.name}")
    print(f"user-data-dir: {prof.user_data_dir}")
    print(f"profile-directory: {prof.profile_dir}")
    if kill_browser:
        print(f"taskkill: closing {prof.name} to avoid cookie DB lock...")
        taskkill_browser(prof.name)
    return read_hoyolab_tokens_from_profile(prof)


def run_cookie_grab(
    *,
    url: str,
    browser: str,
    profile_directory: Optional[str],
    use_default_profile: bool,
    headless: bool,
    raw: bool,
    pause: bool,
    kill_browser: bool,
) -> int:
    try:
        if not use_default_profile:
            print("ERROR: --no-default-profile is no longer supported in this build (offline cookie read).")
            pause_exit(pause)
            return 1

        if headless:
            print("Note: headless is ignored (offline cookie read).")

        print("== HoYoLAB cookie grabber (offline) ==")
        print(f"target url (for reference): {url}")

        values = _load_hoyolab_tokens_from_default_profile(browser, profile_directory, kill_browser)

        print("\nCookie values:")
        for k in ["LTUID", "LTOKEN", "COOKIE_TOKEN_V2"]:
            v = values.get(k, "")
            print(f"- {k}: {v if raw else mask(v)}")
        print("\nNOTE: This tool does not save secrets to disk; it only prints them.")
        pause_exit(pause)
        return 0
    except Exception as e:
        print(f"\nERROR: {e}")
        pause_exit(pause)
        return 1
