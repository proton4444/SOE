# SOE Readiness and Market Assessment

Status: **valutazione corrente**  
Data: 2026-08-11

La roadmap esecutiva derivata da questa valutazione e in
[`ROADMAP.md`](ROADMAP.md).

## Verdetto

SOE e gia adatto a una demo interna di agenti autonomi e ha una base tecnica
credibile per una Coach League. Non e ancora un prodotto utilizzabile da coach
esterni e non e pronto per una competizione pubblica o a pagamento.

La raccomandazione e **GO per una closed alpha orientata alla validazione**, ma
**NO-GO per piattaforma pubblica, premi o monetizzazione** fino a quando non
esistono blueprint versionati, debrief, integrita competitiva e una prova
misurabile che i giocatori vogliano allenare piu versioni dello stesso agente.

## Prontezza attuale

| Area | Stato | Valutazione |
|---|---|---|
| Motore e regole | Solido prototipo | Determinismo, turni simultanei, fog of war, persistenza e generazione mappe sono presenti. |
| Runtime agenti | Funzionante | Un agente legge stato e report, usa strategist e subagent, invia ordini e puo avanzare in autoplay. |
| Qualita tecnica | Buona | La suite corrente contiene 668 test e passa completamente su Python 3.12. |
| Coach experience | Assente | Il coach dispone solo di `model`, `persona`, `temperature` ed `enabled`, gestiti dall'host. |
| Competizione | Parziale | Esistono baseline, seed accoppiati e scoring, ma l'arena supporta solo due policy gratuite e non esegue ancora modelli LLM. |
| Telemetria e debrief | Insufficiente | Ordini finali ed eventi esistono, ma risposta grezza, blueprint, costo e utilizzo non formano un record di gara persistente. |
| Account e ownership | Assente | Stanze, PIN e chiavi sono adeguati alla beta controllata, non a identita, proprieta dell'agente e classifiche pubbliche. |
| Scalabilita operativa | Non pronta | File JSON, chiamate sequenziali e un unico controller autoplay globale limitano concorrenza e ripartenza dei job. |

## Cosa possiamo riutilizzare

- motore deterministico e replay tramite seed e hash dello stato;
- pipeline unica di validazione degli ordini per umani e agenti;
- stato strutturato con fog of war e mappe JSON, SVG e PNG;
- gestione degli errori del provider, retry e sospensione dei bot guasti;
- autoplay, timeline degli eventi e dashboard master;
- mappe generate e scenario duel gia sottoposto a una prima calibrazione;
- baseline casuale e scripted per verificare che lo scenario premi gioco coerente.

Questi elementi riducono fortemente il rischio di costruzione del motore. Il
rischio principale si e spostato sul prodotto, sull'integrita della
competizione e sulla domanda.

## Blocchi prima della Coach League

### 1. Agent Blueprint e proprieta

L'attuale `AgentProfile` appartiene a una coppia stanza/fazione, non a un
giocatore. Serve un'entita persistente indipendente dalla partita con:

- proprietario;
- sezioni strategiche strutturate;
- versione immutabile e hash;
- stato draft, frozen e retired;
- modello e budget consentiti;
- storico delle versioni;
- visibilita pubblica o privata.

Il coach deve poter modificare il proprio blueprint con la propria credenziale.
Oggi configurazione ed esecuzione dei bot sono riservate all'host.

### 2. Ciclo competitivo

Mancano allenamento, congelamento, iscrizione, matchmaking, calendario,
risultato ufficiale, rating e classifica. Una partita ufficiale deve creare un
manifest immutabile contenente almeno:

- engine, scenario, mappa e seed policy;
- blueprint e prompt hash;
- modello, temperatura, token e retry policy;
- seat assignment;
- ordini, warning, errori, stato finale e risultato.

### 3. Debrief utile al coach

Il prodotto vive sul ciclo `prova -> comprende -> modifica -> riprova`. Oggi la
risposta del modello non viene conservata e usage e latenza finiscono solo nei
log. Il debrief deve mostrare:

- obiettivo dichiarato e decisione sintetica del turno;
- ordini proposti, scartati e accettati;
- effetto osservabile degli ordini;
- errori sintattici e strategici;
- metriche territoriali, economiche e militari;
- costo e latenza;
- confronto tra due versioni dello stesso blueprint.

Non va raccolta o mostrata chain-of-thought privata. Serve una breve rationale
esplicita destinata al coach.

### 4. Esecuzione equa e sicura

- Il prompt di produzione espone solo una parte delle azioni del motore; va
  deciso se questa e la superficie ufficiale o se il gioco deve insegnare piu
  meccaniche agli agenti.
- Stato e report vengono troncati nelle campagne lunghe; serve memoria o
  sintesi controllata e riproducibile.
- I messaggi provenienti da altri giocatori devono essere trattati come dati
  non affidabili. Senza separazione possono diventare prompt injection.
- Modello, strumenti, subagent e budget devono essere applicati dal server,
  non soltanto dichiarati dal concorrente.
- L'operatore deve poter riprendere un match interrotto senza alterare seed,
  seat o configurazione.

### 5. Scenario realmente competitivo

La prima calibrazione dimostra un gradiente tra scripted e random sul duel, ma
il segnale rimane rumoroso e non esistono ancora risultati model-vs-model. Il
mondo completo non e validato per il contatto tra avversari.

La prima Coach League deve quindi usare soltanto:

- due giocatori;
- una mappa piccola congelata;
- un singolo strategist senza vision o subagent;
- un modello uguale per tutti;
- un limite breve e dichiarato di turni;
- seed accoppiati e scambio dei posti.

Una partita duel di 30 turni richiede 60 chiamate al modello nella
configurazione a singolo strategist. L'orchestrazione completa attuale ne
richiede fino a 180, eseguite in sequenza: e troppo costosa e lenta per essere
il formato iniziale.

### 6. Operazioni pubbliche

Prima di aprire il servizio servono almeno account, recupero accesso, rate
limits, quote di spesa, job queue persistente, isolamento tra match,
moderazione dei contenuti pubblici, privacy policy e cancellazione dati. PIN e
chiavi di stanza restano utili per inviti temporanei, non come identita del
coach.

## Segnali di mercato

Esistono segnali forti per la categoria adiacente:

- [Google DeepMind e Kaggle Game Arena](https://blog.google/innovation-and-ai/models-and-research/google-deepmind/kaggle-game-arena-updates/)
  hanno esteso nel 2026 il benchmark da chess a poker e Werewolf e hanno
  prodotto eventi live con commentatori esperti. Questo convalida sia i giochi
  come eval agentiche sia il potenziale spettacolare.
- La pagina corrente delle
  [competizioni Kaggle](https://www.kaggle.com/competitions?group=all) mostra
  migliaia di team nella PTCG AI Battle Challenge. Kaggle offre inoltre agli
  organizzatori supporto specifico per ambienti di gioco agentici.
- [MIT Battlecode](https://battlecode.org/) continua nel 2026 con un mese di
  competizione, oltre 20.000 dollari di premi e sponsor tecnologici e
  finanziari. Dimostra che costruire, osservare e migliorare bot strategici
  puo sostenere una comunita e sponsorizzazioni.

Questi segnali non dimostrano ancora domanda per SOE. Tutti i casi forti
beneficiano di distribuzione, brand o IP molto superiori. Inoltre la categoria
generica e gia affollata: [AgentArena](https://agentarena.io/),
[Agent Sports League](https://www.agentsportsleague.com/) e
[Spartic](https://www.spartic.com/) dichiarano gia agent customization,
tournaments, ranking o gioco senza codice. Le loro affermazioni non sono prova
di traction, ma mostrano che il messaggio "agenti che competono" non e una
differenziazione sufficiente.

## Mercato plausibile per SOE

Il segmento iniziale piu credibile non e il pubblico generalista dei giochi di
strategia. E composto da:

1. builder di agenti e prompt engineer che vogliono un test competitivo piu
   ricco di un task statico;
2. sviluppatori AI curiosi che non vogliono costruire un game bot da zero;
3. community, corsi e universita che possono organizzare una Coach League;
4. model provider e sponsor, soltanto dopo che risultati e pubblico sono
   credibili;
5. spettatori, soltanto quando replay e commento rendono leggibile una partita.

Il posizionamento distintivo deve essere:

> Una grand strategy persistente, giocata da agenti che le persone allenano
> senza scrivere codice, con un debrief che mostra perche una dottrina ha
> funzionato.

Non bisogna competere frontalmente con Kaggle come piattaforma generale di
benchmark, ne con i prodotti crypto basati su premi. La profondita del mondo,
la pianificazione su piu turni e il ciclo di coaching sono il vantaggio
potenziale.

## Monetizzazione da validare

Ordine consigliato:

1. stagione gratuita su invito, con crediti di allenamento limitati;
2. pacchetti di simulazioni o abbonamento coach per piu training e analisi;
3. tornei sponsorizzati e Model League finanziate dai provider;
4. licenze private per community formative o ricerca.

Entry fee, scommesse, token e premi finanziati dai giocatori non devono entrare
nel primo prodotto. Aggiungono rischio legale, frodi e incentivi agli exploit
prima che il gioco abbia dimostrato valore.

## Esperimento di mercato

Non serve costruire subito una piattaforma completa. Serve una closed alpha
con circa 20-30 partecipanti reclutati da community AI e strategy gaming.

Offerta minima:

- modello fisso;
- blueprint strutturato;
- tre allenamenti per versione;
- congelamento e iscrizione;
- duel ufficiali con seat swap;
- replay e debrief;
- una finale osservabile.

Gate proposti per decidere se investire:

- almeno 60% degli invitati completa e congela un blueprint;
- almeno 40% crea volontariamente una seconda versione dopo il debrief;
- almeno 90% dei match ufficiali termina senza intervento operativo;
- almeno 30% ritorna per una seconda competizione;
- almeno 20% dichiara una disponibilita concreta a pagare per altri training o
  porta una propria chiave modello;
- almeno 25% condivide spontaneamente un replay o risultato.

Queste percentuali sono soglie decisionali, non dati di mercato gia osservati.
Il segnale principale non e il numero di registrazioni: e se le persone
iterano davvero la dottrina del proprio agente.

## Roadmap consigliata

### Gate 0 - Competenza dell'agente

Integrare un'LLM policy nell'arena e dimostrare che almeno un modello supera il
random e produce differenze ripetibili tra due blueprint volutamente diversi.

### Gate 1 - Coach loop

Costruire blueprint versionato, training, freeze e debrief. Nessun account
pubblico, torneo aperto o pagamento.

### Gate 2 - Closed alpha

Eseguire l'esperimento con utenti reali e misurare attivazione, iterazione,
ritorno, affidabilita e costo per match.

### Gate 3 - Prodotto pubblico

Procedere con account, matchmaking, classifiche, job infrastructure e
monetizzazione soltanto se Gate 2 supera le soglie. In caso contrario, mantenere
SOE come benchmark tecnico o strumento di ricerca invece di forzarlo a essere
un prodotto consumer.

## Decisione corrente

Il progetto non deve espandere ora mappa, grafica o numero di meccaniche. La
priorita e provare due ipotesi:

1. un agente LLM puo giocare il duel con competenza sufficiente;
2. un essere umano prova soddisfazione nel migliorare il proprio blueprint e
   vuole tornare a farlo.

Se entrambe passano, SOE ha una nicchia difendibile. Se passa soltanto la
prima, ha valore come benchmark. Se non passa la prima, il prodotto non e
ancora pronto indipendentemente dalla qualita della dashboard.
