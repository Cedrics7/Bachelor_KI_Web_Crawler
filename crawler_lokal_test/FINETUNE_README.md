# Gemma Fine-Tuning Pipeline

Diese drei Dateien bilden eine komplette Fine-Tuning-Pipeline fuer Gemma 3 4B,
optimiert fuer die kommunale Massnahmen-Extraktion.

---

## Voraussetzungen

```bash
pip install transformers datasets peft trl bitsandbytes accelerate torch
```

Ausserdem brauchst du einen **HuggingFace-Token** fuer Gemma (Gated Model):
1. Account auf https://huggingface.co erstellen
2. Zugriff auf `google/gemma-3-4b-it` beantragen
3. Token erstellen unter https://huggingface.co/settings/tokens
4. Token in `.env` setzen: `HF_TOKEN=hf_...`

---

## Schritt-fuer-Schritt

### Schritt 1: Ground-Truth generieren
Fuehre zuerst `crawler_eval.py` mit `claude-sonnet-4-6` fuer deine Ziel-Kommunen aus.
Die Outputs landen in `output_eval/`.

### Schritt 2: Trainingsdaten aufbereiten
```bash
cd crawler_lokal_test/
python finetune_data_builder.py \
    --input_dir ../output_eval \
    --ground_truth_model claude-sonnet-4-6 \
    --output_dir ../finetune_data
```
Ergebnis: `../finetune_data/train.jsonl` und `../finetune_data/eval.jsonl`

### Schritt 3: Training starten
```bash
python finetune_gemma.py \
    --train_file ../finetune_data/train.jsonl \
    --eval_file  ../finetune_data/eval.jsonl \
    --output_dir ../finetune_model \
    --epochs 3
```
Das Modell wird als HuggingFace-Format unter `../finetune_model/` gespeichert.

### Schritt 4: In Ollama importieren
```bash
ollama create gemma-crawler -f ../finetune_model/Modelfile
```
Danach kannst du in `eval_config.py` die Modell-ID auf `gemma-crawler` setzen.

### Schritt 5: Evaluieren
```bash
python finetune_eval.py \
    --eval_file ../finetune_data/eval.jsonl \
    --model_base gemma3:4b \
    --model_ft_ollama_id gemma-crawler
```
Du siehst direkt den F1-Score-Vergleich zwischen Basis- und Fine-Tuned-Modell.

---

## Hinweise fuer RTX 3080 (10 GB VRAM)

- **QLoRA mit 4-Bit** ist Pflicht – Full Fine-Tuning geht nicht in 10 GB
- `per_device_train_batch_size=1` und `gradient_accumulation_steps=8` halten den Speicher klein
- Gemma 3 4B braucht ca. 6-7 GB VRAM im 4-Bit-Modus – das passt knapp
- Wenn CUDA OOM: `--epochs 1` testen oder `max_seq_length` auf 1024 reduzieren

---

## Dateistruktur nach dem Training

```
Bachelor_KI_Web_Crawler/
  crawler_lokal_test/
    finetune_data_builder.py   <- Daten aufbereiten
    finetune_gemma.py          <- QLoRA Training
    finetune_eval.py           <- Modell-Vergleich
    FINETUNE_README.md         <- Diese Datei
  finetune_data/
    train.jsonl                <- Trainingsdaten
    eval.jsonl                 <- Eval-Daten
  finetune_model/
    adapter_model.safetensors  <- LoRA-Gewichte
    Modelfile                  <- Ollama-Import
  finetune_results/
    finetune_eval_<datum>.json <- Eval-Ergebnisse
```
