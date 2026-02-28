#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


DATA_FILE = Path(".clawbot_data.json")
ICS_FILE = Path("clawbot_agenda.ics")
PRIORITIES = {"baixa", "media", "alta"}
DATE_INPUT_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_SPEECH_RATE = 180
DEFAULT_TTS_VOICE = "pt-BR"
VOICE_PRESETS = {
    "pt-BR": ["Luciana", "Fernanda", "Joana"],
    "pt-PT": ["Joana"],
    "en-US": ["Samantha", "Alex"],
}

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None


@dataclass
class Task:
    id: int
    text: str
    done: bool
    created_at: str
    priority: str
    due_at: Optional[str]
    remind_at: Optional[str]


@dataclass
class Note:
    id: int
    text: str
    created_at: str


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def load_data() -> dict:
    if not DATA_FILE.exists():
        return {
            "tasks": [],
            "notes": [],
            "settings": {
                "voice_reply": False,
                "tts_voice": DEFAULT_TTS_VOICE,
                "speech_rate": DEFAULT_SPEECH_RATE,
            },
        }
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "tasks": [],
            "notes": [],
            "settings": {
                "voice_reply": False,
                "tts_voice": DEFAULT_TTS_VOICE,
                "speech_rate": DEFAULT_SPEECH_RATE,
            },
        }

    # Backward compatibility for older data files.
    for task in data.get("tasks", []):
        task.setdefault("priority", "media")
        task.setdefault("due_at", None)
        task.setdefault("remind_at", None)
    data.setdefault("notes", [])
    data.setdefault("tasks", [])
    data.setdefault("settings", {})
    data["settings"].setdefault("voice_reply", False)
    data["settings"].setdefault("tts_voice", DEFAULT_TTS_VOICE)
    data["settings"].setdefault("speech_rate", DEFAULT_SPEECH_RATE)
    return data


def save_data(data: dict) -> None:
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def next_id(items: list[dict]) -> int:
    if not items:
        return 1
    return max(item["id"] for item in items) + 1


def parse_user_datetime(raw: str) -> Optional[datetime]:
    try:
        return datetime.strptime(raw.strip(), DATE_INPUT_FORMAT)
    except ValueError:
        return None


def format_task_line(task: dict) -> str:
    status = "x" if task["done"] else " "
    due = f" | ate: {task['due_at']}" if task.get("due_at") else ""
    remind = f" | lembrar: {task['remind_at']}" if task.get("remind_at") else ""
    return (
        f'- [{status}] #{task["id"]} {task["text"]}'
        f' | prioridade: {task.get("priority", "media")}{due}{remind}'
    )


def add_task(
    data: dict,
    text: str,
    priority: str = "media",
    due_at: Optional[str] = None,
) -> str:
    task = Task(
        id=next_id(data["tasks"]),
        text=text,
        done=False,
        created_at=now_iso(),
        priority=priority,
        due_at=due_at,
        remind_at=None,
    )
    data["tasks"].append(asdict(task))
    save_data(data)
    extra = f" prioridade={priority}"
    if due_at:
        extra += f" prazo={due_at}"
    return f"Tarefa #{task.id} criada ({extra.strip()})."


def list_tasks(data: dict) -> str:
    if not data["tasks"]:
        return "Sem tarefas."
    lines = ["Tarefas:"]
    ordered = sorted(
        data["tasks"],
        key=lambda t: (
            t.get("done", False),
            {"alta": 0, "media": 1, "baixa": 2}.get(t.get("priority", "media"), 1),
            t.get("due_at") or "9999-12-31 23:59",
            t["id"],
        ),
    )
    for task in ordered:
        lines.append(format_task_line(task))
    return "\n".join(lines)


def complete_task(data: dict, task_id: int) -> str:
    for task in data["tasks"]:
        if task["id"] == task_id:
            if task["done"]:
                return f"Tarefa #{task_id} ja estava concluida."
            task["done"] = True
            save_data(data)
            return f"Tarefa #{task_id} concluida."
    return f"Tarefa #{task_id} nao encontrada."


def set_reminder(data: dict, task_id: int, remind_at: str) -> str:
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["remind_at"] = remind_at
            save_data(data)
            return f"Lembrete da tarefa #{task_id} definido para {remind_at}."
    return f"Tarefa #{task_id} nao encontrada."


def add_note(data: dict, text: str) -> str:
    note = Note(
        id=next_id(data["notes"]),
        text=text,
        created_at=now_iso(),
    )
    data["notes"].append(asdict(note))
    save_data(data)
    return f"Nota #{note.id} salva."


def list_notes(data: dict) -> str:
    if not data["notes"]:
        return "Sem notas."
    lines = ["Notas:"]
    for note in data["notes"]:
        lines.append(f'- #{note["id"]} {note["text"]}')
    return "\n".join(lines)


def summary(data: dict) -> str:
    total = len(data["tasks"])
    done = len([t for t in data["tasks"] if t["done"]])
    pending = total - done
    notes = len(data["notes"])
    return (
        "Resumo:\n"
        f"- Tarefas: {total}\n"
        f"- Concluidas: {done}\n"
        f"- Pendentes: {pending}\n"
        f"- Notas: {notes}"
    )


def reminders(data: dict) -> str:
    now = datetime.now()
    due = []
    upcoming = []
    for task in data["tasks"]:
        if task.get("done"):
            continue
        remind_at = task.get("remind_at")
        if not remind_at:
            continue
        dt = parse_user_datetime(remind_at)
        if not dt:
            continue
        if dt <= now:
            due.append(task)
        else:
            upcoming.append((dt, task))

    lines = []
    if due:
        lines.append("Lembretes vencidos/agora:")
        for task in due:
            lines.append(format_task_line(task))
    if upcoming:
        lines.append("Proximos lembretes:")
        for _, task in sorted(upcoming, key=lambda x: x[0]):
            lines.append(format_task_line(task))
    if not lines:
        return "Sem lembretes ativos."
    return "\n".join(lines)


def to_ics_timestamp(raw: str) -> Optional[str]:
    dt = parse_user_datetime(raw)
    if not dt:
        return None
    return dt.strftime("%Y%m%dT%H%M%S")


def export_calendar(data: dict) -> str:
    events = []
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for task in data["tasks"]:
        if task.get("done"):
            continue
        when = task.get("remind_at") or task.get("due_at")
        if not when:
            continue
        dt = to_ics_timestamp(when)
        if not dt:
            continue
        uid = f"{uuid4()}@clawbot"
        summary = task["text"].replace(",", "\\,").replace(";", "\\;")
        desc = (
            f"Task #{task['id']} | prioridade: {task.get('priority', 'media')}"
            .replace(",", "\\,")
            .replace(";", "\\;")
        )
        event = (
            "BEGIN:VEVENT\n"
            f"UID:{uid}\n"
            f"DTSTAMP:{now_utc}\n"
            f"DTSTART:{dt}\n"
            f"DTEND:{dt}\n"
            f"SUMMARY:{summary}\n"
            f"DESCRIPTION:{desc}\n"
            "END:VEVENT\n"
        )
        events.append(event)

    if not events:
        return "Nenhuma tarefa com prazo/lembrete para exportar."

    content = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//Clawbot//PT-BR//EN\n"
        + "".join(events)
        + "END:VCALENDAR\n"
    )
    ICS_FILE.write_text(content, encoding="utf-8")
    return f"Calendario exportado em {ICS_FILE} com {len(events)} evento(s)."


def build_context(data: dict) -> str:
    pending_tasks = [t for t in data["tasks"] if not t.get("done")]
    pending_tasks = sorted(
        pending_tasks,
        key=lambda t: (
            {"alta": 0, "media": 1, "baixa": 2}.get(t.get("priority", "media"), 1),
            t.get("due_at") or "9999-12-31 23:59",
            t["id"],
        ),
    )[:12]
    recent_notes = data["notes"][-8:]

    task_lines = [format_task_line(t) for t in pending_tasks] or ["(sem tarefas pendentes)"]
    note_lines = [f'- #{n["id"]} {n["text"]}' for n in recent_notes] or ["(sem notas)"]

    return (
        "Contexto do usuario:\n"
        + "\n".join(task_lines)
        + "\nNotas recentes:\n"
        + "\n".join(note_lines)
    )


def ask_gpt(data: dict, prompt: str) -> str:
    if OpenAI is None:
        return "Biblioteca 'openai' nao instalada. Rode: pip install openai"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Defina OPENAI_API_KEY no ambiente para usar o comando gpt."

    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    client = OpenAI(api_key=api_key)

    system_prompt = (
        "Voce e o Clawbot pessoal do usuario. Responda em portugues do Brasil, "
        "de forma curta, pratica e orientada a acao."
    )
    user_input = build_context(data) + "\nPedido do usuario:\n" + prompt

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        )
    except Exception as exc:
        return f"Falha ao consultar ChatGPT: {exc}"

    text = getattr(response, "output_text", "").strip()
    if text:
        return text
    return "Nao consegui extrair uma resposta textual do ChatGPT."


def is_voice_reply_enabled(data: dict) -> bool:
    return bool(data.get("settings", {}).get("voice_reply", False))


def set_voice_reply(data: dict, enabled: bool) -> str:
    data.setdefault("settings", {})
    data["settings"]["voice_reply"] = enabled
    save_data(data)
    state = "ativada" if enabled else "desativada"
    return f"Resposta por voz {state}."


def get_speech_rate(data: dict) -> int:
    val = data.get("settings", {}).get("speech_rate", DEFAULT_SPEECH_RATE)
    try:
        num = int(val)
    except (TypeError, ValueError):
        return DEFAULT_SPEECH_RATE
    return num


def get_tts_voice(data: dict) -> str:
    return str(data.get("settings", {}).get("tts_voice", DEFAULT_TTS_VOICE))


def list_system_voices() -> Optional[set]:
    say_bin = shutil.which("say")
    if not say_bin:
        return None
    try:
        out = subprocess.run(
            [say_bin, "-v", "?"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    voices = set()
    for line in out.stdout.splitlines():
        chunks = line.split()
        if chunks:
            voices.add(chunks[0].strip())
    return voices


def resolve_voice_choice(choice: str, system_voices: Optional[set]) -> Tuple[Optional[str], Optional[str]]:
    selected = choice.strip()
    if not selected:
        return None, "Informe uma voz. Exemplo: voz pt-BR"
    preset_key = selected.lower()
    for key in VOICE_PRESETS:
        if key.lower() == preset_key:
            for candidate in VOICE_PRESETS[key]:
                if system_voices is None or candidate in system_voices:
                    return candidate, None
            return None, f"Nenhuma voz disponivel para {key} neste sistema."
    if system_voices is not None and selected not in system_voices:
        return None, f"Voz '{choice}' nao encontrada no sistema."
    return selected, None


def set_tts_voice(data: dict, choice: str) -> str:
    system_voices = list_system_voices()
    selected, err = resolve_voice_choice(choice, system_voices)
    if err:
        return err
    data.setdefault("settings", {})
    data["settings"]["tts_voice"] = selected
    save_data(data)
    return f"Voz de resposta definida para '{selected}'."


def set_speech_rate(data: dict, value: str) -> str:
    if not value.isdigit():
        return "Velocidade invalida. Exemplo: velocidade 180"
    speed = int(value)
    if speed < 100 or speed > 300:
        return "Use velocidade entre 100 e 300."
    data.setdefault("settings", {})
    data["settings"]["speech_rate"] = speed
    save_data(data)
    return f"Velocidade de fala definida para {speed}."


def tts_status(data: dict) -> str:
    voice_state = get_tts_voice(data)
    speed = get_speech_rate(data)
    return f"Voz atual: {voice_state} | velocidade: {speed}"


def speak_text(text: str, data: dict) -> Optional[str]:
    if os.getenv("CLAWBOT_MUTE") == "1":
        return None
    if not text.strip():
        return None

    say_bin = shutil.which("say")
    if not say_bin:
        return "Comando 'say' nao encontrado no sistema para resposta por voz."

    # Keep speech concise to avoid very long TTS playback.
    normalized = " ".join(text.split())
    snippet = normalized[:320]
    voice = get_tts_voice(data)
    speed = get_speech_rate(data)
    system_voices = list_system_voices()
    resolved_voice, _ = resolve_voice_choice(voice, system_voices)
    cmd = [say_bin, "-r", str(speed)]
    if resolved_voice:
        cmd.extend(["-v", resolved_voice])
    cmd.append(snippet)
    try:
        subprocess.run(cmd, check=True)
    except Exception as exc:
        return f"Falha ao reproduzir voz: {exc}"
    return None


def transcribe_microphone(seconds: int) -> Tuple[Optional[str], Optional[str]]:
    if sr is None:
        return None, "Biblioteca 'SpeechRecognition' nao instalada. Rode: pip install SpeechRecognition pyaudio"
    if OpenAI is None:
        return None, "Biblioteca 'openai' nao instalada. Rode: pip install openai"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "Defina OPENAI_API_KEY no ambiente para usar o comando de voz."

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("Ouvindo... fale agora.")
            recognizer.adjust_for_ambient_noise(source, duration=0.6)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=seconds)
    except Exception as exc:
        return None, f"Falha ao capturar audio do microfone: {exc}"

    wav_bytes = audio.get_wav_data()
    model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    client = OpenAI(api_key=api_key)

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            tmp.write(wav_bytes)
            tmp.flush()
            tmp.seek(0)
            transcript = client.audio.transcriptions.create(
                model=model,
                file=tmp,
                language="pt",
            )
    except Exception as exc:
        return None, f"Falha ao transcrever audio: {exc}"

    text = getattr(transcript, "text", "").strip()
    if not text:
        return None, "Nao consegui entender a fala."
    return text, None


def execute_voice_command(data: dict, seconds: int) -> str:
    transcribed, err = transcribe_microphone(seconds)
    if err:
        return err

    spoken = (transcribed or "").strip()
    if not spoken:
        return "Nenhum comando reconhecido."

    lowered = spoken.lower()
    if lowered.startswith("voz") or lowered.startswith("ouvir"):
        return f'Voce disse: "{spoken}"\nComando de voz em cadeia bloqueado para evitar loop.'

    result = handle_command(spoken, data)
    return f'Voce disse: "{spoken}"\n{result}'


def parse_task_command(
    payload: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    # Example:
    # tarefa pagar conta | p:alta | ate:2026-03-05 18:00
    if not payload.strip():
        return None, None, None

    parts = [p.strip() for p in payload.split("|")]
    text = parts[0]
    priority = "media"
    due_at = None

    for part in parts[1:]:
        if part.startswith("p:"):
            val = part.removeprefix("p:").strip().lower()
            if val not in PRIORITIES:
                return None, None, None
            priority = val
        elif part.startswith("ate:"):
            val = part.removeprefix("ate:").strip()
            if not parse_user_datetime(val):
                return None, None, None
            due_at = val
        else:
            return None, None, None
    if not text:
        return None, None, None
    return text, priority, due_at


HELP_TEXT = """Comandos:
  help                         mostra esta ajuda
  tarefa <texto> | p:<nivel> | ate:<YYYY-MM-DD HH:MM>
                               cria tarefa com prioridade e prazo opcionais
  tarefas                      lista tarefas
  concluir <id>                conclui tarefa
  lembrar <id> <YYYY-MM-DD HH:MM>
                               define lembrete para uma tarefa
  lembretes                    mostra lembretes ativos
  calendario                   exporta .ics para importar no Google Calendar
  ouvir [segundos]             ouve no microfone e executa comando (padrao: 8s)
  falar [on|off]               ativa/desativa resposta por voz do Clawbot
  voz [pt-BR|pt-PT|en-US|nome] define voz da resposta (ou mostra status)
  velocidade [100-300]         define velocidade da resposta por voz
  gpt <pergunta>               conversa com ChatGPT usando contexto do Clawbot
  nota <texto>                 salva nota
  notas                        lista notas
  resumo                       resumo geral
  sair                         fecha o Clawbot
"""


def handle_command(raw: str, data: dict) -> str:
    cmd = raw.strip()
    if not cmd:
        return "Digite um comando. Use 'help'."

    if cmd == "help":
        return HELP_TEXT.rstrip()
    if cmd == "tarefas":
        return list_tasks(data)
    if cmd == "notas":
        return list_notes(data)
    if cmd == "resumo":
        return summary(data)
    if cmd == "lembretes":
        return reminders(data)
    if cmd == "calendario":
        return export_calendar(data)
    if cmd == "falar":
        state = "ativada" if is_voice_reply_enabled(data) else "desativada"
        return f"Resposta por voz esta {state}."
    if cmd == "falar on":
        return set_voice_reply(data, True)
    if cmd == "falar off":
        return set_voice_reply(data, False)
    if cmd == "voz":
        return tts_status(data)
    if cmd.startswith("voz "):
        val = cmd.removeprefix("voz ").strip()
        if val.isdigit():
            seconds = int(val)
            if seconds < 2 or seconds > 30:
                return "Use entre 2 e 30 segundos."
            return execute_voice_command(data, seconds=seconds)
        return set_tts_voice(data, val)
    if cmd == "ouvir":
        return execute_voice_command(data, seconds=8)
    if cmd.startswith("ouvir "):
        val = cmd.removeprefix("ouvir ").strip()
        if not val.isdigit():
            return "Formato invalido. Exemplo: ouvir 10"
        seconds = int(val)
        if seconds < 2 or seconds > 30:
            return "Use entre 2 e 30 segundos."
        return execute_voice_command(data, seconds=seconds)
    if cmd == "velocidade":
        return f"Velocidade atual: {get_speech_rate(data)}"
    if cmd.startswith("velocidade "):
        return set_speech_rate(data, cmd.removeprefix("velocidade ").strip())
    if cmd.startswith("gpt "):
        question = cmd.removeprefix("gpt ").strip()
        if not question:
            return "Use: gpt <pergunta>"
        return ask_gpt(data, question)
    if cmd.startswith("tarefa "):
        parsed = parse_task_command(cmd.removeprefix("tarefa ").strip())
        if parsed[0] is None:
            return (
                "Formato invalido. Exemplo:\n"
                "tarefa pagar conta | p:alta | ate:2026-03-10 18:00"
            )
        text, priority, due_at = parsed
        return add_task(data, text, priority=priority, due_at=due_at)
    if cmd.startswith("nota "):
        return add_note(data, cmd.removeprefix("nota ").strip())
    if cmd.startswith("lembrar "):
        match = re.match(r"^lembrar\s+(\d+)\s+(.+)$", cmd)
        if not match:
            return "Formato invalido. Exemplo: lembrar 2 2026-03-10 09:00"
        task_id = int(match.group(1))
        when = match.group(2).strip()
        if not parse_user_datetime(when):
            return "Data invalida. Use YYYY-MM-DD HH:MM"
        return set_reminder(data, task_id, when)
    if cmd.startswith("concluir "):
        val = cmd.removeprefix("concluir ").strip()
        if not val.isdigit():
            return "ID invalido. Exemplo: concluir 2"
        return complete_task(data, int(val))
    return "Comando nao reconhecido. Use 'help'."


def main() -> None:
    data = load_data()
    print("Clawbot pessoal iniciado. Use 'help' para comandos.")
    while True:
        try:
            raw = input("clawbot> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaindo.")
            break
        if raw in {"sair", "exit", "quit"}:
            print("Saindo.")
            break
        output = handle_command(raw, data)
        print(output)
        if is_voice_reply_enabled(data):
            err = speak_text(output, data)
            if err:
                print(err)


if __name__ == "__main__":
    main()
