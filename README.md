# Relativity Releases FAQ Chatbot

Chatbot en **Flask (Python)** que responde preguntas **exclusivamente** con la documentación oficial de **Relativity** (Release Notes) para:
- **Relativity One**
- **Server 2024**
- **Server 2023**

Si una consulta no está cubierta, el bot solicita **datos de contacto** (nombre, email, organización) y los registra en **Google Sheets** junto con un timestamp y el contexto de la pregunta.

## ✨ Características
- **Modos**: Quick, Guided, Power.
- **Respuestas con citas** a la documentación relevante.
- **Captura de contacto** + **registro en Google Sheets**.
- **Historial por versión**; **nuevo chat** por versión.
- **Exportación** de conversación a **PDF/JSON**.
- **Compartir** última respuesta por **Gmail / WhatsApp / Telegram**.
- **Voz**: entrada por micrófono (HTTPS/localhost) y lectura en voz alta (TTS).
- **Login / Registro / Perfil**: tema (morado por defecto), foto, limpiar historial, logout.

---

## 🚀 Demo local (rápida)

> Windows / PowerShell (Python 3.11 recomendado)

```powershell
# 1) Crear y activar entorno
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) Instalar dependencias
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3) (Opcional) Variables de entorno temporales
$env:PORT="5055"             # Puerto HTTP local
# $env:GOOGLE_APPLICATION_CREDENTIALS="C:\ruta\service-account.json"
# $env:GOOGLE_SHEETS_SPREADSHEET_ID="TU_SPREADSHEET_ID"

# 4) Ejecutar
python -u app.py
# Abre: http://127.0.0.1:5055

