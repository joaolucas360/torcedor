from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN")

BASE_URL = "https://api.football-data.org/v4"
SAO_PAULO_TZ = timezone(timedelta(hours=-3))
STATUS_PRIORITY = {
    "IN_PLAY": 0,
    "EXTRA_TIME": 1,
    "PENALTY_SHOOTOUT": 2,
    "PAUSED": 3,
    "TIMED": 4,
    "SCHEDULED": 5,
    "FINISHED": 6,
}


class LiveDataTemporaryError(Exception):
    pass

FOOTBALL_DATA_IDS: dict[int, int] = {
    127: 737,
    133: 6357,
    126: 1062,
    121: 1763,
    131: 1768,
    128: 6119,
    124: 6309,
    120: 1764,
    1062: 1081,
    135: 6318,
    130: 6308,
    119: 6301,
    118: 6320,
    136: 6316,
    129: 6323,
    154: 6321,
    123: 6313,
    134: 6317,
    147: 6319,
    151: 6322,
    125: 6315,
}


def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    if not FOOTBALL_DATA_TOKEN:
        raise RuntimeError("FOOTBALL_DATA_TOKEN nao configurado no .env")
    url = f"{BASE_URL}{path}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    resp = requests.get(url, headers=headers, params=params or {}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def buscar_jogo_ao_vivo(team_id_interno: int) -> dict | None:
    fd_id = FOOTBALL_DATA_IDS.get(team_id_interno)
    if not fd_id:
        return None

    try:
        data = _get(
            f"/teams/{fd_id}/matches",
            params={"status": "IN_PLAY,PAUSED,EXTRA_TIME,PENALTY_SHOOTOUT"},
        )
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code in {429, 502, 503, 504}:
            raise LiveDataTemporaryError("falha temporaria ao consultar live") from e
        raise
    except requests.RequestException as e:
        raise LiveDataTemporaryError("falha de rede ao consultar live") from e

    matches = data.get("matches") or []
    if not matches:
        return None

    return _normalizar_match(matches[-1], fd_id)


def buscar_jogo_hoje_live(team_id_interno: int) -> dict | None:
    fd_id = FOOTBALL_DATA_IDS.get(team_id_interno)
    if not fd_id:
        return None

    hoje = datetime.now(SAO_PAULO_TZ).date().isoformat()

    try:
        data = _get(f"/teams/{fd_id}/matches", params={"dateFrom": hoje, "dateTo": hoje})
    except Exception:
        return None

    matches = data.get("matches") or []
    if not matches:
        return None

    melhor = min(matches, key=_chave_prioridade_jogo)
    return _normalizar_match(melhor, fd_id)


def _chave_prioridade_jogo(match: dict[str, Any]) -> tuple[int, str]:
    status = str(match.get("status") or "").upper()
    prioridade = STATUS_PRIORITY.get(status, 99)
    kickoff = str(match.get("utcDate") or "")
    return prioridade, kickoff


def _normalizar_match(match: dict[str, Any], meu_fd_id: int) -> dict | None:
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}

    eh_casa = int(home.get("id", 0)) == meu_fd_id
    meu_time_obj = home if eh_casa else away
    rival_obj = away if eh_casa else home

    meu_time = str(meu_time_obj.get("shortName") or meu_time_obj.get("name") or "Seu time")
    rival = str(rival_obj.get("shortName") or rival_obj.get("name") or "Adversario")

    score = match.get("score") or {}
    ft = score.get("fullTime") or {}
    current = score.get("regularTime") or ft

    if eh_casa:
        gols_meus = int(current.get("home") or ft.get("home") or 0)
        gols_rival = int(current.get("away") or ft.get("away") or 0)
    else:
        gols_meus = int(current.get("away") or ft.get("away") or 0)
        gols_rival = int(current.get("home") or ft.get("home") or 0)

    status_raw = str(match.get("status") or "").upper()
    status_map = {
        "SCHEDULED": "NS",
        "TIMED": "NS",
        "IN_PLAY": "1H",
        "PAUSED": "HT",
        "FINISHED": "FT",
        "EXTRA_TIME": "ET",
        "PENALTY_SHOOTOUT": "P",
        "SUSPENDED": "FT",
        "CANCELLED": "FT",
        "POSTPONED": "NS",
    }
    status = status_map.get(status_raw, "NS")

    minute = match.get("minute")
    if minute and status == "1H":
        try:
            status = "2H" if int(minute) > 45 else "1H"
        except Exception:
            pass

    bookings = match.get("bookings") or []
    cv_meu = 0
    cv_rival = 0
    for booking in bookings:
        team_id_booking = int((booking.get("team") or {}).get("id") or 0)
        if str(booking.get("card") or "").upper() == "RED_CARD":
            if team_id_booking == meu_fd_id:
                cv_meu += 1
            else:
                cv_rival += 1

    goals = match.get("goals") or []
    penaltis = sum(1 for g in goals if str(g.get("type") or "").upper() == "PENALTY")

    liga = str((match.get("competition") or {}).get("name") or "Campeonato")

    return {
        "meu_time": meu_time,
        "rival": rival,
        "gols_meus": gols_meus,
        "gols_rival": gols_rival,
        "status": status,
        "minuto": str(minute) if minute else None,
        "liga": liga,
        "cartoes_vermelhos_meus": cv_meu,
        "cartoes_vermelhos_rival": cv_rival,
        "penaltis": penaltis,
        "eh_casa": eh_casa,
    }
