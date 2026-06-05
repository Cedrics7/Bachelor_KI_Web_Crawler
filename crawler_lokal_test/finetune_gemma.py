"""
finetune_gemma.py
=================
QLoRA Fine-Tuning fuer Gemma 3 4B auf deinem lokalen Extraktionsdatensatz.
Optimiert fuer RTX 3080 (10 GB VRAM).

Voraussetzungen:
    pip install transformers datasets peft trl bitsandbytes accelerate

Nutzung:
    python finetune_gemma.py
    python finetune_gemma.py --train_file ../finetune_data/train.jsonl
                             --eval_file  ../finetune_data/eval.jsonl
                             --output_dir ../finetune_model

Nach dem Training:
    Das Modell liegt unter ../finetune_model/
    In Ollama importieren: ollama create gemma-crawler -f Modelfile
"""

import argparse
import json
import os

import torch


def check_dependencies():
    missing = []
    for pkg in ["transformers", "datasets", "peft", "trl", "bitsandbytes", "accelerate"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"FEHLER: Fehlende Pakete: {', '.join(missing)}")
        print(f"Installieren mit: pip install {' '.join(missing)}")
        exit(1)


def load_jsonl(path: str) -> list:
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def format_prompt(example: dict) -> str:
    """
    Alpaca-Format -> Gemma-Prompt.
    Gemma erwartet: <start_of_turn>user ... <end_of_turn><start_of_turn>model
    """
    instruction = example.get("instruction", "")
    inp         = example.get("input", "")
    output      = example.get("output", "")

    if inp:
        user_content = f"{instruction}\n\nText:\n{inp}"
    else:
        user_content = instruction

    return (
        f"<start_of_turn>user\n{user_content}<end_of_turn>\n"
        f"<start_of_turn>model\n{output}<end_of_turn>"
    )


def run_training(args):
    check_dependencies()

    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
    from trl import SFTTrainer, SFTConfig

    print(f"\n=== Gemma QLoRA Fine-Tuning ===")
    print(f"  Modell:      {args.model_name}")
    print(f"  Train-File:  {args.train_file}")
    print(f"  Eval-File:   {args.eval_file}")
    print(f"  Output-Dir:  {args.output_dir}")
    print(f"  VRAM:        RTX 3080 10 GB (optimiert)")
    print()

    # --- Daten laden ---
    print("1. Lade Trainingsdaten ...")
    train_data = load_jsonl(args.train_file)
    eval_data  = load_jsonl(args.eval_file)
    print(f"   -> {len(train_data)} Train / {len(eval_data)} Eval")

    # Prompts formatieren
    train_texts = [format_prompt(e) for e in train_data]
    eval_texts  = [format_prompt(e) for e in eval_data]

    train_dataset = Dataset.from_dict({"text": train_texts})
    eval_dataset  = Dataset.from_dict({"text": eval_texts})

    # --- 4-Bit Quantisierung (QLoRA) fuer 10 GB VRAM ---
    print("2. Lade Modell mit 4-Bit Quantisierung ...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name,
        trust_remote_code=True,
        token=args.hf_token,
    )
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        token=args.hf_token,
    )
    model = prepare_model_for_kbit_training(model)

    # --- LoRA Konfiguration ---
    print("3. Konfiguriere LoRA ...")
    lora_config = LoraConfig(
        r=16,                   # Rank – hoeher = mehr Parameter, mehr VRAM
        lora_alpha=32,          # Skalierungsfaktor
        target_modules=[        # Ziel-Module fuer Gemma
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj"
        ],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # --- Training ---
    print("4. Starte Training ...")
    sft_config = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,     # VRAM-schonend fuer 10 GB
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,    # Effektive Batchgroesse = 8
        warmup_ratio=0.05,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=5,
        eval_strategy="steps",
        eval_steps=20,
        save_strategy="steps",
        save_steps=50,
        save_total_limit=2,
        load_best_model_at_end=True,
        report_to="none",
        max_seq_length=2048,
        dataset_text_field="text",
        optim="paged_adamw_8bit",          # 8-Bit Optimizer spart VRAM
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=sft_config,
    )

    trainer.train()

    # --- Speichern ---
    print("5. Speichere Modell ...")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"   -> Gespeichert in: {args.output_dir}")

    # --- Ollama Modelfile generieren ---
    _write_modelfile(args.output_dir, args.model_name)

    print("\nFertig! Naechster Schritt: python finetune_eval.py")
    print(f"Ollama: ollama create gemma-crawler -f {args.output_dir}/Modelfile")


def _write_modelfile(output_dir: str, base_model: str):
    """Schreibt ein Ollama-kompatibles Modelfile."""
    content = f"""FROM {output_dir}

SYSTEM \""""
Du bist ein praeziser Extraktor fuer kommunale Baumassnahmen.
Extrahiere aus dem gegebenen Text ausschliesslich konkrete Bau-,
Sanierungs- oder Infrastrukturmassnahmen als JSON.
\""""

PARAMETER temperature 0.0
PARAMETER num_ctx 4096
"""
    path = os.path.join(output_dir, "Modelfile")
    os.makedirs(output_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"   -> Modelfile geschrieben: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemma QLoRA Fine-Tuning")
    parser.add_argument("--model_name",  default="google/gemma-3-4b-it",
                        help="HuggingFace Modell-ID (Standard: google/gemma-3-4b-it)")
    parser.add_argument("--train_file",  default="../finetune_data/train.jsonl")
    parser.add_argument("--eval_file",   default="../finetune_data/eval.jsonl")
    parser.add_argument("--output_dir",  default="../finetune_model")
    parser.add_argument("--epochs",      type=int, default=3)
    parser.add_argument("--hf_token",    default=os.getenv("HF_TOKEN"),
                        help="HuggingFace Access Token (oder HF_TOKEN in .env setzen)")
    args = parser.parse_args()

    if not args.hf_token:
        print("WARNUNG: Kein HF_TOKEN gesetzt.")
        print("Gemma ist ein 'gated model' – du brauchst einen HuggingFace-Token.")
        print("Registriere dich auf https://huggingface.co/google/gemma-3-4b-it")
        print("Dann: export HF_TOKEN=hf_...")

    run_training(args)
