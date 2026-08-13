# SOE Product Roadmap

Status: **roadmap corrente**  
Data: 2026-08-13  
Orizzonte: dalla base tecnica attuale alla prima Coach League pubblica

## Obiettivo

Trasformare SOE da dashboard per bot gestiti dall'host a gioco competitivo nel
quale ogni persona crea, allena, congela e schiera un agente autonomo.

La roadmap segue una sequenza di gate. Una fase si considera completata solo
quando supera i propri criteri di uscita; il completamento del codice non e
sufficiente.

## Principi

- La **Coach League** viene prima di Model League e Open Agent League.
- La prima competizione usa due giocatori, una mappa piccola e un modello fisso.
- Il singolo strategist viene validato prima di vision, memoria e subagent.
- Ogni match ufficiale deve essere riproducibile e accompagnato da un manifest.
- Il debrief e parte del gioco, non una funzione amministrativa secondaria.
- Nessuna classifica pubblica prima di aver dimostrato integrita e affidabilita.
- Nessun pagamento o premio prima di aver dimostrato ritorno e iterazione degli utenti.
- Nuove mappe e meccaniche non hanno priorita finche il coach loop non funziona.

## Stato iniziale

Il progetto dispone gia di:

- motore deterministico e simultaneo;
- fog of war e stato strutturato per fazione;
- ordini validati dalla stessa pipeline per umani e bot;
- managed bots, retry, subagent e autoplay;
- dashboard master, timeline, mappe e report;
- backup, hash dello stato e test di integrita del turno;
- arena scripted-vs-random con seed accoppiati;
- arena LLM headless con manifest, decision trace, resume e report;
- 725 test raccolti su Python 3.12.

La base tecnica non include ancora identita del coach, blueprint indipendenti
dalla stanza, versioni, freeze, training, iscrizioni, match ufficiali o
classifiche.

## Phase 0 - Agent Competence Gate

Specifica di implementazione: [`PHASE0_IMPLEMENTATION.md`](PHASE0_IMPLEMENTATION.md).

### Risultato

Dimostrare che un LLM sa giocare il duel e che istruzioni diverse producono
comportamenti strategici osservabilmente diversi.

### Scope

- Implementare una policy LLM nell'arena headless.
- Usare lo stesso prompt e la stessa superficie informativa della produzione.
- Disabilitare vision e subagent.
- Persistire prompt, risposta, ordini estratti, warning, usage, latenza ed errori.
- Aggiungere manifest, checkpoint e ripresa dei batch.
- Eseguire probe sintattico prima dei match.
- Confrontare modello-vs-random, modello-vs-scripted e blueprint-vs-blueprint.
- Misurare costo e durata di un duel completo.

### Exit criteria

Revisione del 2026-08-13. I run dell'11 agosto sono stati valutati sulla
formulazione precedente, che la tabella di stato riporta; le tre debolezze
elencate piu sotto sono qui chiuse. Le soglie numeriche e lo scenario sono
congelati in `configs/phase0_gate.json`.

**Qualificazione dello scenario.** La mappa del gate deve separare su entrambi
gli assi, verificato con policy scripted a costo zero:

- una policy deliberata batte `random` al test dei sweep;
- due stili scripted intenzionalmente diversi si separano fra loro allo stesso
  test.

Nessuna delle due mappe estreme qualifica: `starter_map.json` e cieca rispetto
alla strategia, `world.json` e cieca rispetto alla differenza fra gioco
deliberato e rumore. Il gate ufficiale usa `calib_12.json`, congelata con hash
SHA-256 e contratto di run in `configs/phase0_gate.json`.

**Test dei sweep.** Ogni confronto usa almeno **40 coppie di seed** (80 partite)
con scambio dei posti. Si contano solo le coppie che producono uno sweep; sotto
l'ipotesi nulla queste si distribuiscono come una binomiale con p=0.5, e il
confronto e superato se il vantaggio e significativo a **p < 0.01** a una coda.
Il win rate grezzo non e mai sufficiente, perche mescola abilita e fortuna della
citta iniziale.

**Competenza.**

- Almeno il 95% delle chiamate produce un ordine accettato.
- Al massimo il **5% delle righe di ordine emesse** produce uno o piu warning.
  Una riga conta una sola volta anche se genera piu messaggi. L'arena misura le
  righe emesse prima del filtro di sicurezza, quindi rimuovere un ordine invalido
  prima dell'esecuzione non nasconde l'errore del modello, e misura separatamente
  le righe inviate dopo la risoluzione del motore. Il gate applica la soglia al
  peggiore dei due tassi. Il vecchio 10.6% (352 messaggi / 3306 ordini
  analizzati) resta solo un segnale storico, non la misura esatta del nuovo
  criterio.
- Il modello supera al test dei sweep la **policy scripted piu forte disponibile
  sulla mappa qualificata**, non `random`.
- Almeno due blueprint intenzionalmente diversi si separano fra loro allo stesso
  test, con differenze visibili in espansione, economia o aggressivita. Il
  verdetto automatico richiede anche almeno 5 punti percentuali di differenza
  nella quota di una famiglia d'ordini rilevante.

**Integrita del run.**

- Tutti i match del batch terminano senza errore del motore.
- Il seat del modello ha effettivamente giocato: `call_failures` vuoto e almeno
  il 99% delle chiamate completate. Un run con seat non configurato o muto e
  **nullo**, non una sconfitta, e non puo comparire in un confronto.
- Un batch interrotto riprende e ricostruisce le partite gia concluse con lo
  stesso `state_sha`.
- Ogni risultato puo essere ricostruito da manifest e ordini salvati.
- Nessun run ufficiale parte da un worktree dirty.
- Costo e durata per match sono noti.

### Stato al 2026-08-13

Il gate **non e ancora superato**. Il contratto e ora eseguibile e rifiuta in
preflight una mappa diversa, meno di 40 coppie, un avversario diverso,
blueprint diversi da quelli congelati, chiave assente, probe del modello non
riuscito nelle ultime 24 ore o worktree dirty. Mancano i due batch ufficiali
provider-backed.

Lo smoke corretto `games/arena/run-20260813-121307-993ca7` chiude il blocker
di prompt e misurazione: 240/240 chiamate completate, 7 vittorie a 1 contro
`scripted:military`, 3 sweep del modello, 0 sweep dell'avversario e 1 split.
Le righe emesse con warning sono 1/924 (0,11%); dopo validazione ed esecuzione
sono 34/923 (3,68%), quindi anche il peggiore dei due tassi resta sotto il 5%.
Il run non e evidenza ufficiale perche usa 4, non 40, coppie e il manifest
registra `git_dirty: true`. E costato 0,119935 USD ed e durato 483 secondi.

Evidenza: **un solo run reale**, `games/arena/run-20260811-110859-2464c0`
(gpt-4o-mini, `expansionist-v1` contro `random`, 8 partite da 30 turni).

Gli altri due run dell'11 agosto non sono prove di competenza. In entrambi il
seat LLM registra `call_failures: not_configured = 240` su 240 chiamate, zero
ordini prodotti e 240 turni no-op: la chiave del provider non era configurata e
`random` ha vinto 8 partite a 0 per forfait. L'arena li registra correttamente
nella tabella di reliability, ma a livello di run restano `status: complete` con
`errors` vuoto, indistinguibili da un run sano.

Ne segue una lacuna del gate: il criterio "tutti i match terminano senza errore
del motore" e soddisfatto anche quando il modello non ha giocato affatto. Il
motore in effetti non ha sbagliato nulla, semplicemente non e mai stato
interrogato.

| Evidenza storica | Esito | Misura |
|---|---|---|
| 95% chiamate con ordine accettato | superato | 240/240 chiamate LLM con almeno un ordine accettato, 0 no-op, 0 retry |
| Match senza errore del motore | superato | 8/8 completi, `errors` vuoto |
| Modello supera random (accoppiato) | superato ma non informativo | 4 sweep su 4 coppie di seed: con n=4 non e distinguibile dal caso (p circa 0.06), e il criterio stesso e debole perche `random` non e un pavimento (vedi sezione seguente) |
| Due blueprint con differenze misurabili | **non testato** | `consolidation-v1` esiste in `configs/blueprints/` ma non e mai entrato in un run; tutti e tre i run sono `expansionist-v1` contro `random` |
| Ricostruibile da manifest e ordini | parziale | decision trace completo per chiamata (raw reply, ordini estratti, ordini accettati, usage, latenza, hash di input), ma il run e partito da un worktree con `git_dirty: true`, contro il prerequisito dello spec |
| Costo e durata noti | superato | 0.1216 USD per 8 partite, circa **0.015 USD per match**; 15m04s per 8 partite, circa **113s per match** |

### Il gradiente dipende dalla mappa, non solo dalla policy

La lettura precedente ("il gioco non ha un gradiente di abilita") era tratta da
un solo confronto su una sola mappa. Tre run del 2026-08-13, a parita di seed,
lunghezza e motore, mostrano un quadro diverso e piu scomodo.

| 30 turni, 40 coppie di seed | `balanced` contro `random` | `military` contro `religious` |
|---|---|---|
| `starter_map.json` | 61.3 / 38.8, sweep **9 - 0**, split 31/40 | 50.0 / 50.0, sweep **4 - 4**, split 32/40 |
| `world.json` | 50.0 / 50.0, sweep **8 - 8**, split 24/40 | 28.7 / 71.3, sweep **2 - 19**, split 19/40 |

Fonti: `checkpoint_3_scoring`, `gradient_styles_starter`,
`gradient_control_balanced_random_world`, `gradient_styles_t30`.

Le due mappe premiano cose opposte:

- su `starter_map.json` il gioco deliberato batte il rumore in modo debole ma
  asimmetrico (9 sweep a 0), mentre i due stili strategici sono indistinguibili;
- su `world.json` accade l'inverso: `scripted:balanced` non si separa affatto dal
  gioco arbitrario (8 a 8, cioe una moneta), ma `religious` domina `military`
  vincendo da entrambi i posti su 19 coppie contro 2.

Ne seguono due conseguenze per il gate.

**La mappa pesa piu della policy.** Lo stesso identico confronto cambia esito
invertendo soltanto lo scenario. Finche la mappa non e calibrata, un risultato
di arena descrive lo scenario almeno quanto l'agente, e la scelta della mappa va
trattata come parte del regolamento, non come un dettaglio di configurazione.

**`random` non e il pavimento che il suo docstring dichiara.** Su `world.json`
regge il pareggio contro una policy deliberata, perche il punteggio e dominato
dall'accumulo di soldati e il baseline casuale recluta di continuo. Un criterio
della forma "il modello supera random" non dimostra quindi competenza e va
sostituito da un avversario forte e deliberato.

Da notare infine che lo smoke LLM della Phase 0 e girato su `starter_map.json`,
cioe sulla mappa in cui l'asse strategico risulta piatto, con n=4 coppie.

### Calibrazione della mappa

La causa e la dimensione. `starter_map.json` ha **6 citta**, `world.json` ne ha
**154**: sono i due estremi, e ciascuno acceca un asse diverso. Con 6 citta non
esiste spazio strategico e gli stili convergono; con 154 nessuno copre la mappa
in 30 turni, il punteggio si riduce all'accumulo di soldati e anche il baseline
casuale ci arriva.

Da questo segue una previsione verificabile: deve esistere una dimensione
intermedia in cui entrambi gli assi sono vivi. Tre mappe candidate generate con
`scripts/generate_world.py --seed 1`, screenate a 40 coppie e 30 turni con il
test dei sweep:

| Mappa | Citta | `balanced` contro `random` | `military` contro `religious` |
|---|---:|---|---|
| `starter_map.json` | 6 | separa, 9-0, p=0.002 | piatta, 4-4, p=0.64 |
| `calib_12.json` | 12 | **separa, 30-1, p=1.5e-08** | **separa, 15-4, p=0.0096** |
| `calib_24.json` | 24 | separa, 21-1, p=5.5e-06 | piatta, 9-10, p=0.5 |
| `calib_48.json` | 48 | piatta, 10-2, p=0.019 | piatta, 7-4, p=0.27 |
| `world.json` | 154 | piatta, 8-8, p=0.6 | separa, 2-19, p=0.00011 |

**`calib_12.json` e l'unica candidata che qualifica su entrambi gli assi**, ed e
anche la piu decisiva: 30 sweep su 40 coppie contro random, con soli 9 split,
mentre `starter_map.json` produce 31 split su 40.

Le due riserve iniziali sono state verificate.

**Campione doppio: confermato.** A 80 coppie di seed l'asse strategico regge con
margine, 29 sweep a 10, p=0.0017, e la direzione e la stessa del campione da 40.

**Seed del generatore: non confermato, ed e la scoperta piu utile.** Ripetendo
la qualificazione su altre due mappe da 12 citta:

| Mappa | Rotte | `balanced` contro `random` | `military` contro `religious` | Qualifica |
|---|---:|---|---|---|
| `calib_12.json` (seed 1) | 14 | separa, p=1.5e-08 | separa, p=0.0017 | si |
| `calib_12_s2.json` (seed 2) | 17 | piatta, p=0.032 | piatta, p=0.5 | **no** |
| `calib_12_s3.json` (seed 3) | 14 | separa, p=1.5e-11 | separa, p=0.00046 | si |

Due mappe su tre qualificano. Il numero di citta e quindi una condizione
**necessaria ma non sufficiente**: a parita di dimensione la topologia decide, e
la mappa con piu rotte e proprio quella che fallisce entrambi gli assi, anche se
tre mappe non bastano per affermare che sia la densita la causa.

La conseguenza operativa e che il gate non puo adottare una regola sulla
dimensione della mappa. Ogni mappa candidata va qualificata individualmente con
i due confronti scripted, che costano zero, prima di essere usata per un match
ufficiale. E la procedura gia scritta negli exit criteria, e questi dati la
giustificano.

Nota su quale stile risulti forte: su `calib_12` vince `military`, su
`world.json` vince `religious`. Anche l'avversario di riferimento e quindi una
proprieta della mappa, non una costante del gioco.

Due avvertenze di lettura sui confronti:

- il seat scripted legge lo stato completo, il seat LLM vede solo la propria fog
  of war; scripted-contro-random e un confronto equo, scripted-contro-modello no;
- lo smoke storico produceva warning nel 70% delle chiamate LLM (168 su 240),
  ma quella misura mescolava messaggi e turni; il runner corretto conta righe
  distinte sia prima del filtro sia dopo l'esecuzione e usa il tasso peggiore.
  Sullo smoke corretto i due tassi sono rispettivamente 0,11% e 3,68%.

### Debolezze del gate, chiuse il 2026-08-13

Le tre debolezze trovate nella formulazione originale, con la correzione
adottata negli exit criteria:

- non era fissata una dimensione campionaria, e questo permetteva a uno smoke da
  8 partite di risultare superato; ora servono 40 coppie di seed e un test di
  significativita sui sweep;
- la soglia "ordine accettato" non distingueva un turno pulito da un turno con
  ordini scartati; ora esiste un limite separato sulla percentuale di righe di
  ordine che producono un warning;
- la ripresa dei batch era nello Scope ma non negli exit criteria, mentre la
  Definition of Done dello spec la richiedeva; ora e un criterio verificabile
  tramite `state_sha`. Il test interrompe un batch, lo riprende e confronta gli
  hash intermedi e finali con un run fresco.

La calibrazione e chiusa: `calib_12.json` e lo scenario ufficiale congelato.

### Decisione

Se il gate fallisce, non si costruisce il prodotto coach. Si correggono prompt,
superficie informativa o scenario e si ripete il gate.

## Phase 1 - Agent Blueprint

### Risultato

Rendere l'agente un oggetto posseduto e versionato, indipendente da una stanza.

### Scope

- Introdurre identita minima del coach per la closed alpha.
- Creare il modello persistente `AgentBlueprint`.
- Separare sezioni strategiche, runtime configuration e stato editoriale.
- Supportare draft, clone, version, freeze e retire.
- Generare hash immutabile delle versioni congelate.
- Collegare una versione congelata a una fazione senza copiarne testo mutabile.
- Migrare l'attuale `persona` in una sezione compatibile del blueprint.
- Consentire al coach, non solo all'host, di gestire i propri agenti.

### Exit criteria

- Un coach puo creare, modificare, duplicare e congelare un blueprint.
- Una versione congelata non puo essere alterata.
- Due versioni dello stesso agente restano distinguibili e recuperabili.
- Nessun coach puo leggere o modificare blueprint privati altrui.
- Il runtime usa esattamente l'hash iscritto al match.
- Migrazione e autorizzazioni sono coperte da test.

## Phase 2 - Training and Debrief

### Risultato

Completare il loop `crea -> prova -> comprende -> modifica` senza intervento
dell'operatore.

### Scope

- Aggiungere arena di allenamento con scenario e avversari predefiniti.
- Applicare quote di training per coach e versione.
- Registrare una rationale sintetica separata dagli ordini.
- Non registrare chain-of-thought privata.
- Mostrare ordini proposti, scartati, accettati ed effetti osservabili.
- Aggiungere replay turno per turno.
- Mostrare territorio, esercito, economia, affidabilita, costo e latenza.
- Confrontare due versioni dello stesso blueprint.
- Rendere chiari gli errori sintattici, provider e strategici.

### Exit criteria

- Un nuovo utente completa un training senza assistenza dell'operatore.
- Dal debrief puo duplicare il blueprint e avviare una nuova prova.
- Ogni numero mostrato deriva dal record persistito del match.
- Nessun dato nascosto di una fazione avversaria appare nel debrief del coach.
- Un test con utenti interni dimostra che vittoria, errore principale e costo
  del match sono comprensibili.

## Phase 3 - Competition Control Plane

### Risultato

Eseguire una Coach League ufficiale, riprendibile e verificabile.

### Scope

- Modellare competition, season, entry, match e result.
- Congelare regolamento, modello, budget, scenario e seed policy.
- Iscrivere versioni specifiche dei blueprint.
- Generare accoppiamenti con seat swap.
- Introdurre job queue persistente e ripresa dopo riavvio.
- Isolare i match e applicare timeout, rate limit e budget lato server.
- Salvare manifest, eventi, ordini, errori e hash finali.
- Trattare messaggi e contenuti avversari come input non affidabili.
- Produrre standings verificabili senza introdurre ancora un rating globale.
- Aggiungere pannello operativo per retry consentiti, sospensione e audit.

### Exit criteria

- Una stagione interna completa almeno 20 agenti senza modifica manuale dei dati.
- Almeno il 95% dei match termina automaticamente.
- Ogni match interrotto puo riprendere senza cambiare configurazione o risultato
  deterministico del motore.
- Nessun concorrente supera modello, token, retry o strumenti consentiti.
- Risultato, manifest e replay concordano per ogni match.
- Le prove di prompt injection non modificano istruzioni di sistema o blueprint.

## Phase 4 - Closed Coach Alpha

### Risultato

Verificare che persone reali vogliano migliorare e schierare piu versioni del
proprio agente.

### Formato

- 20-30 partecipanti invitati da community AI e strategy gaming;
- stesso modello e stessi limiti per tutti;
- blueprint strutturato;
- tre training per versione;
- duel accoppiati e finale osservabile;
- nessun pagamento, premio finanziario o classifica permanente.

### Metriche

- activation: completa e congela un blueprint;
- iteration: crea una seconda versione dopo il debrief;
- match completion: match conclusi senza intervento;
- return: partecipa a una seconda competizione;
- willingness to pay: scelta concreta, non interesse generico;
- sharing: replay o risultato condiviso spontaneamente;
- cost per completed match;
- tempo da registrazione a primo blueprint congelato.

### Go criteria

- activation almeno 60%;
- iteration almeno 40%;
- match completion almeno 90%;
- return almeno 30%;
- willingness to pay o bring-your-own-key almeno 20%;
- sharing almeno 25%;
- nessun problema di integrita che alteri una classifica.

### Decisione

- Se competenza e mercato passano: procedere alla Public Beta.
- Se passa la competenza ma non il mercato: mantenere SOE come benchmark o
  strumento di ricerca e ripensare il prodotto consumer.
- Se gli utenti giocano ma non iterano: il debrief o il blueprint non stanno
  creando il vero loop di gioco.
- Se non passa la competenza: tornare alla Phase 0.

## Phase 5 - Public Beta

### Risultato

Aprire una Coach League gratuita, sicura e operativamente sostenibile.

### Scope

- account, login, recupero e gestione sessioni;
- onboarding e tutorial del coach;
- quote, crediti, controllo costi e protezione dagli abusi;
- orchestrazione concorrente di piu match;
- moderazione di nomi, blueprint pubblici e contenuti condivisi;
- privacy, termini, esportazione e cancellazione dei dati;
- lobby, calendario, notifiche e standings pubblici;
- replay condivisibili e pagina pubblica dell'agente;
- osservabilita, alert e procedure di recovery;
- analytics del funnel e del coach loop.

### Exit criteria

- Due stagioni pubbliche completate senza incidente di integrita.
- Costo per utente e per match rientra nel budget definito.
- Affidabilita e ritorno non peggiorano materialmente rispetto alla closed alpha.
- Supporto e recovery sono gestibili senza interventi manuali sui file.
- Esiste evidenza sufficiente per scegliere una prima monetizzazione.

## Phase 6 - Expansion

Questa fase non e autorizzata finche la Public Beta non supera i propri gate.

Possibili linee, da validare separatamente:

- **Model League:** blueprint fisso e modelli diversi, come benchmark pubblico.
- **Open Agent League:** memoria, vision, subagent e strumenti entro un budget.
- **Regional multiplayer:** quattro agenti su mappe calibrate per contatto e seat fairness.
- **Sponsored seasons:** provider o community finanziano modello e crediti.
- **Education:** competizioni private per corsi, universita e bootcamp.
- **External agent API:** concorrenti avanzati portano un proprio runtime.
- **Spectator product:** commentary, highlight e live finals.

Il mondo completo a sei giocatori entra soltanto dopo una calibrazione che
dimostri contatto, cambi territoriali e assenza di vantaggi dominanti dei posti.

## Non ora

- nuove famiglie di ordini o maggiore fedelta alle regole;
- ampliamento della mappa principale;
- app mobile native;
- marketplace di agenti;
- token, betting o entry fee con premi;
- campionato unico che mescola coach, modelli e sistemi aperti;
- interventi umani turno per turno nelle leghe autonome;
- investimento importante in grafica prima che replay e debrief funzionino;
- rating Elo globale prima di comprendere non-transitivita e seat variance.

## Critical Path

`LLM competence -> Blueprint -> Training/debrief -> Competition control plane -> Closed alpha -> Public beta`

Account consumer completo, monetizzazione, multiplayer regionale e benchmark
pubblico sono dipendenze successive, non lavoro parallelo al critical path.

## Prossimo incremento

Il prossimo lavoro autorizzato resta esclusivamente la **Phase 0 - Agent
Competence Gate**, che e iniziata ma non e superata. Il suo output deve essere
un batch LLM riproducibile, non una nuova pagina della dashboard.

Ordine di lavoro, dal piu economico al piu costoso:

1. ~~Scegliere e calibrare la mappa del gate.~~ **Fatto il 2026-08-13.**
   `calib_12.json` qualifica su entrambi gli assi ed e congelata come scenario
   ufficiale; `calib_12_s3.json` resta una seconda mappa qualificata ma non fa
   parte del gate.
2. ~~Fissare la dimensione campionaria negli exit criteria.~~ **Fatto**, insieme
   alla soglia sui warning, al criterio di ripresa e alla clausola che annulla
   un run con seat del modello non configurato. Il runner produce ora un
   verdetto machine-readable per ogni candidate ufficiale.
3. ~~Sostituire `random` come avversario di riferimento.~~ **Fatto.** L'arena
   supportava gia `scripted:military`; `configs/phase0_competence.json` lo
   seleziona senza altra modifica al motore.
4. ~~Correggere prompt e metrica warning.~~ **Fatto e validato con lo smoke.**
   `run-20260813-121307-993ca7` completa 240/240 chiamate, vince 7-1 contro
   `scripted:military` e resta sotto soglia sia prima del filtro (0,11%) sia
   dopo l'esecuzione (3,68%).
5. **Eseguire il candidate di competenza**, da un worktree pulito e
   con la chiave del provider verificata prima della partenza, a 40 coppie di
   seed: `configs/phase0_competence.json`.
6. **Eseguire il candidate blueprint-vs-blueprint** con `expansionist-v1` e
   `consolidation-v1`: `configs/phase0_blueprints.json`.

Il candidate modello-contro-scripted costa circa 1.22 USD a 40 coppie, sulla
base dei 0.015 USD per match misurati l'11 agosto. Il confronto fra due
blueprint usa due seat LLM e costa quindi circa il doppio, **2.43 USD**. I
ceiling configurati sono rispettivamente 1.50 e 3.00 USD.

L'ipotesi che 30 turni fossero troppo pochi e stata verificata e scartata,
completando il quadro a 60 turni su entrambe le mappe estreme:

| Mappa | Turni | `balanced` contro `random` | `military` contro `religious` |
|---|---:|---|---|
| `starter_map.json` | 30 | separa, 9-0 | piatta, 4-4 |
| `starter_map.json` | 60 | separa, 9-0 | piatta, 5-3 |
| `world.json` | 30 | piatta, 8-8 | separa, 2-19 |
| `world.json` | 60 | piatta, 8-12 | separa, **0-24**, p=6e-08 |

Il comportamento di ogni mappa e stabile rispetto alla lunghezza. Raddoppiare i
turni **rafforza** l'asse che gia funzionava, fino allo sweep totale di
`religious` su 24 coppie decisive, ma non fa comparire quello assente: su
`starter_map.json` gli stili restano indistinguibili e su `world.json` il
baseline casuale prende addirittura piu sweep della policy deliberata.

Ne segue la formulazione piu forte del risultato: **la lunghezza amplifica un
gradiente che esiste gia, non puo crearne uno.** La leva e la mappa, non il
tempo.

Nota operativa sui costi di calcolo: una partita scripted-contro-random dura
circa 0.1s, mentre due policy deliberate che si affrontano davvero costano circa
due ordini di grandezza in piu per partita. Il budget di una stagione va stimato
sul secondo numero, non sul primo.
