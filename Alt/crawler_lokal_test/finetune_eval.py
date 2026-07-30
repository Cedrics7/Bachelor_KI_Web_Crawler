"""
finetune_eval.py
================
Vergleicht das Fine-Tuned Gemma-Modell gegen das Basis-Modell
bei der kommunalen Massnahmen-Extraktion.

Messgroessen:
  - Precision:  Wie viele gefundene Massnahmen sind korrekt?
  - Recall:     Wie viele Ground-Truth-Massnahmen wurden gefunden?
  - F1-Score:   Harmonisches Mittel aus Precision und Recall
  - Fehlertypen: generisch, fehlendes_datum, falsche_url, abgelaufen

Nutzung:
    python finetune_eval.py \
        --eval_file    ../finetune_data/eval.jsonl \
        --model_base   gemma3:4b \
        --model_ft     ../finetune_model \
        --ollama_url   http://localhost:11434
"""

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Inference-Helfer
# ---------------------------------------------------------------------------

def call_ollama(prompt: str, model: str, base_url: str, timeout: int = 120) -> str:
    """Ruft ein Ollama-Modell auf und gibt den Rohtext zurueck."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.0},
    }
    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  FEHLER beim Modell-Call ({model}): {e}")
        return ""


def call_hf_model(prompt: str, model_path: str) -> str:
    """Ruft ein lokales HuggingFace-Modell auf (nach Fine-Tuning)."""
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
        import torch
        pipe = pipeline(
            "text-generation",
            model=model_path,
            tokenizer=model_path,
            torch_dtype=torch.float16,
            device_map="auto",
            max_new_tokens=1024,
            temperature=0.0,
            do_sample=False,
        )
        result = pipe(prompt)
        return result[0]["generated_text"].replace(prompt, "").strip()
    except Exception as e:
        print(f"  FEHLER beim HF-Modell-Call: {e}")
        return ""


# ---------------------------------------------------------------------------
# JSON-Parsing
# ---------------------------------------------------------------------------

def parse_output(raw: str) -> list:
    """Extrahiert Massnahmen-Liste aus Modell-Output."""
    if not raw:
        return []
    clean = re.sub(r'```(?:json)?\s*', '', raw).replace('```', '').strip()
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL | re.IGNORECASE).strip()
    try:
        data = json.loads(clean)
        return data.get("massnahmen", []) if isinstance(data, dict) else []
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0)).get("massnahmen", [])
            except Exception:
                pass
    return []


# ---------------------------------------------------------------------------
# Qualitaets-Checks
# ---------------------------------------------------------------------------

TODAY = date.today().isoformat()


def check_massnahme_quality(m: dict) -> dict:
    """Prueft einen einzelnen Eintrag auf Qualitaetskriterien."""
    issues = []

    if len(m.get("massnahme", "")) < 15:
        issues.append("beschreibung_zu_kurz")

    adresse = m.get("adresse", "").lower()
    if any(x in adresse for x in ["verschiedene", "mehrere", "stadtgebiet",
                                    "deutschland", "standorte", ""]):
        if not adresse or adresse.strip() in ["", "hamburg, deutschland", "deutschland"]:
            issues.append("generische_adresse")

    if not m.get("massnahme_start") and not m.get("massnahme_ende"):
        issues.append("fehlendes_datum")

    ende = m.get("massnahme_ende")
    if ende and ende < TODAY:
        issues.append("abgelaufen")

    url = m.get("quelle_url", "")
    if not url.startswith("http"):
        issues.append("ungueltige_url")

    return {"valid": len(issues) == 0, "issues": issues}


def compute_overlap_score(pred: list, gold: list) -> float:
    """
    Einfacher Token-Overlap-Score zwischen Vorhersage und Ground-Truth.
    Vergleicht Massnahmen-Beschreibungen als Bag-of-Words.
    """
    if not gold:
        return 1.0 if not pred else 0.0

    gold_tokens = set()
    for m in gold:
        gold_tokens.update(m.get("massnahme", "").lower().split())

    pred_tokens = set()
    for m in pred:
        pred_tokens.update(m.get("massnahme", "").lower().split())

    if not pred_tokens:
        return 0.0

    intersection = gold_tokens & pred_tokens
    precision = len(intersection) / len(pred_tokens) if pred_tokens else 0.0
    recall    = len(intersection) / len(gold_tokens) if gold_tokens else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)  # F1


# ---------------------------------------------------------------------------
# Evaluation-Loop
# ---------------------------------------------------------------------------

def run_eval(args):
    print(f"\n=== Gemma Fine-Tuning Evaluation ===")
    print(f"  Basis-Modell:  {args.model_base}")
    print(f"  Fine-Tuned:    {args.model_ft}")
    print(f"  Eval-File:     {args.eval_file}")
    print()

    # Eval-Daten laden
    eval_data = []
    with open(args.eval_file, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                eval_data.append(json.loads(line))
    print(f"  {len(eval_data)} Eval-Beispiele geladen")

    results = {"basis": [], "finetuned": []}

    for i, example in enumerate(eval_data):
        instruction = example.get("instruction", "")
        inp         = example.get("input", "")
        gold_output = example.get("output", "{}")

        try:
            gold = json.loads(gold_output).get("massnahmen", [])
        except Exception:
            gold = []

        prompt = f"{instruction}\n\nText:\n{inp}" if inp else instruction

        print(f"\nBeispiel {i+1}/{len(eval_data)} | Gold: {len(gold)} Massnahmen")

        # --- Basis-Modell ---
        t0 = time.time()
        raw_basis = call_ollama(prompt, args.model_base, args.ollama_url)
        t_basis   = round(time.time() - t0, 2)
        pred_basis = parse_output(raw_basis)
        quality_basis = [check_massnahme_quality(m) for m in pred_basis]
        score_basis   = compute_overlap_score(pred_basis, gold)

        results["basis"].append({
            "gold_count":   len(gold),
            "pred_count":   len(pred_basis),
            "f1_score":     round(score_basis, 3),
            "valid_count":  sum(1 for q in quality_basis if q["valid"]),
            "issues":       [i for q in quality_basis for i in q["issues"]],
            "latenz_s":     t_basis,
        })
        print(f"  Basis:     {len(pred_basis)} gefunden | F1={score_basis:.3f} | {t_basis}s")

        # --- Fine-Tuned Modell ---
        # Versuche zuerst ueber Ollama (wenn registriert), sonst direkt HF
        t0 = time.time()
        raw_ft = call_ollama(prompt, args.model_ft_ollama_id, args.ollama_url)
        if not raw_ft:
            raw_ft = call_hf_model(prompt, args.model_ft)
        t_ft = round(time.time() - t0, 2)
        pred_ft   = parse_output(raw_ft)
        quality_ft = [check_massnahme_quality(m) for m in pred_ft]
        score_ft   = compute_overlap_score(pred_ft, gold)

        results["finetuned"].append({
            "gold_count":   len(gold),
            "pred_count":   len(pred_ft),
            "f1_score":     round(score_ft, 3),
            "valid_count":  sum(1 for q in quality_ft if q["valid"]),
            "issues":       [i for q in quality_ft for i in q["issues"]],
            "latenz_s":     t_ft,
        })
        print(f"  Fine-Tuned: {len(pred_ft)} gefunden | F1={score_ft:.3f} | {t_ft}s")

    # --- Zusammenfassung ---
    _print_summary(results)
    _save_results(results, args.output_dir)


def _print_summary(results: dict):
    print("\n" + "="*50)
    print("ZUSAMMENFASSUNG")
    print("="*50)

    for key in ["basis", "finetuned"]:
        data = results[key]
        if not data:
            continue
        avg_f1      = sum(r["f1_score"]   for r in data) / len(data)
        avg_pred    = sum(r["pred_count"]  for r in data) / len(data)
        avg_valid   = sum(r["valid_count"] for r in data) / len(data)
        avg_latenz  = sum(r["latenz_s"]    for r in data) / len(data)
        all_issues  = [i for r in data for i in r["issues"]]

        label = "Basis-Modell  " if key == "basis" else "Fine-Tuned    "
        print(f"\n{label}:")
        print(f"  Durchschn. F1-Score:       {avg_f1:.3f}")
        print(f"  Durchschn. Funde:          {avg_pred:.1f}")
        print(f"  Durchschn. Gueltige Funde: {avg_valid:.1f}")
        print(f"  Durchschn. Latenz:         {avg_latenz:.1f}s")
        if all_issues:
            from collections import Counter
            top = Counter(all_issues).most_common(5)
            print(f"  Haeufigste Fehlertypen:")
            for issue, count in top:
                print(f"    - {issue}: {count}x")


def _save_results(results: dict, output_dir: str):
    import os
    os.makedirs(output_dir, exist_ok=True)
    ts   = date.today().isoformat()
    path = os.path.join(output_dir, f"finetune_eval_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nErgebnisse gespeichert: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-Tuning Evaluation")
    parser.add_argument("--eval_file",         default="../finetune_data/eval.jsonl")
    parser.add_argument("--model_base",         default="gemma3:4b",
                        help="Basis-Modell (Ollama-ID)")
    parser.add_argument("--model_ft",           default="../finetune_model",
                        help="Pfad zum Fine-Tuned Modell (HF-Format)")
    parser.add_argument("--model_ft_ollama_id", default="gemma-crawler",
                        help="Ollama-ID des Fine-Tuned Modells (nach ollama create)")
    parser.add_argument("--ollama_url",         default="http://localhost:11434")
    parser.add_argument("--output_dir",         default="../finetune_results")
    args = parser.parse_args()
    run_eval(args)
