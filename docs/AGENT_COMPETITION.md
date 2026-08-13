# SOE Agent Competition

Status: **direzione di prodotto corrente**  
Data: 2026-08-11

La valutazione di prontezza tecnica, mercato e gate di validazione e in
[`READINESS_AND_MARKET.md`](READINESS_AND_MARKET.md).
La sequenza di implementazione e i criteri di uscita sono in
[`ROADMAP.md`](ROADMAP.md).

## Scopo

SOE e un gioco competitivo nel quale i giocatori umani non comandano
direttamente una fazione. Ogni giocatore progetta, istruisce e allena un
agente, poi lo schiera in un mondo simultaneo, persistente e parzialmente
osservabile.

La promessa centrale e:

> Costruisci la dottrina del tuo agente, allenalo, schieralo e scopri se sa
> governare un mondo senza il tuo intervento.

Il gioco e l'ambiente competitivo. Il benchmark e il protocollo rigoroso che
rende confrontabili alcune partite. Condividono motore e regole, ma non vanno
presentati come la stessa cosa.

## Ruoli

- **Coach umano:** definisce la dottrina, osserva gli allenamenti, analizza gli
  errori e pubblica versioni successive dell'agente.
- **Agente:** interpreta la situazione, prende decisioni e invia gli ordini
  senza controllo umano durante una partita ufficiale.
- **Operatore:** sceglie scenario e formato, congela le configurazioni e
  garantisce integrita, riproducibilita e pubblicazione dei risultati.

Il supporto al gioco umano diretto puo rimanere come sandbox e strumento di
calibrazione, ma non e il centro del prodotto.

## Agent Blueprint

Ogni concorrente e una versione immutabile di un `Agent Blueprint`. La prima
versione deve includere:

- modello utilizzato;
- identita e stile decisionale;
- obiettivo strategico;
- priorita territoriali;
- politica economica;
- condizioni per attaccare, sostenere o ritirarsi;
- comportamento in condizioni di informazione incompleta;
- politica diplomatica;
- regole di emergenza;
- eventuale playbook o memoria consentita;
- limiti di token, strumenti, subagent e tentativi;
- versione del prompt e data di pubblicazione.

L'interfaccia deve offrire sezioni strutturate, non soltanto un campo prompt
libero. Questo rende l'addestramento comprensibile, limita gli exploit e
permette di confrontare versioni diverse dello stesso agente.

## Ciclo del giocatore

1. Creare o duplicare un blueprint.
2. Scegliere il modello consentito dalla competizione.
3. Scrivere la dottrina dell'agente.
4. Eseguire partite di allenamento su scenari pubblici.
5. Esaminare ordini, eventi, risultati, costi ed errori.
6. Modificare la dottrina e produrre una nuova versione.
7. Congelare e iscrivere una versione a una competizione.
8. Osservare la partita senza intervenire.

Le motivazioni mostrate nella dashboard devono essere sintesi decisionali
esplicite prodotte per l'utente, non chain-of-thought privata del modello.

## Formati competitivi

### Coach League

Tutti i concorrenti usano lo stesso modello e gli stessi limiti. Cambia il
blueprint scritto dal giocatore. Questa e la modalita principale del gioco e
misura la capacita umana di istruire un agente.

### Model League

Tutti i modelli ricevono lo stesso blueprint, gli stessi input e lo stesso
budget. Cambia soltanto il modello. Questa e la modalita adatta al benchmark
comparativo tra modelli.

### Open Agent League

Sono consentiti modelli, memoria, strumenti, vision e subagent diversi entro
un budget dichiarato. Confronta sistemi completi, non modelli isolati.

I risultati delle tre leghe devono avere classifiche separate. Una classifica
unica non permetterebbe di distinguere l'abilita del coach, quella del modello
e la qualita dell'orchestrazione.

## Autonomia e intervento umano

In una partita ufficiale il blueprint viene congelato prima dell'inizio e il
coach non puo cambiare prompt, memoria o ordini turno per turno. In caso
contrario, a giocare sarebbe nuovamente l'essere umano.

Una futura modalita separata puo introdurre un numero limitato di direttive da
coach come risorsa di gioco. I suoi risultati non devono essere mescolati con
quelli delle leghe autonome.

## Benchmark e marketing

La dashboard puo mostrare scontri tra agenti, replay, classifiche e campagne
come contenuto pubblico. Ogni partita deve pero essere etichettata come:

- **allenamento**, con configurazioni modificabili e nessuna pretesa di
  comparabilita;
- **esibizione**, pensata per dimostrazione o intrattenimento;
- **ufficiale**, eseguita con scenario, seed policy, blueprint, budget e
  versione del motore congelati.

Il benchmark deve pubblicare risultati, ordini accettati, errori, costi,
latenza e manifest di esecuzione. Le metriche di strategia, affidabilita ed
efficienza devono rimanere visibili separatamente, senza ridurre tutto a un
singolo punteggio opaco.

## Direzione della dashboard

La dashboard deve evolvere da pannello amministrativo a centro operativo del
coach:

- editor strutturato dell'Agent Blueprint;
- storico e confronto tra versioni;
- arena di allenamento;
- deployment e iscrizione alle competizioni;
- osservazione live senza comandi diretti;
- debrief con ordini, eventi, errori, costi e indicatori strategici;
- classifiche distinte per lega e versione del regolamento.

## Prossime decisioni

1. Definire lo schema persistente di `Agent Blueprint` e la sua ereditarieta
   rispetto all'attuale campo `persona`.
2. Stabilire quali parti del blueprint sono pubbliche prima e dopo una partita.
3. Scegliere il modello standard e il budget della prima Coach League.
4. Definire il ciclo completo allenamento, congelamento, iscrizione e replay.
5. Trasformare il formato duel gia calibrato nella prima competizione giocabile.
6. Tenere la Model League come benchmark separato, con prompt uguale per tutti.

## Materiale storico

I documenti precedenti sono conservati in
`docs/archive/pre-agent-competition-2026-08-11/`. Descrivono l'implementazione,
la beta e le prime prove di benchmark antecedenti a questa direzione di
prodotto. Non sono documenti decisionali correnti.
