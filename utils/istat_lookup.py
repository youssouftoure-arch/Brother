import os
import sys

import pandas as pd
from config.settings import Settings


def resource_path(relative_path: str) -> str:
    """Resolve bundled resources for both local runs and PyInstaller builds."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)

class GetProvince:
    def __init__(self):
        file = resource_path(str(Settings.ISTAT_CSV))
        # Preservati i tuoi parametri reali del CSV
        self.df = pd.read_csv(
            file,
            usecols=["Codice Catastale del comune", "Sigla automobilistica", "Denominazione in italiano"],
            sep=';',
            dtype=str,
            encoding="latin-1",
        ).dropna()
        self.df = self.df.rename(columns={
            "Denominazione in italiano": "comune",
            "Sigla automobilistica": "provincia",
            "Codice Catastale del comune": "cod_catastale",
        })
        self.df["provincia_full"] = self.df["provincia"].apply(lambda sigla: self._provincia_full_from_sigla(sigla))

    @staticmethod
    def _provincia_full_from_sigla(sigla: str) -> str:
        mapping = {
            "AG": "Agrigento",
            "AL": "Alessandria",
            "AN": "Ancona",
            "AO": "Aosta",
            "AR": "Arezzo",
            "AP": "Ascoli Piceno",
            "AT": "Asti",
            "AV": "Avellino",
            "BA": "Bari",
            "BL": "Belluno",
            "BN": "Benevento",
            "BG": "Bergamo",
            "BI": "Biella",
            "BO": "Bologna",
            "BR": "Brindisi",
            "BS": "Brescia",
            "BT": "Barletta-Andria-Trani",
            "BZ": "Bolzano",
            "CA": "Cagliari",
            "CB": "Campobasso",
            "CE": "Caserta",
            "CH": "Chieti",
            "CL": "Caltanissetta",
            "CN": "Cuneo",
            "CO": "Como",
            "CR": "Cremona",
            "CS": "Cosenza",
            "CT": "Catania",
            "CZ": "Catanzaro",
            "EN": "Enna",
            "FC": "Forlì-Cesena",
            "FE": "Ferrara",
            "FG": "Foggia",
            "FI": "Firenze",
            "FM": "Fermo",
            "FR": "Frosinone",
            "GE": "Genova",
            "GO": "Gorizia",
            "GR": "Grosseto",
            "IM": "Imperia",
            "IS": "Isernia",
            "KR": "Crotone",
            "LC": "Lecco",
            "LE": "Lecce",
            "LI": "Livorno",
            "LO": "Lodi",
            "LT": "Latina",
            "LU": "Lucca",
            "MB": "Monza e della Brianza",
            "MC": "Macerata",
            "ME": "Messina",
            "MI": "Milano",
            "MN": "Mantova",
            "MO": "Modena",
            "MS": "Massa-Carrara",
            "MT": "Matera",
            "NA": "Napoli",
            "NO": "Novara",
            "NU": "Nuoro",
            "OR": "Oristano",
            "PA": "Palermo",
            "PC": "Piacenza",
            "PD": "Padova",
            "PE": "Pescara",
            "PG": "Perugia",
            "PI": "Pisa",
            "PN": "Pordenone",
            "PO": "Prato",
            "PR": "Parma",
            "PT": "Pistoia",
            "PU": "Pesaro e Urbino",
            "PV": "Pavia",
            "PZ": "Potenza",
            "RA": "Ravenna",
            "RC": "Reggio Calabria",
            "RE": "Reggio Emilia",
            "RG": "Ragusa",
            "RI": "Rieti",
            "RM": "Roma",
            "RN": "Rimini",
            "RO": "Rovigo",
            "SA": "Salerno",
            "SI": "Siena",
            "SO": "Sondrio",
            "SP": "La Spezia",
            "SR": "Siracusa",
            "SS": "Sassari",
            "SU": "Sud Sardegna",
            "TA": "Taranto",
            "TE": "Teramo",
            "TN": "Trento",
            "TO": "Torino",
            "TP": "Trapani",
            "TR": "Terni",
            "TS": "Trieste",
            "TV": "Treviso",
            "UD": "Udine",
            "VA": "Varese",
            "VB": "Vercelli",
            "VC": "Verbano-Cusio-Ossola",
            "VE": "Venezia",
            "VR": "Verona",
            "VV": "Vibo Valentia",
            "VT": "Viterbo",
        }
        return mapping.get(str(sigla).strip().upper(), sigla.strip())

    def get_province(self) -> dict[str, list[str]]:
        lookup: dict[str, list[str]] = {}
        for _, row in self.df.iterrows():
            key = row["comune"].strip().upper()
            lookup.setdefault(key, []).append(row["provincia"].strip().upper())
        return lookup

# --- APPARATO DI CACHE PER L'ORCHESTRAZIONE ---
_cache: dict | None = None

def build_lookup() -> dict[str, list[str]]:
    """Carica il tuo parser ISTAT una volta sola in memoria."""
    global _cache
    if _cache is None:
        _cache = GetProvince().get_province()
    return _cache
