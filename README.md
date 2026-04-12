# Torcedor Bot

Bot de Telegram para torcedores acompanharem seu time com linguagem natural, resultados e notificacoes ao vivo.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Telegram](https://img.shields.io/badge/Telegram-Bot-2CA5E0)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)

## Visao geral
O projeto usa tres fontes principais:
- Gemini: interpreta intencao do usuario e gera respostas conversacionais.
- ESPN (scraping): proximo jogo, jogo de hoje e ultimo resultado.
- football-data.org: status ao vivo e eventos (gol, cartao, penalti, etc.).

Fluxo principal:
1. Usuario salva o time (`/time Flamengo` ou linguagem natural).
2. Pergunta por texto livre (ex: "quando joga?", "como foi o ultimo?").
3. Bot responde usando dados normalizados e contexto do time salvo.
4. Em paralelo, um loop em background monitora partidas ao vivo e envia notificacoes automaticas.

## Funcionalidades atuais
- Cadastro de time por chat no Telegram (persistido em SQLite).
- Busca de times por nome/alias (dicionario local de clubes brasileiros).
- Comandos:
  - `/start`
  - `/time <nome>`
  - `/limpar`
  - `/proximo`
  - `/hoje`
  - `/ultimo`
  - `/aovivo`
- Interpretacao de linguagem natural para:
  - salvar time
  - proximo jogo
  - jogo de hoje
  - ultimo jogo
  - conversa geral
- Monitoramento ao vivo em background com notificacoes de:
  - inicio
  - gol
  - cartao vermelho
  - penalti
  - intervalo
  - segundo tempo
  - fim de jogo
- Controle de resiliencia no live tracker:
  - agrupamento de usuarios por time (menos chamadas na API)
  - tratamento de falha temporaria (ex.: 429) sem reset imediato de estado
  - limpeza de estado apenas apos misses consecutivos

## Arquitetura (arquivos)
- `bot.py`: entrada principal, handlers Telegram e inicializacao do loop de monitoramento.
- `ai_message.py`: interpretacao de intencao (fallback local + Gemini) e formatacao de respostas.
- `football_api.py`: scraping da ESPN e normalizacao de jogos (proximo/hoje/ultimo).
- `football_live.py`: integracao com football-data.org para jogos ao vivo.
- `live_tracker.py`: loop assincromo de monitoramento e disparo de notificacoes.
- `database.py`: persistencia SQLite de inscricoes e estado do jogo ao vivo.
- `teste_live.py`: script de simulacao local de notificacoes (nao usado em producao).

## Stack
- Python 3.11+
- `python-telegram-bot`
- `requests`
- `beautifulsoup4`
- `python-dotenv`
- `sqlite3` (nativo)

## Pre-requisitos
- Token do bot Telegram (`TELEGRAM_TOKEN`)
- Chave Gemini (`GEMINI_API_KEY`) para NLP/conversa
- Token football-data.org (`FOOTBALL_DATA_TOKEN`) para live

## Instalacao
1. Clone o repositorio
2. (Opcional) crie um ambiente virtual
3. Instale dependencias:

```bash
pip install -r requirements.txt
```

4. Crie `.env` na raiz:

```env
TELEGRAM_TOKEN=seu_token_telegram
GEMINI_API_KEY=sua_chave_gemini
FOOTBALL_DATA_TOKEN=seu_token_football_data
```

## Execucao
```bash
python bot.py
```

## Como funciona o monitoramento ao vivo
- O bot inicia `loop_monitoramento` no `post_init` do Telegram app.
- A cada ciclo (`POLL_INTERVAL`), usuarios sao agrupados por `team_id`.
- Para cada time, consulta-se a API live e compara com o ultimo estado salvo em banco.
- Diferencas viram eventos e geram mensagens no Telegram.

## Banco de dados
Arquivo local: `torcedor.db`

Tabelas atuais:
- `subscriptions`:
  - `chat_id` (PK)
  - `team_id`
  - `team_name`
  - `created_at`
- `live_state`:
  - `chat_id` (PK)
  - `state_json`
  - `updated_at`

## Limitacoes conhecidas
- O scraping da ESPN pode quebrar se a estrutura HTML mudar.
- O dicionario de clubes e local (lista fixa no codigo).
- Dados ao vivo dependem da cobertura e limites do plano da football-data.org.
- Nao ha suite de testes automatizados no repositório ainda.

## Seguranca e versionamento
- `.env`, `*.db`, `*.pyc` e `__pycache__/` estao no `.gitignore`.
- Nao commitar tokens/chaves.

## Roadmap sugerido
- Adicionar testes automatizados para tracker e parser.
- Tornar mapeamento de times (ESPN <-> football-data) mais dinamico.
- Adicionar observabilidade basica (metricas de eventos, erros por ciclo).
- Melhorar mensagens para cenarios de indisponibilidade de API.

## Licenca
Uso livre para estudo e evolucao do projeto.
