from dataclasses import dataclass, field

@dataclass
class DownloadJob:
    comune: str
    foglio: str
    particella: str
    sub: str | None
    tipo: str
    opera: str
    categoria: str
    riga_excel: int = 0
    dati_originali: dict = field(default_factory=dict)
    chiave: str = field(init=False)

    def __post_init__(self):
        sub_part = f"_{self.sub}" if self.sub else ""
        self.chiave = f"{self.comune}_{self.foglio}_{self.particella}{sub_part}_{self.tipo}".upper()


@dataclass
class rigaInvalida:
    riga_excel: int
    motivo: str
    dati_originali: dict


@dataclass
class jobConflictWarning:
    chiave: str
    jobA: DownloadJob
    jobB: DownloadJob
    

