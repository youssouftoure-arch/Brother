# core/folder_builder.py — Costruzione albero delle cartelle dinamico ed esportazione visure conformi
import shutil
from pathlib import Path
from config.settings import Settings
from core.cache_manager import CacheManager
from utils.logger import get_logger
from utils.istat_lookup import build_lookup

# Sintonizziamo il logger interno per tracciare lo smistamento
logger = get_logger("FolderBuilder")

class FolderBuilder:
    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.root = Settings.OUTPUT_DIR
        self.istat = build_lookup()

    def build(self, mappa: dict[str, list[str]]) -> None:
        """
        Strict Row Routing — Il FolderBuilder è ora un esecutore puro.
        La mappa ricevuta dal parser contiene già i percorsi finali completi
        (opera/categoria/subfolder) calcolati riga per riga da excel_parser.py.
        Questo metodo si occupa esclusivamente di:
          1. Rinominare il PDF in formato PROVINCIA-COMUNE-FG-PART[-SUB].pdf
          2. Creare le directory necessarie
          3. Copiare il file in ogni percorso distinto associato alla chiave
        Nessuna keyword-detection, nessun calcolo di routing qui.
        """
        logger.info("Avvio smistamento strutturato (Strict Row Routing) delle visure...")

        self.root.mkdir(parents=True, exist_ok=True)
        contatore_copie = 0

        for chiave, destinazioni in mappa.items():
            # ── Recupera il PDF dalla cache ────────────────────────────────────
            src = self.cache.get_path(chiave)
            if not src.exists():
                logger.warning(f"File PDF non trovato in cache per la chiave: {chiave} (Impossibile smistare)")
                continue

            # ── Componi il nome file standard PROVINCIA-COMUNE-FG-PART[-SUB].pdf ─
            parts = chiave.split('_')
            if len(parts) >= 4 and parts[-1].upper() in ("NCT", "NCF"):
                comune    = parts[0].strip()
                foglio    = parts[1].strip()
                particella = parts[2].strip()
                sub       = parts[3].strip() if len(parts) == 5 else ""

                prov_list = self.istat.get(comune.upper(), [])
                provincia = prov_list[0] if prov_list else "GENERIC"

                if sub and sub.lower() != "nan" and sub != "0":
                    nuovo_nome_file = f"{provincia}-{comune}-{foglio}-{particella}-{sub}.pdf"
                else:
                    nuovo_nome_file = f"{provincia}-{comune}-{foglio}-{particella}.pdf"
            else:
                nuovo_nome_file = src.name

            # ── Copia il file in ogni percorso finale già calcolato dal parser ─
            for destinazione in destinazioni:
                # Pulizia difensiva del percorso (a capo, barre miste, spazi doppi)
                dest_clean = str(destinazione).replace("\n", " ").replace("\r", " ").replace("\\", "/").strip()
                while "  " in dest_clean:
                    dest_clean = dest_clean.replace("  ", " ")

                dest_dir = self.root / Path(dest_clean)

                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_dir / nuovo_nome_file
                    shutil.copy2(src, dest_file)
                    logger.debug(f"Smistato: {nuovo_nome_file} -> {dest_clean}")
                    contatore_copie += 1
                except Exception as e:
                    logger.error(f"Errore copia {nuovo_nome_file} in '{dest_clean}': {e}")

        logger.info(f"Smistamento completato. Effettuate {contatore_copie} copie conformi nel nuovo layout d'impianto.")