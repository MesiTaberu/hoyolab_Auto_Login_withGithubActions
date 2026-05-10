import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from cookie_check_common import load_env


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_TIMEOUT = 20
DEFAULT_REDEEM_DELAY_SECONDS = 5.0
HOYOLAB_SEARCH_URL = "https://bbs-api-os.hoyolab.com/community/search/wapi/search"
HOYOLAB_GAME_RECORD_CARD_URL = "https://bbs-api-os.hoyolab.com/game_record/card/wapi/getGameRecordCard"
LOGIN_REQUIRED_RETCODES = {-1071}
CODE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]{8,20}(?![A-Za-z0-9])")
URL_RE = re.compile(r"https?://[^\s<>\"]+")
LABELED_CODE_RE = re.compile(
    r"(?:code|codes|redeem\s*code|redemption\s*code|コード|交換コード)\s*(?:\d+)?\s*[:：-]\s*([A-Za-z0-9]{8,24})",
    re.IGNORECASE,
)
HOYOLAB_TAG_RE = re.compile(r"</?hoyolab>", re.IGNORECASE)
TITLE_KEYWORD_RE = re.compile(
    r"(redeem|redemption|code|codes|gift\s*code|コード|交換コード|シリアルコード)",
    re.IGNORECASE,
)
CODE_BANLIST = {
    "ADVENTURE",
    "ADVENTURER",
    "ANNOUNCEMENT",
    "CHARACTER",
    "COMMUNITY",
    "DISCUSSION",
    "EXPERIENCE",
    "FOLLOWERS",
    "GENSHINIMPACT",
    "HONKAISTARRAIL",
    "HOYOLAB",
    "HOYOVERSE",
    "LIVESTREAM",
    "POLYCHROME",
    "PRIMOGEM",
    "PRIMOGEMS",
    "REDEMPTION",
    "REDEEMCODE",
    "STELLARJADE",
    "TRAILBLAZER",
    "ZENLESSZONEZERO",
}


@dataclass(frozen=True)
class GameConfig:
    key: str
    name: str
    env_prefix: str
    endpoint: str
    game_biz: str
    hoyolab_gids: int
    search_keywords: tuple[str, ...]


SUPPORTED_GAMES: dict[str, GameConfig] = {
    "genshin": GameConfig(
        key="genshin",
        name="Genshin Impact",
        env_prefix="GENSHIN",
        endpoint="https://sg-hk4e-api.hoyoverse.com/common/apicdkey/api/webExchangeCdkey",
        game_biz="hk4e_global",
        hoyolab_gids=2,
        search_keywords=("redeem code", "redemption code", "primogems code", "コード"),
    ),
    "hsr": GameConfig(
        key="hsr",
        name="Honkai: Star Rail",
        env_prefix="HSR",
        endpoint="https://sg-hkrpg-api.hoyoverse.com/common/apicdkey/api/webExchangeCdkey",
        game_biz="hkrpg_global",
        hoyolab_gids=6,
        search_keywords=("redeem code", "redemption code", "stellar jade code", "コード"),
    ),
    "zzz": GameConfig(
        key="zzz",
        name="Zenless Zone Zero",
        env_prefix="ZZZ",
        endpoint="https://public-operation-nap.hoyoverse.com/common/apicdkey/api/webExchangeCdkey",
        game_biz="nap_global",
        hoyolab_gids=8,
        search_keywords=("redeem code", "redemption code", "polychrome code", "コード"),
    ),
}


@dataclass
class RedeemProfile:
    name: str
    endpoint: str
    game_biz: str
    uid: str
    region: str
    codes: list[str]
    lang: str = "ja"


def merge_codes(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for code in group:
            c = code.strip()
            if not c or c in seen:
                continue
            seen.add(c)
            merged.append(c)
    return merged


def _is_code_candidate(token: str) -> bool:
    t = token.strip().upper()
    if t in CODE_BANLIST:
        return False
    if t.startswith("HTTP"):
        return False
    return any(ch.isdigit() for ch in t) and token == t


def extract_codes_from_url(raw_url: str) -> list[str]:
    try:
        parsed = urlparse(unquote(raw_url))
    except ValueError:
        return []
    values = parse_qs(parsed.query).get("code", [])
    return [v.strip() for v in values if v.strip()]


def clean_hoyolab_text(text: str) -> str:
    return HOYOLAB_TAG_RE.sub("", text or "")


def title_has_code_keyword(title: str) -> bool:
    return bool(TITLE_KEYWORD_RE.search(clean_hoyolab_text(title)))


def extract_codes_from_text(text: str) -> list[str]:
    cleaned = clean_hoyolab_text(text)
    labeled = [m.group(1) for m in LABELED_CODE_RE.finditer(cleaned)]
    generic = [m.group(0) for m in CODE_RE.finditer(cleaned) if _is_code_candidate(m.group(0))]
    url_codes: list[str] = []
    for url in URL_RE.finditer(cleaned):
        url_codes.extend(extract_codes_from_url(url.group(0)))
    return merge_codes(labeled, generic, url_codes)


def extract_codes_from_hoyolab_post(post: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("subject", "content", "structured_content", "desc"):
        candidates.extend(extract_codes_from_text(str(post.get(key) or "")))

    for image in post.get("images") or []:
        candidates.extend(extract_codes_from_url(str(image)))

    return merge_codes(candidates)


def int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        print(f"{name}: invalid integer value {raw!r}; using {default}.")
        value = default
    return max(minimum, min(maximum, value))


def float_env(name: str, default: float, minimum: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        print(f"{name}: invalid number value {raw!r}; using {default}.")
        value = default
    return max(minimum, value)


def fetch_codes_from_hoyolab(cfg: GameConfig) -> list[str]:
    if os.getenv("REDEEM_HOYOLAB_ENABLED", "true").strip().lower() in {"0", "false", "no"}:
        return []

    lookback_hours = int_env("HOYOLAB_LOOKBACK_HOURS", 168, 1, 168)
    oldest_ts = int((datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp())
    page_size = int_env("HOYOLAB_PAGE_SIZE", 20, 1, 50)

    seen_post_ids: set[str] = set()
    codes: list[str] = []

    for keyword in cfg.search_keywords:
        params = {
            "keyword": keyword,
            "gids": str(cfg.hoyolab_gids),
            "page_size": str(page_size),
            "order_type": "2",
        }
        try:
            response = requests.get(
                HOYOLAB_SEARCH_URL,
                params=params,
                headers={"User-Agent": "Mozilla/5.0", "x-rpc-language": "en-us"},
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            print(f"{cfg.name}: HoYoLAB search failed: {e}")
            continue
        if response.status_code >= 400:
            print(f"{cfg.name}: HoYoLAB search failed: HTTP {response.status_code} {response.text[:160]}")
            continue

        try:
            payload = response.json()
        except ValueError:
            print(f"{cfg.name}: HoYoLAB search failed: non-JSON response {response.text[:160]}")
            continue
        if not isinstance(payload, dict):
            continue
        posts = ((payload.get("data") or {}).get("posts")) or []
        if not isinstance(posts, list):
            continue

        for item in posts:
            post = (item or {}).get("post") if isinstance(item, dict) else None
            if not isinstance(post, dict):
                continue
            if int(post.get("game_id") or 0) != cfg.hoyolab_gids:
                continue
            post_id = str(post.get("post_id") or "")
            if post_id in seen_post_ids:
                continue
            seen_post_ids.add(post_id)

            created_at = int(post.get("created_at") or 0)
            if created_at and created_at < oldest_ts:
                continue

            title = str(post.get("subject") or "")
            if not title_has_code_keyword(title):
                continue

            post_codes = extract_codes_from_hoyolab_post(post)
            if post_codes:
                title_clean = clean_hoyolab_text(title).replace("\n", " ")
                print(f"{cfg.name}: code candidate post: {title_clean[:120]}")
                codes.extend(post_codes)

    found = merge_codes(codes)
    if found:
        print(f"{cfg.name}: found {len(found)} code candidate(s) from HoYoLAB posts.")
    return found


def hoyolab_cookie_header() -> str:
    ltuid = os.getenv("LTUID", "").strip()
    ltoken = os.getenv("LTOKEN", "").strip()
    cookie_token = os.getenv("COOKIE_TOKEN_V2", "").strip()
    return (
        f"ltuid={ltuid}; ltuid_v2={ltuid}; "
        f"account_id={ltuid}; account_id_v2={ltuid}; "
        f"ltoken={ltoken}; ltoken_v2={ltoken}; "
        f"cookie_token_v2={cookie_token};"
    )


def redeem_cookie_header() -> str:
    hoyoverse_cookie = os.getenv("HOYOVERSE_COOKIE", "").strip()
    if hoyoverse_cookie:
        return hoyoverse_cookie
    return hoyolab_cookie_header()


def fetch_game_roles() -> list[dict[str, Any]]:
    ltuid = os.getenv("LTUID", "").strip()
    if not ltuid:
        return []

    try:
        response = requests.get(
            HOYOLAB_GAME_RECORD_CARD_URL,
            params={"uid": ltuid},
            headers={
                "Cookie": hoyolab_cookie_header(),
                "User-Agent": "Mozilla/5.0",
                "x-rpc-language": "en-us",
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as e:
        print(f"HoYoLAB game role lookup failed: {e}")
        return []
    if response.status_code >= 400:
        print(f"HoYoLAB game role lookup failed: HTTP {response.status_code} {response.text[:160]}")
        return []

    try:
        payload = response.json()
    except ValueError:
        print(f"HoYoLAB game role lookup failed: non-JSON response {response.text[:160]}")
        return []
    if not isinstance(payload, dict):
        return []
    if payload.get("retcode") != 0:
        print(f"HoYoLAB game role lookup failed: retcode={payload.get('retcode')} message={payload.get('message')}")
        return []

    roles = ((payload.get("data") or {}).get("list")) or []
    return roles if isinstance(roles, list) else []


def resolve_uid_region(cfg: GameConfig, roles: list[dict[str, Any]]) -> tuple[str, str]:
    uid = os.getenv(f"{cfg.env_prefix}_UID", "").strip()
    region = os.getenv(f"{cfg.env_prefix}_REGION", "").strip()
    if uid and region:
        return uid, region

    for role in roles:
        if not isinstance(role, dict):
            continue
        if int(role.get("game_id") or 0) != cfg.hoyolab_gids:
            continue
        role_uid = str(role.get("game_role_id") or "").strip()
        role_region = str(role.get("region") or "").strip()
        if role_uid and role_region:
            print(f"{cfg.name}: resolved UID/region from HoYoLAB game record card.")
            return role_uid, role_region

    return uid, region


def load_profiles_from_env() -> list[RedeemProfile]:
    profiles: list[RedeemProfile] = []
    roles = fetch_game_roles()
    for key, cfg in SUPPORTED_GAMES.items():
        uid, region = resolve_uid_region(cfg, roles)
        if not uid or not region:
            print(f"{cfg.name}: skipped because UID/region could not be resolved.")
            continue

        codes = fetch_codes_from_hoyolab(cfg)
        if not codes:
            print(f"{cfg.name}: no code candidates found from HoYoLAB posts.")
            continue

        profiles.append(RedeemProfile(cfg.name, cfg.endpoint, cfg.game_biz, uid, region, codes))

    return profiles


def load_profiles() -> list[RedeemProfile]:
    load_env()
    return load_profiles_from_env()


def has_explicit_uid_region() -> bool:
    for cfg in SUPPORTED_GAMES.values():
        uid = os.getenv(f"{cfg.env_prefix}_UID", "").strip()
        region = os.getenv(f"{cfg.env_prefix}_REGION", "").strip()
        if uid and region:
            return True
    return False


def validate_environment() -> bool:
    missing_hoyolab_cookie = [k for k in ["LTUID", "LTOKEN", "COOKIE_TOKEN_V2"] if not os.getenv(k, "").strip()]
    has_hoyoverse_cookie = bool(os.getenv("HOYOVERSE_COOKIE", "").strip())

    if missing_hoyolab_cookie and not has_explicit_uid_region():
        print(f"Missing HoYoLAB secrets for UID/region lookup: {', '.join(missing_hoyolab_cookie)}")
        return False

    if missing_hoyolab_cookie and not has_hoyoverse_cookie:
        print(f"Missing redeem secrets: HOYOVERSE_COOKIE or {', '.join(missing_hoyolab_cookie)}")
        return False

    return True


def is_already_used_message(message: str) -> bool:
    lowered = message.lower()
    return (
        "already" in lowered
        or "使用済" in message
        or "交換済" in message
        or ("既に" in message and ("使用" in message or "交換" in message))
    )


def is_login_required(retcode: Any, message: str) -> bool:
    lowered = message.lower()
    return retcode in LOGIN_REQUIRED_RETCODES or "login" in lowered or "ログイン" in message


def redeem_code(profile: RedeemProfile, code: str) -> dict[str, Any]:
    params = {
        "uid": profile.uid,
        "region": profile.region,
        "lang": profile.lang,
        "cdkey": code,
        "game_biz": profile.game_biz,
        "sLangKey": profile.lang,
    }
    headers = {
        "Cookie": redeem_cookie_header(),
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.hoyoverse.com/",
        "Origin": "https://www.hoyoverse.com",
        "Accept": "application/json, text/plain, */*",
    }

    try:
        response = requests.get(profile.endpoint, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as e:
        return {
            "ok": False,
            "fatal": True,
            "http": None,
            "retcode": None,
            "message": str(e),
        }
    try:
        payload = response.json()
    except ValueError:
        return {
            "ok": False,
            "fatal": True,
            "http": response.status_code,
            "retcode": None,
            "message": response.text[:200],
        }

    retcode = payload.get("retcode")
    message = str(payload.get("message", ""))
    # HoYoverse APIs usually return 0 for success and negative values for already used/expired/invalid.
    # Treat "already used" as non-fatal so scheduled workflows do not fail on repeated public codes.
    ok = retcode == 0 or is_already_used_message(message)
    fatal = response.status_code >= 500 or retcode in {-100, -101, -10001} or is_login_required(retcode, message)
    return {
        "ok": bool(ok),
        "fatal": bool(fatal),
        "http": response.status_code,
        "retcode": retcode,
        "message": message,
    }


def main() -> int:
    load_env()
    if not validate_environment():
        return 1

    profiles = load_profiles_from_env()
    if not profiles:
        print("No redeem codes found from HoYoLAB posts.")
        return 0

    failed = False
    for profile in profiles:
        print(f"\n== {profile.name} code redeem ==")
        delay_seconds = float_env("REDEEM_DELAY_SECONDS", DEFAULT_REDEEM_DELAY_SECONDS, 0.0)
        for index, code in enumerate(profile.codes):
            if index > 0 and delay_seconds:
                time.sleep(delay_seconds)
            result = redeem_code(profile, code)
            status = "ok" if result["ok"] else "rejected"
            print(
                f"- {code}: {status} "
                f"(HTTP {result['http']}, retcode={result['retcode']}, message={result['message']})"
            )
            if result.get("fatal"):
                failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
