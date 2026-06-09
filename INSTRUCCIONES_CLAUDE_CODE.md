# Instrucciones para Claude Code

## Qué eres
Estás construyendo PsiAgente: un agente de Telegram para gestión de citas
de la psicóloga Dra. Marysol Beltrán.

## Qué hacer paso a paso

1. Lee main.py completo — el código ya está escrito
2. Instala dependencias: `pip install -r requirements.txt`
3. Crea el archivo .env con las variables de .env.example
4. Corre el SQL de supabase_setup.sql en Supabase > SQL Editor
5. Verifica que las tablas existan en Supabase
6. Corre: `python main.py`
7. Si hay errores de importación, instala el paquete faltante con pip

## Variables que necesitas del usuario antes de correr
- ANTHROPIC_API_KEY → su API key de Anthropic
- TELEGRAM_TOKEN → el token del bot de Telegram (BotFather)
- SUPABASE_URL → URL del proyecto Supabase
- SUPABASE_KEY → anon key de Supabase
- PSYCHOLOGIST_TELEGRAM_ID → pedirle a la Dra. Marysol que te mande
  su ID de Telegram (puede obtenerlo escribiéndole a @userinfobot)

## Qué NO cambiar
- El SYSTEM_PROMPT es deliberado, no lo simplifiques
- El protocolo de crisis es crítico, no lo elimines
- La función save_history guarda solo los últimos 20 mensajes (diseño intencional)

## Cuando funcione
Dile al usuario: "Escríbele a tu bot en Telegram para probarlo"
