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
        Legge la mappa delle destinazioni generata dal parser Excel,
        applica l'ereditarietà territoriale del Campo per Foglio catastale,
        smista le sottocartelle basandosi sulla colonna OGGETTO
        e rinomina i file in formato standard PROVINCIA-COMUNE-FG-PART[-SUB].pdf.
        """
        logger.info("Avvio smistamento strutturato delle visure secondo il layout dinamico del cliente...")
        
        # Ci assicuriamo che la cartella radice di output esista
        self.root.mkdir(parents=True, exist_ok=True)
        
        # 🎯 PASSAGGIO 1: RADAR GEOGRAFICO CORAZZATO (Mappatura pulita Foglio -> Campo)
        mappa_fogli_campi = {}
        for chiave, destinazioni in mappa.items():
            parts = chiave.split('_')
            if len(parts) >= 2:
                foglio_corrente = parts[1].strip()
                
                for d in destinazioni:
                    # Purificazione profonda immediata della stringa da a capo o spazi occulti
                    d_clean = str(d).replace("\n", " ").replace("\r", " ").replace("\\", "/").strip()
                    while "  " in d_clean:
                        d_clean = d_clean.replace("  ", " ")
                        
                    parts_d = [p.strip() for p in d_clean.split("/") if p.strip()]
                    for p in parts_d:
                        if "campo" in p.lower():
                            mappa_fogli_campi[foglio_corrente] = p
                            break

        # Calcoliamo un campo di fallback globale nel caso un intero foglio sia orfano di dati
        campo_default_progetto = "Opere Generali Impianto"
        for c in mappa_fogli_campi.values():
            if c:
                campo_default_progetto = c
                break

        # 🎯 PASSAGGIO 2: ELABORAZIONE, RINOMINA E SMISTAMENTO NELL'ALBERO
        contatore_copie = 0
        
        for chiave, destinazioni in mappa.items():
            # Recuperiamo il percorso del file sorgente nella cache
            src = self.cache.get_path(chiave)
            
            # Controllo di sicurezza: se il download è saltato, lo segnaliamo senza crashare
            if not src.exists():
                logger.warning(f"File PDF non trovato in cache per la chiave: {chiave} (Impossibile smistare)")
                continue
            
            # PARSER UNIVERSALE CHIAVE (Gestisce sia 4 che 5 elementi divisi da _)
            parts = chiave.split('_')
            foglio = ""
            if len(parts) >= 4 and parts[-1].upper() in ["NCT", "NCF"]:
                comune = parts[0].strip()
                foglio = parts[1].strip()
                particella = parts[2].strip()
                sub = parts[3].strip() if len(parts) == 5 else ""
                
                prov_list = self.istat.get(comune.upper(), [])
                provincia = prov_list[0] if prov_list else "GENERIC"
                
                if sub and sub.lower() != "nan" and sub != "0":
                    nuovo_nome_file = f"{provincia}-{comune}-{foglio}-{particella}-{sub}.pdf"
                else:
                    nuovo_nome_file = f"{provincia}-{comune}-{foglio}-{particella}.pdf"
            else:
                nuovo_nome_file = src.name
                
            # ESTRAZIONE MACRO-CARTELLA DEL CAMPO
            macro_cartella = None
            for d in destinazioni:
                d_clean = str(d).replace("\n", " ").replace("\r", " ").replace("\\", "/").strip()
                parts_d = [p.strip() for p in d_clean.split("/") if p.strip()]
                for p in parts_d:
                    if "campo" in p.lower():
                        p_clean = p
                        while "  " in p_clean:
                            p_clean = p_clean.replace("  ", " ")
                        macro_cartella = p_clean
                        break
                if macro_cartella:
                    break
            
            # 🛡️ INTERVENTO PREVENTIVO: Se la riga è vuota, eredita dal Foglio o dal Campo principale del progetto
            if not macro_cartella:
                macro_cartella = mappa_fogli_campi.get(foglio, campo_default_progetto)

            # IDENTIFICAZIONE SOTTOCARTELLA (Filtro selettivo basato sulla colonna OGGETTO e OPERA)
            sottocartelle_target = set()
            for d in destinazioni:
                text = str(d).replace("\n", " ").replace("\r", " ").replace("\\", "/").lower()
                
                # 🎯 BYPASS CONCESSIONE: Controlliamo se la riga appartiene alle opere di concessione/connessione
                is_concessione = "conces" in text or "connes" in text
                
                matched = False
                
                if is_concessione:
                    # Tassativo cliente: Per le opere di concessione estrapoliamo SOLO le cabine
                    if "cabin" in text:
                        sottocartelle_target.add("cabine")
                        matched = True
                else:
                    # Per tutte le altre opere del piano particellare, manteniamo il setaccio completo
                    if "cancell" in text or "ingresso" in text:
                        sottocartelle_target.add("cancelli ingresso")
                        matched = True
                    if "cabin" in text:
                        sottocartelle_target.add("cabine")
                        matched = True
                    if "stradelle" in text or ("strad" in text and "progetto" in text):
                        sottocartelle_target.add("stradelle in progetto esterne impianto")
                        matched = True
                    if "accesso" in text or "esistenti" in text:
                        sottocartelle_target.add("strade accesso esistenti")
                        matched = True
                    if "accessorie" in text and "invarianza" in text:
                        sottocartelle_target.add("opere accessorie di invarianza idraulica")
                        matched = True
                    elif "invarianza" in text or "idraulica" in text:
                        sottocartelle_target.add("opere di invarianza idraulica")
                        matched = True
                    
                # Se la riga non intercetta nessuna sottocartella ammessa, va dritta nella ROOT del Campo
                if not matched:
                    sottocartelle_target.add("")

                    
            # CREAZIONE STRUTTURA FISICA E COPIA DEFINITIVA
            for sotto in sottocartelle_target:
                percorso_relativo = Path(macro_cartella) / sotto if sotto else Path(macro_cartella)
                dest_dir = self.root / percorso_relativo
                
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_dir / nuovo_nome_file
                    
                    shutil.copy2(src, dest_file)
                    logger.debug(f"Smistato strutturato: {nuovo_nome_file} -> {percorso_relativo}")
                    contatore_copie += 1
                    
                except Exception as e:
                    logger.error(f"Errore durante la copia di {nuovo_nome_file} in {percorso_relativo}: {e}")
        
        logger.info(f"Smistamento completato. Effettuate {contatore_copie} copie conformi nel nuovo layout d'impianto.")