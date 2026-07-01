# (Fase 2) Lettura Excel, routing logico, normalizzazione
from collections import defaultdict
import pandas as pd
from config.settings import Settings
from model.po.rigaExcel import DownloadJob, jobConflictWarning, rigaInvalida

# Mapping colonne Excel -> nomi interni
COL_MAP = {
    "opere ": "opera",
    "opera": "opera",
    "Opera": "opera",
    "campo": "categoria",
    "categoria": "categoria",
    "Categoria": "categoria",
    "CATASTO ": "tipo",
    "Tipo": "tipo",
    "tipo": "tipo",
    "COMUNE ": "comune",
    "Comune": "comune",
    "comune": "comune",
    "FG.": "foglio",
    "Foglio": "foglio",
    "foglio": "foglio",
    "P.lla ": "particella",
    "Particella": "particella",
    "particella": "particella",
    "Sub": "sub",
    "sub": "sub",
    "Porz.": "porzione",
    "Porzione": "porzione",
    "porzione": "porzione",
}

OPERA_INVALIDE = {"FOSSO", "CANALE", "STRADA"}


class stramExcel:
    original_headers = []

    def __init__(self):
        pass

    @staticmethod
    def _load_df(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Carica il DataFrame dall'Excel con header sulla riga 1.
        Se il file non ha la riga introduttiva attesa, ripiega su header=0.
        Ritorna una tupla (df_renamed, df_original).
        """
        df_orig = pd.read_excel(path, dtype=str, header=1)
        rename = {k: v for k, v in COL_MAP.items() if k in df_orig.columns}
        if not rename:
            df_orig = pd.read_excel(path, dtype=str, header=0)
            rename = {k: v for k, v in COL_MAP.items() if k in df_orig.columns}

        # 🟢 RIATTIVATO IL FORWARD FILL SOLO PER LE OPERE
        # Consente alle righe sotto di ereditare la lavorazione speciale (es. Invarianza Idraulica)
        col_opera_orig = None
        for k in COL_MAP:
            if COL_MAP[k] == "opera" and k in df_orig.columns:
                col_opera_orig = k
                break
        if col_opera_orig:
            df_orig[col_opera_orig] = df_orig[col_opera_orig].ffill()

        df_renamed = df_orig.rename(columns=rename)
        return df_renamed, df_orig

    @staticmethod
    def _normalize_tipo(tipo_val: str) -> str:
        """
        Normalizza il valore della colonna CATASTO convertendolo 
        nelle sigle standard accettate da Sister (NCT o NCF).
        """
        val = str(tipo_val).strip().upper()
        if not val or val in ("NAN", "NONE"):
            return ""
        if "FAB" in val or "NCF" in val or "URB" in val or "FABBRICATI" in val:
            return "NCF"
        return "NCT"

    @staticmethod
    def _metadati_interrogazione(job: DownloadJob) -> tuple:
        """
        Ritorna i metadati essenziali di ricerca per il confronto univoco dei job.
        """
        return (job.comune, job.foglio, job.particella, job.sub, job.tipo)

    @staticmethod
    def parse_excel(path: str = None) -> tuple[list[DownloadJob], list[rigaInvalida]]:
        path = path or str(Settings.INPUT_EXCEL)
        df_renamed, df_orig = stramExcel._load_df(path)
        stramExcel.original_headers = df_orig.columns.tolist()
        valid: list[DownloadJob] = []
        invalid: list[rigaInvalida] = []

        for idx, row in df_renamed.iterrows():
            riga_num = idx + 3
            orig_row = df_orig.iloc[idx].to_dict()

            tipo_raw = str(row.get("tipo", "")).strip()
            tipo = tipo_raw.upper()
            comune = str(row.get("comune", "")).strip()
            foglio = str(row.get("foglio", "")).strip()
            particella = str(row.get("particella", "")).strip()
            sub = str(row.get("sub", "")).strip()
            porzione = str(row.get("porzione", "")).strip()
            opera = str(row.get("opera", "")).strip()
            categoria = str(row.get("categoria", "")).strip()

            tipo = "" if tipo in ("NAN", "NONE") else tipo
            comune = "" if comune.upper() in ("NAN", "NONE") else comune
            foglio = "" if foglio.upper() in ("NAN", "NONE") else foglio
            particella = "" if particella.upper() in ("NAN", "NONE") else particella
            sub = "" if sub.upper() in ("NAN", "NONE") else sub
            porzione = "" if porzione.upper() in ("NAN", "NONE") else porzione
            opera = "" if opera.upper() in ("NAN", "NONE") else opera
            categoria = "" if categoria.upper() in ("NAN", "NONE") else categoria

            if opera.upper() in OPERA_INVALIDE or tipo in OPERA_INVALIDE:
                invalid.append(rigaInvalida(
                    riga_num,
                    f"Tipo scartato: opera non gestita ({opera or tipo_raw})",
                    orig_row,
                ))
                continue

            tipo_normalizzato = stramExcel._normalize_tipo(tipo)
            if not comune or not particella or not tipo_normalizzato:
                if comune or particella or tipo_raw:
                    invalid.append(rigaInvalida(
                        riga_num,
                        f"Dati catastali mancanti o incompleti (tipo={tipo_raw!r}, comune={comune!r}, particella={particella!r})",
                        orig_row,
                    ))
                continue

            sub_eff = sub or porzione or None
            valid.append(DownloadJob(
                comune=comune,
                foglio=foglio,
                particella=particella,
                sub=sub_eff,
                tipo=tipo_normalizzato,
                opera=opera,
                categoria=categoria,
                riga_excel=riga_num,
                dati_originali=orig_row,
            ))

        return valid, invalid

    @staticmethod
    def _resolve_subfolder(oggetto_val: str) -> str:
        """
        Strict Row Routing — Calcola la sottocartella tecnica dalla colonna OGGETTO
        della singola riga Excel. Nessuna logica esterna nel FolderBuilder.
        """
        t = oggetto_val.lower()
        if "cancell" in t or "ingresso" in t:
            return "cancelli ingresso"
        if "cabin" in t:
            return "cabine"
        if "stradelle" in t or ("strad" in t and "progetto" in t):
            return "stradelle in progetto esterne impianto"
        if "accesso" in t or "esistenti" in t:
            return "strade accesso esistenti"
        if "accessorie" in t and "invarianza" in t:
            return "opere accessorie di invarianza idraulica"
        if "invarianza" in t or "idraulica" in t:
            return "opere di invarianza idraulica"
        return ""

    @staticmethod
    def deduplicate_jobs(
        jobs: list[DownloadJob],
    ) -> tuple[list[DownloadJob], dict[str, list[str]], list[jobConflictWarning]]:
        seen: dict[str, DownloadJob] = {}
        mappa: dict[str, list[str]] = defaultdict(list)
        conflitti: list[jobConflictWarning] = []

        for job in jobs:
            oggetto_val = ""
            if job.dati_originali:
                for k, v in job.dati_originali.items():
                    if k.strip().upper() == "OGGETTO":
                        oggetto_val = str(v).strip()
                        break

            # 🟢 LA RADICE COMUNE: La cartella principale è sempre il CAMPO (job.categoria)
            root_folder = str(job.categoria).strip()
            opere_clean = str(job.opera).strip().upper()
            text_oggetto = oggetto_val.lower()

            destinazione_finale = None

            # 🛠️ CANALE B: Se l'opera è una lavorazione speciale, comanda lei la sottocartella
            if "INVARIANZA" in opere_clean and "ACCESSORIE" in opere_clean:
                destinazione_finale = f"{root_folder}/opere accessorie di invarianza idraulica"
            elif "INVARIANZA" in opere_clean:
                destinazione_finale = f"{root_folder}/opere di invarianza idraulica"
            elif "STRADELLE" in opere_clean:
                destinazione_finale = f"{root_folder}/stradelle in progetto esterne impianto"
            elif "ACCESSO" in opere_clean:
                destinazione_finale = f"{root_folder}/strade accesso esistenti"
            elif "DISMISSIONE" in opere_clean:
                destinazione_finale = f"{root_folder}/opere di dismissione"
                
            # 🛠️ CANALE A-SPECIAL: Se è il gruppo "OPERE CONNESSIONE", applica il filtro RIGIDO richiesto da Martina
            elif "CONNESSIONE" in opere_clean:
                if "cancell" in text_oggetto or "ingresso" in text_oggetto:
                    destinazione_finale = f"{root_folder}/cancelli ingresso"
                elif "cabin" in text_oggetto:
                    destinazione_finale = f"{root_folder}/cabine"
                else:
                    # Tassativamente escluso: non crea la root del campo e non scarica la visura
                    destinazione_finale = None
            
            # 🛠️ CANALE A-STANDARD: Campi base normali (es. Campo FV 13)
            else:
                if "cancell" in text_oggetto or "ingresso" in text_oggetto:
                    destinazione_finale = f"{root_folder}/cancelli ingresso"
                elif "cabin" in text_oggetto:
                    destinazione_finale = f"{root_folder}/cabine"
                else:
                    destinazione_finale = root_folder

            # 🎯 SELEZIONE RIGIDA ANTI-SPRECO:
            # Registriamo il percorso e abilitiamo il download da Sister SOLO se la destinazione è valida
            if destinazione_finale:
                if destinazione_finale not in mappa[job.chiave]:
                    mappa[job.chiave].append(destinazione_finale)

                if job.chiave not in seen:
                    seen[job.chiave] = job
                else:
                    esistente = seen[job.chiave]
                    if stramExcel._metadati_interrogazione(job) != stramExcel._metadati_interrogazione(esistente):
                        conflitti.append(jobConflictWarning(job.chiave, jobA=esistente, jobB=job))

        return list(seen.values()), dict(mappa), conflitti