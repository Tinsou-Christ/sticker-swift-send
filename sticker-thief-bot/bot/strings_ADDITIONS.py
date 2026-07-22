# === A. Ajouter cette ligne dans START_MESSAGE, juste après la ligne "/add ..." ===
#                      "/add to add stickers to an existing pack\n"
#                      "/import to convert a Telegram pack to WhatsApp stickers\n"
#                      "/help for more commands\n")

# === B. Ajouter cette ligne dans HELP_MESSAGE, juste après la ligne "- /add: ..." ===
#                     "- /add: add a stickers to a pack\n"
#                     "- /import: convert a whole Telegram stickers pack to WhatsApp "
#                     "(.wastickers) files, 30 stickers per file\n"

# === C. Ajouter ces nouvelles Strings n'importe où dans la classe Strings (par ex. apres EXPORT_ONGOING) ===

    IMPORT_PACK_SELECT = "Please send me a sticker from the Telegram pack you want to convert to WhatsApp, or /cancel"

    IMPORT_PACK_NO_PACK = "This sticker doesn't belong to any pack. Please send me a sticker from a pack, or /cancel"

    IMPORT_PACK_PROCESSING = "⌛ Your request for the pack is now processing..."

    IMPORT_PACK_STARTING = (
        "🚀 Starting conversion for your pack...\n"
        "🤔 Estimated time: ~{} minute(s)"
    )

    IMPORT_PACK_DETAILS = (
        "📊 Pack Details:\n"
        "• Name: {}\n"
        "• Total stickers: {}\n"
        "• This will create {} .wastickers file(s)."
    )

    IMPORT_PACK_COMPLETE = "✅ Conversion complete! Sending {} file(s)..."

    IMPORT_PACK_SKIPPED_STICKERS = "\n⚠️ {} sticker(s) could not be converted and were skipped."

    IMPORT_ANIMATED_NOT_SUPPORTED = (
        "⚠️ This pack contains animated (.tgs) stickers. They will be converted too, but this "
        "requires the optional 'lottie' package on the server; if it's missing they'll be skipped."
    )

    IMPORT_ONGOING = "Hold on, a pack conversion is already processing..."
