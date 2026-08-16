# SOE Product Roadmap

Status: **roadmap corrente**  
Data: 2026-08-14  
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

### Stato al 2026-08-13: gate superato

Il gate **e superato**. I due batch ufficiali provider-backed sono conclusi e
ciascuno riporta `phase0_run_gate.status = "pass"` con tutti e dodici i criteri
verdi. Modello `openai/gpt-4o-mini`, scenario congelato `calib_12.json`, 40
coppie di seed con scambio dei posti, worktree pulito.

| | Competenza | Blueprint |
|---|---|---|
| Run | `run-20260813-141002-20e66d` | `run-20260813-153826-f562a8` |
| Avversari | `expansionist-v1` contro `scripted:military` | `expansionist-v1` contro `consolidation-v1` |
| Sweep | 25 a 1, split 14/40 | 40 a 0, split 0/40 |
| p a una coda | 4.0e-07 | 9.1e-13 |
| Chiamate | 2400/2400 accettate | 4800/4800 accettate |
| Tasso warning peggiore | 3.61% | 3.70% |
| Costo | 1.225473 USD | 2.410201 USD |

Il divario comportamentale fra le due dottrine e ampio e soprattutto coerente
con il testo che le definisce: `expansionist-v1` recluta (26.0% contro 4.6%),
si muove e mette in sicurezza; `consolidation-v1` raccoglie (21.7% contro
1.8%), investe e lavora. Il massimo divario per famiglia d'ordini e 20.5 punti
percentuali contro i 5 richiesti. Le istruzioni cambiano davvero il gioco, non
solo la prosa della rationale.

Costo totale del gate: 3.64 USD. Durata circa 4 ore su 7200 chiamate a circa
2 secondi l'una.

### Due riserve da portare in Phase 1

**La verifica del resume e piu debole di quanto suggerisca il criterio.** Il run
blueprint e stato realmente interrotto al 82% e ripreso fino a chiusura senza
perdere lavoro, il che e evidenza concreta che la ripresa funziona. Ma il
controllo `state_hashes` implementato verifica soltanto che ogni partita abbia
un `final_state_sha` di 64 caratteri: non confronta gli hash con quelli di un
run non interrotto. Il criterio come scritto nella roadmap chiede il confronto,
il codice non lo fa. Va rafforzato prima di dipenderne in Phase 3.

**Le due dottrine non sono bilanciate.** `expansionist-v1` vince 80 partite su
80. Il gate chiedeva che i blueprint si separassero, e si separano nel modo piu
netto possibile, ma questo dice anche che `consolidation-v1` e semplicemente
una strategia perdente su `calib_12.json`. Per una Coach League servono
dottrine che si scambino il vantaggio, non una dominante e una dominata: e un
problema di design del gioco, non del gate, e appartiene alla calibrazione
delle mappe e delle regole.

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

#### Candidato successivo: `calib_12_fbm.json` (2026-08-16)

Lo screen di qualificazione, che era prosa, ora e uno script:
`scripts/screen_gate_map.py`. Riproduce prima la mappa nota — `calib_12.json`
e `--seed 1 --towns 12 --regions 3`, byte per byte — e legge entrambi gli assi
sugli sweep con un sign test.

Screenati 60 seed sul rilievo `fbm` con la regola `detour`: otto qualificano, e
tutti e otto tengono a 80 coppie. Il migliore e il seed 24, congelato come
`calib_12_fbm.json` con il suo sidecar. A 80 coppie:

| Mappa | strategico (`balanced` vs `random`) | stilistico (`military` vs `religious`) |
|---|---|---|
| `calib_12.json` | 36-0 (a 40 coppie) | 27-11, p=0.014 |
| `calib_12_fbm.json` | **76-0, p=2.6e-23** | **31-8, p=0.00029** |

Due avvertenze registrate.

**Il campione da 40 coppie e sottodimensionato sul motore di oggi.** Sull'asse
stilistico `calib_12` risulta piatta a 40 coppie (14-6, p=0.12) e separa a 80
(27-11, p=0.014). La mappa non e decaduta; il campione era piccolo. Nessuno
screen singolo a 40 coppie vale come verdetto.

**Un taglio a dodici citta di `world2` non qualifica.** Il seed 49 e la mappa
scelta per il lavoro cartografico e le dodici citta stanno davvero sul suo
continente, ma l'asse stilistico e piatto a 40 coppie e ancora a 80: military
13, religious 20, p=0.30. La taglia e necessaria, la topologia decide.

`calib_12_fbm.json` **non e ancora lo scenario ufficiale**. Diventarlo richiede
una ri-esecuzione del gate con un modello sulla nuova mappa, cioe spesa reale
sotto un tetto di budget che non e ancora deciso. Fino ad allora `calib_12.json`
resta congelata e le 7.200 chiamate del gate descrivono quella, non questa.

### Decisione

Se il gate fallisce, non si costruisce il prodotto coach. Si correggono prompt,
superficie informativa o scenario e si ripete il gate.

Il gate e superato il 2026-08-13, quindi la Phase 1 e autorizzata.

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

### Stato al 2026-08-14: sei criteri su sei

Il blueprint non e piu un file scelto da riga di comando ma un oggetto
posseduto: `webapp/blueprints.py` per l'entita, `webapp/coaches.py` per
l'identita minima che la possiede, `tests/test_phase1_blueprints.py` per i
criteri di uscita, uno per uno.

Una versione tiene separate tre cose, e la separazione e la parte che conta:

- **strategia** (`persona`, `doctrine`): l'unica parte che il modello legge;
- **runtime** (`model`, `temperature`, `max_tokens`): non e prompt, ma un
  modello diverso gioca una partita diversa, quindi l'hash lo include;
- **editoriale** (nome, note, visibilita, stato): fuori dall'hash, cosi
  rinominare un blueprint non invalida un match gia giocato contro di lui.

L'hash copre le prime due piu id e numero di versione. Ne segue che due
versioni con lo stesso testo restano distinte, e cosi un blueprint e il suo
clone: un match iscrive *questa* versione di *quell'agente*, non "un testo che
suona cosi".

Il confine e il freeze. Una bozza e del coach; una versione congelata non e di
nessuno, nemmeno dell'operatore. Un seat puo iscrivere solo versioni congelate,
e a ogni turno `orchestrator._enrolled_strategy` ricalcola l'hash e rifiuta di
giocare se si e mosso: l'iscrizione porta id, numero e hash, mai il testo.

L'autorizzazione nega leggendo, non solo scrivendo, e risponde 404 e non 403
sul blueprint privato altrui: un 403 su un id conferma che quell'id esiste.

La migrazione (`migrate_personas`) solleva ogni `persona` di seat in un
blueprint congelato, la iscrive sul seat e svuota il campo vecchio: due
sorgenti di strategia sullo stesso seat prima o poi divergono.

### La prima riserva di Phase 0 e chiusa

`test_resume_reproduces_every_turn_hash_not_just_the_final_one` confronta la
traccia intera — turno per turno, partita per partita — fra un run interrotto e
ripreso e un run mai interrotto. Gli hash finali uguali dicevano solo che i due
run finiscono nello stesso posto; una ripresa che ci fosse arrivata per un'altra
strada sarebbe passata lo stesso.

### La seconda riserva ha una causa, e non e la dottrina

`expansionist-v1` vince 80 partite su 80 contro `consolidation-v1`, con 40 sweep
e zero split. Il bundle `run-20260813-153826-f562a8` dice pero anche questo:

| | expansionist-v1 | consolidation-v1 |
|---|---:|---:|
| Attacchi | 0 | 0 |
| Eliminazioni | 0 | 0 |
| Sopravvivenza | 1.0 | 1.0 |
| Secure | 655 | 94 |
| Recruit | 2447 | 511 |
| Collect + Invest + Work | 182 | 4727 |

Le due dottrine non si scontrano mai. Il primo contatto e al turno 2 e nessuno
attacca in 80 partite: la partita finisce al turno 30 e viene assegnata da un
confronto di metriche, non da una conquista. E la catena e
`TIEBREAK = (secured, controlled, soldiers, characters_alive, gold)`.

`expansionist-v1` ha in dottrina "secure cities" e "recruit soldiers", cioe la
prima e la terza voce della catena. `consolidation-v1` ha "costruisci economia",
cioe l'ultima, raggiunta solo se tutto il resto pareggia. Il 100% non misura una
dottrina piu forte: misura una dottrina scritta sulla funzione di punteggio
contro una scritta altrove. Riformulare il testo di `consolidation-v1` non
toglie il problema, lo sposta.

Le due leve vere sono di design, non di prompt:

1. **il punteggio** — se l'economia deve poter vincere, deve pesare nella
   decisione, non stare in fondo alla catena di spareggio;
2. **lo scenario** — a 30 turni senza un attacco, l'economia non ha tempo ne
   motivo di convertirsi in forza. Un contesto in cui i due si contendono
   davvero qualcosa e cio che rende comparabili due dottrine diverse.

La scelta fra le due e una decisione di prodotto e costa una ri-esecuzione
d'arena (circa 2.43 USD a 40 coppie di seed), quindi resta aperta e va presa
prima di trattare la lega come una classifica di dottrine.

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

### Stato al 2026-08-14: prima meta, la prova

Il loop e `crea -> prova -> comprende -> modifica`. La Phase 1 ha chiuso
*crea*; questa meta chiude *prova*, e lascia *comprende* al debrief.

**Un training run e un run d'arena.** L'arena persiste gia cio su cui un
debrief deve poggiare — hash di stato per turno, ogni decisione, gli ordini
come emessi e come accettati, costo, latenza, fallimenti del provider — e sa
riprendere. Costruire un secondo runner avrebbe voluto dire un secondo record
piu debole. `webapp/training.py` decide quindi solo *chi puo eseguire cosa* e
passa il resto a `scripts/arena.py`.

**Il blueprint viaggia per valore.** L'arena prendeva i blueprint da
`configs/blueprints`; un blueprint di Phase 1 e una riga in uno store. La
config di un training porta quindi il payload inline (`blueprint_inline`) e il
bundle lo scrive in forma canonica: il run resta leggibile e riproducibile dopo
che lo store e andato avanti. `run_config` risolve la versione attraverso lo
store, non dal record, quindi una versione modificata dopo l'avvio fa fallire
il run *prima* di spendere — lo stesso rifiuto che riceve un seat di lega.

**Niente chain-of-thought su disco.** I run del coach girano con
`redact_reasoning`, quindi il testo libero del modello prima del marker non
viene mai persistito. Il controllo e in
`test_llm_policy_redacts_private_reasoning_when_asked`: a parita di ordini,
tipi e accettati, spariscono `raw_reply` e `rationale`. Un debrief deve al
coach il resoconto di cosa il suo agente **ha fatto**; il monologo interno del
modello non e ne affidabile come spiegazione ne suo da leggere.

**Le quote sono due, non una.** Quella giornaliera limita il conto; quella per
versione impedisce di bruciare l'intera giornata rieseguendo una versione che
non si e cambiata. Aprire una versione nuova apre una nuova allowance, che e
esattamente l'incentivo giusto.

Il catalogo (`configs/training/scenarios.json`) e fisso: due coach che allenano
lo stesso blueprint incontrano la stessa mappa e lo stesso avversario, quindi i
loro debrief sono confrontabili.

Copertura: `tests/test_phase2_training.py`.

### Stato al 2026-08-14: seconda meta, il debrief

`webapp/debrief.py` non calcola niente da una partita viva: ogni campo esce dal
bundle (`manifest.json`, `games.jsonl`, `turns.jsonl`, `decisions/`,
`arena_results.json`) o e aritmetica che il coach puo rifare. Perche cio fosse
possibile, `record_turn` persiste ora anche le metriche per fazione a fine
turno: erano gia calcolate per il sommario, non erano scritte.

**Una sedia sola.** Il bundle e il record dell'operatore e contiene entrambi i
lati; il debrief e la vista dal posto del coach. Ordini, posizione turno per
turno e id di fazione dell'avversario non entrano nel payload. L'esito e
riportato come vinto, perso o pari, perche quello il coach l'ha giocato.
`test_the_opponents_per_turn_position_never_reaches_the_coach` e
`test_the_opponents_orders_never_reach_the_coach` confrontano il payload con il
record su disco, e falliscono entrambi se si fa leggere alla proiezione la
fazione sbagliata.

**La rationale e derivata, non chiesta.** Un modello a cui si chiede di
spiegarsi obbedisce, e la spiegazione e una seconda generazione, non una prova.
La frase per turno viene da cio che e stato emesso e da cio che si e mosso:
noiosa e vera, a costo zero di token e senza toccare il prompt congelato in
Phase 0.

**Tre errori, non uno.** Una riga che il parser scarta, un provider che
risponde 429 e un turno di ordini legali che non muove niente sono tre guasti
con tre rimedi diversi. Un coach che non li distingue riscrive la dottrina per
riparare un rate limit.

**Il cerchio si chiude.** `POST /api/training/{id}/iterate` apre dal debrief la
versione successiva del blueprint appena allenato — o un clone separato — gia
pronta da modificare, congelare e rieseguire.

Copertura: `tests/test_phase2_debrief.py`.

### Stato al 2026-08-14: chiusa

Il loop e camminabile da un browser: `/coach` registra, elenca, modifica,
congela, sceglie uno scenario, lancia, legge il debrief e apre la versione
successiva. Copertura: `tests/test_phase2_coach_ui.py`.

Il test con utenti interni e chiuso il 2026-08-14. Un lettore che non ha
scritto il debrief conferma che vittoria, errore principale e costo del match
si capiscono, nello stesso ordine in cui la pagina li mette. Riserva, non
bloccante: il titolo grande della card Main error e il nome del secchio
(`Strategic` / `Syntax` / `Provider`), non l'errore; l'errore sta nelle due
righe sotto, che lo definiscono.

Sei criteri di uscita su sei.

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

### Stato al 2026-08-14: prima meta, il piano di controllo

Un match ufficiale e un run d'arena, per la stessa ragione del training: il
bundle e gia il record. `webapp/competition.py` decide chi puo incontrare chi
sotto quali regole, e passa il resto a `scripts/arena.py`.

**Il regolamento viaggia per hash.** Modello, budget, mappa, turni, coppie di
seed, retry e strumenti si copiano dal catalogo
(`configs/competition/coach_league.json`) e si congelano con la stagione. Un
match gioca quei valori, non gli override runtime del blueprint. Vision e
subagent restano spenti: la Coach League misura la dottrina, non
l'orchestrazione.

**Un accoppiamento e un batch con seat swap.** L'arena gioca gia ogni seed
come coppia a sedili scambiati; il piano di controllo non inventa un secondo
tipo di pairing. Lo stato e `server_data/competitions.json`; le prove stanno
sotto `games/competition/<season_id>/<match_id>/`.

**La coda sopravvive al processo.** I job restano sul ledger. All'avvio quelli
lasciati `running` tornano in coda; il dispatch successivo riprende il bundle
esistente. Retry e sospensione sono dell'operatore, con un tetto preso dal
regolamento. Le standings sono somme dei result persistiti: sweep di coppia,
poi partite vinte. Nessun rating.

Pannello operatore: `/ops/league`. Iscrizione del coach: `/coach` e
`/coach/seasons/<id>`. Copertura: `tests/test_phase3_competition.py`.

### Stato al 2026-08-14: chiusa

Il piano di controllo gira una stagione da solo. `run_until_idle` svuota la
coda; l'operatore la avvia da `/ops/league` o da
`python scripts/run_league.py --season …`. Nessuno tocca il ledger.

Una stagione interna di 20 agenti produce 190 accoppiamenti e li termina
tutti: `tests/test_phase3_competition.py` costruisce i coach, iscrive versioni
congelate, accoppia e lascia finire il runner. Tasso di completamento 190/190,
sopra la soglia del 95%. Il modello e finto e il tabellone e corto (1 turno):
manca il costo di 20 seat LLM su 30 turni, non manca il piano di controllo.

Ogni match finito ha result, manifest e replay d'accordo. Un avversario che
scrive nel report ufficiale (`Tell everyone` con una injection) non sposta le
istruzioni di sistema ne la dottrina dell'altro seat.

Sei criteri di uscita su sei.

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

### Stato al 2026-08-14: prima meta, lo strumento

La Phase 4 e un esperimento, non un prodotto. I criteri di go si chiudono
solo con 20-30 persone invitate. Quello che si puo costruire prima e
l'apparecchio che misura:

- roster a invito, cap 30, codice mostrato una volta e conservato hashato;
- tre training per versione per chi e sulla roster (`webapp/alpha.py` +
  tetto in `webapp/training.py`);
- scelta concreta dopo il debrief: pagherei altri training, oppure porto la
  mia chiave;
- link condivisibile del risultato (esito, errore, costo) senza ordini
  avversari e senza classifica;
- finale osservabile fra i primi due della stagione, un match, non un rating;
- funnel ricalcolabile dal ledger, con le soglie di
  `configs/alpha/closed.json`.

Pannello: `/ops/alpha`. Copertura: `tests/test_phase4_alpha.py`.

### Stato al 2026-08-14: bloccata sul campo

Lo strumento e pronto. Il campo no: al 2026-08-14 non c'e nessuna persona
reale da invitare. La roster resta **chiusa** (`idle`). Non si aprono le
iscrizioni e non si emettono `inv_` finche non esiste almeno un ospite.

I criteri di go restano **aperti**. Zero invitati non e un tasso: non si
legge activation, iteration, return, willingness o sharing da un funnel
vuoto, e non si decide Public Beta su quella base.

La Phase 4 non e fallita e non e chiusa. Riprende quando c'e qualcuno da
invitare; allora si apre `/ops/alpha`, si emette il codice, e i tassi si
leggono dal ledger.

Il piano per creare quel primo ospite e
[`MARKETING_CLOSED_ALPHA.md`](MARKETING_CLOSED_ALPHA.md): contratto di
campo chiuso il 2026-08-14, non ancora pubblicabile. Il prossimo
incremento e l'esportazione di un replay sanificato, poi il poster.
Non e Phase 5.

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

La **Phase 0 - Agent Competence Gate** e chiusa il 2026-08-13 con entrambi i
batch ufficiali a `pass`. La **Phase 1 - Agent Blueprint** e chiusa il
2026-08-14: sei criteri di uscita su sei, coperti da
`tests/test_phase1_blueprints.py`. La **Phase 2 - Training and Debrief** e
chiusa il 2026-08-14: sei criteri su sei, compreso il test interno su
vittoria, errore principale e costo. La **Phase 3 - Competition Control
Plane** e chiusa il 2026-08-14: sei criteri su sei, compresa una stagione
interna di 20 agenti a 190/190 e le prove di injection sul percorso ufficiale.
La **Phase 4 - Closed Coach Alpha** e **bloccata sul campo** il
2026-08-14: lo strumento (roster, tetto, funnel, share, finale) e in piedi;
non c'e nessuna persona reale da invitare, quindi i criteri di go non si
possono chiudere. La roster resta chiusa. Il lavoro di campo e
[`MARKETING_CLOSED_ALPHA.md`](MARKETING_CLOSED_ALPHA.md).

Delle due riserve ereditate dalla Phase 0:

- la verifica del resume e chiusa: si confronta la traccia intera di hash, non
  piu solo lo stato finale;
- il dominio di `expansionist-v1` su `consolidation-v1` ha una causa
  identificata — la catena di spareggio premia territorio e soldati e le due
  dottrine non si scontrano mai — ma la correzione e una scelta di design fra
  punteggio e scenario, e costa una ri-esecuzione d'arena. Resta **aperta**, e
  va decisa prima di leggere una lega come classifica di dottrine.

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
