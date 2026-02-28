# Clawbot Pessoal

Bot de terminal para ajudar no dia a dia com tarefas, notas, prioridades, prazos e lembretes.

## Requisitos

- Python 3.9+

## Como rodar

```bash
python3 clawbot.py
```

## Integracao com ChatGPT

1. Instale a SDK da OpenAI:

```bash
pip install -r requirements.txt
```

2. Configure a chave da API:

```bash
export OPENAI_API_KEY="sua_chave_aqui"
```

3. (Opcional) escolha o modelo:

```bash
export OPENAI_MODEL="gpt-4o-mini"
```

4. (Opcional) modelo de transcricao de voz:

```bash
export OPENAI_TRANSCRIBE_MODEL="gpt-4o-mini-transcribe"
```

## Comando de voz (microfone)

- Use `ouvir` para ouvir por 8 segundos e executar o comando falado.
- Use `ouvir <segundos>` para ajustar (entre 2 e 30).
- Atalho antigo ainda aceito: `voz 10` (escuta por 10s).
- Na primeira vez, permita acesso ao microfone no sistema.

## Resposta por voz

- Use `falar on` para o Clawbot falar as respostas.
- Use `falar off` para desativar.
- Use `falar` para ver o status atual.
- Use `voz pt-BR` para voz em portugues do Brasil.
- Use `velocidade 180` para ajustar velocidade (100 a 300).
- A reproducao de voz usa o comando `say` do macOS.

## Comandos

- `help`: mostra ajuda
- `tarefa <texto> | p:<baixa|media|alta> | ate:<YYYY-MM-DD HH:MM>`: cria tarefa com prioridade e prazo opcionais
- `tarefas`: lista tarefas
- `concluir <id>`: marca tarefa como concluida
- `lembrar <id> <YYYY-MM-DD HH:MM>`: define lembrete para tarefa
- `lembretes`: mostra lembretes vencidos e proximos
- `calendario`: gera `clawbot_agenda.ics` para importar no Google Calendar
- `ouvir [segundos]`: ouve no microfone e executa o comando reconhecido
- `falar [on|off]`: ativa/desativa resposta por voz
- `voz [pt-BR|pt-PT|en-US|nome]`: define voz de resposta
- `velocidade [100-300]`: define velocidade da fala
- `gpt <pergunta>`: consulta o ChatGPT usando contexto das tarefas e notas
- `nota <texto>`: salva nota
- `notas`: lista notas
- `resumo`: mostra totais
- `sair`: encerra

## Exemplos

```bash
tarefa pagar aluguel | p:alta | ate:2026-03-05 18:00
lembrar 1 2026-03-05 09:00
calendario
ouvir 10
falar on
voz pt-BR
velocidade 180
gpt monte meu plano de amanha em 5 itens
```

## Persistencia

Os dados ficam em `.clawbot_data.json` na raiz do projeto.
