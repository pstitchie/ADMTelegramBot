import os
import logging
from datetime import datetime, date # Import date
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Logging ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Google Sheets Setup ===
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
try:
    # Attempt to load credentials from the environment variable first
    # This is safer for deployment environments like Heroku, Railway, etc.
    if os.getenv("GSPREAD_CREDENTIALS"):
        import json
        creds_json = json.loads(os.getenv("GSPREAD_CREDENTIALS"))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    else:
        # Fallback to local file if environment variable is not set
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

    client = gspread.authorize(creds)
    sheet = client.open("AnthonyDarkoMinistriesBot")
    logger.info("Successfully connected to Google Sheets.")
except Exception as e:
    logger.critical(f"Failed to connect to Google Sheets: {e}")
    # If Google Sheets connection is critical, exit the application
    # In a production bot, you might want to implement retry logic or alerts
    exit(1)

# Define worksheet names and their respective headers
worksheet_data = {
    "Members": ["User ID", "Name", "Phone", "Country", "Timestamp"],
    "Prayers": ["User ID", "Name", "Prayer Request", "Timestamp"], # Added 'Name' to Prayers sheet header
    "Partners": ["User ID", "Partner Type", "Name", "Phone", "Country", "Amount", "Timestamp", "Payment Proof File ID"],
    "School of Discipleship": ["User ID", "Name", "Phone", "Country", "Timestamp"],
    "Master Class": ["User ID", "Name", "Phone", "Country", "Timestamp"],
    "Daily Messages": ["Date", "Scripture", "Motivational Message"] # NEW: Daily Messages Worksheet
}

# Initialize worksheets and add headers if they don't exist
for name, headers in worksheet_data.items():
    try:
        worksheet = sheet.worksheet(name)
        # Check if headers exist (by checking if the first row is empty)
        if not worksheet.row_values(1):
            worksheet.append_row(headers)
            logger.info(f"Added headers to '{name}' worksheet.")
    except gspread.exceptions.WorksheetNotFound:
        logger.info(f"Worksheet '{name}' not found, creating it...")
        worksheet = sheet.add_worksheet(title=name, rows="100", cols="10")
        worksheet.append_row(headers)
        logger.info(f"Created and added headers to '{name}' worksheet.")
    except Exception as e:
        logger.critical(f"Error setting up worksheet '{name}': {e}")
        exit(1) # Critical error, bot cannot function without sheets

# Assign worksheet objects for easy access
members_sheet = sheet.worksheet("Members")
prayer_sheet = sheet.worksheet("Prayers")
partner_sheet = sheet.worksheet("Partners")
school_sheet = sheet.worksheet("School of Discipleship")
masterclass_sheet = sheet.worksheet("Master Class")
daily_messages_sheet = sheet.worksheet("Daily Messages") # NEW: Daily Messages Sheet Object

# === Config ===
# Use environment variables for sensitive information (BOT_TOKEN, ADMIN_ID)
# Provide default values for local testing, but ensure they are set in production
BOT_TOKEN = os.getenv("BOT_TOKEN", "8052602429:AAEwV1qU5oyBKCK2Kg3tHzfBiyvAcZMYHPc")
# Ensure ADMIN_ID is an integer
ADMIN_ID = int(os.getenv("ADMIN_ID", "7159818971"))

# === States ===
# Renamed and added new states for the enhanced partner flow
(
    LANG_SELECT, MENU,
    PARTNER_MAIN_OPTIONS, PARTNER_GIVE_OPTIONS, PARTNER_PARTNER_OPTIONS, # New states for nested partner menu
    PARTNER_DETAILS_NAME, PARTNER_DETAILS_PHONE, PARTNER_DETAILS_COUNTRY,
    PARTNER_PAYMENT_METHOD, PARTNER_AMOUNT, PARTNER_PAYMENT_PROOF,
    PRAYER_NAME, PRAYER_INPUT, # Added PRAYER_NAME state
    MEMBER_NAME, MEMBER_PHONE, MEMBER_COUNTRY,
    SCHOOL_NAME, SCHOOL_PHONE, SCHOOL_COUNTRY,
    MASTER_NAME, MASTER_PHONE, MASTER_COUNTRY,
    CONTACT_ADMIN_INFO # New state for contact admin details
) = range(23) # Increased range to accommodate new states

# === Languages & Translations ===
LANGUAGES = {
    "English 🇬🇧": "en",
    "Español 🇪🇸": "es",
    "Français 🇫🇷": "fr",
    "Português 🇧🇷": "pt"
}
user_languages = {} # Stores user's selected language

translations = {
    "welcome": {
        "en": "Welcome to Anthony Darko Ministries!\n\nVision: Raising Kingdom Ambassadors (Matthew 28:19–20)\nMission: Spreading the message of hope and power through Christ (Romans 1:16)",
        "es": "¡Bienvenido a Anthony Darko Ministries!\n\nVisión: Levantando embajadores del Reino (Mateo 28:19–20)\nMisión: Difundir el mensaje de esperanza y poder a través de Cristo (Romanos 1:16)",
        "fr": "Bienvenue chez Anthony Darko Ministries !\n\nVision : Élever des ambassadeurs du Royaume (Matthieu 28:19–20)\nMission : Propager le message d'espoir et de puissance par le Christ (Romans 1:16)",
        "pt": "Bem-vindo ao Anthony Darko Ministries!\n\nVisão: Levantar embaixadores do Reino (Mateus 28:19–20)\nMissão: Espalhar o mensagem de esperança e poder através de Cristo (Romans 1:16)"
    },
    "menu": {
        "en": "Please choose an option:",
        "es": "Por favor elija una opción:",
        "fr": "Veuillez choisir una opción :",
        "pt": "Por favor, escolha uma opção:"
    },
    "buttons": {
        "en": ["👤 Member Sign-Up", "🙏 Prayer Request", "📚 School of Discipleship", "🎓 Master Class", "💰 Give or Partner", "📊 Admin Dashboard"],
        "es": ["👤 Registro de miembro", "🙏 Solicitud de oración", "📚 Escuela de discipulado", "🎓 Clase Magistral", "💰 Donar o Asociarse", "📊 Panel de Administración"],
        "fr": ["👤 Devenir membre", "🙏 Demande de prière", "📚 École de discipolat", "🎓 Cours magistral", "💰 Donner ou Partenaire", "📊 Tableau de bord Admin"],
        "pt": ["👤 Inscrever-se como membro", "🙏 Pedido de oração", "📚 Escola de discipulado", "🎓 Aula Magna", "💰 Dar ou Parceiro", "📊 Painel de Administração"]
    },
    "partner_main_options_prompt": {
        "en": "Please choose a giving or partnership category:",
        "es": "Por favor, elija una categoría de donación o asociación:",
        "fr": "Veuillez choisir une catégorie de don ou de partenariat :",
        "pt": "Por favor, escolha uma categoria de doação ou parceria:"
    },
    "partner_give_options": { # Updated scriptures for Offering and Seed of Faith
        "en": ["Tithe (Malachi 3:10)", "Offering (2 Corinthians 9:7)", "Seed of Faith (Luke 6:38)"],
        "es": ["Diezmo (Malaquías 3:10)", "Ofrenda (2 Corintios 9:7)", "Semilla de Fe (Lucas 6:38)"],
        "fr": ["Dîme (Malachie 3:10)", "Offrande (2 Corinthiens 9:7)", "Graine de Foi (Luc 6:38)"],
        "pt": ["Dízimo (Malaquias 3:10)", "Oferta (2 Coríntios 9:7)", "Semente de Fé (Lucas 6:38)"]
    },
    "partner_partner_options": {
        "en": ["Partner with Man of God", "Ministry Partner", "Angels on Assignment"],
        "es": ["Asociarse con Hombre de Dios", "Socio del Ministerio", "Ángeles en Asignación"],
        "fr": ["Partenaire avec l'Homme de Dieu", "Partenaire du Ministère", "Anges en Mission"],
        "pt": ["Parceiro com Homem de Deus", "Parceiro do Ministério", "Anjos em Missão"]
    },
    "back": {
        "en": "↩️ Back to Menu",
        "es": "↩️ Volver al Menú",
        "fr": "↩️ Retour au Menu",
        "pt": "↩️ Voltar ao Menu"
    },
    "back_to_partner_categories": {
        "en": "⬅️ Back to Partner Categories",
        "es": "⬅️ Volver a Categorías de Socio",
        "fr": "⬅️ Retour aux Catégories de Partenariat",
        "pt": "⬅️ Voltar para Categorias de Parceiro"
    },
    "lang_prompt": "Please select your language / Por favor seleccione su idioma / Veuillez choisir votre langue / Por favor selecione seu idioma",
    "prompt_name": {
        "en": "Please enter your full name:",
        "es": "Por favor, ingrese su nombre completo:",
        "fr": "Veuillez entrer votre nom completo :",
        "pt": "Por favor, digite seu nome completo:"
    },
    "prompt_phone": {
        "en": "Please enter your phone number (e.g., +1234567890):",
        "es": "Por favor, ingrese su número de teléfono (ej. +1234567890):",
        "fr": "Veuillez entrer votre numéro de téléphone (ex. +1234567890) :",
        "pt": "Por favor, digite seu número de telefone (ex. +1234567890):"
    },
    "prompt_country": {
        "en": "Please enter your country (e.g., South Africa, USA):",
        "es": "Por favor, ingrese su país (ej. Sudáfrica, EE. UU.):",
        "fr": "Veuillez entrer your país (ex. Afrique du Sud, États-Unis) :",
        "pt": "Por favor, digite seu país (ex. África do Sul, EUA):"
    },
    "prompt_prayer": {
        "en": "Type your prayer request:",
        "es": "Escriba su solicitud de oración:",
        "fr": "Écrivez su demande de prière :",
        "pt": "Digite seu pedido de oração:"
    },
    "prompt_amount": {
        "en": "Please enter the amount you want to give (e.g., 100.00):",
        "es": "Por favor, ingrese la cantidad que desea dar (ej. 100.00):",
        "fr": "Veuillez entrer le montant que vous souhaitez donner (ex. 100.00) :",
        "pt": "Por favor, digite o valor que deseja doar (ex. 100.00):"
    },
    "prompt_payment_proof": {
        "en": "Once payment is made, please upload proof of payment and Admin will contact you as soon as proof of payment is verified, Thank you for your support in the Kingdom,",
        "es": "Una vez realizado el pago, por favor, suba el comprobante de pago y el Administrador se pondrá en contacto contigo tan pronto como se verifique el comprobante de pago. ¡Gracias por tu apoyo en el Reino!",
        "fr": "Una vez el pago hecho, por favor, sube el comprobante de pago y el Administrador te contactará tan pronto como se verifique el comprobante de pago. ¡Gracias por tu apoyo en el Reino!",
        "pt": "Uma vez que o pagamento seja feito, por favor, envie o comprovante de pagamento e o Administrador entrará em contacto assim que o comprovante de pagamento for verificado. Obrigado pelo seu apoio no Reino!"
    },
    "payment_sa": {
        "en": "�🇦 *South Africa Payment Options:*\n\n*Mobile Money (Capitec, Absa, Nedbank, FNB, Standard Bank):*\nSend to: `067 797 9198`\n\n_\"Gather my saints together unto me; those that have made a covenant with me by sacrifice.\" (Psalm 50:5)_",
        "es": "🇿🇦 *Opciones de Pago en Sudáfrica:*\n\n*Dinero Móvil (Capitec, Absa, Nedbank, FNB, Standard Bank):*\nEnviar a: `067 797 9198`\n\n_\"Juntadme mis santos, los que hicieron conmigo pacto con sacrificio.\" (Salmo 50:5)_",
        "fr": "🇿🇦 *Opciones de Pago en Afrique du Sud:*\n\n*Mobile Money (Capitec, Absa, Nedbank, FNB, Standard Bank):*\nEnvoyer à : `067 797 9198`\n\n_\"Rassemblez-moi mes saints, Qui ont fait alliance avec moi par le sacrifice !\" (Psaumes 50:5)_",
        "pt": "🇿🇦 *Opciones de Pagamento na África do Sul:*\n\n*Dinheiro Móvil (Capitec, Absa, Nedbank, FNB, Standard Bank):*\nEnviar para: `067 797 9198`\n\n_\"Congregai a mim os meus santos, aqueles que fizeram comigo aliança com sacrifícios.\" (Salmos 50:5)_"
    },
    "payment_international": { # Updated MTN MOMO details and scripture
        "en": "🌍 *International Payment Options:*\n\n*PayPal:*\nEmail: `anthonydarkoministries@gmail.com`\n\n*MTN MOMO - GHANA:*\n+233592289243 (Wendy N. Darko)\nReference: ADM(Tithe, Offering, Seed, Gift, Partner etc.)\n\n*For Remitly, World Remit, MoneyGram, Western Union:*\nPlease contact Admin for more details.\n\n_\"Gather my saints together unto me; those that have made a covenant with me by sacrifice.\" (Psalm 50:5)_",
        "es": "🌍 *Opciones de Pago Internacionales:*\n\n*PayPal:*\nCorreo electrónico: `anthonydarkoministries@gmail.com`\n\n*MTN MOMO - GHANA:*\n+233592289243 (Wendy N. Darko)\nReferencia: ADM(Diezmo, Ofrenda, Semilla, Donación, Socio, etc.)\n\n*Para Remitly, World Remit, MoneyGram, Western Union:*\nPor favor, contacte al Administrador para más detalles.\n\n_\"Juntadme mis santos, los que hicieron conmigo pacto con sacrificio.\" (Salmo 50:5)_",
        "fr": "🌍 *Opciones de Pago Internacionales:*\n\n*PayPal:*\nEmail : `anthonydarkoministries@gmail.com`\n\n*MTN MOMO - GHANA:*\n+233592289243 (Wendy N. Darko)\nRéférence : ADM(Dîme, Offrande, Semence, Don, Partenaire, etc.)\n\n*Pour Remitly, World Remit, MoneyGram, Western Union:*\nVeuillez contacter l'administrador para más detalles.\n\n_\"Rassemblez-moi mes saints, Qui ont fait alliance avec moi par le sacrifice !\" (Psaumes 50:5)_",
        "pt": "🌍 *Opciones de Pagamento Internacionais:*\n\n*PayPal:*\nE-mail: `anthonydarkoministries@gmail.com`\n\n*MTN MOMO - GHANA:*\n+233592289243 (Wendy N. Darko)\nReferência: ADM(Dízimo, Oferta, Semente, Doação, Parceiro, etc.)\n\n*Para Remitly, World Remit, MoneyGram, Western Union:*\nPor favor, entre em contato com o Administrador para mais detalhes.\n\n_\"Congregai a mim os meus santos, aqueles que fizeram comigo aliança com sacrifícios.\" (Salmos 50:5)_"
    },
    "contact_admin_button": {
        "en": "📞 Contact Admin",
        "es": "📞 Contactar Administrador",
        "fr": "📞 Contacter l'Admin",
        "pt": "📞 Contatar Administrador"
    },
    "admin_contact_info": {
        "en": "You can contact the admin directly on Telegram:\nTelegram ID: `{admin_id}`",
        "es": "Puede contactar al administrador directamente en Telegram:\nID de Telegram: `{admin_id}`",
        "fr": "Vous pouvez contacter l'administrador directamente sur Telegram :\nID Telegram : `{admin_id}`",
        "pt": "Você pode contatar o administrador diretamente no Telegram:\nID do Telegram: `{admin_id}`"
    },
    "invalid_input": {
        "en": "⚠️ Invalid input. Please try again.",
        "es": "⚠️ Entrada inválida. Por favor, inténtelo de nuevo.",
        "fr": "⚠️ Entrée invalide. Veuillez réessayer.",
        "pt": "⚠️ Entrada inválida. Por favor, tente novamente."
    },
    "saved_success": { # Generic success message, not used directly by specific flows anymore
        "en": "✅ Information saved successfully. Thank you for your support!",
        "es": "✅ Información guardada exitosamente. ¡Gracias por su apoyo!",
        "fr": "✅ Informations enregistrées avec succès. Merci pour votre soutien !",
        "pt": "✅ Informações salvas com sucesso. Obrigado pelo seu apoio!"
    },
    "member_signup_success": { # New specific success message for members
        "en": "✅ Information saved successfully, we are pleased to have you as a ministry member. _\"Then the church throughout Judea, Galilee and Samaria enjoyed a time of peace and was strengthened. Living in the fear of the Lord and encouraged by the Holy Spirit, it increased in numbers.\" (Acts 9:31)_",
        "es": "✅ Información guardada exitosamente, nos complace tenerte como miembro del ministerio. _\"Entonces las iglesias tenían paz por toda Judea, Galilea y Samaria; y eran edificadas, andando en el temor del Señor, y se acrecentaban por el consuelo del Espíritu Santo.\" (Hechos 9:31)_",
        "fr": "✅ Informations enregistrées avec succès, nous sommes ravis de vous compter parmi les membres du ministère. _\"L'Église était en paix dans toute la Judée, la Galilée et la Samarie, s'édifiant et marchant dans la crainte du Seigneur, et elle s'accroissait par l'assistance du Saint-Esprit.\" (Actes 9:31)_",
        "pt": "✅ Informações salvas com sucesso, estamos felizes em tê-lo como membro do ministério. _\"Então as igrejas em toda a Judéia, Galiléia e Samaria tinham paz e eram edificadas; e, andando no temor do Senhor e na consolação do Espírito Santo, multiplicavam-se.\" (Atos 9:31)_"
    },
    "school_signup_success": { # New specific success message for school of discipleship
        "en": "✅ Information saved successfully, Thank you for becoming a Disciple of Anthony Darko Ministries.",
        "es": "✅ Información guardada exitosamente, gracias por convertirte en un Discípulo de Anthony Darko Ministries.",
        "fr": "✅ Informations enregistrées con éxito, gracias por convertirte en un Discípulo de Anthony Darko Ministries.",
        "pt": "✅ Informações salvas com sucesso, obrigado por se tornar um Discípulo de Anthony Darko Ministries."
    },
    "masterclass_signup_success": { # New specific success message for master class
        "en": "✅ Information saved successfully. We look forward to your growth in the Master Class!",
        "es": "✅ Información guardada exitosamente. ¡Esperamos tu crecimiento en la Clase Magistral!",
        "fr": "✅ Informations enregistrées con éxito, nous attendons avec impatience votre croissance dans le Cours Magistral !",
        "pt": "✅ Informações salvas com sucesso. Estamos ansiosos pelo seu crescimento na Aula Magna!"
    },
    "prayer_thankyou": { # Updated prayer request message
        "en": "🙏 Prayer request received, we will stand in the gap for you in prayers, God bless you.",
        "es": "🙏 Solicitud de oración recibida, estaremos intercediendo por ti en oración, Dios te bendiga.",
        "fr": "🙏 Demande de prière reçue, nous intercéderons pour vous dans la prière, que Dieu vous bénisse.",
        "pt": "🙏 Pedido de oração recebido, estaremos intercedendo por você em oração, Deus te abençoe."
    },
    "partner_thankyou": {
        "en": "🙌 Thank you for partnering with us! Your seed is blessed. Admin will contact you as soon as proof of payment is verified, Thank you for your support in the Kingdom, _\"Gather my saints together unto me; those that have made a covenant with me by sacrifice.\" (Psalm 50:5)_",
        "es": "🙌 ¡Gracias por asociarte con nosotros! Tu semilla es bendecida. El administrador se pondrá en contacto contigo tan pronto como se verifique el comprobante de pago. ¡Gracias por tu apoyo en el Reino! _\"Juntadme mis santos, los que hicieron conmigo pacto con sacrificio.\" (Salmo 50:5)_",
        "fr": "🙌 Merci de vous être associé à nous ! Votre semence est bénie. L'administrateur vous contactera dès que la preuve de paiement sera vérifiée. Merci pour votre soutien au Royaume ! _\"Rassemblez-moi mes saints, Qui ont fait alliance avec moi par le sacrifice !\" (Psaumes 50:5)_",
        "pt": "🙌 Obrigado por fazer parceria conosco! Sua semente é abençoada. O administrador entrará em contato assim que o comprovante de pagamento for verificado. Obrigado pelo seu apoio no Reino! _\"Congregai a mim os meus santos, aqueles que fizeram comigo aliança com sacrifícios.\" (Salmos 50:5)_"
    },
    "access_denied": {
        "en": "🚫 Access denied. You are not authorized to view this dashboard.",
        "es": "🚫 Acceso denegado. No está autorizado para ver este panel.",
        "fr": "🚫 Accès refusé. Vous n'êtes pas autorisé a consultar este tableau de bord.",
        "pt": "🚫 Acesso negado. Você no está autorizado a ver este panel."
    },
    "unknown_option": {
        "en": "🤔 Unknown option. Please choose from the menu.",
        "es": "🤔 Opción desconocida. Por favor, elija del menú.",
        "fr": "🤔 Opción inconnue. Veuillez elegir dans le menu.",
        "pt": "🤔 Opción desconocida. Por favor, escolha no menu."
    },
    "upload_proof_error": {
        "en": "Please upload a valid photo or document as proof of payment.",
        "es": "Por favor, suba una foto o documento válido como comprobante de pago.",
        "fr": "Veuillez descargar una foto o un documento válido como prueba de pago.",
        "pt": "Por favor, envie una foto o un documento válido como comprobante de pago."
    },
    "error_general": {
        "en": "An unexpected error occurred. Please try again later or contact support.",
        "es": "Ocurrió un error inesperado. Por favor, inténtelo de nuevo más tarde o contacte a soporte.",
        "fr": "Ocurrió un error inesperado. Veuillez réessayer plus tard o contacter le support.",
        "pt": "Ocorreu un error inesperado. Por favor, tente novamente mais tarde o entre em contacto con el soporte."
    },
    "scripture_discipleship": {
        "en": "_\"Therefore go and make disciples of all nations, baptizing them in the name of the Father and of the Son and of the Holy Spirit, and teaching them to obey everything I have commanded you. And surely I am with you always, to the very end of the age.\" (Matthew 28:19-20)_",
        "es": "_\"Por tanto, id, y haced discípulos a todas las naciones, bautizándolos en el nombre del Padre, y del Hijo, y del Espíritu Santo; enseñándoles que guarden todas las cosas que os he mandado; y he aquí yo estoy con vosotros todos los días, hasta el fin del mundo. Amén.\" (Mateo 28:19-20)_",
        "fr": "_\"Allez donc, faites de toutes les nations des disciples, les baptisant au nom du Père, du Fils et du Saint-Esprit, et leur enseignant à observer tout ce que je vous ai prescrit. Et voici, je suis avec vous tous les jours, jusqu'à la fin du monde.\" (Matthieu 28:19-20)_",
        "pt": "_\"Portanto ide, fazei discípulos de todas as nações, batizando-os em nome do Pai, e do Filho, e do Espírito Santo; ensinando-os a observar todas as coisas que vos tenho mandado; e eis que estou convosco todos os dias, até à consumação dos séculos. Amém.\" (Mateo 28:19-20)_"
    },
    "scripture_masterclass": { # Changed to Proverbs 1:5
        "en": "_\"A wise man will hear and increase learning, and a man of understanding will attain wise counsel.\" (Proverbs 1:5)_",
        "es": "_\"Oirá el sabio, y aumentará su saber, y el entendido adquirirá consejo.\" (Proverbios 1:5)_",
        "fr": "_\"Que le sage écoute et augmente son savoir, et que l'homme intelligent acquière de sages conseils.\" (Proverbes 1:5)_",
        "pt": "_\"O sábio ouvirá e crescerá em conhecimento, e o entendido adquirirá sábios conselhos.\" (Provérbios 1:5)_"
    },
    "daily_message_placeholder": { # NEW: Placeholder for when no daily message is found
        "en": "No daily scripture and motivational message found for today.",
        "es": "No se encontró ningún mensaje diario de escritura y motivación para hoy.",
        "fr": "Aucun message quotidien d'écriture et de motivation trouvé pour aujourd'hui.",
        "pt": "Nenhuma mensagem diária de escritura e motivação encontrada para hoje."
    }
}

# === Utility function to get daily message from Google Sheet ===
async def get_daily_message() -> str:
    """Fetches the daily scripture and motivational message from Google Sheet."""
    today_str = date.today().strftime("%Y-%m-%d")
    try:
        # Get all records from the 'Daily Messages' worksheet
        # This assumes the first row is headers: Date, Scripture, Motivational Message
        records = daily_messages_sheet.get_all_records() #

        for record in records:
            if record.get("Date") == today_str:
                scripture = record.get("Scripture", "")
                message = record.get("Motivational Message", "")
                if scripture and message:
                    return f"📖 *Daily Scripture:*\n{scripture}\n\n💡 *Motivational Message:*\n{message}"
                elif scripture:
                    return f"📖 *Daily Scripture:*\n{scripture}"
                elif message:
                    return f"💡 *Motivational Message:*\n{message}"
        
        logger.info(f"No daily message found for {today_str}.")
        return "" # Return empty string if no message found for today

    except gspread.exceptions.WorksheetNotFound:
        logger.error("Daily Messages worksheet not found. Please ensure it exists.")
        return ""
    except Exception as e:
        logger.error(f"Error fetching daily message: {e}")
        return ""

# === Start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiates the bot and prompts for language selection."""
    
    # NEW: Display daily scripture and motivational message
    daily_msg = await get_daily_message()
    if daily_msg:
        await update.message.reply_text(daily_msg, parse_mode="Markdown")
    
    keyboard = [[InlineKeyboardButton(lang, callback_data=code)] for lang, code in LANGUAGES.items()]
    await update.message.reply_text(translations["lang_prompt"], reply_markup=InlineKeyboardMarkup(keyboard))
    return LANG_SELECT

# === Language Selection ===
async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles language selection and displays the welcome message and main menu."""
    query = update.callback_query
    await query.answer()
    lang_code = query.data
    user_languages[query.from_user.id] = lang_code
    # Only display welcome message once after language selection
    await query.message.reply_text(translations["welcome"][lang_code], parse_mode="Markdown") #
    await query.message.reply_text(translations["menu"][lang_code], reply_markup=build_main_menu(lang_code)) #
    return MENU

# === Build Main Menu ===
def build_main_menu(lang: str) -> InlineKeyboardMarkup:
    """Constructs the main menu keyboard based on the selected language."""
    buttons = translations["buttons"][lang] #
    keyboard = [] #
    for i in range(0, len(buttons), 2): #
        row = [InlineKeyboardButton(buttons[i], callback_data=buttons[i])] #
        if i + 1 < len(buttons): #
            row.append(InlineKeyboardButton(buttons[i + 1], callback_data=buttons[i + 1])) #
        keyboard.append(row) #
    return InlineKeyboardMarkup(keyboard) #

# === Language Getter ===
def get_lang(update: Update) -> str:
    """Retrieves the user's selected language or defaults to English."""
    return user_languages.get(update.effective_user.id, "en") #

# === Menu Handler ===
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles selections from the main menu."""
    query = update.callback_query #
    await query.answer() #
    lang = get_lang(update) #
    text = query.data #
    buttons = translations["buttons"][lang] #

    # Clean previous inline keyboard to prevent multiple interactions
    try:
        await query.edit_message_reply_markup(reply_markup=None) #
    except Exception as e:
        logger.warning(f"Failed to clear inline keyboard: {e}") #

    if text == buttons[0]:  # 👤 Member Sign-Up
        await query.message.reply_text(translations["prompt_name"][lang]) #
        return MEMBER_NAME #
    elif text == buttons[1]:  # 🙏 Prayer Request
        await query.message.reply_text(translations["prompt_name"][lang]) # Ask for name first #
        return PRAYER_NAME # Transition to new PRAYER_NAME state #
    elif text == buttons[2]:  # 📚 School of Discipleship
        await query.message.reply_text(translations["scripture_discipleship"][lang], parse_mode="Markdown") #
        await query.message.reply_text(translations["prompt_name"][lang]) #
        return SCHOOL_NAME #
    elif text == buttons[3]:  # 🎓 Master Class
        await query.message.reply_text(translations["scripture_masterclass"][lang], parse_mode="Markdown") #
        await query.message.reply_text(translations["prompt_name"][lang]) #
        return MASTER_NAME #
    elif text == buttons[4]:  # 💰 Give or Partner
        return await show_partner_main_options(update, context) # Call new function #
    elif text == buttons[5]:  # 📊 Admin Dashboard
        if query.from_user.id != ADMIN_ID: #
            await query.message.reply_text(translations["access_denied"][lang]) #
            return MENU #
        try:
            # Fetch all records for counting, ensuring header row is skipped for accurate counts
            # Use max(0, ...) to prevent negative counts if sheets are empty or only have headers
            member_count = max(0, len(members_sheet.get_all_records()) - 1) #
            prayer_count = max(0, len(prayer_sheet.get_all_records()) - 1) #
            partner_count = max(0, len(partner_sheet.get_all_records()) - 1) #
            school_count = max(0, len(school_sheet.get_all_records()) - 1) #
            masterclass_count = max(0, len(masterclass_sheet.get_all_records()) - 1) #

            stats = {
                "Members": member_count,
                "Prayers": prayer_count,
                "Partners": partner_count,
                "School of Discipleship": school_count,
                "Master Class": masterclass_count
            }
            stats_message = "📊 *Admin Dashboard Stats:*\n\n" + "\n".join([f"• {k}: {v}" for k, v in stats.items()]) #
            await query.message.reply_text(stats_message, parse_mode="Markdown") #
        except gspread.exceptions.APIError as api_e: #
            logger.error(f"Google Sheets API error fetching admin stats: {api_e}") #
            # Specific guidance for the header row error
            if "multiple empty cells" in str(api_e) or "A column has been deleted" in str(api_e): #
                await query.message.reply_text(
                    f"⚠️ An error occurred with Google Sheets: The header row in one of your worksheets contains empty cells or a column has been deleted. "
                    f"Please open your Google Sheet ('{sheet.title}') and ensure the very first row (header row) "
                    f"does not have any empty cells *between* column names. Delete any empty columns if necessary. "
                    f"Error details: {api_e.args[0]}",
                    parse_mode="Markdown"
                )
            else:
                await query.message.reply_text(f"⚠️ An API error occurred while fetching stats: {api_e.args[0]}. Please check Google Sheets permissions or try again later.") #
        except Exception as e:
            logger.error(f"General error fetching admin stats: {e}") #
            await query.message.reply_text(translations["error_general"][lang]) #
        finally:
            return MENU #
    elif text == "BACK_TO_MENU":
        await query.message.reply_text(translations["menu"][lang], reply_markup=build_main_menu(lang)) #
        return MENU #
    else:
        await query.message.reply_text(translations["unknown_option"][lang]) #
        return MENU #

# === Helper: Ask Input ===
async def ask_input(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, prompt_key: str, next_state: int) -> int:
    """Helper to store user input and ask the next question."""
    lang = get_lang(update) #
    # For MessageHandler, input comes from update.message.text
    if update.message and update.message.text: #
        context.user_data[key] = update.message.text #
    await update.effective_message.reply_text(translations[prompt_key][lang]) #
    return next_state #

# === Helper: Save to Sheet ===
async def save_to_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet_obj: gspread.Worksheet, keys: list[str], success_message_key: str) -> int:
    """Helper to save collected data to the specified Google Sheet with a custom success message."""
    lang = get_lang(update) #
    user_id = str(update.effective_user.id) #
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Consistent timestamp format #
    data = [user_id] + [context.user_data.get(k, "") for k in keys] + [timestamp] #

    try:
        sheet_obj.append_row(data) #
        await update.effective_message.reply_text(translations[success_message_key][lang], parse_mode="Markdown") #
    except Exception as e:
        logger.error(f"Failed to append row to sheet {sheet_obj.title}: {e}") #
        await update.effective_message.reply_text(translations["error_general"][lang]) #

    await update.effective_message.reply_text(translations["menu"][lang], reply_markup=build_main_menu(lang)) #
    context.user_data.clear() # Clear user data after successful submission #
    return MENU #

# === Member Signup ===
async def set_member_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await ask_input(update, context, "member_name", "prompt_phone", MEMBER_PHONE) #

async def set_member_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.text #
    # Basic validation for phone number: starts with '+' and remaining characters are digits
    if not (phone_number.startswith('+') and phone_number[1:].isdigit()): #
        lang = get_lang(update) #
        await update.message.reply_text(translations["invalid_input"][lang] + "\n" + translations["prompt_phone"][lang]) #
        return MEMBER_PHONE #
    return await ask_input(update, context, "member_phone", "prompt_country", MEMBER_COUNTRY) #

async def set_member_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["member_country"] = update.message.text #
    # Use the new specific success message key
    return await save_to_sheet(update, context, members_sheet, ["member_name", "member_phone", "member_country"], "member_signup_success") #

# === Prayer Request ===
async def set_prayer_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collects the user's name for the prayer request."""
    return await ask_input(update, context, "prayer_name", "prompt_prayer", PRAYER_INPUT) #

async def save_prayer_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_lang(update) #
    user_id = str(update.effective_user.id) #
    prayer_name = context.user_data.get("prayer_name", "N/A") # Get name from user_data #
    prayer_text = update.message.text #
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") #
    try:
        prayer_sheet.append_row([user_id, prayer_name, prayer_text, timestamp]) # Save name and prayer #
        await update.message.reply_text(translations["prayer_thankyou"][lang], parse_mode="Markdown") # Ensure Markdown for consistency #
    except Exception as e:
        logger.error(f"Failed to append prayer request: {e}") #
        await update.message.reply_text(translations["error_general"][lang]) #

    await update.message.reply_text(translations["menu"][lang], reply_markup=build_main_menu(lang)) #
    context.user_data.clear() #
    return MENU #

# === School of Discipleship ===
async def set_school_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await ask_input(update, context, "school_name", "prompt_phone", SCHOOL_PHONE) #

async def set_school_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.text #
    if not (phone_number.startswith('+') and phone_number[1:].isdigit()): #
        lang = get_lang(update) #
        await update.message.reply_text(translations["invalid_input"][lang] + "\n" + translations["prompt_phone"][lang]) #
        return SCHOOL_PHONE #
    return await ask_input(update, context, "school_phone", "prompt_country", SCHOOL_COUNTRY) #

async def set_school_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["school_country"] = update.message.text #
    # Use the new specific success message key
    return await save_to_sheet(update, context, school_sheet, ["school_name", "school_phone", "school_country"], "school_signup_success") #

# === Master Class ===
async def set_master_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await ask_input(update, context, "master_name", "prompt_phone", MASTER_PHONE) #

async def set_master_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.text #
    if not (phone_number.startswith('+') and phone_number[1:].isdigit()): #
        lang = get_lang(update) #
        await update.message.reply_text(translations["invalid_input"][lang] + "\n" + translations["prompt_phone"][lang]) #
        return MASTER_PHONE #
    return await ask_input(update, context, "master_phone", "prompt_country", MASTER_COUNTRY) #

async def set_master_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["master_country"] = update.message.text #
    # Use the new specific success message key
    return await save_to_sheet(update, context, masterclass_sheet, ["master_name", "master_phone", "master_country"], "masterclass_signup_success") #

# === Partner Giving - New Flow ===
async def show_partner_main_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the main 'Give' and 'Partner' options."""
    query = update.callback_query #
    await query.answer() #
    lang = get_lang(update) #

    # Clean previous inline keyboard
    try:
        await query.edit_message_reply_markup(reply_markup=None) #
    except Exception as e:
        logger.warning(f"Failed to clear inline keyboard: {e}") #

    keyboard = [
        [
            InlineKeyboardButton("🎁 Give Options", callback_data="SHOW_GIVE_OPTIONS"), #
            InlineKeyboardButton("🤝 Partner Options", callback_data="SHOW_PARTNER_OPTIONS") #
        ],
        [InlineKeyboardButton(translations["back"][lang], callback_data="BACK_TO_MENU")] #
    ]

    await query.message.reply_text(translations["partner_main_options_prompt"][lang], reply_markup=InlineKeyboardMarkup(keyboard)) #
    return PARTNER_MAIN_OPTIONS #

async def handle_partner_main_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the selection from the main 'Give or Partner' options."""
    query = update.callback_query #
    await query.answer() #
    lang = get_lang(update) #
    selected_option = query.data #

    # Clean previous inline keyboard
    try:
        await query.edit_message_reply_markup(reply_markup=None) #
    except Exception as e:
        logger.warning(f"Failed to clear inline keyboard: {e}") #

    if selected_option == "BACK_TO_MENU": #
        await query.message.reply_text(translations["menu"][lang], reply_markup=build_main_menu(lang)) #
        return MENU #
    elif selected_option == "SHOW_GIVE_OPTIONS": #
        give_options = translations["partner_give_options"][lang] #
        keyboard = [[InlineKeyboardButton(opt, callback_data=f"GIVE_{opt.split(' ')[0].upper()}")] for opt in give_options] #
        keyboard.append([InlineKeyboardButton(translations["back_to_partner_categories"][lang], callback_data="BACK_TO_PARTNER_CATEGORIES")]) #
        await query.message.reply_text("Please select a giving option:", reply_markup=InlineKeyboardMarkup(keyboard)) #
        return PARTNER_GIVE_OPTIONS # New state for specific give options #
    elif selected_option == "SHOW_PARTNER_OPTIONS": #
        partner_options = translations["partner_partner_options"][lang] #
        keyboard = [] #
        for opt in partner_options: #
            cb_data = f"PARTNER_{'_'.join(opt.split(' ')[0:2]).upper()}" if len(opt.split(' ')) > 1 else f"PARTNER_{opt.upper()}" #
            keyboard.append([InlineKeyboardButton(opt, callback_data=cb_data)]) #
        keyboard.append([InlineKeyboardButton(translations["back_to_partner_categories"][lang], callback_data="BACK_TO_PARTNER_CATEGORIES")]) #
        await query.message.reply_text("Please select a partnership option:", reply_markup=InlineKeyboardMarkup(keyboard)) #
        return PARTNER_PARTNER_OPTIONS # New state for specific partner options #
    else: # This handles the actual selection of Tithe, Offering, etc.
        context.user_data["partner_type"] = selected_option # Store the selected type #
        await query.message.reply_text(translations["prompt_name"][lang]) #
        return PARTNER_DETAILS_NAME #

async def handle_partner_give_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles specific 'Give' option selection."""
    query = update.callback_query #
    await query.answer() #
    lang = get_lang(update) #
    selected_option = query.data #

    # Clean previous inline keyboard
    try:
        await query.edit_message_reply_markup(reply_markup=None) #
    except Exception as e:
        logger.warning(f"Failed to clear inline keyboard: {e}") #

    if selected_option == "BACK_TO_PARTNER_CATEGORIES": #
        return await show_partner_main_options(update, context) # Go back to main categories #
    else:
        context.user_data["partner_type"] = selected_option #
        await query.message.reply_text(translations["prompt_name"][lang]) #
        return PARTNER_DETAILS_NAME #

async def handle_partner_partner_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles specific 'Partner' option selection."""
    query = update.callback_query #
    await query.answer() #
    lang = get_lang(update) #
    selected_option = query.data #

    # Clean previous inline keyboard
    try:
        await query.edit_message_reply_markup(reply_markup=None) #
    except Exception as e:
        logger.warning(f"Failed to clear inline keyboard: {e}") #

    if selected_option == "BACK_TO_PARTNER_CATEGORIES": #
        return await show_partner_main_options(update, context) # Go back to main categories #
    else:
        context.user_data["partner_type"] = selected_option #
        await query.message.reply_text(translations["prompt_name"][lang]) #
        return PARTNER_DETAILS_NAME #


async def set_partner_details_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collects partner's full name."""
    return await ask_input(update, context, "partner_name", "prompt_phone", PARTNER_DETAILS_PHONE) #

async def set_partner_details_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collects partner's phone number with validation."""
    phone_number = update.message.text #
    if not (phone_number.startswith('+') and phone_number[1:].isdigit()): #
        lang = get_lang(update) #
        await update.message.reply_text(translations["invalid_input"][lang] + "\n" + translations["prompt_phone"][lang]) #
        return PARTNER_DETAILS_PHONE #
    return await ask_input(update, context, "partner_phone", "prompt_country", PARTNER_DETAILS_COUNTRY) #

async def set_partner_details_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collects partner's country and proceeds to payment method."""
    context.user_data["partner_country"] = update.message.text.strip().title() # Capitalize for consistency #
    lang = get_lang(update) #
    country = context.user_data["partner_country"] #

    payment_message = "" #
    keyboard_buttons = [] #

    if "south africa" in country.lower(): #
        payment_message = translations["payment_sa"][lang] #
    else:
        payment_message = translations["payment_international"][lang] #
        keyboard_buttons.append([InlineKeyboardButton(translations["contact_admin_button"][lang], callback_data="CONTACT_ADMIN")]) #

    keyboard_buttons.append([InlineKeyboardButton(translations["back_to_partner_categories"][lang], callback_data="BACK_TO_PARTNER_CATEGORIES")]) # Changed back button #

    await update.message.reply_text(
        payment_message,
        reply_markup=InlineKeyboardMarkup(keyboard_buttons),
        parse_mode="Markdown"
    ) #
    await update.message.reply_text(translations["prompt_amount"][lang], parse_mode="Markdown") # Prompt for amount after payment info #
    return PARTNER_AMOUNT #

async def handle_contact_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Provides admin contact information."""
    query = update.callback_query #
    await query.answer() #
    lang = get_lang(update) #

    # Clean previous inline keyboard
    try:
        await query.edit_message_reply_markup(reply_markup=None) #
    except Exception as e:
        logger.warning(f"Failed to clear inline keyboard: {e}") #

    await query.message.reply_text(
        translations["admin_contact_info"][lang].format(admin_id=ADMIN_ID),
        parse_mode="Markdown"
    ) #
    # After showing contact info, return to the main menu
    await query.message.reply_text(translations["menu"][lang], reply_markup=build_main_menu(lang)) #
    return MENU #

async def set_partner_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collects partner's amount with validation."""
    lang = get_lang(update) #
    amount_text = update.message.text #
    try:
        amount = float(amount_text) #
        if amount <= 0: #
            raise ValueError # Amount must be positive #
        context.user_data["partner_amount"] = f"{amount:.2f}" # Store as formatted string #
        await update.message.reply_text(translations["prompt_payment_proof"][lang], parse_mode="Markdown") # Ensure Markdown for consistency #
        return PARTNER_PAYMENT_PROOF #
    except ValueError:
        await update.message.reply_text(translations["invalid_input"][lang] + "\n" + translations["prompt_amount"][lang]) #
        return PARTNER_AMOUNT #

async def set_partner_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collects payment proof and saves all partner data."""
    lang = get_lang(update) #
    file_id = None #
    if update.message.photo: #
        file_id = update.message.photo[-1].file_id #
    elif update.message.document: #
        file_id = update.message.document.file_id #
    else:
        await update.message.reply_text(translations["upload_proof_error"][lang]) #
        return PARTNER_PAYMENT_PROOF #

    context.user_data["payment_proof_file_id"] = file_id #

    # Keys for partner_sheet: ["User ID", "Partner Type", "Name", "Phone", "Country", "Amount", "Timestamp", "Payment Proof File ID"]
    return await save_to_sheet(
        update, context, partner_sheet,
        ["partner_type", "partner_name", "partner_phone", "partner_country", "partner_amount", "payment_proof_file_id"],
        "partner_thankyou" # Use the specific partner thank you message
    ) #

# === Error Handler ===
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Logs errors and sends a user-friendly message."""
    logger.error("Exception while handling update:", exc_info=context.error) #
    if isinstance(update, Update) and update.effective_message: #
        lang = get_lang(update) if update.effective_user else "en" # Try to get user lang, else default #
        await update.effective_message.reply_text(translations["error_general"][lang]) #

# === Main Function ===
def main():
    """Main function to run the bot."""
    app = ApplicationBuilder().token(BOT_TOKEN).build() #

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)], #
        states={
            LANG_SELECT: [CallbackQueryHandler(language_selected)], #
            MENU: [CallbackQueryHandler(handle_menu)], #

            # Partner Flow
            PARTNER_MAIN_OPTIONS: [CallbackQueryHandler(handle_partner_main_selection)], #
            PARTNER_GIVE_OPTIONS: [CallbackQueryHandler(handle_partner_give_selection)], # Handles specific give options #
            PARTNER_PARTNER_OPTIONS: [CallbackQueryHandler(handle_partner_partner_selection)], # Handles specific partner options #
            PARTNER_DETAILS_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_partner_details_name)], #
            PARTNER_DETAILS_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_partner_details_phone)], #
            PARTNER_DETAILS_COUNTRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_partner_details_country), #
                CallbackQueryHandler(handle_partner_main_selection, pattern="^BACK_TO_PARTNER_CATEGORIES$") # Allow going back #
            ],
            PARTNER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_partner_amount)], #
            PARTNER_PAYMENT_PROOF: [MessageHandler(filters.PHOTO | filters.Document.ALL, set_partner_payment_proof)], #
            CONTACT_ADMIN_INFO: [CallbackQueryHandler(handle_contact_admin_button, pattern="^CONTACT_ADMIN$")],


            # Other Flows
            PRAYER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_prayer_name)], # New handler for prayer name #
            PRAYER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_prayer_request)], #
            MEMBER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_member_name)], #
            MEMBER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_member_phone)], #
            MEMBER_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_member_country)], #
            SCHOOL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_school_name)], #
            SCHOOL_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_school_phone)], #
            SCHOOL_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_school_country)], #
            MASTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_master_name)], #
            MASTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_master_phone)], #
            MASTER_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_master_country)], #
        },
        fallbacks=[
            CommandHandler("start", start), # Allows user to restart conversation #
            # A general message handler for any unhandled text, redirecting to start
            MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, start) #
        ],
        # Enable per-user data persistence across conversations (optional, but good for language)
        # per_user=True,
        # per_chat=False,
    )

    app.add_handler(conv_handler) #
    app.add_error_handler(error_handler) #

    print("🤖 Bot is running...") #
    logger.info("Bot started polling.") #
    app.run_polling() #

if __name__ == "__main__":
    main() #
