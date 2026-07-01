import logging
from logging.handlers import RotatingFileHandler  # 🎯 L'unico innesto necessario per la rotazione
from config.settings import Settings

def get_logger(name: str) -> logging.Logger:
    """
    Configura e restituisce un logger centralizzato.
    Mantiene il layout personalizzato, corregge i conflitti di handler e ruota i file.
    """
    logger = logging.getLogger(name)
    
    # Se il logger ha già gli handler configurati, lo restituiamo subito senza duplicarli
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = True
    
    # Preservato al 100% il tuo stile di formattazione personalizzato (incluso l'allineamento -12s)
    formatter = logging.Formatter('%(levelname)-8s | %(asctime)s | %(name)-12s | %(message)s')

    # 1. Handler Console (Mostra solo da INFO in su per non intasare il terminale)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Handler File ROTANTE (Mantiene il tuo try/except protettivo e la tua variabile Settings)
    try:
        import os
        os.makedirs(Settings.LOG_FILE.parent, exist_ok=True)
        # Sostituito con RotatingFileHandler preservando Settings.LOG_FILE ed encoding originali
        file_handler = RotatingFileHandler(
            str(Settings.LOG_FILE), 
            maxBytes=5 * 1024 * 1024,  # Limite tassativo di 5 MB a file
            backupCount=5,             # Tiene al massimo 5 file storici di riserva
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"[WARN] Impossibile inizializzare il file di log: {e}")

    return logger