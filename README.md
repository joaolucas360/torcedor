# Torcedor Bot

Bot de Telegram conversacional para acompanhar jogos do seu time com linguagem natural.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Telegram](https://img.shields.io/badge/Telegram-Bot-2CA5E0)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)

## Visão geral
O projeto combina IA + scraping para entregar respostas rápidas sobre futebol sem depender de API paga de partidas.

Você pode conversar de forma natural, por exemplo:
- `sou flamengo`
- `quando joga?`
- `como foi o ultimo jogo?`
- `tem jogo hoje?`

## Funcionalidades
- Interpretação de linguagem natural com Gemini
- Fluxo conversacional no Telegram
- Persistência de time por usuário (SQLite)
- Busca de próximos jogos e últimos resultados via scraping da ESPN
- Comandos clássicos de fallback para compatibilidade

## Stack
- Python 3.11+
- `python-telegram-bot`
- `requests`
- `beautifulsoup4`
- `sqlite3` (nativo)
- Gemini API

## Estrutura do projeto
- `bot.py` -> handlers do Telegram e orquestração
- `ai_message.py` -> interpretação de intenção e geração de respostas
- `football_api.py` -> scraping e normalização dos dados de jogos
- `database.py` -> persistência de preferências (`torcedor.db`)
- `.env` -> segredos e tokens

## Pré-requisitos
- Token do bot Telegram
- Chave da API Gemini

## Instalação
1. Clone o repositório
2. (Opcional) crie e ative ambiente virtual
3. Instale as dependências:

```bash
pip install -r requirements.txt
```

4. Crie o arquivo `.env`:

```env
TELEGRAM_TOKEN=seu_token_aqui
GEMINI_API_KEY=sua_chave_aqui
```

## Execução
```bash
python bot.py
```

## Comandos disponíveis
- `/start`
- `/time <nome do time>`
- `/limpar`
- `/proximo` (compatibilidade)
- `/hoje` (compatibilidade)
- `/ultimo` (compatibilidade)

## Exemplo de fluxo
1. Usuário: `sou vasco`
2. Bot salva o time
3. Usuário: `quando joga?`
4. Bot responde com próximo jogo formatado
5. Usuário: `como foi o ultimo?`
6. Bot responde com placar e contexto

## Notas importantes
- O bot usa um dicionário local de times em `football_api.py`
- O scraping pode exigir ajuste se o HTML da ESPN mudar
- `.env`, `*.db` e cache Python ficam fora do Git via `.gitignore`

## Roadmap
- Melhorar reconhecimento de times fora do dicionário local
- Adicionar testes automatizados
- Suporte a notificações programadas pré-jogo

## Licença
Uso livre para estudo e evolução do projeto.
