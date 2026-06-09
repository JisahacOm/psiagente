from dotenv import load_dotenv
load_dotenv()

import os
import json
import asyncio
import requests
from datetime import datetime
from anthropic import Anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client

MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}

# ── Clientes ──────────────────────────────────────────────────────────────────
anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
supabase  = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

SYSTEM_PROMPT = """
Eres Sofía, la asistente virtual de la Psic. Marysol Beltrán, psicóloga clínica.

Tu único rol es gestionar citas: recibir pacientes, agendar, confirmar y hacer seguimiento.
NO realizas terapia, NO das consejos psicológicos, NO diagnosticas.

── IDIOMA ────────────────────────────────────────────────────────────────────
Detecta automáticamente el idioma del paciente (español o inglés) y responde
en ese mismo idioma desde el primer mensaje. No lo cambies durante la conversación.

── PERSONALIDAD ──────────────────────────────────────────────────────────────
- Cálida, profesional y empática
- Nunca robótica ni con menús numerados
- Respuestas cortas (2-4 líneas máximo en WhatsApp/Telegram)
- Usa el nombre del paciente cuando lo sepas

── FLUJO DE AGENDAMIENTO ─────────────────────────────────────────────────────
1. Saluda y pregunta en qué puedes ayudar
2. Si quiere cita: pide nombre completo y número de contacto en un solo mensaje — "Para agendar tu cita, ¿me compartes tu nombre completo y número de contacto?"
3. Informa disponibilidad: Lunes a Viernes 9am–7pm, Sábados 9am–2pm (Tijuana, México)
4. Confirma día y hora específicos
5. Muestra el resumen completo de la cita (nombre, fecha, hora) y pregunta explícitamente: "¿Confirmas tu cita?" o "¿Todo correcto?"
6. SOLO después de que el paciente responda afirmativamente: llama a save_appointment
7. Despídete cálidamente e incluye el link de ubicación: https://maps.app.goo.gl/xjbDU7EJVJKfmrj68?g_st=ic

── REAGENDAMIENTO ────────────────────────────────────────────────────────────
Si el paciente quiere cambiar su cita existente:
1. Confirma que desea reagendar (no cancelar)
2. Pide el nuevo día y hora
3. Confirma los nuevos datos con el paciente
4. Llama a reschedule_appointment — esto marca la cita anterior como "rescheduled" y crea la nueva

── CANCELACIÓN ───────────────────────────────────────────────────────────────
Si el paciente quiere cancelar su cita:
1. Confirma que desea cancelar definitivamente
2. Ofrece reagendar en su lugar antes de proceder
3. Si confirma la cancelación, llama a cancel_appointment — esto marca la cita como "cancelled_by_patient"
4. Despídete con amabilidad y recuerda que puede volver a agendar cuando quiera

── DISPONIBILIDAD ────────────────────────────────────────────────────────────
La fecha actual es: {fecha_actual}. Úsala como referencia para interpretar fechas que el paciente mencione sin año.
Cuando el paciente mencione una fecha ambigua (sin año, sin día de semana, o que corrija una fecha anterior), SIEMPRE confirma antes de continuar y espera su respuesta. No asumas la fecha hasta que el paciente confirme.
Reglas para interpretar el año:
- Si el mes mencionado ya pasó en el año actual ({fecha_actual}), pregunta: "¿Quisiste decir [mes] de 2027?"
- Si el mes es el actual o futuro dentro del año actual, confirma: "¿Quisiste decir el [día] de [mes] de 2026?"
Nunca repitas literalmente lo que el paciente escribió sin verificar que tenga sentido con la fecha actual.
Solo considera ocupados los horarios de citas con status "confirmed". Citas con status "rescheduled" o "cancelled_by_patient" liberan ese horario.
Por ahora usa disponibilidad fija:
- Lunes a Viernes: 9:00, 10:00, 11:00, 12:00, 15:00, 16:00, 17:00, 18:00, 19:00
- Sábados: 9:00, 10:00, 11:00, 12:00, 13:00
Duración de cada sesión: 50 minutos
Modalidad: únicamente presencial en Tijuana. No ofrecer ni mencionar videollamada.

── INFORMACIÓN DEL CONSULTORIO ───────────────────────────────────────────────
- Psicóloga: Psic. Marysol Beltrán
- Costo por sesión: $800 MXN
- Ubicación: Edificio Verde, segundo piso al fondo a la izquierda, Tijuana
- Google Maps: https://maps.app.goo.gl/xjbDU7EJVJKfmrj68?g_st=ic
- Para emergencias del consultorio: responde con el número directo de la Psic. Marysol

Todas las citas son presenciales. Siempre incluye el link de ubicación al confirmar: https://maps.app.goo.gl/xjbDU7EJVJKfmrj68?g_st=ic

── 🚨 PROTOCOLO DE CRISIS — PRIORIDAD MÁXIMA ─────────────────────────────────
Si el paciente expresa ideación suicida, autolesión, abuso, o angustia severa:

1. DETÉN inmediatamente el flujo de agendamiento
2. Responde con calidez, SIN minimizar lo que siente
3. Proporciona estas líneas de ayuda:
   - SAPTEL (24/7): 55 5259-8121
   - IMSS Línea de la Vida: 800 890 3200
   - Emergencias: 911
4. Ofrece contactar directamente a la Psic. Marysol
5. Llama a la función flag_crisis para alertar a la psicóloga

Señales a detectar (no solo palabras literales, evalúa el contexto emocional):
- Menciones de hacerse daño, no querer seguir, sentirse sin salida
- Desesperanza extrema, despedidas, regalar posesiones
- Abuso activo o situación de peligro inmediato

── LO QUE NO HACES ───────────────────────────────────────────────────────────
- No interpretas sueños, no das diagnósticos, no haces terapia
- No discutes honorarios más allá del costo por sesión
- No agendas fuera del horario establecido sin confirmación
- No compartes información de otros pacientes
"""

# ── Funciones del agente ───────────────────────────────────────────────────────
tools = [
    {
        "name": "save_appointment",
        "description": "Guarda una cita confirmada en la base de datos",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_name":  {"type": "string", "description": "Nombre completo del paciente"},
                "phone":         {"type": "string", "description": "Número de contacto"},
                "date":          {"type": "string", "description": "Fecha de la cita YYYY-MM-DD"},
                "time":          {"type": "string", "description": "Hora de la cita HH:MM"},
                "telegram_id":   {"type": "string", "description": "ID de Telegram del paciente"}
            },
            "required": ["patient_name", "phone", "date", "time", "telegram_id"]
        }
    },
    {
        "name": "reschedule_appointment",
        "description": "Reagenda una cita: marca la cita activa del paciente como 'rescheduled' y crea una nueva con los datos actualizados",
        "input_schema": {
            "type": "object",
            "properties": {
                "telegram_id":  {"type": "string", "description": "ID de Telegram del paciente"},
                "patient_name": {"type": "string", "description": "Nombre completo del paciente"},
                "phone":        {"type": "string", "description": "Número de contacto"},
                "date":         {"type": "string", "description": "Nueva fecha YYYY-MM-DD"},
                "time":         {"type": "string", "description": "Nueva hora HH:MM"}
            },
            "required": ["telegram_id", "patient_name", "phone", "date", "time"]
        }
    },
    {
        "name": "cancel_appointment",
        "description": "Cancela la cita activa del paciente cambiando su status a 'cancelled_by_patient'",
        "input_schema": {
            "type": "object",
            "properties": {
                "telegram_id": {"type": "string", "description": "ID de Telegram del paciente"}
            },
            "required": ["telegram_id"]
        }
    },
    {
        "name": "flag_crisis",
        "description": "Alerta a la psicóloga cuando un paciente expresa una crisis emocional",
        "input_schema": {
            "type": "object",
            "properties": {
                "telegram_id": {"type": "string"},
                "patient_name": {"type": "string"},
                "summary":     {"type": "string", "description": "Breve resumen de la situación"}
            },
            "required": ["telegram_id", "summary"]
        }
    }
]

def save_appointment(data: dict) -> str:
    try:
        supabase.table("appointments").insert({
            "patient_name": data["patient_name"],
            "phone":        data["phone"],
            "date":         data["date"],
            "time":         data["time"],
            "modality":     "presencial",
            "telegram_id":  data["telegram_id"],
            "created_at":   datetime.utcnow().isoformat(),
            "status":       "confirmed"
        }).execute()
        return "Cita guardada correctamente."
    except Exception as e:
        return f"Error al guardar: {e}"

def reschedule_appointment(data: dict) -> str:
    try:
        res = supabase.table("appointments") \
            .select("id") \
            .eq("telegram_id", data["telegram_id"]) \
            .eq("status", "confirmed") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if res.data:
            supabase.table("appointments") \
                .update({"status": "rescheduled"}) \
                .eq("id", res.data[0]["id"]) \
                .execute()
        supabase.table("appointments").insert({
            "patient_name": data["patient_name"],
            "phone":        data["phone"],
            "date":         data["date"],
            "time":         data["time"],
            "modality":     "presencial",
            "telegram_id":  data["telegram_id"],
            "created_at":   datetime.utcnow().isoformat(),
            "status":       "confirmed"
        }).execute()
        return "Cita reagendada correctamente."
    except Exception as e:
        return f"Error al reagendar: {e}"

def cancel_appointment(data: dict) -> str:
    try:
        res = supabase.table("appointments") \
            .select("id") \
            .eq("telegram_id", data["telegram_id"]) \
            .eq("status", "confirmed") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if not res.data:
            return "No se encontró cita activa para cancelar."
        supabase.table("appointments") \
            .update({"status": "cancelled_by_patient"}) \
            .eq("id", res.data[0]["id"]) \
            .execute()
        return "Cita cancelada correctamente."
    except Exception as e:
        return f"Error al cancelar: {e}"

def flag_crisis(data: dict, bot_token: str, psych_telegram_id: str) -> str:
    name = data.get("patient_name", "Paciente desconocido")
    tid  = data["telegram_id"]
    msg  = (
        f"🚨 ALERTA DE CRISIS\n\n"
        f"Paciente: {name}\n"
        f"Telegram ID: {tid}\n"
        f"Situación: {data['summary']}\n\n"
        f"Por favor contacta al paciente directamente."
    )
    requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": psych_telegram_id, "text": msg}
    )
    return "Alerta enviada a la Psic. Marysol."

# ── Serialización de bloques SDK ──────────────────────────────────────────────
def blocks_to_dicts(content) -> list:
    """Convierte bloques SDK de Anthropic a dicts serializables en JSON."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input
            })
    return result

# ── Memoria por chat_id ────────────────────────────────────────────────────────
def get_history(chat_id: str) -> list:
    try:
        res = supabase.table("conversations") \
            .select("messages") \
            .eq("chat_id", chat_id) \
            .execute()
        if res.data:
            return res.data[0]["messages"]
        return []
    except Exception as e:
        print(f"[ERROR get_history chat_id={chat_id}] {e}")
        return []

def save_history(chat_id: str, messages: list):
    try:
        supabase.table("conversations").upsert({
            "chat_id":    chat_id,
            "messages":   messages,
            "updated_at": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        print(f"[ERROR save_history chat_id={chat_id}] {e}")

# ── Comando /cancelar (solo psicóloga) ────────────────────────────────────────
async def handle_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    psych_id  = os.environ.get("PSYCHOLOGIST_TELEGRAM_ID", "")
    sender_id = str(update.effective_chat.id)

    if sender_id != psych_id:
        await update.message.reply_text("Solo la Psic. Marysol puede usar este comando.")
        return

    raw = " ".join(context.args) if context.args else ""
    if not raw:
        await update.message.reply_text("Uso: /cancelar [nombre paciente] | [motivo opcional]")
        return

    if "|" in raw:
        nombre, motivo = raw.split("|", 1)
        nombre = nombre.strip()
        motivo = motivo.strip()
    else:
        nombre = raw.strip()
        motivo  = None

    try:
        res = supabase.table("appointments") \
            .select("id, telegram_id, date, time, patient_name") \
            .ilike("patient_name", f"%{nombre}%") \
            .eq("status", "confirmed") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
    except Exception as e:
        await update.message.reply_text(f"Error al buscar la cita: {e}")
        return

    if not res.data:
        await update.message.reply_text(f"No encontré cita activa para '{nombre}'.")
        return

    appt       = res.data[0]
    patient_tid = appt["telegram_id"]
    first_name  = appt["patient_name"].split()[0]
    hora_str    = str(appt["time"])[:5]

    try:
        dt       = datetime.strptime(str(appt["date"]), "%Y-%m-%d")
        fecha_fmt = f"{dt.day} de {MESES[dt.month]}"
    except Exception:
        fecha_fmt = str(appt["date"])

    motivo_txt = motivo if motivo else "motivos personales"
    msg = (
        f"Hola {first_name} 🙏 Te pido una gran disculpa, la Psic. Marysol tuvo que cancelar "
        f"tu cita del {fecha_fmt} a las {hora_str} por {motivo_txt}. "
        f"Disculpa el inconveniente, cuando quieras reagendar aquí estamos 💪"
    )

    bot_token = os.environ["TELEGRAM_TOKEN"]
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": patient_tid, "text": msg}
    )

    if resp.status_code == 200:
        supabase.table("appointments") \
            .update({"status": "cancelled_by_doctor"}) \
            .eq("id", appt["id"]) \
            .execute()
        await update.message.reply_text(
            f"✅ Mensaje enviado a {appt['patient_name']} y cita cancelada."
        )
    else:
        await update.message.reply_text(f"Error enviando mensaje al paciente: {resp.text}")

# ── Handler principal de Telegram ─────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id   = str(update.effective_chat.id)
    user_text = update.message.text

    history = get_history(chat_id)
    before = len(history)
    print(f"[HIST] chat_id={chat_id} | ANTES: {before} mensajes")
    history.append({"role": "user", "content": user_text})

    fecha_actual  = datetime.now().strftime("%d de %B de %Y")
    system_prompt = SYSTEM_PROMPT.replace("{fecha_actual}", fecha_actual)

    # Llamada a Claude con tools
    response = anthropic.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system_prompt,
        tools=tools,
        messages=history
    )

    bot_token       = os.environ["TELEGRAM_TOKEN"]
    psych_id        = os.environ.get("PSYCHOLOGIST_TELEGRAM_ID", "")
    assistant_text  = ""
    tool_was_called = False

    for block in response.content:
        if block.type == "text":
            assistant_text += block.text

        elif block.type == "tool_use":
            if not tool_was_called:
                tool_was_called = True
                # Guarda el turno del asistente como dicts serializables (Bug 1)
                history.append({"role": "assistant", "content": blocks_to_dicts(response.content)})

            # Inyecta el chat_id real — Claude no conoce el telegram_id del usuario
            tool_input = {**block.input, "telegram_id": chat_id}

            if block.name == "save_appointment":
                result = save_appointment(tool_input)
            elif block.name == "reschedule_appointment":
                result = reschedule_appointment(tool_input)
            elif block.name == "cancel_appointment":
                result = cancel_appointment(tool_input)
            elif block.name == "flag_crisis":
                result = flag_crisis(tool_input, bot_token, psych_id)
            else:
                result = "Función no reconocida."

            # Devuelve resultado del tool a Claude para que continúe
            history.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": block.id, "content": result}
            ]})
            followup = anthropic.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=512,
                system=system_prompt,
                tools=tools,
                messages=history
            )
            for b2 in followup.content:
                if b2.type == "text":
                    assistant_text += b2.text
            # Agrega la respuesta del followup al historial (Bug 2)
            history.append({"role": "assistant", "content": blocks_to_dicts(followup.content)})

    if assistant_text:
        await update.message.reply_text(assistant_text)
        if not tool_was_called:
            # Si no hubo tool call, el turno del asistente aún no está en history
            history.append({"role": "assistant", "content": assistant_text})
        save_history(chat_id, history)
        print(f"[HIST] chat_id={chat_id} | DESPUÉS: {len(history)} mensajes guardados")

# ── Arranque ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(os.environ["TELEGRAM_TOKEN"]).build()
    app.add_handler(CommandHandler("cancelar", handle_cancelar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ PsiAgente corriendo...")
    app.run_polling()
