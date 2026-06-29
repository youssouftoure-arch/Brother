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

        # forward fill the "opera" column (using the key that maps to "opera")
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
    def deduplicate_jobs(
        jobs: list[DownloadJob],
    ) -> tuple[list[DownloadJob], dict[str, list[str]], list[jobConflictWarning]]:
        seen: dict[str, DownloadJob] = {}
        mappa: dict[str, list[str]] = defaultdict(list)
        conflitti: list[jobConflictWarning] = []

        for job in jobs:
            # 🎯 INIEZIONE STRUTTURALE COLONNA OGGETTO
            # Estraiamo dinamicamente il valore di OGGETTO dalla riga nativa salvata in cache
            oggetto_val = ""
            if job.dati_originali:
                for k, v in job.dati_originali.items():
                    if k.strip().upper() == "OGGETTO":
                        oggetto_val = str(v).strip()
                        break

            # Costruiamo la destinazione includendo anche l'oggetto per attivare i filtri del FolderBuilder
            base_dest = job.opera if not job.categoria else f"{job.opera}/{job.categoria}"
            if oggetto_val and oggetto_val.upper() not in ("NAN", "NONE"):
                destinazione = f"{base_dest}/{oggetto_val}"
            else:
                destinazione = base_dest

            if destinazione not in mappa[job.chiave]:
                mappa[job.chiave].append(destinazione)

            if job.chiave not in seen:
                seen[job.chiave] = job
            else:
                esistente = seen[job.chiave]
                if stramExcel._metadati_interrogazione(job) != stramExcel._metadati_interrogazione(esistente):
                    conflitti.append(jobConflictWarning(job.chiave, jobA=esistente, jobB=job))

        return list(seen.values()), dict(mappa), conflitti

    @staticmethod
    def _metadati_interrogazione(job: DownloadJob) -> tuple:
        return (job.comune, job.foglio, job.particella, job.sub, job.tipo)

    @staticmethod
    def _normalize_tipo(tipo: str) -> str:
        tipo_norm = (tipo or "").strip().upper()
        mapping = {
            "NCT": "NCT",
            "NCF": "NCF",
            "T": "NCT",
            "TERRENO": "NCT",
            "TERRENI": "NCT",
            "F": "NCF",
            "FABBRICATO": "NCF",
            "FABBRICATI": "NCF",
        }
        return mapping.get(tipo_norm, "")