# Torcedor Bot

Bot de Telegram conversacional para acompanhar jogos do seu time com linguagem natural.

## O que ele faz
- Entende mensagens como:
  - `sou flamengo`
  - `quando joga?`
  - `como foi o ultimo?`
- Salva o time por usuário
- Busca jogos via scraping da ESPN
- Responde no Telegram com texto claro e direto

## Stack
- Python 3.11+
- `python-telegram-bot`
- `requests`
- `beautifulsoup4`
- `sqlite3` (nativo)
- Gemini API (interpretação conversacional)

## Estrutura
- `bot.py`: entrada principal, comandos e fluxo de conversa
- `ai_message.py`: interpretação de intenção e respostas de texto
- `football_api.py`: scraping e normalização dos jogos
- `database.py`: persistência de preferências do usuário
- `.env`: variáveis sensíveis

## Pré-requisitos
- Token de bot do Telegram
- Chave da API Gemini

## Configuração
1. Clone o projeto
2. Crie e ative seu ambiente virtual (opcional, recomendado)
3. Instale as dependências:

```bash
pip install -r requirements.txt
```

4. Crie o `.env`:

```env
TELEGRAM_TOKEN=seu_token_aqui
GEMINI_API_KEY=sua_chave_aqui
```

## Como rodar
```bash
python bot.py
```

## Comandos
- `/start`
- `/time <nome do time>`
- `/limpar`
- `/proximo` (compatibilidade)
- `/hoje` (compatibilidade)
- `/ultimo` (compatibilidade)

## Exemplos de conversa
- `oi`
- `torco pro sao paulo`
- `tem jogo hoje?`
- `resultado do ultimo`

## Observações
- O bot usa um dicionário local de times mapeados em `football_api.py`
- O scraping depende da estrutura da ESPN e pode exigir ajuste no futuro
- `.env` e `*.db` já estão no `.gitignore`

## Licença
Uso livre para estudo e evolução do projeto.
