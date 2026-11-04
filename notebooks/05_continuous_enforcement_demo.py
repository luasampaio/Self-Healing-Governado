"""
05 — Continuous Enforcement Demo

Script de simulação do mecanismo de enforcement contínuo.
Inicia o Listener em background, cria arquivos de teste e exibe o fluxo
ponta a ponta de validação, ownership e linhagem.
"""

import json
import os
import sys
import time
from pathlib import Path

# Ajuste de path para execução local
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quality_audit.enforcement.continuous_enforcer import ContinuousEnforcer
from quality_audit.policy.policy_engine import Decision


def main():
    print("=" * 60)
    print("Self-Healing Governado — Simulação de Enforcement Contínuo")
    print("=" * 60)
    
    contracts_dir = PROJECT_ROOT / "src" / "quality_audit" / "contracts"
    input_dir = PROJECT_ROOT / "output" / "input_queue"
    output_dir = PROJECT_ROOT / "output"

    # 1. Limpar pastas de simulação para iniciar limpo
    print("\n🧹 Limpando pastas temporárias...")
    for sub in ["input_queue", "input_history", "approved", "quarantine", "review_pending"]:
        path = output_dir / sub
        if path.exists():
            for f in path.glob("*.*"):
                try:
                    os.remove(f)
                except Exception:
                    pass
    
    # Remove audit log antigo para facilitar visualização
    audit_log = output_dir / "audit_log.jsonl"
    if audit_log.exists():
        try:
            os.remove(audit_log)
        except Exception:
            pass

    # 2. Inicializar o Enforcer Contínuo
    print("\n🚀 Inicializando o ContinuousEnforcer...")
    enforcer = ContinuousEnforcer(
        contracts_dir=contracts_dir,
        input_dir=input_dir,
        output_dir=output_dir,
        poll_interval_seconds=1.0
    )

    print(f"  Diretório monitorado: {input_dir.relative_to(PROJECT_ROOT)}")
    print(f"  Diretório de saída:    {output_dir.relative_to(PROJECT_ROOT)}")

    # Inicia a thread de background
    enforcer.start()
    time.sleep(1.0)

    # 3. Gerar Lote 1: Registros Válidos e Corrigíveis (Approved + Auto Correct)
    print("\n💾 Escrevendo Lote 1: Registros de Sucesso (pessoa_fisica_batch1.jsonl)...")
    batch_1 = [
        {
            "id": "B1_001",
            "nome": "Fernando Souza",
            "cpf": "23456789012",
            "data_nascimento": "1989-10-12",
            "email": "fernando@email.com",
            "cidade": "São Paulo",
            "uf": "SP",
            "status": "ativo"
        },
        {
            "id": "B1_002",
            "nome": "  Paula Teixeira  ", # necessita trim/trimming
            "cpf": "123.456.789-09", # necessita limpeza de pontuação
            "data_nascimento": "1995-02-17",
            "cidade": "Belo Horizonte",
            "uf": "mg", # necessita caixa alta
            "status": "ativo"
        }
    ]
    
    with open(input_dir / "pessoa_fisica_batch1.jsonl", "w", encoding="utf-8") as fh:
        for r in batch_1:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Espera o enforcer capturar e processar o lote
    time.sleep(2.5)

    # 4. Gerar Lote 2: Registros com Dúvidas Cadastrais (Review Pending)
    print("\n💾 Escrevendo Lote 2: Inconsistências de Negócio (pessoa_fisica_batch2.jsonl)...")
    batch_2 = [
        {
            "id": "B2_001",
            "nome": "Ricardo Menezes",
            "cpf": "99999999999", # CPF inválido repetido
            "data_nascimento": "1978-05-24",
            "cidade": "Rio de Janeiro",
            "uf": "RJ",
            "renda_mensal": -100.0, # renda inválida (atribuída ao owner: financeiro)
            "status": "ativo"
        }
    ]
    
    with open(input_dir / "pessoa_fisica_batch2.jsonl", "w", encoding="utf-8") as fh:
        for r in batch_2:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    time.sleep(2.5)

    # 5. Gerar Lote 3: Registros Críticos (Quarantine)
    print("\n💾 Escrevendo Lote 3: Dados Corrompidos (pessoa_fisica_batch3.jsonl)...")
    batch_3 = [
        {
            "id": "B3_001",
            "nome": None, # Campo obrigatório nulo (atribuído ao time de cadastro)
            "cpf": "987", # CPF totalmente quebrado
            "data_nascimento": "1990-01-01",
            "status": "inativo"
        }
    ]
    
    with open(input_dir / "pessoa_fisica_batch3.jsonl", "w", encoding="utf-8") as fh:
        for r in batch_3:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    time.sleep(2.5)

    # 6. Exibir Resumo das Métricas
    print("\n📊 Métricas finais do Listener:")
    print(f"  Total de arquivos lidos: {enforcer.processed_files_count}")
    print(f"  Tempo do último lote:    {enforcer.last_process_time:.2f}s" if enforcer.last_process_time else "N/A")
    
    # 7. Finalizar Enforcer
    print("\n🛑 Parando o ContinuousEnforcer...")
    enforcer.stop()
    
    # 8. Inspecionar e Exibir Arquivos nas Pastas de Saída
    print("\n🔍 Inspeção física de pastas de saída:")
    
    def show_dir_files(name, path):
        print(f"\n  [{name.upper()}] - {path}")
        files = list(path.glob("*.jsonl"))
        if not files:
            print("    Nenhum arquivo.")
        for f in files:
            print(f"    📄 File: {f.name}")
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    data = json.loads(line)
                    gov = data.get("_governance", {})
                    rec_id = data.get("id")
                    print(f"      - ID: {rec_id} | Decisão: {gov.get('decision')} | Erros: {gov.get('reasons')}")

    show_dir_files("Approved (Silver Ready)", output_dir / "approved")
    show_dir_files("Review Pending (Human Queue)", output_dir / "review_pending")
    show_dir_files("Quarantined", output_dir / "quarantine")

    print("\n" + "=" * 60)
    print("Simulação Concluída. Use o Streamlit para ver o dashboard!")
    print("Comando: streamlit run frontend/app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
