from telegram.ext import Updater, CommandHandler

# Ersetze 'YOUR_TOKEN_HERE' durch deinen echten Bot-Token von BotFather
updater = Updater("YO7739598034:AAEoNVvtz_yHIj67ftBIuo9vQqBcFUvEv2M", use_context=True)

def start(update, context):
    update.message.reply_text('Hallo, willkommen beim Bot!')

dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))

updater.start_polling()
updater.idle()
