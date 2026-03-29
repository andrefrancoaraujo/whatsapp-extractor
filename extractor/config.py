SERVER_URL = "https://dashboard.andrefrancoaraujo.shop/extractor/whatsapp-upload"
WHATSAPP_PACKAGE = "com.whatsapp.w4b"
WHATSAPP_MAIN = "com.whatsapp.Main"
EXPORT_DIR = "/sdcard/Download/whatsapp_exports"
UI_DUMP_PATH = "/sdcard/window_dump.xml"

# Strings PT-BR and EN for UI element matching
# Multiple variants per action to handle different WA Business versions and Android versions
STRINGS = {
    "more_options": [
        "Mais opções", "More options",
        "Mais opcões", "Mais opcoes",
        "Menu", "Opções", "Options",
    ],
    "more": ["Mais", "More", "Ver mais", "See more"],
    "export_chat": [
        "Exportar conversa", "Export chat",
        "Exportar", "Export",
        "Exportar histórico", "Exportar historico",
    ],
    "without_media": [
        "SEM MÍDIA", "Sem mídia", "Sem midia",
        "WITHOUT MEDIA", "Without media", "Without Media",
        "SEM MEDIA",
    ],
    "files": [
        "Arquivos", "Files", "Meus arquivos", "My Files",
        "Salvar em", "Save to", "Salvar no dispositivo",
        "Save to device", "Gerenciador de arquivos", "File Manager",
        "Meus Arquivos", "Samsung My Files",
        "Documentos", "Documents", "Google Files",
    ],
    "downloads": ["Download", "Downloads", "Transferências", "Transferencias"],
    "save": ["Salvar", "Save", "OK", "SALVAR", "SAVE", "Concluído", "Done"],
}

SCROLL_PAUSE = 1.5
TAP_PAUSE = 0.8
LOAD_PAUSE = 2.0
