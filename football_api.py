from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.espn.com.br"
SAO_PAULO_TZ = timezone(timedelta(hours=-3))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

TIMES = [
    {"id": 127, "nome": "Flamengo", "espn_id": 819, "slug": "flamengo", "aliases": ["fla", "mengao"]},
    {"id": 133, "nome": "Vasco da Gama", "espn_id": 3454, "slug": "vasco-da-gama", "aliases": ["vasco"]},
    {"id": 126, "nome": "São Paulo", "espn_id": 2026, "slug": "sao-paulo", "aliases": ["sao paulo", "spfc"]},
    {"id": 121, "nome": "Palmeiras", "espn_id": 2029, "slug": "palmeiras", "aliases": ["verdao"]},
    {"id": 131, "nome": "Corinthians", "espn_id": 874, "slug": "corinthians", "aliases": ["timao"]},
    {"id": 128, "nome": "Santos", "espn_id": 2674, "slug": "santos", "aliases": []},
    {"id": 124, "nome": "Fluminense", "espn_id": 3445, "slug": "fluminense", "aliases": ["flu"]},
    {"id": 120, "nome": "Botafogo", "espn_id": 6086, "slug": "botafogo", "aliases": ["botafogo-rj"]},
    {"id": 1062, "nome": "Atlético Mineiro", "espn_id": 7632, "slug": "atletico-mg", "aliases": ["atletico-mg", "galo"]},
    {"id": 135, "nome": "Cruzeiro", "espn_id": 2022, "slug": "cruzeiro", "aliases": []},
    {"id": 130, "nome": "Grêmio", "espn_id": 6273, "slug": "gremio", "aliases": ["gremio"]},
    {"id": 119, "nome": "Internacional", "espn_id": 1936, "slug": "internacional", "aliases": ["inter"]},
    {"id": 118, "nome": "Bahia", "espn_id": 9967, "slug": "bahia", "aliases": []},
    {"id": 136, "nome": "Vitória", "espn_id": 3457, "slug": "vitoria", "aliases": ["vitoria"]},
    {"id": 129, "nome": "Ceará", "espn_id": 9969, "slug": "ceara", "aliases": ["ceara"]},
    {"id": 154, "nome": "Fortaleza", "espn_id": 6272, "slug": "fortaleza", "aliases": ["fortaleza ec"]},
    {"id": 123, "nome": "Sport", "espn_id": 7635, "slug": "sport", "aliases": ["sport recife"]},
    {"id": 134, "nome": "Athletico Paranaense", "espn_id": 3458, "slug": "athletico-pr", "aliases": ["athletico-pr"]},
    {"id": 147, "nome": "Coritiba", "espn_id": 3456, "slug": "coritiba", "aliases": ["coxa"]},
    {"id": 151, "nome": "Goiás", "espn_id": 3395, "slug": "goias", "aliases": ["goias"]},
    {"id": 125, "nome": "América Mineiro", "espn_id": 6154, "slug": "america-mineiro", "aliases": ["america-mg", "américa-mg"]},
]

TIMES_POR_ID = {int(t["id"]): t for t in TIMES}

GRANDES_TIMES = {
    "Flamengo", "Fluminense", "Vasco da Gama", "Botafogo",
    "São Paulo", "Corinthians", "Palmeiras", "Santos",
    "Atlético Mineiro", "Cruzeiro", "Grêmio", "Internacional",
    "Bahia", "Vitória", "Ceará", "Fortaleza", "Sport",
    "Athletico Paranaense", "Coritiba", "Goiás", "América Mineiro",
}


def get_ultimo_erro_api() -> str | None:
    return None


def buscar_times_por_nome(nome: str, pais: str = "Brazil") -> list[dict]:
    consulta = _normalizar_texto(nome)
    resultado: list[dict] = []

    for t in TIMES:
        candidatos = [t["nome"], *t.get("aliases", [])]
        norm_candidatos = [_normalizar_texto(c) for c in candidatos]
        if any(consulta in c for c in norm_candidatos):
            resultado.append(
                {
                    "id": int(t["id"]),
                    "nome": str(t["nome"]),
                    "pais": pais,
                    "logo": f"https://a.espncdn.com/i/teamlogos/soccer/500/{t['espn_id']}.png",
                    "cidade": "",
                }
            )
    return resultado[:5]


def get_proximo_jogo(time_id: int) -> dict | None:
    jogos = _obter_jogos_time(time_id, page_type="calendario")
    if not jogos:
        return None

    agora = datetime.now(SAO_PAULO_TZ)
    futuros = [j for j in jogos if j["kickoff"] and j["kickoff"] >= agora and j["status"] == "NS"]
    if not futuros:
        return None
    futuros.sort(key=lambda x: x["kickoff"])
    return futuros[0]["payload"]


def get_jogo_finalizado(time_id: int) -> dict | None:
    time_cfg = TIMES_POR_ID.get(int(time_id))
    if not time_cfg:
        return None

    def _parse_placar_texto(evento: dict[str, Any]) -> tuple[str | None, str | None]:
        status_detail = str((evento.get("status") or {}).get("detail") or "")
        score_text = str(evento.get("score") or "")
        placar_texto: tuple[str, str] | None = None

        comps = evento.get("competitors") or []
        meu = None
        rival = None
        meu_espn_id = str(time_cfg["espn_id"])
        for c in comps:
            if str(c.get("id", "")) == meu_espn_id:
                meu = c
            elif rival is None:
                rival = c

        eh_casa = bool((meu or {}).get("isHome"))

        base_textos = [status_detail, score_text]
        for bruto in base_textos:
            texto = re.sub(r"\s+", " ", bruto).replace("–", "-").replace("—", "-").strip()
            m = re.search(r"(\d+)\s*[-xX]\s*(\d+)", texto)
            if not m:
                continue

            a, b = m.group(1), m.group(2)
            if re.search(r"\b[VDE]\b", texto, re.IGNORECASE):
                placar_texto = (a, b)
                break

            placar_texto = (a, b) if eh_casa else (b, a)
            break

        meu_score = _digitos_placar((meu or {}).get("score"))
        rival_score = _digitos_placar((rival or {}).get("score"))
        if meu_score is not None and rival_score is not None:
            placar_comp = (meu_score, rival_score)
            if placar_texto and placar_comp == ("0", "0") and placar_texto != ("0", "0"):
                return placar_texto
            return placar_comp

        if placar_texto:
            return placar_texto

        print(
            "[football_api] DEBUG placar nao encontrado. "
            f"status.detail='{status_detail}' score='{score_text}'"
        )
        return None, None

    try:
        html = _baixar_html_time(time_cfg, page_type="resultados")
        data = _extrair_espnfitt_data(html)
        eventos = _extrair_eventos(data)
    except Exception as e:
        print(f"[football_api] Erro ao raspar jogos finalizados: {e}")
        return None

    agora = datetime.now(SAO_PAULO_TZ)
    candidatos: list[tuple[datetime, dict[str, Any]]] = []

    for evento in eventos:
        kickoff = _parse_espn_date(evento.get("date"))
        if not kickoff or kickoff > agora:
            continue

        status_raw = str((evento.get("status") or {}).get("state") or "").lower()
        concluido = bool(evento.get("completed"))
        if not (concluido or status_raw in {"post", "final"}):
            continue

        candidatos.append((kickoff, evento))

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x[0], reverse=True)
    ultimo_evento = candidatos[0][1]

    jogo = _normalizar_evento(ultimo_evento, time_cfg)
    if not jogo:
        return None

    gols_meus, gols_rival = _parse_placar_texto(ultimo_evento)
    if gols_meus is not None and gols_rival is not None:
        jogo["payload"]["gols_meus"] = gols_meus
        jogo["payload"]["gols_rival"] = gols_rival
    else:
        jogo["payload"]["gols_meus"] = None
        jogo["payload"]["gols_rival"] = None

    jogo["payload"]["status"] = "FT"
    return jogo["payload"]


def get_jogo_hoje(time_id: int) -> dict | None:
    jogos = _obter_jogos_time(time_id, page_type="calendario")
    if not jogos:
        return None

    hoje = datetime.now(SAO_PAULO_TZ).date()
    jogos_hoje = [j for j in jogos if j["kickoff"] and j["kickoff"].date() == hoje]
    if not jogos_hoje:
        return None
    jogos_hoje.sort(key=lambda x: x["kickoff"])
    return jogos_hoje[0]["payload"]


def get_jogo_em_breve(time_id: int, horas: int = 1) -> dict | None:
    jogo = get_proximo_jogo(time_id)
    if not jogo:
        return None

    kickoff = _parse_iso_local(jogo["data_iso"])
    if not kickoff:
        return None

    agora = datetime.now(SAO_PAULO_TZ)
    limite = agora + timedelta(hours=horas)
    if agora <= kickoff <= limite:
        return jogo
    return None


def _obter_jogos_time(time_id: int, page_type: str = "calendario") -> list[dict]:
    time_cfg = TIMES_POR_ID.get(int(time_id))
    if not time_cfg:
        return []

    try:
        html = _baixar_html_time(time_cfg, page_type=page_type)
        data = _extrair_espnfitt_data(html)
        events = _extrair_eventos(data)
    except Exception as e:
        print(f"[football_api] Erro ao raspar jogos: {e}")
        return []

    jogos: list[dict] = []
    for evento in events:
        jogo = _normalizar_evento(evento, time_cfg)
        if jogo is None:
            continue
        jogos.append(jogo)

    jogos.sort(key=lambda x: x["kickoff"] or datetime.max.replace(tzinfo=SAO_PAULO_TZ))
    return jogos


def _baixar_html_time(time_cfg: dict, page_type: str = "calendario") -> str:
    if page_type not in {"calendario", "resultados"}:
        page_type = "calendario"
    url = f"{BASE_URL}/futebol/time/{page_type}/_/id/{time_cfg['espn_id']}/{time_cfg['slug']}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def _extrair_espnfitt_data(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        texto = script.string or script.get_text("", strip=False)
        if not texto or "__espnfitt__" not in texto:
            continue

        marker = "window['__espnfitt__']"
        start = texto.find(marker)
        if start < 0:
            continue
        eq_idx = texto.find("=", start)
        brace_idx = texto.find("{", eq_idx)
        if eq_idx < 0 or brace_idx < 0:
            continue

        json_str = _extrair_objeto_json_balanceado(texto, brace_idx)
        if not json_str:
            continue
        return json.loads(json_str)

    raise ValueError("Nao foi possivel localizar o payload __espnfitt__ no HTML.")


def _extrair_objeto_json_balanceado(texto: str, inicio: int) -> str:
    nivel = 0
    em_string = False
    escape = False

    for i in range(inicio, len(texto)):
        c = texto[i]
        if em_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                em_string = False
            continue

        if c == '"':
            em_string = True
        elif c == "{":
            nivel += 1
        elif c == "}":
            nivel -= 1
            if nivel == 0:
                return texto[inicio : i + 1]
    return ""


def _extrair_eventos(data: dict[str, Any]) -> list[dict[str, Any]]:
    eventos = (
        data.get("page", {})
        .get("content", {})
        .get("scheduleData", {})
        .get("events", [])
    )
    if isinstance(eventos, list) and eventos:
        return [e for e in eventos if isinstance(e, dict)]

    coletados: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if _parece_evento(node):
                coletados.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)

    unicos: dict[str, dict[str, Any]] = {}
    for ev in coletados:
        chave = f"{ev.get('id')}|{ev.get('date')}"
        unicos[chave] = ev
    return list(unicos.values())


def _parece_evento(node: dict[str, Any]) -> bool:
    return (
        isinstance(node.get("date"), str)
        and isinstance(node.get("competitors"), list)
        and len(node.get("competitors", [])) >= 2
    )


def _normalizar_evento(evento: dict[str, Any], time_cfg: dict[str, Any]) -> dict[str, Any] | None:
    comps = evento.get("competitors") or []
    if len(comps) < 2:
        return None

    meu_espn_id = str(time_cfg["espn_id"])
    meu_time = None
    rival = None
    for c in comps:
        cid = str(c.get("id", ""))
        if cid == meu_espn_id:
            meu_time = c
        else:
            rival = c if rival is None else rival
    if not meu_time:
        return None
    if rival is None:
        rival = comps[1] if comps[0] == meu_time else comps[0]

    kickoff = _parse_espn_date(evento.get("date"))

    status_raw = str((evento.get("status") or {}).get("state") or "").lower()
    concluido = bool(evento.get("completed"))
    if concluido or status_raw in {"post", "final"}:
        status = "FT"
    elif status_raw in {"pre"}:
        status = "NS"
    else:
        status = "NS"

    eh_casa = bool(meu_time.get("isHome"))
    nome_meu_time = str(meu_time.get("displayName") or time_cfg["nome"])
    nome_rival = str(rival.get("displayName") or "Adversario")

    gols_meus, gols_rival = _extrair_placar(evento, meu_time, rival)
    if status != "FT":
        gols_meus, gols_rival = None, None

    liga = str(evento.get("league") or "Campeonato")
    estadio = str((evento.get("venue") or {}).get("fullName") or "A definir")
    data_iso = kickoff.strftime("%Y-%m-%dT%H:%M:%S") if kickoff else ""
    horario = kickoff.strftime("%Hh%M") if kickoff else "—"

    return {
        "payload": {
            "meu_time": nome_meu_time,
            "rival": nome_rival,
            "data_iso": data_iso,
            "horario": horario,
            "status": status,
            "estadio": estadio,
            "liga": liga,
            "eh_casa": eh_casa,
            "gols_meus": gols_meus,
            "gols_rival": gols_rival,
            "e_classico": _checar_classico(nome_meu_time, nome_rival),
        },
        "kickoff": kickoff,
        "status": status,
    }


def _extrair_placar(evento: dict[str, Any], meu_time: dict[str, Any], rival: dict[str, Any]) -> tuple[str | None, str | None]:
    meu_score = _digitos_placar(meu_time.get("score"))
    rival_score = _digitos_placar(rival.get("score"))
    if meu_score is not None and rival_score is not None:
        return meu_score, rival_score

    score_texto = str(evento.get("score") or "")
    m = re.search(r"(\d+)\s*[-xX]\s*(\d+)", score_texto)
    if not m:
        return None, None

    home_score, away_score = m.group(1), m.group(2)
    if bool(meu_time.get("isHome")):
        return home_score, away_score
    return away_score, home_score


def _digitos_placar(valor: Any) -> str | None:
    if valor is None:
        return None
    s = str(valor).strip()
    return s if s.isdigit() else None


def _parse_espn_date(data_str: Any) -> datetime | None:
    if not isinstance(data_str, str) or not data_str.strip():
        return None
    try:
        dt = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
        return dt.astimezone(SAO_PAULO_TZ)
    except Exception:
        return None


def _parse_iso_local(data_iso: str) -> datetime | None:
    if not data_iso:
        return None
    try:
        dt = datetime.fromisoformat(data_iso)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=SAO_PAULO_TZ)
        return dt.astimezone(SAO_PAULO_TZ)
    except Exception:
        return None


def _normalizar_texto(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s)


GRANDES_TIMES_NORMALIZADOS = {_normalizar_texto(t) for t in GRANDES_TIMES}


def _checar_classico(time1: str, time2: str) -> bool:
    return _normalizar_nome_time(time1) in GRANDES_TIMES_NORMALIZADOS and _normalizar_nome_time(time2) in GRANDES_TIMES_NORMALIZADOS


def _normalizar_nome_time(nome: str) -> str:
    return _normalizar_texto(nome)
