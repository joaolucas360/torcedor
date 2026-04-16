from __future__ import annotations

import asyncio
import logging
import os
import re

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from ai_message import (
    interpretar_acao_usuario,
    mensagem_sem_jogo,
    mensagem_sem_time,
    mensagem_time_salvo,
    resposta_conversa,
    resposta_jogo,
)
from database import init_db, obter_time, remover_time, salvar_time
from football_api import buscar_times_por_nome, get_jogo_finalizado, get_jogo_hoje, get_proximo_jogo
from football_live import buscar_jogo_hoje_live
from live_tracker import loop_monitoramento

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class RedactSecretsFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets = [s for s in (secrets or []) if s]
        self.bot_token_pattern = re.compile(r"/bot\d{8,12}:[A-Za-z0-9_-]{30,}")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self.bot_token_pattern.sub("/bot***REDACTED***", message)
        for secret in self.secrets:
            redacted = redacted.replace(secret, "***REDACTED***")

        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def _setup_safe_logging() -> None:
    root_logger = logging.getLogger()
    filter_ = RedactSecretsFilter([TELEGRAM_TOKEN] if TELEGRAM_TOKEN else [])
    for handler in root_logger.handlers:
        handler.addFilter(filter_)

    # Evita log de request completo (URL inclui o token do bot).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Fala! Bora acompanhar seu time? Me diz qual time voce torce ou manda /time <nome do time> 😄\n\n"
        "Quando seu time tiver jogo ao vivo, te mando notificacao automatica de gol ⚽, "
        "cartao vermelho 🟥, penalti 🎯 e muito mais!\n\n"
        "Use /aovivo pra ver o placar ao vivo na hora que quiser."
    )


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    nome = " ".join(context.args).strip()
    if not nome:
        await update.message.reply_text("Manda assim: /time Flamengo")
        return
    await _processar_salvar_time(update, context, chat_id, nome)


async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ok = remover_time(update.effective_chat.id)
    if ok:
        await update.message.reply_text("Boa, removi seu time salvo. Quando quiser, manda /time <nome>.")
    else:
        await update.message.reply_text("Voce ainda nao tinha time salvo.")


async def proximo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _responder_acao_jogo(update, "proximo_jogo")


async def hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _responder_acao_jogo(update, "jogo_hoje")


async def ultimo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _responder_acao_jogo(update, "ultimo_jogo")


async def aovivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pref = obter_time(update.effective_chat.id)
    if not pref:
        await update.message.reply_text(mensagem_sem_time())
        return

    team_id = int(pref["team_id"])
    jogo = buscar_jogo_hoje_live(team_id)

    if not jogo:
        await update.message.reply_text(
            f"Nenhum jogo ao vivo ou agendado hoje para o {pref['team_name']}."
        )
        return

    status = jogo.get("status", "NS")
    meu = jogo.get("meu_time", pref["team_name"])
    rival = jogo.get("rival", "Adversario")
    gm = jogo.get("gols_meus", 0)
    gr = jogo.get("gols_rival", 0)
    liga = jogo.get("liga", "-")
    minuto = jogo.get("minuto")
    min_txt = f" ({minuto}')" if minuto else ""

    status_texto = {
        "NS": "⏳ Aguardando inicio",
        "1H": f"🔴 Ao vivo - 1º tempo{min_txt}",
        "HT": "☕ Intervalo",
        "2H": f"🔴 Ao vivo - 2º tempo{min_txt}",
        "ET": f"⚡ Prorrogacao{min_txt}",
        "P": "🎯 Disputa de penaltis",
        "FT": "🏁 Encerrado",
    }.get(status, status)

    linhas = [
        f"🏆 {liga}",
        f"{meu} {gm} x {gr} {rival}",
        f"Status: {status_texto}",
    ]

    cv_meu = jogo.get("cartoes_vermelhos_meus", 0)
    cv_rival = jogo.get("cartoes_vermelhos_rival", 0)
    if cv_meu:
        linhas.append(f"🟥 {meu}: {cv_meu} cartao(s) vermelho(s)")
    if cv_rival:
        linhas.append(f"🟥 {rival}: {cv_rival} cartao(s) vermelho(s)")

    await update.message.reply_text("\n".join(linhas))


async def tratar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = (update.message.text or "").strip()
    if not texto:
        return

    if "candidatos_times" in context.user_data:
        await _tratar_escolha_numero(update, context, texto)
        return

    pref = obter_time(update.effective_chat.id)
    time_salvo = pref["team_name"] if pref else None
    decisao = interpretar_acao_usuario(texto, time_salvo)
    acao = decisao.get("acao", "conversa")

    if acao == "salvar_time":
        nome_time = str(decisao.get("time") or "").strip()
        if not nome_time:
            await update.message.reply_text("Me fala o time certinho pra salvar. Exemplo: /time Flamengo")
            return
        await _processar_salvar_time(update, context, update.effective_chat.id, nome_time)
        return

    if acao in {"proximo_jogo", "ultimo_jogo", "jogo_hoje"}:
        if not pref:
            await update.message.reply_text(mensagem_sem_time())
            return
        await _responder_acao_jogo(update, acao)
        return

    resposta = str(decisao.get("resposta") or "").strip()
    if not resposta:
        resposta = resposta_conversa(texto, time_salvo)
    await update.message.reply_text(resposta)


async def _processar_salvar_time(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    nome: str,
) -> None:
    candidatos = buscar_times_por_nome(nome)
    if not candidatos:
        await update.message.reply_text("Nao achei esse time. Tenta de novo com outro nome.")
        return

    if len(candidatos) == 1:
        time = candidatos[0]
        salvar_time(chat_id, int(time["id"]), str(time["nome"]))
        context.user_data.pop("candidatos_times", None)
        await update.message.reply_text(mensagem_time_salvo(str(time["nome"])))
        return

    context.user_data["candidatos_times"] = candidatos
    linhas = ["Achei mais de um. Me manda so o numero do time certo:"]
    for i, t in enumerate(candidatos, start=1):
        linhas.append(f"{i}. {t.get('nome')} ({t.get('pais')})")
    await update.message.reply_text("\n".join(linhas))


async def _tratar_escolha_numero(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    texto: str,
) -> None:
    if not texto.isdigit():
        await update.message.reply_text("Me responde so com o numero do time.")
        return

    candidatos = context.user_data.get("candidatos_times", [])
    idx = int(texto) - 1
    if idx < 0 or idx >= len(candidatos):
        await update.message.reply_text("Numero invalido. Tenta de novo.")
        return

    escolhido = candidatos[idx]
    salvar_time(update.effective_chat.id, int(escolhido["id"]), str(escolhido["nome"]))
    context.user_data.pop("candidatos_times", None)
    await update.message.reply_text(mensagem_time_salvo(str(escolhido["nome"])))


async def _responder_acao_jogo(update: Update, acao: str) -> None:
    pref = obter_time(update.effective_chat.id)
    if not pref:
        await update.message.reply_text(mensagem_sem_time())
        return

    team_id = int(pref["team_id"])
    if acao == "proximo_jogo":
        jogo = get_proximo_jogo(team_id)
        contexto = "proximo jogo"
    elif acao == "jogo_hoje":
        jogo = get_jogo_hoje(team_id)
        contexto = "jogo de hoje"
    else:
        jogo = get_jogo_finalizado(team_id)
        contexto = "ultimo jogo"

    if not jogo:
        await update.message.reply_text(mensagem_sem_jogo(contexto))
        return

    await update.message.reply_text(resposta_jogo(acao, jogo, pref.get("team_name")))


async def _post_init(app) -> None:
    task = asyncio.create_task(loop_monitoramento(app))
    app.bot_data["live_tracker_task"] = task
    logger.info("[bot] Live tracker iniciado em background.")


async def _post_stop(app) -> None:
    task = app.bot_data.get("live_tracker_task")
    if not task:
        return
    if task.done():
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("[bot] Live tracker finalizado com shutdown gracioso.")


def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN nao encontrado no .env")

    _setup_safe_logging()
    init_db()

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .post_stop(_post_stop)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("time", set_time))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(CommandHandler("proximo", proximo))
    app.add_handler(CommandHandler("hoje", hoje))
    app.add_handler(CommandHandler("ultimo", ultimo))
    app.add_handler(CommandHandler("aovivo", aovivo))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tratar_mensagem))
    app.run_polling()


if __name__ == "__main__":
    main()
