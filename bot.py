"""
bot.py
Bot Telegram conversacional para acompanhar jogos do time escolhido.
"""
from __future__ import annotations

import os
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

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Fala! Bora acompanhar seu time? Me diz qual time voce torce ou manda /time <nome do time> 😄"
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


async def tratar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = (update.message.text or "").strip()
    if not texto:
        return

    # Se o usuario estiver escolhendo um time por numero, prioriza isso.
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


def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN nao encontrado no .env")

    init_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("time", set_time))
    app.add_handler(CommandHandler("limpar", limpar))

    # Mantidos por compatibilidade, mas o fluxo principal e conversacional.
    app.add_handler(CommandHandler("proximo", proximo))
    app.add_handler(CommandHandler("hoje", hoje))
    app.add_handler(CommandHandler("ultimo", ultimo))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tratar_mensagem))
    app.run_polling()


if __name__ == "__main__":
    main()
