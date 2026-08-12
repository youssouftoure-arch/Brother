# scraper/sister_client.py — Gestore statico delle ricerche su Sister con VISION AI GPT
import time
import base64
import random
import re
import unicodedata
from config.settings import Settings
from core.historical_workbook import HistoricalJob, PropertyResult
from utils.logger import get_logger
from openai import OpenAI
import requests

logger = get_logger("SisterClient")

class SisterError(Exception): pass
class ImmobileNonTrovato(SisterError): pass
class ParticellaSoppressa(SisterError): pass
class CaptchaServiceUnavailable(SisterError): pass

DIZIONARIO_PROVINCE = {
    "AG": "AGRIGENTO", "AL": "ALESSANDRIA", "AN": "ANCONA", "AO": "AOSTA", "AR": "AREZZO", "AP": "ASCOLI PICENO",
    "AT": "ASTI", "AV": "AVELLINO", "BA": "BARI", "BL": "BELLUNO", "BN": "BENEVENTO", "BG": "BERGAMO", "BI": "BIELLA",
    "BO": "BOLOGNA", "BR": "BRINDISI", "BS": "BRESCIA", "BT": "BARLETTA-ANDRIA-TRANI", "BZ": "BOLZANO",
    "CA": "CAGLIARI", "CB": "CAMPOBASSO", "CE": "CASERTA", "CH": "CHIETI", "CL": "CALTANISSETTA", "CN": "CUNEO",
    "CO": "COMO", "CR": "CREMONA", "CS": "COSENZA", "CT": "CATANIA", "CZ": "CATANZARO", "EN": "ENNA", "FC": "FORLI",
    "FE": "FERRARA", "FG": "FOGGIA", "FI": "FIRENZE", "FM": "FERMO", "FR": "FROSINONE", "GE": "GENOVA", "GO": "GORIZIA",
    "GR": "GROSSETO", "IM": "IMPERIA", "IS": "ISERNIA", "KR": "CROTONE", "LC": "LECCO", "LE": "LECCE", "LI": "LIVORNO",
    "LO": "LODI", "LT": "LATINA", "LU": "LUCCA", "MB": "MONZA E DELLA BRIANZA", "MC": "MACERATA", "ME": "MESSINA",
    "MI": "MILANO", "MN": "MANTOVA", "MO": "MODENA", "MS": "MASSA", "MT": "MATERA", "NA": "NAPOLI", "NO": "NOVARA",
    "NU": "NUORO", "OR": "ORISTANO", "PA": "PALERMO", "PC": "PIACENZA", "PD": "PADOVA", "PE": "PESCARA", "PG": "PERUGIA",
    "PI": "PISA", "PN": "PORDENONE", "PO": "PRATO", "PR": "PARMA", "PT": "PISTOIA", "PU": "PESARO", "PV": "PAVIA",
    "PZ": "POTENZA", "RA": "RAVENNA", "RC": "REGGIO CALABRIA", "RE": "REGGIO EMILIA", "RG": "RAGUSA", "RI": "RIETI",
    "RM": "ROMA", "RN": "RIMINI", "RO": "ROVIGO", "SA": "SALERNO", "SI": "SIENA", "SO": "SONDRIO", "SP": "LA SPEZIA",
    "SR": "SIRACUSA", "SS": "SASSARI", "SU": "SUD SARDEGNA", "TA": "TARANTO", "TE": "TERAMO", "TN": "TRENTO",
    "TO": "TORINO", "TP": "TRAPANI", "TR": "TERNI", "TS": "TRIESTE", "TV": "TREVISO", "UD": "UDINE", "VA": "VARESE",
    "VB": "VERBANIA", "VC": "VERCELLI", "VE": "VENEZIA", "VR": "VERONA", "VV": "VIBO VALENTIA", "VT": "VITERBO"
}

class NavigatoreSister:
    @staticmethod
    def _normalizza_testo(value: str) -> str:
        value = unicodedata.normalize("NFKD", str(value or ""))
        value = "".join(char for char in value if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @staticmethod
    def _frame_con_selettore(page, selector: str, visible: bool = False):
        for frame in list(page.frames):
            try:
                locator = frame.locator(selector)
                if locator.count() and (not visible or locator.first.is_visible()):
                    return frame
            except Exception:
                continue
        return None

    @staticmethod
    def _digita(locator, value: str) -> None:
        locator.click()
        try:
            locator.fill("")
        except Exception:
            pass
        locator.type(str(value), delay=random.randint(100, 200))
        NavigatoreSister._forza_evento_dom(locator)

    @staticmethod
    def _seleziona_label_o_valore(locator, desired: str) -> None:
        options = locator.locator("option")
        desired_norm = NavigatoreSister._normalizza_testo(desired)
        for index in range(options.count()):
            option = options.nth(index)
            label = option.text_content() or ""
            value = option.get_attribute("value") or ""
            if desired_norm in {
                NavigatoreSister._normalizza_testo(label),
                NavigatoreSister._normalizza_testo(value),
            }:
                locator.select_option(value=value)
                NavigatoreSister._forza_evento_dom(locator)
                return
        raise SisterError(f"Valore '{desired}' non presente nel menu a tendina.")

    @staticmethod
    def check_session() -> bool:
        return Settings.STATE_FILE.exists()

    @staticmethod
    def _forza_evento_dom(locator):
        try:
            locator.evaluate("""el => {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
            }""")
        except Exception:
            pass

    @staticmethod
    def _compila_modulo_unificato(page, comune: str, tipo_catasto: str, foglio: str, particella: str, sub: str = ""):
        target_frame = None
        for tentativo_frame in range(5):
            for idx, frame in enumerate(page.frames):
                if frame.locator("select[name='denomComune']").count() > 0 or frame.locator("select[name='tipoCatasto']").count() > 0:
                    target_frame = frame
                    logger.info(f"   🎯 Form individuato nel Frame [{idx}] (Tentativo radar {tentativo_frame + 1}/5). Verifica e iniezione dati...")
                    break
            if target_frame:
                break
            time.sleep(1.0)

        if not target_frame:
            raise SisterError("Impossibile agganciare la maschera nei frame per l'iniezione dei parametri (Timeout rendering struttura).")
        
        label_catasto = "Terreni" if tipo_catasto == "NCT" else "Fabbricati"
        loc_catasto = target_frame.locator(Settings.SEL_CATASTO_DROPDOWN)
        
        catasto_corrente = loc_catasto.evaluate("el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''")
        if catasto_corrente.strip().lower() != label_catasto.lower():
            loc_catasto.select_option(label=label_catasto)
            NavigatoreSister._forza_evento_dom(loc_catasto)
            page.wait_for_load_state("networkidle")
            time.sleep(1.0)

        loc_comune = target_frame.locator(Settings.SEL_NCT_COMUNE)
        comune_corrente = loc_comune.evaluate("el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''")
        
        if comune_corrente.strip().upper() != comune.strip().upper():
            logger.info(f"   -> Cambio comune rilevato. Imposto: {comune.upper()}...")
            loc_comune.select_option(label=comune.upper())
            NavigatoreSister._forza_evento_dom(loc_comune)
            page.wait_for_load_state("networkidle")
            time.sleep(2.0)
        else:
            logger.info(f"   -> Comune '{comune.upper()}' già agganciato. Salto la selezione del dropdown.")

        # Compilazione con digitazione simulata (ritardi umani)
        loc_foglio = target_frame.locator(Settings.SEL_NCT_FOGLIO)
        loc_foglio.click()
        try:
            loc_foglio.fill("")
        except Exception:
            pass
        loc_foglio.type(str(foglio), delay=random.randint(100, 200))
        time.sleep(random.uniform(0.4, 0.8))

        loc_part = target_frame.locator(Settings.SEL_NCT_PARTICELLA)
        loc_part.click()
        try:
            loc_part.fill("")
        except Exception:
            pass
        loc_part.type(str(particella), delay=random.randint(100, 200))
        time.sleep(random.uniform(0.4, 0.8))

        if sub and tipo_catasto == "NCF":
            loc_sub = target_frame.locator(Settings.SEL_NCF_SUB)
            loc_sub.click()
            try:
                loc_sub.fill("")
            except Exception:
                pass
            loc_sub.type(str(sub), delay=random.randint(100, 200))
            time.sleep(random.uniform(0.4, 0.8))
        else:
            if target_frame.locator(Settings.SEL_NCF_SUB).count() > 0:
                try:
                    target_frame.locator(Settings.SEL_NCF_SUB).fill("")
                except Exception:
                    pass

        loc_rich = target_frame.locator(Settings.SEL_FORM_RICHIEDENTE)
        loc_rich.click()
        try:
            loc_rich.fill("")
        except Exception:
            pass
        loc_rich.type("Uso Professionale", delay=random.randint(80, 150))
        time.sleep(random.uniform(0.3, 0.6))

        loc_mot = target_frame.locator(Settings.SEL_FORM_MOTIVAZIONE)
        loc_mot.click()
        try:
            loc_mot.fill("")
        except Exception:
            pass
        loc_mot.type("Verifica particellare", delay=random.randint(80, 150))
        time.sleep(random.uniform(0.4, 0.8))

        return target_frame



    @staticmethod
    def _risolvi_captcha_automatico(frame, chiave: str) -> str:
        MAX_TENTATIVI = 3
        TIMEOUT_SECONDI = 20

        try:
            img_locator = frame.locator("img[src*='captcha'], img[src*='Validazione'], img[src*='image'], img[src*='Display']").first
            if img_locator.count() == 0:
                img_locator = frame.locator("img").first

            img_bytes = img_locator.screenshot()
            base64_image = base64.b64encode(img_bytes).decode('utf-8')

            # 🟢 Modello aggiornato: gemini-1.5 è stato ritirato (404 su tutti gli endpoint)
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"

            payload = {
                "contents": [{
                    "parts": [
                        {
                            "text": (
                                "Analizza questa immagine di testo distorto per l'accessibilità. "
                                "È una stringa casuale di caratteri senza senso compiuto. "
                                "Scrivi unicamente i caratteri esatti che vedi ordinati di seguito, "
                                "tutto in minuscolo, senza spazi, senza introduzioni e senza punteggiatura."
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": base64_image
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 15
                }
            }

            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": Settings.GEMINI_API_KEY
            }

            response = None
            ultimo_errore = None

            for tentativo in range(1, MAX_TENTATIVI + 1):
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDI)

                    if response.status_code == 429:
                        raise CaptchaServiceUnavailable("Quota o limite rateo della chiave Gemini API esaurito.")

                    response.raise_for_status()
                    break  # richiesta riuscita, esce dal loop di retry

                except requests.exceptions.ReadTimeout as e:
                    ultimo_errore = e
                    logger.warning(
                        f"⏱️ Timeout Gemini (tentativo {tentativo}/{MAX_TENTATIVI}) per {chiave}, "
                        f"nuovo tentativo tra {2 * tentativo}s..."
                    )
                    if tentativo == MAX_TENTATIVI:
                        raise
                    time.sleep(2 * tentativo)

            data = response.json()
            testo_indovinato = data['candidates'][0]['content']['parts'][0]['text'].strip().lower()

            logger.info(f"🤖 [GEMINI FLASH] Codice analizzato per {chiave} -> Tentativo: '{testo_indovinato}'")

            campo_testo = frame.locator(Settings.SEL_CAPTCHA_INPUT)
            campo_testo.fill(testo_indovinato)
            NavigatoreSister._forza_evento_dom(campo_testo)
            return testo_indovinato

        except CaptchaServiceUnavailable:
            raise

        except Exception as e:
            logger.error(f"Errore durante la risoluzione AI del codice: {e}")
            error_text = str(e).lower()
            if "429" in error_text or "quota" in error_text:
                raise CaptchaServiceUnavailable(
                    "Vision non disponibile: quota o limite rateo della chiave Gemini API esaurito."
                ) from e
            raise SisterError(f"Impossibile leggere il codice di sicurezza con Gemini Vision: {e}") from e

    @staticmethod
    def _attendi_caricamento_captcha_page(page, comune="", foglio="", particella=""):
        """
        🎯 RADAR AD ATTESA ESPLICITA E DINAMICA:
        Scansiona la pagina ogni 500ms. Se intercetta errori di mancato reperimento,
        immobili inesistenti o soppressi, fa scattare l'Early Exit immediato.
        
        🚀 CORREZIONE DA MAESTRO: Se il campo captcha non c'è, ma individua il bottone
        'Inoltra', aggancia il frame e consente l'inoltro diretto senza codice!
        """
        tentativi_massimi = int(Settings.CAPTCHA_TIMEOUT_S * 2)
        label_info = f"{comune} FG {foglio} PART {particella}"
        
        for _ in range(tentativi_massimi):
            try:
                body = page.content().lower()
                
                # Avvisi ed eccezioni bloccanti di Sister
                if "non trovato" in body or "nessun immobile" in body or "esito negativo" in body:
                    raise ImmobileNonTrovato(f"Immobile non trovato per {label_info}")
                if "soppressa" in body or "soppresso" in body:
                    raise ParticellaSoppressa(f"Particella soppressa per {label_info}")
                if "error 500" in body or "nullpointer" in body or "eccezione" in body:
                    raise SisterError("Il server di Sister ha risposto con Errore 500 (NullPointerException).")
                if "reperimento dei dati" in body or "problemi in fase" in body:
                    raise SisterError("Mancato reperimento dati in tempo reale (Schermata Rossa Sogei).")

                # Analisi dei Frame per l'aggancio della sottomissione
                for frame in page.frames:
                    try:
                        # Opzione A: Schermata standard con casella Captcha visibile
                        if frame.locator(Settings.SEL_CAPTCHA_INPUT).count() > 0:
                            frame.locator(Settings.SEL_CAPTCHA_INPUT).wait_for(state="visible", timeout=1000)
                            return frame
                        
                        # Opzione B (Bypass): Manca il captcha ma il tasto 'Inoltra' è già presente ed utilizzabile
                        elif frame.locator("input[type='submit'][value='Inoltra']").count() > 0:
                            return frame
                    except Exception:
                        continue
            except (ImmobileNonTrovato, ParticellaSoppressa, SisterError):
                raise
            except Exception:
                pass
            time.sleep(0.5)
        return None

    @staticmethod
    def _processa_ricerca_con_retry(page, comune: str, provincia: str, foglio: str, particella: str, tipo: str, sub: str = ""):
        if tipo == "NCT":
            target_frame = NavigatoreSister._compila_modulo_unificato(page, comune, "NCT", foglio, particella)
            # Pausa riflessiva prima dell'invio per dare tempo al server di sincronizzare
            pausa = random.uniform(1.5, 2.2)
            logger.info(f"   ⏳ Pausa riflessiva di {pausa:.2f}s prima dell'invio (NCT)...")
            time.sleep(pausa)
            btn = target_frame.locator(Settings.SEL_NCT_SUBMIT)
            try:
                btn.hover()
                time.sleep(0.3)
            except Exception:
                pass
            btn.click()
        else:
            target_frame = NavigatoreSister._compila_modulo_unificato(page, comune, "NCF", foglio, particella, sub)
            pausa = random.uniform(1.5, 2.2)
            logger.info(f"   ⏳ Pausa riflessiva di {pausa:.2f}s prima dell'invio (NCF)...")
            time.sleep(pausa)
            btn = target_frame.locator(Settings.SEL_NCF_SUBMIT)
            try:
                btn.hover()
                time.sleep(0.3)
            except Exception:
                pass
            btn.click()

        captcha_frame = NavigatoreSister._attendi_caricamento_captcha_page(page, comune, foglio, particella)
        if not captcha_frame:
            raise SisterError("La pagina di riepilogo con il codice di sicurezza non è comparsa (Timeout server).")

        for tentativo in range(1, 3):
            if tentativo > 1:
                captcha_frame = NavigatoreSister._attendi_caricamento_captcha_page(page, comune, foglio, particella)
                if not captcha_frame:
                    raise SisterError("Il frame di convalida è svanito durante la rigenerazione del codice.")

            # 🎯 INTEGRAZIONE SCUDO BYPASS CAPTCHA
            # Controlliamo se la casella di testo del captcha esiste fisicamente nel frame agganciato
            ha_captcha = captcha_frame.locator(Settings.SEL_CAPTCHA_INPUT).count() > 0
            
            if ha_captcha:
                # Se c'è il captcha, la Vision AI entra in azione normalmente
                NavigatoreSister._risolvi_captcha_automatico(captcha_frame, f"{comune} FG {foglio} PART {particella}")
                time.sleep(0.1)
            else:
                # Se il captcha è assente, applichiamo l'esitazione dinamica e andiamo dritti al clic
                logger.info("   🚀 [MASTER BYPASS] Pagina senza captcha rilevata! Applico un'esitazione dinamica di sicurezza...")
                time.sleep(1.5) 
            
            # Clic sul tasto Inoltra (funzionerà sia con captcha compilato sia in modalità bypass diretto)
            captcha_frame.locator("input[type='submit'][value='Inoltra']").click()
            try:
                page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass

            body_check = page.content().lower()
            
            if "error 500" in body_check or "nullpointer" in body_check or "eccezione" in body_check:
                raise SisterError("Il server di Sister ha risposto con Errore 500 (NullPointerException). Richiesto Hard Reset.")

            if "reperimento dei dati" in body_check or "problemi in fase" in body_check:
                raise SisterError("Mancato reperimento dati in tempo reale (Schermata Rossa Sogei). Sposto il record nella coda dei differiti.")

            # Verifica finale: se non siamo più sulla pagina del captcha, la visura è andata a buon fine!
            ancora_su_captcha = captcha_frame.locator(Settings.SEL_CAPTCHA_INPUT).count() > 0
            if not ancora_su_captcha:
                logger.info(f"   ✅ Codice accettato o bypassato con successo al tentativo [{tentativo}/2]!")
                return page

            logger.warning(f"   ⚠️ Tentativo [{tentativo}/2] fallito (Codice errato). Sister ha rigenerato l'immagine.")

        logger.error(f"   ❌ Falliti 2 tentativi di codice consecutivi per la particella {particella}.")
        if captcha_frame.locator(Settings.SEL_BUTTON_INDIETRO).count() > 0:
            try:
                captcha_frame.locator(Settings.SEL_BUTTON_INDIETRO).first.click()
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
        raise SisterError(f"Codice di sicurezza errato per 2 volte consecutive. Record saltato.")

    @staticmethod
    def search_nct(page, comune: str, provincia: str, foglio: str, particella: str):
        return NavigatoreSister._processa_ricerca_con_retry(page, comune, provincia, foglio, particella, "NCT")

    @staticmethod
    def search_ncf(page, comune: str, provincia: str, foglio: str, particella: str, sub: str = ""):
        return NavigatoreSister._processa_ricerca_con_retry(page, comune, provincia, foglio, particella, "NCF", sub)

    @staticmethod
    def _aggancia_form_ricerca_storica(page):
        for tentativo in range(5):
            frame = NavigatoreSister._frame_con_selettore(page, Settings.SEL_NCT_COMUNE)
            if frame and frame.locator(Settings.SEL_NCT_FOGLIO).count() and frame.locator(Settings.SEL_NCT_PARTICELLA).count():
                logger.info(f"   🎯 Form ricerca storica agganciato (tentativo {tentativo + 1}/5).")
                return frame
            time.sleep(1.0)
        raise SisterError("Impossibile agganciare il form Comune/Foglio/Particella nei frame.")

    @staticmethod
    def _imposta_sezione(page, frame, section: str):
        section_select = frame.locator(Settings.SEL_SECTION_DROPDOWN)
        if not section:
            # Sermide e Felonica non possiede una sezione: lascia il controllo neutro.
            if section_select.count():
                try:
                    section_select.first.select_option(index=0)
                    NavigatoreSister._forza_evento_dom(section_select.first)
                except Exception:
                    pass
            return frame

        def section_is_available() -> bool:
            if not section_select.count():
                return False
            desired = NavigatoreSister._normalizza_testo(section)
            for option_index in range(section_select.first.locator("option").count()):
                option = section_select.first.locator("option").nth(option_index)
                if desired in {
                    NavigatoreSister._normalizza_testo(option.text_content()),
                    NavigatoreSister._normalizza_testo(option.get_attribute("value")),
                }:
                    return True
            return False

        if not section_is_available():
            choose_button = frame.locator(Settings.SEL_CHOOSE_SECTION_SUBMIT)
            if not choose_button.count():
                raise SisterError("Pulsante 'scegli la sezione' non trovato nel form.")
            logger.info("   -> Click su 'scegli la sezione' per caricare l'elenco sezioni.")
            choose_button.first.click()
            try:
                page.wait_for_load_state("load", timeout=5000)
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            time.sleep(1.5)
            # Il submit ricrea il DOM e rende non più valido il vecchio frame.
            frame = NavigatoreSister._aggancia_form_ricerca_storica(page)
            section_select = frame.locator(Settings.SEL_SECTION_DROPDOWN)

        section_select = frame.locator(Settings.SEL_SECTION_DROPDOWN)
        if not section_select.count():
            raise SisterError("Il menu della sezione non è comparso dopo 'Scegli la sezione'.")
        NavigatoreSister._seleziona_label_o_valore(section_select.first, section)
        return frame

    @staticmethod
    def search_historical_property(page, job: HistoricalJob) -> PropertyResult:
        """Esegue la ricerca catastale fino all'Elenco Immobili e ne legge la prima riga."""
        frame = NavigatoreSister._aggancia_form_ricerca_storica(page)

        comune = frame.locator(Settings.SEL_NCT_COMUNE)
        current = comune.evaluate("el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''")
        if NavigatoreSister._normalizza_testo(current) != NavigatoreSister._normalizza_testo(job.comune):
            logger.info(f"   -> Cambio comune: {job.comune.upper()}")
            NavigatoreSister._seleziona_label_o_valore(comune, job.comune)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            time.sleep(2.0)
            # Il cambio comune può ricostruire completamente il frame.
            frame = NavigatoreSister._aggancia_form_ricerca_storica(page)

        frame = NavigatoreSister._imposta_sezione(page, frame, job.sezione)
        NavigatoreSister._digita(frame.locator(Settings.SEL_NCT_FOGLIO), job.foglio)
        time.sleep(random.uniform(0.4, 0.8))
        NavigatoreSister._digita(frame.locator(Settings.SEL_NCT_PARTICELLA), job.particella)

        sub = frame.locator(Settings.SEL_NCF_SUB)
        if sub.count():
            try:
                sub.fill("")
            except Exception:
                pass

        pausa = random.uniform(1.5, 2.2)
        logger.info(f"   ⏳ Pausa riflessiva di {pausa:.2f}s prima di Ricerca...")
        time.sleep(pausa)
        search_button = frame.locator(Settings.SEL_SEARCH_SUBMIT)
        if not search_button.count():
            raise SisterError("Pulsante 'Ricerca' non trovato nel form catastale.")
        search_button.first.click()

        # La conferma compare soltanto quando la ricerca è stata fatta senza subalterno.
        for _ in range(int(Settings.CAPTCHA_TIMEOUT_S * 2)):
            NavigatoreSister._check_errori_sister(page, f"{job.comune} FG {job.foglio} PART {job.particella}")
            confirm_frame = NavigatoreSister._frame_con_selettore(page, Settings.SEL_CONFIRM_SUBMIT, visible=True)
            if confirm_frame:
                logger.info("   -> Conferma dell'assenza del subalterno.")
                confirm_frame.locator(Settings.SEL_CONFIRM_SUBMIT).first.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                break
            if NavigatoreSister._find_property_table(page):
                break
            time.sleep(0.5)

        for _ in range(int(Settings.CAPTCHA_TIMEOUT_S * 2)):
            NavigatoreSister._check_errori_sister(page, f"{job.comune} FG {job.foglio} PART {job.particella}")
            if NavigatoreSister._find_property_table(page):
                break
            time.sleep(0.5)
        result = NavigatoreSister.extract_first_property(page)
        return result

    @staticmethod
    def _find_property_table(page):
        required = {"foglio", "particella", "qualita"}
        for frame in list(page.frames):
            try:
                tables = frame.locator("table")
                for index in range(tables.count()):
                    table = tables.nth(index)
                    header_texts = table.locator("tr").first.locator("th, td").all_inner_texts()
                    normalized = {NavigatoreSister._normalizza_testo(item) for item in header_texts}
                    if required.issubset(normalized):
                        return table
            except Exception:
                continue
        return None

    @staticmethod
    def extract_first_property(page) -> PropertyResult:
        table = NavigatoreSister._find_property_table(page)
        if table is None:
            raise SisterError("Tabella 'Elenco Immobili' non trovata o incompleta.")

        rows = table.locator("tr")
        headers = [NavigatoreSister._normalizza_testo(value) for value in rows.first.locator("th, td").all_inner_texts()]
        values = None
        for index in range(1, rows.count()):
            cells = rows.nth(index).locator("td").all_inner_texts()
            if cells and any(str(cell).strip() for cell in cells):
                values = [re.sub(r"\s+", " ", str(cell)).strip() for cell in cells]
                break
        if values is None:
            raise ImmobileNonTrovato("La tabella Elenco Immobili non contiene righe catastali.")

        return NavigatoreSister._property_result_from_cells(headers, values)

    @staticmethod
    def _property_result_from_cells(headers: list[str], values: list[str]) -> PropertyResult:
        headers = [NavigatoreSister._normalizza_testo(value) for value in headers]
        def value_for(*aliases):
            for alias in aliases:
                normalized_alias = NavigatoreSister._normalizza_testo(alias)
                if normalized_alias in headers:
                    position = headers.index(normalized_alias)
                    return values[position] if position < len(values) else ""
            return ""

        return PropertyResult(
            sub=value_for("Sub"),
            ha=value_for("ha"),
            are=value_for("are"),
            ca=value_for("ca", "cent."),
            qualita=value_for("Qualità", "Qualità terreno categoria"),
            reddito_dominicale=value_for("Reddito dominicale", "Reddito Dom."),
            reddito_agrario=value_for("Reddito agrario", "Reddito Agr."),
        )

    @staticmethod
    def extract_owners(page) -> list[str]:
        body = page.content().lower()
        zero_markers = (
            "nessun intestat",
            "non risultano intestat",
            "intestatari: 0",
            "intestati: 0",
            "nessun soggetto",
            "nessuna corrispondenza trovata",
        )
        if any(marker in body for marker in zero_markers):
            return []

        owner_markers = ("intestat", "codicefiscale", "diritto", "quota", "nominativo")
        for frame in list(page.frames):
            try:
                tables = frame.locator("table")
                for table_index in range(tables.count()):
                    table = tables.nth(table_index)
                    table_norm = NavigatoreSister._normalizza_testo(table.inner_text())
                    if not any(marker in table_norm for marker in owner_markers):
                        continue
                    owners = []
                    rows = table.locator("tr")
                    for row_index in range(rows.count()):
                        row = rows.nth(row_index)
                        if not row.locator("td").count():
                            continue
                        cell_norms = {
                            NavigatoreSister._normalizza_testo(cell)
                            for cell in row.locator("th, td").all_inner_texts()
                        }
                        header_labels = {"intestatario", "nominativo", "codicefiscale", "diritto", "quota"}
                        if row.locator("th").count() or len(cell_norms & header_labels) >= 2:
                            continue
                        text = re.sub(r"\s+", " ", row.inner_text()).strip()
                        if text:
                            owners.append(text)
                    if owners:
                        return owners
            except Exception:
                continue
        raise SisterError("Pagina Intestati caricata, ma nessuna tabella o messaggio di esito è riconoscibile.")

    @staticmethod
    def open_owners(page) -> list[str]:
        frame = NavigatoreSister._frame_con_selettore(page, Settings.SEL_OWNERS_SUBMIT, visible=True)
        if not frame:
            raise SisterError("Pulsante 'Intestati' non trovato nell'Elenco Immobili.")
        frame.locator(Settings.SEL_OWNERS_SUBMIT).first.click()
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        time.sleep(1.5)
        last_error = None
        for _ in range(int(Settings.CAPTCHA_TIMEOUT_S * 2)):
            try:
                return NavigatoreSister.extract_owners(page)
            except SisterError as exc:
                last_error = exc
                time.sleep(0.5)
        raise last_error or SisterError("Pagina Intestati non riconosciuta.")

    @staticmethod
    def _click_indietro(page) -> bool:
        frame = NavigatoreSister._frame_con_selettore(page, Settings.SEL_BUTTON_INDIETRO, visible=True)
        if not frame:
            return False
        frame.locator(Settings.SEL_BUTTON_INDIETRO).first.click()
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        time.sleep(1.5)
        return True

    @staticmethod
    def _select_historical_analytical(page) -> None:
        for frame in list(page.frames):
            try:
                # L'HTML Sister riutilizza erroneamente id="tipoVisura" per tutti
                # i radio: cliccare la label Analitica può quindi attivare Completa.
                analytical = frame.locator("input[type='radio'][name='tipoVisura'][value='3']")
                if analytical.count() and analytical.first.is_visible():
                    analytical.first.check()
                    NavigatoreSister._forza_evento_dom(analytical.first)
                    logger.info("   -> Visura Storica Analitica selezionata (tipoVisura=3).")
                    return
            except Exception:
                continue
        raise SisterError("Radio 'Storica - Analitica' non trovato nella pagina Visura per immobile.")

    @staticmethod
    def _conferma_captcha_corrente(page, chiave: str) -> None:
        captcha_frame = NavigatoreSister._attendi_caricamento_captcha_page(page)
        if not captcha_frame:
            raise SisterError("Pagina di inoltro della visura storica non comparsa.")
        for tentativo in range(1, 3):
            if tentativo > 1:
                captcha_frame = NavigatoreSister._attendi_caricamento_captcha_page(page)
                if not captcha_frame:
                    break
            if captcha_frame.locator(Settings.SEL_CAPTCHA_INPUT).count():
                NavigatoreSister._risolvi_captcha_automatico(captcha_frame, chiave)
                time.sleep(0.1)
            else:
                logger.info("   🚀 Pagina senza captcha: inoltro diretto dopo la pausa di sicurezza.")
                time.sleep(1.5)
            captcha_frame.locator(Settings.SEL_FORWARD_SUBMIT).first.click()
            try:
                page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass
            body = page.content().lower()
            if "error 500" in body or "nullpointer" in body or "eccezione" in body:
                raise SisterError("Errore 500 durante l'inoltro della visura storica.")
            if not captcha_frame.locator(Settings.SEL_CAPTCHA_INPUT).count():
                logger.info(f"   ✅ Inoltro visura storica accettato [{tentativo}/2].")
                return
            logger.warning(f"   ⚠️ Captcha storico non accettato [{tentativo}/2].")
        raise SisterError("Codice di sicurezza della visura storica errato per 2 volte.")

    @staticmethod
    def request_historical_analytical(page, job: HistoricalJob) -> None:
        # Si parte dalla pagina Intestati: un Indietro riporta all'Elenco Immobili.
        if not NavigatoreSister._click_indietro(page):
            raise SisterError("Impossibile tornare dagli Intestati all'Elenco Immobili.")
        frame = NavigatoreSister._frame_con_selettore(page, Settings.SEL_HISTORICAL_REPORT_SUBMIT, visible=True)
        if not frame:
            raise SisterError("Pulsante 'Visura Per Immobile' non trovato.")
        frame.locator(Settings.SEL_HISTORICAL_REPORT_SUBMIT).first.click()
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        time.sleep(1.5)
        NavigatoreSister._select_historical_analytical(page)
        NavigatoreSister._conferma_captcha_corrente(
            page, f"{job.comune} FG {job.foglio} PART {job.particella}"
        )

    @staticmethod
    def return_to_historical_search(page, initial_url: str) -> None:
        logger.info("🔄 Ritorno alla pagina iniziale Ricerca per immobile...")
        time.sleep(1.5)
        for step in range(1, 6):
            try:
                frame = NavigatoreSister._frame_con_selettore(page, Settings.SEL_SEARCH_SUBMIT)
                if frame and frame.locator(Settings.SEL_NCT_FOGLIO).count():
                    logger.info("✅ Form di ricerca iniziale nuovamente pronto.")
                    return
            except Exception:
                pass
            logger.info(f"   -> Ritorno strutturale, passo {step}/5.")
            if not NavigatoreSister._click_indietro(page):
                try:
                    page.go_back()
                    time.sleep(2.0)
                except Exception:
                    break

        logger.warning("   -> Percorso Indietro incompleto; ripristino tramite URL iniziale.")
        page.goto(initial_url)
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        time.sleep(2.5)
        NavigatoreSister._aggancia_form_ricerca_storica(page)

    @staticmethod
    def torna_al_form(page, url_iniziale: str = None):
        """
        Riporta il browser alla maschera principale di inserimento dati.
        🎯 SCUDO ANTI-DETACHED FRAME: Protegge i cicli di scansione dei frame dalle 
        mutazioni asincrone di Playwright ed applica un freno idraulico sui tempi di caricamento.
        """
        logger.info("🔄 Avvio della procedura di ritorno alla maschera principale (Freno a max 2 livelli)...")
        
        fallback_local_url = "https://sister3.agenziaentrate.gov.it/Visure/vimm/IndietroDatiImm.do"
        fallback_office_url = "https://sister3.agenziaentrate.gov.it/Visure/SceltaLink.do?lista=IMM&codUfficio=LI"
        
        # ⏱️ Pausa preventiva di stabilizzazione post-download
        time.sleep(1.5)

        # 🛡️ Funzione interna di sicurezza per scansionare i frame senza rischiare il "Frame was detached"
        def verifica_form_protetto() -> bool:
            try:
                for f in list(page.frames):
                    try:
                        if f.locator("input[type='submit'][name='scelta'][value='Visura']").count() > 0:
                            return True
                    except Exception:
                        continue  # Se il frame si distacca durante il controllo, passa al successivo senza crashare
            except Exception:
                pass
            return False

        # 🚨 CONTROLLO RAPIDO ERRORE 500
        try:
            testo_pagina = str(page.content()).upper()
            if "500" in testo_pagina or "NULLPOINTER" in testo_pagina or "EXCEPTION" in testo_pagina:
                logger.warning("   ⚠️ RILEVATO ERRORE 500 SUL SERVER! Forzo il reset macro dell'ufficio...")
                raise ValueError()
        except Exception:
            pass

        # -------------------------------------------------------------------------
        # TENTATIVO 1: Navigazione a ritroso controllata (Solo se la pagina è stabile)
        # -------------------------------------------------------------------------
        else:
            for step in range(1, 3):  # Al massimo 2 passi indietro
                if verifica_form_protetto():
                    logger.info("✅ Maschera principale agganciata con successo. Pronto per il prossimo job.")
                    return

                cliccato = False
                try:
                    for frame in list(page.frames):
                        try:
                            btn_indietro = frame.locator(Settings.SEL_BUTTON_INDIETRO)
                            if btn_indietro.count() > 0 and btn_indietro.first.is_visible():
                                logger.info(f"   -> [Passo {step}] Clic su bottone 'Indietro' strutturale.")
                                btn_indietro.first.click()
                                cliccato = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
                
                if cliccato:
                    try:
                        page.wait_for_load_state("load", timeout=3000)
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass
                    time.sleep(2.0)  # ⏱️ Freno idraulico post-click
                else:
                    logger.warning(f"   -> [Passo {step}] Nessun bottone rilevato. Eseguo go_back() nativo...")
                    try:
                        page.go_back()
                        page.wait_for_load_state("load", timeout=3000)
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except Exception:
                        pass
                    time.sleep(2.0)  # ⏱️ Freno idraulico post-go_back

            if verifica_form_protetto():
                logger.info("✅ Maschera principale riagganciata con successo dopo i passi a ritroso.")
                return

        # -------------------------------------------------------------------------
        # TENTATIVO 2: Hard Recovery (Rigenerazione Totale della struttura Frame)
        # -------------------------------------------------------------------------
        logger.warning("   🚨 Stato instabile o frame distaccati. Eseguo l'Hard Reset della sessione...")
        
        # 1. Tentativo con modulo locale
        try:
            page.goto(fallback_local_url)
            page.wait_for_load_state("load", timeout=4000)
            page.wait_for_load_state("networkidle", timeout=4000)
            time.sleep(2.0)
            if verifica_form_protetto():
                logger.info("✅ Ripristino locale riuscito. Sessione pulita.")
                return
        except Exception:
            pass

        # 2. Hard Reset strutturale sull'Ufficio provinciale (Livorno)
        logger.warning("   🚨 Reset locale fallito. ESEGUO HARD RESET SULL'UFFICIO DI LIVORNO...")
        try:
            page.goto(fallback_office_url)
            page.wait_for_load_state("load", timeout=6000)
            page.wait_for_load_state("networkidle", timeout=6000)
            time.sleep(3.0)  # Pausa estesa indispensabile per consentire a Java di ricreare i frame
            
            if verifica_form_protetto():
                logger.info("✅ HARD RESET RIUSCITO! La struttura frame di Livorno è stata rigenerata.")
                return
        except Exception:
            pass

        # 3. Ultimissima spiaggia
        if url_iniziale:
            logger.warning("   -> Tentativo estremo su url_iniziale...")
            try:
                page.goto(url_iniziale)
                page.wait_for_load_state("load", timeout=5000)
                page.wait_for_load_state("networkidle", timeout=5000)
                time.sleep(2.5)
                if verifica_form_protetto():
                    return
            except Exception:
                pass
            
        raise SisterError("Impossibile ritornare alla maschera principale. Struttura della pagina compromessa.")

    @staticmethod
    def _check_errori_sister(page, label: str):
        body = page.content().lower()
        if "non trovato" in body or "nessun immobile" in body or "esito negativo" in body:
            raise ImmobileNonTrovato(label)
        if "soppressa" in body or "soppresso" in body:
            raise ParticellaSoppressa(label)
        if "error 500" in body or "nullpointer" in body or "eccezione" in body:
            raise SisterError(f"Errore 500 Sister durante la ricerca: {label}")
        if "reperimento dei dati" in body or "problemi in fase" in body:
            raise SisterError(f"Mancato reperimento dei dati in tempo reale: {label}")

    @staticmethod
    def recupera_richieste_differite(page, cache):
        import re
        logger.info("📩 Avvio scansione per il recupero delle visure differite (Area Richieste)...")
        
        link_locator = None
        for frame in page.frames:
            if frame.locator(Settings.SEL_LINK_RICHIESTE).count() > 0:
                link_locator = frame.locator(Settings.SEL_LINK_RICHIESTE).first
                break
        if not link_locator and page.locator(Settings.SEL_LINK_RICHIESTE).count() > 0:
            link_locator = page.locator(Settings.SEL_LINK_RICHIESTE).first

        if not link_locator:
            logger.warning("⚠️ Impossibile individuare il link 'Richieste' nel menu laterale della pagina corrente.")
            return

        try:
            with page.context.expect_page(timeout=15000) as popup_info:
                link_locator.click()
            richieste_page = popup_info.value
            richieste_page.wait_for_load_state("networkidle")
            time.sleep(2.0)
            
            rows = richieste_page.locator(Settings.SEL_ROW_RICHIESTA)
            rows_count = rows.count()
            logger.info(f"📊 Rilevate {rows_count} righe di documenti elaborati presenti in tabella.")
            
            for i in range(rows_count):
                row = rows.nth(i)
                text_content = row.text_content().replace('\xa0', ' ')
                
                match = re.search(r"FG\.\s*(\d+)\s+PART\.\s*([A-Za-z0-9/]+)(?:\s+SUB\.\s*(\d+))?\s+DI\s+(.+)", text_content, re.IGNORECASE)
                if match:
                    foglio = match.group(1)
                    particella = match.group(2)
                    sub = match.group(3) or "nan"
                    comune_grezzo = match.group(4).strip().upper()
                    
                    comune = comune_grezzo.split('\n')[0].split('\t')[0].strip()
                    tipo = "NCF" if sub != "nan" else "NCT"
                    
                    chiave = f"{comune}_{foglio}_{particella}_{sub.lower()}_{tipo}"
                    
                    if cache.is_cached(chiave):
                        logger.info(f"   -> [{i+1}/{rows_count}] Rec: {chiave} già presente in locale (Skip).")
                        continue
                        
                    logger.info(f"   -> [{i+1}/{rows_count}] Download in corso per visura differita recuperata: {chiave}")
                    dest_path = cache.get_path(chiave)
                    
                    try:
                        btn_salva = row.locator("a[href*='metodo=salva']").first
                        with richieste_page.expect_download(timeout=30000) as dl_info:
                            btn_salva.click()
                        download = dl_info.value
                        download.save_as(str(dest_path))
                        logger.info("      ✅ File recuperato ed inserito in cache con successo.")
                    except Exception as e_dl:
                        logger.error(f"      ❌ Errore durante il download del file {chiave}: {e_dl}")
            
            richieste_page.close()
            logger.info("✅ Fase di recupero differito completata ordinatamente.")
            
        except Exception as e_pop:
            logger.error(f"❌ Impossibile gestire l'apertura o la consultazione della finestra Richieste: {e_pop}")
