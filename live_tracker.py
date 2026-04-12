from __future__ import annotations

"""
live_tracker.py
---------------
Roda em background e envia notificacoes ao vivo no Telegram.
Verifica todos os usuarios a cada 60 segundos.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram.ext import Application

from database import listar_todos_usuarios, obter_estado_jogo, salvar_estado_jogo
from football_live import LiveDataTemporaryError, buscar_jogo_ao_vivo

logger = logging.getLogger(__name__)
SAO_PAULO_TZ = timezone(timedelta(hours=-3))
POLL_INTERVAL = 60
LIVE_STATUSES = {"1H", "2H", "HT", "ET", "P"}
MAX_CONSECUTIVE_MISSES = 3


def _emoji_evento(tipo: str) -> str:
    return {
        "gol": "⚽",
        "cartao_vermelho": "🟥",
        "penalti": "🎯",
        "inicio": "🔔",
        "fim": "🏁",
        "intervalo": "☕",
        "segundo_tempo": "▶️",
    }.get(tipo, "📣")


def _montar_cabecalho(jogo: dict) -> str:
    meu = jogo.get("meu_time", "Seu time")
    rival = jogo.get("rival", "Adversario")
    gm = jogo.get("gols_meus", 0)
    gr = jogo.get("gols_rival", 0)
    minuto = jogo.get("minuto", "")
    minuto_txt = f" {minuto}'" if minuto else ""
    return f"{meu} {gm} x {gr} {rival}{minuto_txt}"


def _detectar_eventos(anterior: dict, atual: dict) -> list[dict]:
    eventos: list[dict] = []

    status_ant = anterior.get("status", "")
    status_now = atual.get("status", "")

    # Inicio
    if status_ant in ("NS", "") and status_now == "1H":
        meu = atual.get("meu_time", "Seu time")
        rival = atual.get("rival", "Adversario")
        liga = atual.get("liga", "")
        eventos.append({"tipo": "inicio", "descricao": f"Começou! {meu} x {rival}\n🏆 {liga}"})

    # Intervalo
    if status_ant == "1H" and status_now == "HT":
        gm = atual.get("gols_meus", 0)
        gr = atual.get("gols_rival", 0)
        eventos.append({"tipo": "intervalo", "descricao": f"Intervalo!\nPlacar: {gm} x {gr}"})

    # Segundo tempo
    if status_ant == "HT" and status_now == "2H":
        eventos.append({"tipo": "segundo_tempo", "descricao": "Segundo tempo começou!"})

    meu = atual.get("meu_time", "Seu time")
    rival = atual.get("rival", "Adversario")
    minuto = atual.get("minuto", "")
    minuto_txt = f" ({minuto}')" if minuto else ""

    # Gols
    gm_ant = int(anterior.get("gols_meus") or 0)
    gr_ant = int(anterior.get("gols_rival") or 0)
    gm_now = int(atual.get("gols_meus") or 0)
    gr_now = int(atual.get("gols_rival") or 0)

    for _ in range(gm_now - gm_ant):
        eventos.append({"tipo": "gol", "descricao": f"GOL DO {meu.upper()}!{minuto_txt}\nPlacar: {gm_now} x {gr_now}"})

    for _ in range(gr_now - gr_ant):
        eventos.append({"tipo": "gol", "descricao": f"Gol do {rival}{minuto_txt}\nPlacar: {gm_now} x {gr_now}"})

    # Cartoes vermelhos
    cv_meu_ant = int(anterior.get("cartoes_vermelhos_meus") or 0)
    cv_rival_ant = int(anterior.get("cartoes_vermelhos_rival") or 0)
    cv_meu_now = int(atual.get("cartoes_vermelhos_meus") or 0)
    cv_rival_now = int(atual.get("cartoes_vermelhos_rival") or 0)

    for _ in range(cv_meu_now - cv_meu_ant):
        eventos.append({"tipo": "cartao_vermelho", "descricao": f"Cartão vermelho no {meu}!{minuto_txt}"})

    for _ in range(cv_rival_now - cv_rival_ant):
        eventos.append({"tipo": "cartao_vermelho", "descricao": f"Cartão vermelho no {rival}!{minuto_txt}"})

    # Penaltis
    pen_ant = int(anterior.get("penaltis") or 0)
    pen_now = int(atual.get("penaltis") or 0)
    for _ in range(pen_now - pen_ant):
        eventos.append({"tipo": "penalti", "descricao": f"Pênalti marcado!{minuto_txt}"})

    # Fim de jogo
    if status_ant in LIVE_STATUSES and status_now == "FT":
        gm = atual.get("gols_meus", 0)
        gr = atual.get("gols_rival", 0)
        if gm > gr:
            resultado = f"Vitória do {meu}! 🎉"
        elif gr > gm:
            resultado = f"Derrota para o {rival}. 😔"
        else:
            resultado = "Empate."
        eventos.append({"tipo": "fim", "descricao": f"Fim de jogo! {resultado}\nPlacar final: {gm} x {gr}"})

    return eventos


async def _notificar_usuario(app: Application, chat_id: int, jogo: dict, eventos: list[dict]) -> None:
    cabecalho = _montar_cabecalho(jogo)
    for ev in eventos:
        emoji = _emoji_evento(ev["tipo"])
        texto = f"{emoji} {ev['descricao']}\n\n🏟 {cabecalho}"
        try:
            await app.bot.send_message(chat_id=chat_id, text=texto)
        except Exception as e:
            logger.warning(f"[live_tracker] Erro ao enviar para {chat_id}: {e}")


async def _processar_usuario(app: Application, chat_id: int, jogo: dict | None, falha_temporaria: bool) -> None:
    if falha_temporaria:
        return

    estado_ant = obter_estado_jogo(chat_id) or {}

    if not jogo:
        if estado_ant.get("status") in LIVE_STATUSES:
            misses = int(estado_ant.get("_misses") or 0) + 1
            if misses >= MAX_CONSECUTIVE_MISSES:
                salvar_estado_jogo(chat_id, {})
            else:
                estado_novo = dict(estado_ant)
                estado_novo["_misses"] = misses
                salvar_estado_jogo(chat_id, estado_novo)
        return

    if jogo.get("status") == "NS":
        return

    eventos = _detectar_eventos(estado_ant, jogo)

    if eventos:
        await _notificar_usuario(app, chat_id, jogo, eventos)

    salvar_estado_jogo(chat_id, jogo)

    if jogo.get("status") == "FT":
        salvar_estado_jogo(chat_id, {})


async def loop_monitoramento(app: Application) -> None:
    logger.info("[live_tracker] Monitoramento ao vivo iniciado.")
    while True:
        try:
            usuarios = listar_todos_usuarios()
            usuarios_por_time: dict[int, list[int]] = {}
            for usuario in usuarios:
                team_id = int(usuario["team_id"])
                chat_id = int(usuario["chat_id"])
                usuarios_por_time.setdefault(team_id, []).append(chat_id)

            for team_id, chat_ids in usuarios_por_time.items():
                jogo: dict | None = None
                falha_temporaria = False
                try:
                    jogo = buscar_jogo_ao_vivo(team_id)
                except LiveDataTemporaryError as e:
                    falha_temporaria = True
                    logger.debug(f"[live_tracker] Falha temporaria team_id={team_id}: {e}")
                except Exception as e:
                    falha_temporaria = True
                    logger.debug(f"[live_tracker] Erro ao buscar jogo ao vivo team_id={team_id}: {e}")

                for chat_id in chat_ids:
                    await _processar_usuario(app, chat_id, jogo, falha_temporaria)
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"[live_tracker] Erro no loop: {e}")

        await asyncio.sleep(POLL_INTERVAL)
