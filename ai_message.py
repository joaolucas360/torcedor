"""
ai_message.py
Camada de IA para interpretar mensagens e montar respostas conversacionais.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODELS = [
    "gemini-1.5-flash",  # preferencia solicitada
    "gemini-1.5-flash-latest",
    "gemini-2.5-flash",  # fallback quando 1.5 nao estiver disponivel
]


def mensagem_time_salvo(team_name: str) -> str:
    return f"Fechou! Time salvo: {team_name}. Agora me pergunta de boa sobre proximo jogo, jogo de hoje ou ultimo resultado."


def mensagem_sem_time() -> str:
    return "Ainda nao sei seu time. Me fala de boa tipo: sou Flamengo, torco pro Vasco, meu time e Sao Paulo."


def mensagem_sem_jogo(contexto: str) -> str:
    return f"Nao encontrei dados para {contexto} agora. Tenta de novo daqui a pouco."


def interpretar_acao_usuario(texto_usuario: str, time_salvo: str | None) -> dict[str, Any]:
    local = _inferir_acao_local(texto_usuario, time_salvo)
    if local is not None:
        return local

    prompt = (
        "Voce e um roteador de intents para bot de futebol.\n"
        "Responda SOMENTE JSON valido, sem markdown, sem texto extra.\n"
        "Acoes permitidas: proximo_jogo, ultimo_jogo, jogo_hoje, salvar_time, conversa.\n"
        'Formato:\n{"acao":"proximo_jogo"}\n{"acao":"ultimo_jogo"}\n{"acao":"jogo_hoje"}\n'
        '{"acao":"salvar_time","time":"Flamengo"}\n'
        '{"acao":"conversa","resposta":"..."}\n'
        "Se o usuario pedir jogo e nao houver time salvo, use conversa pedindo o time primeiro.\n"
        "Nao use asteriscos. Seja direto e amigavel. Maximo 2 emojis.\n"
        f"Time salvo atual: {time_salvo or 'nenhum'}\n"
        f"Mensagem do usuario: {texto_usuario}\n"
    )
    txt = _gemini_text(prompt)
    data = _parse_json_relaxado(txt)
    if not isinstance(data, dict):
        return {"acao": "conversa", "resposta": "Nao entendi 100%. Me fala se voce quer proximo jogo, ultimo jogo, jogo de hoje ou salvar um time 🙂"}
    acao = data.get("acao")
    if acao not in {"proximo_jogo", "ultimo_jogo", "jogo_hoje", "salvar_time", "conversa"}:
        return {"acao": "conversa", "resposta": "Me diz em uma frase: proximo jogo, ultimo jogo, jogo de hoje ou qual time salvar."}
    return data


def resposta_conversa(texto_usuario: str, time_salvo: str | None) -> str:
    prompt = (
        "Voce e um amigo apaixonado por futebol respondendo no Telegram.\n"
        "Tom descontraido, direto, sem enrolar.\n"
        "Maximo 2 emojis.\n"
        "Nao usar markdown com asteriscos.\n"
        f"Time salvo do usuario: {time_salvo or 'nenhum'}\n"
        f"Mensagem do usuario: {texto_usuario}\n"
    )
    txt = _gemini_text(prompt).strip()
    if not txt or len(txt) < 8:
        return "Tamo junto! Me pergunta do proximo jogo, jogo de hoje ou ultimo resultado."
    return txt


def resposta_jogo(acao: str, jogo: dict[str, Any], time_salvo: str | None) -> str:
    return _fallback_jogo(acao, jogo)


def _fallback_jogo(acao: str, jogo: dict[str, Any]) -> str:
    data_iso = str(jogo.get("data_iso") or "-")
    data_txt = _data_legivel(data_iso if data_iso != "-" else "")
    horario = str(jogo.get("horario") or "-")
    meu = str(jogo.get("meu_time") or "Seu time")
    rival = str(jogo.get("rival") or "adversario")
    liga = str(jogo.get("liga") or "-")
    estadio = str(jogo.get("estadio") or "A definir")
    mando = "Casa" if jogo.get("eh_casa") else "Fora"
    classico = "Sim" if jogo.get("e_classico") else "Nao"
    if acao == "ultimo_jogo":
        gm = jogo.get("gols_meus")
        gr = jogo.get("gols_rival")
        placar = f"{gm} x {gr}" if gm is not None and gr is not None else "Placar indisponivel"
        return (
            f"ULTIMO RESULTADO - {meu}\n\n"
            f"{meu} {placar} {rival}\n"
            f"Data/Hora: {data_txt}\n"
            f"Competicao: {liga}\n"
            f"Estadio: {estadio}\n"
            f"Status: FT"
        )
    return (
        f"PROXIMO JOGO - {meu}\n\n"
        f"{meu} x {rival}\n"
        f"Data/Hora: {data_txt}\n"
        f"Horario local: {horario}\n"
        f"Competicao: {liga}\n"
        f"Estadio: {estadio}\n"
        f"Mando: {mando}\n"
        f"Classico: {classico}"
    )


def _data_legivel(data_iso: str | None) -> str:
    if not data_iso:
        return "-"
    try:
        data, hora = data_iso.split("T", 1)
        ano, mes, dia = data.split("-")
        hora = hora[:5]
        return f"{dia}/{mes}/{ano} {hora}"
    except Exception:
        return data_iso


def _inferir_acao_local(texto_usuario: str, time_salvo: str | None) -> dict[str, Any] | None:
    txt = (texto_usuario or "").strip().lower()
    if not txt:
        return {"acao": "conversa", "resposta": "Manda ai o que voce quer saber do seu time 😄"}

    # salvar time com linguagem natural
    padroes_time = [
        r"(?:sou|torco(?:\s+pro)?|meu\s+time\s+(?:e|é)|salva(?:\s+meu\s+time)?|time\s+é)\s+(.+)$",
        r"^(flamengo|vasco(?:\s+da\s+gama)?|sao\s+paulo|corinthians|palmeiras|santos|fluminense|botafogo|atletico(?:-mg)?|gremio|internacional|bahia|vitoria|ceara|fortaleza|sport|athletico|coritiba|goias|america(?:\s+mineiro)?)$",
    ]
    for p in padroes_time:
        m = re.search(p, txt, flags=re.IGNORECASE)
        if m:
            time = m.group(1).strip()
            time = re.sub(r"^(do|da|de|pro|pra|o|a)\s+", "", time, flags=re.IGNORECASE)
            time = re.sub(r"[?.!,;]+$", "", time).strip()
            if len(time) >= 3:
                return {"acao": "salvar_time", "time": time}

    pediu_proximo = bool(re.search(r"\b(proximo|próximo|quando\s+joga|prox)\b", txt))
    pediu_hoje = bool(re.search(r"\b(hoje|tem\s+jogo\s+hoje)\b", txt))
    pediu_ultimo = bool(re.search(r"\b(ultimo|último|como\s+foi|resultado|placar)\b", txt))

    if pediu_proximo:
        if not time_salvo:
            return {"acao": "conversa", "resposta": mensagem_sem_time()}
        return {"acao": "proximo_jogo"}
    if pediu_hoje:
        if not time_salvo:
            return {"acao": "conversa", "resposta": mensagem_sem_time()}
        return {"acao": "jogo_hoje"}
    if pediu_ultimo:
        if not time_salvo:
            return {"acao": "conversa", "resposta": mensagem_sem_time()}
        return {"acao": "ultimo_jogo"}

    # Saudações informais
    if re.search(r"\b(oi|ola|olá|e ai|eae|fala|salve|bom dia|boa tarde|boa noite)\b", txt):
        return {"acao": "conversa", "resposta": "Fala! Se quiser, ja te conto proximo jogo, jogo de hoje ou ultimo resultado 😄"}

    return None


def _gemini_text(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return ""

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 300,
        },
    }
    ultimo_erro: Exception | None = None
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for tentativa in range(2):
            try:
                resp = requests.post(
                    url,
                    params={"key": GEMINI_API_KEY},
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(body),
                    timeout=20,
                )
                if resp.status_code == 404:
                    break
                if resp.status_code in {429, 500, 502, 503, 504} and tentativa == 0:
                    time.sleep(0.8)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return _extrair_texto_gemini(data)
            except Exception as e:
                ultimo_erro = e
                if tentativa == 0:
                    time.sleep(0.8)
                continue
    if ultimo_erro:
        print(f"[ai_message] erro Gemini: {ultimo_erro}")
    return ""


def _extrair_texto_gemini(data: dict[str, Any]) -> str:
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = (cands[0].get("content") or {}).get("parts") or []
    textos: list[str] = []
    for p in parts:
        t = p.get("text")
        if isinstance(t, str):
            textos.append(t)
    return "\n".join(textos).strip()


def _parse_json_relaxado(raw: str) -> Any:
    if not raw:
        return None
    txt = raw.strip()
    txt = re.sub(r"^```(?:json)?\s*", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s*```$", "", txt)
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
