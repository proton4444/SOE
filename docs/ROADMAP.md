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

- Almeno il 95% delle chiamate produce un ordine accettato.
- Tutti i match del batch terminano senza errore del motore.
- Il modello supera random nel confronto accoppiato.
- Almeno due blueprint intenzionalmente diversi generano differenze misurabili
  in espansione, economia o aggressivita.
- Ogni risultato puo essere ricostruito da manifest e ordini salvati.
- Costo e durata per match sono noti.

### Stato al 2026-08-13

Il gate **non e superato**: 4 criteri su 6.

Evidenza: tre run reali dell'11 agosto 2026, tutti `status: complete`. Il piu
recente e `games/arena/run-20260811-110859-2464c0` (gpt-4o-mini,
`expansionist-v1` contro `random`, 8 partite da 30 turni).

| Criterio | Esito | Misura |
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

Due avvertenze di lettura sui confronti:

- il seat scripted legge lo stato completo, il seat LLM vede solo la propria fog
  of war; scripted-contro-random e un confronto equo, scripted-contro-modello no;
- il 70% delle chiamate LLM (168 su 240) produce almeno un warning, e nessun
  criterio del gate le osserva: la soglia richiede un solo ordine accettato per
  chiamata.

### Debolezze del gate da correggere

- gli exit criteria non fissano una dimensione campionaria, e questo permette a
  uno smoke da 8 partite di risultare superato;
- la soglia "ordine accettato" non distingue un turno pulito da un turno con
  ordini scartati;
- la ripresa dei batch e nello Scope ma non compare negli exit criteria, mentre
  la Definition of Done dello spec la richiede.

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

1. **Scegliere e calibrare la mappa del gate.** E la variabile che oggi pesa di
   piu ed e gratis da studiare: i run scripted non chiamano il provider. La
   mappa scelta deve mostrare separazione sia tra stili strategici sia tra gioco
   deliberato e rumore. Nessuna delle due mappe attuali soddisfa entrambe le
   condizioni a 30 turni.
2. **Sostituire `random` come avversario di riferimento** con la policy scripted
   piu forte disponibile sulla mappa scelta, e riscrivere di conseguenza il
   terzo exit criterion.
3. **Fissare la dimensione campionaria negli exit criteria**, insieme a una
   soglia esplicita per i warning e a un criterio di ripresa.
4. **Eseguire il confronto blueprint-vs-blueprint** con `expansionist-v1` e
   `consolidation-v1`, da un worktree pulito, come official candidate.

Da verificare come ipotesi successiva, sempre a costo zero: se 30 turni siano
troppo pochi perche una differenza strategica si traduca in vittoria, ripetendo
i due confronti a 60 turni.

Nota operativa sui costi di calcolo: una partita scripted-contro-random dura
circa 0.1s, mentre due policy deliberate che si affrontano davvero costano circa
due ordini di grandezza in piu per partita. Il budget di una stagione va stimato
sul secondo numero, non sul primo.
