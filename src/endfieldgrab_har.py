import argparse
import json
from pathlib import Path


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


def _iter_har_request_headers(har: dict) -> list[dict[str, str]]:
    # Return list of {header_name_lower: value} for each request in HAR.
    out: list[dict[str, str]] = []
    entries = (((har or {}).get("log") or {}).get("entries")) or []
    if not isinstance(entries, list):
        return out

    for ent in entries:
        req = (ent or {}).get("request") or {}
        headers = req.get("headers") or []
        if not isinstance(headers, list):
            continue
        m: dict[str, str] = {}
        for h in headers:
            if not isinstance(h, dict):
                continue
            n = str(h.get("name", "")).strip()
            v = str(h.get("value", "")).strip()
            if n:
                m[n.lower()] = v
        if m:
            out.append(m)
    return out


def extract_endfield_headers_from_har(har: dict) -> dict[str, str]:
    """
    Best-effort extract for:
    - ENDFIELD_CRED from request header "cred"
    - ENDFIELD_SK_GAME_ROLE from request header "sk-game-role"
    - optional ENDFIELD_PLATFORM from "platform"
    - optional ENDFIELD_VNAME from "vname"
    """
    headers_list = _iter_har_request_headers(har)

    best: dict[str, str] = {"ENDFIELD_CRED": "", "ENDFIELD_SK_GAME_ROLE": "", "ENDFIELD_PLATFORM": "", "ENDFIELD_VNAME": ""}
    for h in headers_list:
        cred = h.get("cred", "")
        role = h.get("sk-game-role", "")
        plat = h.get("platform", "")
        vname = h.get("vname", "") or h.get("vName".lower(), "")
        score = 0
        if cred:
            score += 2
        if role:
            score += 2
        if plat:
            score += 1
        if vname:
            score += 1

        # Prefer entries that have both cred and role.
        best_score = 0
        if best["ENDFIELD_CRED"]:
            best_score += 2
        if best["ENDFIELD_SK_GAME_ROLE"]:
            best_score += 2
        if best["ENDFIELD_PLATFORM"]:
            best_score += 1
        if best["ENDFIELD_VNAME"]:
            best_score += 1

        if score > best_score:
            best = {
                "ENDFIELD_CRED": cred,
                "ENDFIELD_SK_GAME_ROLE": role,
                "ENDFIELD_PLATFORM": plat,
                "ENDFIELD_VNAME": vname,
            }
            if best_score >= 6:
                break

    return best


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract Endfield (SKPort) headers from a DevTools-exported HAR file (no WebDriver)."
    )
    ap.add_argument("--har", required=True, help="Path to HAR file exported from browser DevTools Network tab.")
    ap.add_argument("--raw", action="store_true", help="Print raw values to console.")
    ap.add_argument("--no-pause", action="store_true", help="Do not wait for Enter before exit.")
    args = ap.parse_args()

    har_path = Path(args.har).expanduser()
    if not har_path.exists():
        print(f"ERROR: HAR not found: {har_path}")
        pause_exit(not args.no_pause)
        return 1

    try:
        har = json.loads(har_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: Failed to parse HAR: {e}")
        pause_exit(not args.no_pause)
        return 1

    values = extract_endfield_headers_from_har(har)
    print("== Endfield (SKPort) header extract (HAR) ==")
    print(f"har: {har_path}")
    print("\nExtracted values:")
    for k in ["ENDFIELD_CRED", "ENDFIELD_SK_GAME_ROLE", "ENDFIELD_PLATFORM", "ENDFIELD_VNAME"]:
        v = values.get(k, "") or ""
        print(f"- {k}: {v if args.raw else mask(v)}")
    print("\nNOTE: This tool does not save secrets to disk; it only prints them.")

    if not values.get("ENDFIELD_CRED") or not values.get("ENDFIELD_SK_GAME_ROLE"):
        print("\nNOTE: cred / sk-game-role not found in this HAR.")
        print("Tips:")
        print("- In DevTools Network tab, enable 'Preserve log'.")
        print("- Open Endfield sign-in page, click the sign-in button once.")
        print("- Export HAR after the request completes.")

    pause_exit(not args.no_pause)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
