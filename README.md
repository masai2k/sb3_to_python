# sb3_to_python

Converter da file `.sb3` Scratch/PenguinMod a un file Python leggibile, eseguibile da terminale.

## Obiettivo

Questo tool non promette una conversione 1:1 perfetta per ogni progetto complesso, ma è progettato per essere **compatibile con qualunque file `.sb3` senza andare in crash**:

- i blocchi supportati vengono convertiti in Python;
- i blocchi non ancora supportati vengono lasciati come commenti `# TODO ...`;
- per default converte **tutto il progetto** (stage + sprite);
- in alternativa puoi convertire un singolo target.

## Uso rapido

Dentro la cartella del repo:

```bash
python convertitore.py iltuofile.sb3
```

Esempio nello stile che volevi:

```bash
cd sb3python
python convertitore.py word.sb3
```

Questo genera automaticamente:

```bash
word.py
```

## Altri esempi

Convertire tutto il progetto con nome output personalizzato:

```bash
python convertitore.py progetto.sb3 -o progetto_convertito.py
```

Convertire solo un target specifico:

```bash
python convertitore.py progetto.sb3 --single-target --target-index 0
```

Puoi anche usare il package:

```bash
python -m sb3_to_python progetto.sb3
```

## Compatibilità attuale

Supporto già incluso per molti blocchi comuni:

- eventi `when green flag clicked`
- `if`, `if else`, `repeat`, `repeat until`, `forever`, `wait`, `wait until`, `stop`
- variabili
- liste principali
- `ask and wait`, `answer`
- operatori aritmetici, logici e varie operazioni stringa
- parte dei blocchi motion
- alcuni blocchi PenguinMod `localstorage`
- fallback sicuro sui blocchi sconosciuti tramite commenti `TODO`

## Struttura

- `convertitore.py` → script terminale principale
- `sb3_to_python/` → package Python
- `tests/` → test base

## Setup opzionale con venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Nota importante

Il Python generato è un **draft leggibile** del progetto. Per progetti Scratch/PenguinMod avanzati:

- il parallelismo è approssimato con thread;
- alcune estensioni o blocchi grafici/audio restano come `TODO`;
- i comportamenti del runtime Scratch non sono sempre replicati al 100%.

Però il file generato è pensato per essere una base chiara da rifinire a mano.
