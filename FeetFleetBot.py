from flask import Flask
import threading

# --- Flask-Webserver, damit Uptime Robot deinen Bot aktiv hält ---
app = Flask('')

@app.route('/')
def home():
    return "Ich bin online!"

def run():
    app.run(host='0.0.0.0', port=8080)

# Starte den Webserver in einem eigenen Thread
threading.Thread(target=run).start()

# --- Telegram-Bot-Code ---
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
import csv
import datetime
import os

# Zustände im Gesprächsverlauf:
# SELECT_TRUCK: LKW auswählen
# TRIP_MENU: Vorgang während der Fahrt wählen
# GET_KM: Kilometerstand eingeben
# GET_LOCATION: Standort abfragen (über Button)
# GET_WEIGHT: Gewicht eingeben
SELECT_TRUCK, TRIP_MENU, GET_KM, GET_LOCATION, GET_WEIGHT = range(5)

# --- Hilfsfunktionen für persistente Kilometerstände ---

def get_persistent_last_km(truck: str):
    """Liest den letzten Kilometerstand für den angegebenen LKW aus der Datei last_km.csv.
       Gibt None zurück, falls kein Eintrag vorhanden ist."""
    filename = "last_km.csv"
    if not os.path.exists(filename):
        return None
    with open(filename, mode="r", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["truck"] == truck:
                try:
                    return int(row["km"])
                except ValueError:
                    return None
    return None

def update_persistent_last_km(truck: str, km_value: int):
    """Aktualisiert oder fügt den letzten Kilometerstand für den LKW in die Datei last_km.csv ein."""
    filename = "last_km.csv"
    last_km_data = {}
    if os.path.exists(filename):
        with open(filename, mode="r", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                last_km_data[row["truck"]] = row["km"]
    last_km_data[truck] = str(km_value)

    with open(filename, mode="w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["truck", "km"])
        writer.writeheader()
        for t, km in last_km_data.items():
            writer.writerow({"truck": t, "km": km})

# --- Tastaturdefinitionen ---

def get_truck_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("LKW 1", callback_data='LKW1')],
        [InlineKeyboardButton("LKW 2", callback_data='LKW2')]
    ])

def get_event_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Fahrt Start melden", callback_data='fahrt_start')],
        [InlineKeyboardButton("Ladung melden", callback_data='laden')],
        [InlineKeyboardButton("Entladung melden", callback_data='entladen')],
        [InlineKeyboardButton("Tanken melden", callback_data='tanken')],
        [InlineKeyboardButton("Grenzübergang melden", callback_data='grenzuebergang')],
        [InlineKeyboardButton("Fahrerwechsel melden", callback_data='fahrerwechsel')],
        [InlineKeyboardButton("Fahrt beenden", callback_data='fahrt_beenden')]
    ])

def get_location_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Bitte Standort teilen", request_location=True)]],
        one_time_keyboard=True,
        resize_keyboard=True
    )

# --- Bot-Funktionen ---

# Start: /start-Befehl
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Willkommen beim Transport-Helfer!\n\nBitte wählen Sie Ihren LKW:",
        reply_markup=get_truck_keyboard()
    )
    return SELECT_TRUCK

# LKW auswählen, Trip-ID erzeugen und in den Zustand TRIP_MENU wechseln.
# Zusätzlich wird ein Flag 'trip_started' auf False gesetzt, um zu signalisieren,
# dass dies der erste Kilometerstand der neuen Fahrt ist.
async def select_truck(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    truck = query.data
    context.user_data['truck'] = truck

    trip_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    context.user_data['trip_id'] = trip_id

    # Reset für neue Fahrt: "trip_started" auf False und "last_km" aus der aktuellen Fahrt löschen
    context.user_data["trip_started"] = False
    context.user_data.pop("last_km", None)

    await query.edit_message_text(
        text=f"Sie haben {truck} gewählt.\nIhre Trip-ID: {trip_id}\n\nBitte wählen Sie einen Vorgang:",
        reply_markup=get_event_keyboard()
    )
    return TRIP_MENU

# Vorgang auswählen und zur Kilometerstandseingabe auffordern
async def select_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event = query.data
    context.user_data['event'] = event

    if event == 'fahrt_start':
        prompt = "Fahrt Start melden:\nGeben Sie bitte den aktuellen Kilometerstand ein:"
    elif event == 'laden':
        prompt = "Ladung melden:\nGeben Sie bitte den aktuellen Kilometerstand ein:"
    elif event == 'entladen':
        prompt = "Entladung melden:\nGeben Sie bitte den aktuellen Kilometerstand ein:"
    elif event == 'tanken':
        prompt = "Tanken melden:\nGeben Sie bitte den aktuellen Kilometerstand ein:"
    elif event == 'grenzuebergang':
        prompt = "Grenzübergang melden:\nGeben Sie bitte den aktuellen Kilometerstand ein:"
    elif event == 'fahrerwechsel':
        prompt = "Fahrerwechsel melden:\nGeben Sie bitte den aktuellen Kilometerstand ein:"
    elif event == 'fahrt_beenden':
        prompt = "Fahrt beenden:\nGeben Sie bitte den aktuellen Kilometerstand ein:"
    else:
        prompt = "Geben Sie bitte den aktuellen Kilometerstand ein:"

    await query.edit_message_text(prompt)
    return GET_KM

# Kilometerstand eingeben, validieren und anschließend Standort abfragen
async def get_km(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    km_input = update.message.text.strip()

    # Leerzeichen sind nicht erlaubt
    if " " in km_input:
        await update.message.reply_text("❌ Fehler: Der Kilometerstand darf keine Leerzeichen enthalten. Bitte geben Sie den Kilometerstand erneut ein:")
        return GET_KM

    # Komma ist NICHT erlaubt bei Kilometerständen
    if "," in km_input:
        await update.message.reply_text("❌ Fehler: Der Kilometerstand darf kein Komma enthalten. Bitte geben Sie den Kilometerstand erneut ein:")
        return GET_KM

    # Nun muss die Eingabe ausschließlich aus Ziffern bestehen
    if not km_input.isdigit():
        await update.message.reply_text("❌ Fehler: Der Kilometerstand darf nur Ziffern enthalten. Bitte geben Sie den Kilometerstand erneut ein:")
        return GET_KM

    km_value = int(km_input)
    truck = context.user_data.get('truck')

    # Bei Beginn der Fahrt: Vergleiche mit dem letzten persistierten Kilometerstand dieses LKWs
    if not context.user_data.get("trip_started", False):
        persistent_km = get_persistent_last_km(truck)
        if persistent_km is not None and km_value < persistent_km:
            await update.message.reply_text(f"❌ Fehler: Der eingegebene Kilometerstand muss mindestens {persistent_km} betragen, da dies der letzte Kilometerstand der vorherigen Fahrt für {truck} ist. Bitte geben Sie den Kilometerstand erneut ein:")
            return GET_KM

    # Falls bereits ein Kilometerstand in der aktuellen Fahrt existiert, muss der neue Wert größer oder gleich sein
    if "last_km" in context.user_data:
        if km_value < context.user_data["last_km"]:
            await update.message.reply_text("❌ Fehler: Der neue Kilometerstand muss größer oder gleich dem vorherigen Kilometerstand der aktuellen Fahrt sein. Bitte geben Sie den Kilometerstand erneut ein:")
            return GET_KM

    # Speichere den aktuellen Kilometerstand als "last_km" und setze das Flag, dass die Fahrt begonnen hat.
    context.user_data["last_km"] = km_value
    context.user_data["trip_started"] = True

    # Nach erfolgreicher Kilometerstandseingabe: Standort abfragen
    await update.message.reply_text(
        "Bitte teilen Sie Ihren aktuellen Standort:",
        reply_markup=get_location_keyboard()
    )
    return GET_LOCATION

# Standort abfragen (über Button)
async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
        location_str = f"{lat},{lon}"
        context.user_data['location'] = location_str

        await update.message.reply_text(
            "Standort empfangen.\nBitte geben Sie nun das aktuelle Gewicht in Tonnen ein:",
            reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True, one_time_keyboard=True)
        )
        return GET_WEIGHT
    else:
        await update.message.reply_text(
            "Kein Standort empfangen.\nBitte teilen Sie Ihren Standort über den Button:",
            reply_markup=get_location_keyboard()
        )
        return GET_LOCATION

# Gewicht eingeben, validieren, Daten speichern und ggf. Fahrt beenden
async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    weight_input = update.message.text.strip()

    # Keine Leerzeichen erlaubt
    if " " in weight_input:
        await update.message.reply_text("❌ Fehler: Das Gewicht darf keine Leerzeichen enthalten. Bitte geben Sie das Gewicht erneut ein:")
        return GET_WEIGHT

    # Ersetze Komma durch Punkt, um Fließkommazahlen zu ermöglichen
    try:
        weight_value = float(weight_input.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Fehler: Das Gewicht darf nur Ziffern enthalten (Komma als Dezimaltrennzeichen ist erlaubt). Bitte geben Sie das Gewicht erneut ein:")
        return GET_WEIGHT

    # Validierung: Gewicht muss zwischen 0 und 25 Tonnen liegen
    if weight_value < 0 or weight_value > 25:
        await update.message.reply_text("❌ Fehler: Das Gewicht muss zwischen 0 und 25 Tonnen liegen. Bitte geben Sie das Gewicht erneut ein:")
        return GET_WEIGHT

    truck = context.user_data.get('truck')
    event = context.user_data.get('event')
    km = context.user_data.get('last_km')  # Dieser Wert wurde in get_km gesetzt
    location = context.user_data.get('location', 'Nicht angegeben')
    trip_id = context.user_data.get('trip_id')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Erstelle den Dateinamen für diese Fahrt
    file_name = f"transport_data_{trip_id}.csv"

    if not os.path.isfile(file_name):
        with open(file_name, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["LKW", "Vorgang", "Kilometer", "Standort", "Gewicht", "Zeit", "Trip-ID"])

    with open(file_name, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([truck, event, km, location, weight_value, timestamp, trip_id])

    # Bei "Fahrt beenden" wird der persistente Kilometerstand aktualisiert
    if event == 'fahrt_beenden':
        update_persistent_last_km(truck, km)
        await update.message.reply_text(
            f"Fahrt beendet für {truck}.\nTrip-ID: {trip_id}\nVielen Dank!\nStarten Sie eine neue Fahrt mit /start."
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            f"Folgende Daten wurden gespeichert:\nLKW: {truck}\nVorgang: {event}\nKilometer: {km}\nStandort: {location}\nGewicht: {weight_value} Tonnen\nZeit: {timestamp}\nTrip-ID: {trip_id}\n\nBitte wählen Sie den nächsten Vorgang oder beenden Sie die Fahrt:",
            reply_markup=get_event_keyboard()
        )
        return TRIP_MENU

# Abbruchfunktion
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Vorgang abgebrochen.")
    elif update.callback_query:
        await update.callback_query.edit_message_text("Vorgang abgebrochen.")
    return ConversationHandler.END

def main():
    # Ersetze "YOUR_TOKEN_HERE" durch deinen echten Bot-Token
    app_bot = ApplicationBuilder().token("7739598034:AAEoNVvtz_yHIj67ftBIuo9vQqBcFUvEv2M").build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECT_TRUCK: [CallbackQueryHandler(select_truck)],
            TRIP_MENU: [CallbackQueryHandler(select_event)],
            GET_KM: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_km)],
            GET_LOCATION: [MessageHandler(filters.LOCATION, get_location)],
            GET_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app_bot.add_handler(conv_handler)
    app_bot.run_polling()

if __name__ == '__main__':
    main()

