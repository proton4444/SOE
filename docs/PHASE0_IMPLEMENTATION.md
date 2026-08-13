# Phase 0 Implementation Specification

Status: **implementato; gate non superato** (vedi `ROADMAP.md`, Phase 0 - Stato)  
Data: 2026-08-11  
Dipende da: [`ROADMAP.md`](ROADMAP.md)

## Obiettivo

Implementare il primo gate della roadmap: eseguire agenti LLM nell'arena
headless usando la stessa informazione, lo stesso prompt e la stessa validazione
del runtime di produzione.

La Phase 0 non costruisce account, editor Blueprint, tornei o nuove pagine. Il
suo output e evidenza riproducibile che:

1. un modello sa giocare il duel meglio del random;
2. due dottrine diverse modificano davvero il comportamento dell'agente;
3. costo, affidabilita e durata sono compatibili con una Coach League.

## Decisioni iniziali

Default raccomandati:

- provider: endpoint OpenAI-compatible gia supportato;
- modello: configurabile nel run manifest, mai hardcoded nel benchmark;
- temperatura: `0.0`;
- agent stack: un solo strategist, vision e subagent disabilitati;
- scenario: `starter_map.json`, due fazioni, 30 turni;
- smoke: 4 seed pairs, 8 partite;
- official candidate: 20 seed pairs, 40 partite;
- blueprint A: espansione territoriale aggressiva;
- blueprint B: consolidamento economico prudente;
- baseline: random e scripted gia esistenti;
- fallimento provider: turno senza ordini, registrato come reliability failure;
- retry: policy unica dichiarata e congelata nel manifest.

Prima dell'esecuzione a pagamento vanno scelti modello e limite massimo di
spesa. L'implementazione puo procedere senza questa scelta usando un fake LLM.

## Problema architetturale da risolvere

Il bot di produzione usa `service.player_state(room, faction_id)` e l'ultimo
report persistito. L'arena attuale mantiene `GameState` in memoria, legge lo
stato completo nelle policy e non genera report a ogni turno.

Aggiungere semplicemente una chiamata LLM dentro `scripts/arena.py` produrrebbe
un benchmark non equivalente alla dashboard. Serve prima una pipeline pura e
condivisa:

```text
GameState + faction + previous report + blueprint + match metadata
    -> fogged decision context
    -> system/user messages
    -> model call result
    -> extracted and validated orders
    -> persisted decision trace
```

Sia il bot gestito sia l'arena devono usare questa pipeline.

## Work Package 1 - Pure Agent Context

### Modifiche

- Estrarre da `webapp.service.player_state` una funzione che accetta direttamente
  `GameState`, identificatore fazione e metadati minimi della partita.
- Mantenere `player_state(room, faction_id)` come adapter per la webapp.
- Rendere pura la costruzione dei messaggi oggi in `webapp.ai.orchestrator`.
- Passare esplicitamente ultimo report, nome partita, mappa, turno e dottrina.
- Estrarre il filtro degli ordini in una funzione che accetta `GameState` e
  fazione, senza dipendere da `Room` o filesystem.
- Aggiungere un oggetto immutabile `DecisionContext`.

### Contratto

Lo stesso stato di gioco deve produrre lo stesso payload testuale nella webapp
e nell'arena, esclusi identificatori operativi non strategici.

### Test

- parity tra context web e headless;
- nessuna informazione di fazioni non osservate;
- prompt hash stabile;
- messaggi avversari delimitati come dati non affidabili;
- troncamento deterministico di stato e report.

## Work Package 2 - Structured LLM Result

### Modifiche

L'attuale `brain.chat()` restituisce soltanto testo e scarta usage, tentativi e
latenza. Introdurre un risultato strutturato, mantenendo compatibilita con i
call site esistenti:

```python
@dataclass(frozen=True)
class ChatResult:
    text: str
    model: str
    attempts: int
    latency_ms: float
    usage: dict[str, int | float]
    provider_request_id: str = ""
```

- Aggiungere `brain.chat_result(...) -> ChatResult`.
- Conservare `brain.chat(...) -> str` come wrapper.
- Non mettere credenziali, header o URL firmati nel risultato.
- Conservare usage come struttura, non come stringa di log.
- Registrare cost solo quando dichiarato direttamente dal provider; altrimenti
  lasciarlo sconosciuto invece di stimarlo nel record ufficiale.

### Test

- parsing usage completo e assente;
- retry count corretto;
- errori 4xx, 429, 5xx e trasporto;
- nessun segreto nei record serializzati.

## Work Package 3 - LLM Arena Policy

### Modifiche

- Introdurre `LLMPolicy` dietro la stessa interfaccia di `RandomPolicy` e
  `ScriptedPolicy`.
- Evolvere l'interfaccia policy per ricevere `DecisionContext`, non lo stato
  completo.
- Adattare le baseline esistenti senza modificarne il comportamento.
- Generare i report con `reporting.generate_player_reports` dopo ogni turno.
- Passare a ogni agente solo il proprio report precedente.
- Estrarre marker, rationale sintetica e ordini.
- Filtrare gli ordini con il parser di produzione.
- In caso di errore provider produrre un no-op registrato, senza fermare la partita.

### Blueprint Phase 0

In questa fase un blueprint e un file di configurazione immutabile, non ancora
un'entita utente. Deve contenere almeno:

```json
{
  "id": "expansionist-v1",
  "doctrine": {
    "objective": "Expand territorial control quickly.",
    "economy": "Spend early income on soldiers.",
    "risk": "Accept moderate losses to secure contested towns.",
    "diplomacy": "Remain neutral unless attacked."
  }
}
```

Il file viene hashato e copiato nel run bundle. Le due dottrine iniziali devono
usare lo stesso numero massimo di caratteri e le stesse sezioni.

### Test

- risposta valida e ordini accettati;
- marker mancante;
- risposta vuota;
- righe narrative scartate;
- errore provider trasformato in no-op;
- fog of war rispettato;
- report del turno N disponibile al turno N+1;
- blueprint incluso nel prompt senza alterare le regole di sistema.

## Work Package 4 - Run Bundle and Resume

Ogni esecuzione scrive in `games/arena/<run_id>/`:

```text
manifest.json
games.jsonl
turns.jsonl
decisions/
  <game_id>/
    turn_<n>_<faction_id>.json
orders/
  <game_id>/
    turn_<n>_<faction_id>.txt
blueprints/
ARENA_REPORT.md
```

### Manifest minimo

- run id e stato `running | complete | failed`;
- commit Git e dirty-tree flag;
- versione del motore;
- map hash;
- prompt hash;
- blueprint hash;
- modello, temperatura, token e retry policy;
- seed pairs e seat order;
- data di avvio e completamento;
- versione dello schema del bundle.

### Decision trace minimo

- game, turn e faction;
- input hashes;
- modello e configurazione;
- risposta grezza per il run interno;
- rationale sintetica separata;
- ordini estratti e ordini accettati;
- warning parser;
- attempts, latency, usage e failure class;
- timestamp.

Le pubblicazioni future potranno redigere risposte grezze o rationale, ma il
run interno deve conservarle per il debug. Non va mai salvata la chiave API.

### Resume

- Scrittura append-only o atomica per ogni record.
- Chiave idempotente `game + turn + faction`.
- Alla ripresa non ripetere decisioni gia registrate.
- Verificare che manifest, prompt, blueprint, mappa e commit non siano cambiati.
- Un cambio invalida la ripresa e richiede un nuovo run id.

### Test

- stop e resume a meta partita;
- nessuna decisione duplicata;
- file troncato rilevato;
- manifest incompatibile rifiutato;
- stato finale e hash uguali a un run non interrotto quando le risposte fake
  sono le stesse.

## Work Package 5 - Metrics and Report

### Reliability

- calls attempted e completed;
- call failures per classe;
- parseable call rate;
- ordini accettati e warning;
- retry e no-op turns;
- wall time e latency distribution;
- input, output e total tokens;
- cost quando disponibile.

### Strategy

- vittorie, sweep e split;
- eliminazione e turno di eliminazione;
- secured e controlled cities;
- soldiers e characters alive;
- primo hostile contact;
- ordini per famiglia;
- movimento, recruit, secure e attack frequency;
- territorio conquistato e perso.

### Blueprint differentiation

Il report deve confrontare A e B su:

- distribuzione delle famiglie di ordini;
- tempo al primo reclutamento e primo attacco;
- soldati e territorio per turno;
- contact, survival e risultato;
- costo e affidabilita.

Una differenza soltanto nel testo della rationale non supera il gate. Deve
apparire negli ordini o nello stato della partita.

## Work Package 6 - CLI and Run Modes

Evitare di codificare configurazioni complesse nella stringa della policy.
Usare un file di run versionabile, per esempio:

```json
{
  "mode": "smoke",
  "map": "starter_map.json",
  "turns": 30,
  "seed_pairs": 4,
  "entrants": [
    {"type": "llm", "model": "provider/model", "blueprint": "expansionist-v1.json"},
    {"type": "random"}
  ]
}
```

Comandi previsti:

```powershell
python scripts/probe_model.py provider/model
python scripts/arena.py --config configs/phase0_smoke.json
python scripts/arena.py --resume <run_id>
```

Il modello e il limite di spesa devono essere visibili prima della conferma di
un run reale. I test usano sempre un fake brain e non effettuano rete.

## Sequenza di implementazione

1. Pure Agent Context.
2. Structured LLM Result.
3. LLM Arena Policy con fake brain.
4. Report di turno e parita fog-of-war.
5. Run bundle, manifest e resume.
6. Metriche e report.
7. Suite completa e determinism regression.
8. Probe del modello scelto.
9. Smoke da 4 seed pairs.
10. Revisione di costi, errori e differenze tra blueprint.
11. Official candidate soltanto se lo smoke supera i gate.

## Prerequisiti operativi

- `SOE_LLM_KEY` configurata soltanto nell'ambiente di esecuzione;
- modello disponibile e quota provider sufficiente;
- limite massimo di spesa concordato;
- rate limits e retry policy noti;
- commit Git congelato per ogni official candidate;
- directory di output separata dai giochi live;
- nessun run ufficiale da un worktree dirty;
- blueprint e config sottoposti a review prima del freeze.

## Definition of Done

La Phase 0 e completa quando:

- tutti i test passano;
- il probe del modello passa;
- smoke e official candidate sono riprendibili;
- almeno il 95% delle chiamate e parseable;
- il modello supera random nel confronto accoppiato;
- due blueprint producono differenze strategiche osservabili;
- ogni claim del report e ricostruibile dai record del bundle;
- costo e durata di un match sono noti;
- nessuna credenziale compare negli output.

## Non necessario in Phase 0

- account e login;
- editor visuale del Blueprint;
- matchmaking;
- classifiche persistenti;
- billing;
- job queue multi-server;
- multiplayer a quattro o sei fazioni;
- vision e subagent;
- nuove meccaniche di gioco;
- restyling della dashboard.

## Input richiesto prima dei run reali

L'implementazione puo iniziare immediatamente con fake LLM. Prima del primo
smoke reale servono due sole decisioni del proprietario del progetto:

1. modello o breve roster da provare;
2. tetto massimo di spesa per smoke e official candidate.
