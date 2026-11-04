"""
Continuous Enforcer — Motor de monitoramento contínuo de políticas de qualidade.

Monitora um diretório de entrada para novos lotes de dados, executa
o pipeline de validação e roteia os registros conforme as decisões de políticas.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..orchestrator import SelfHealingOrchestrator
from ..governance.policy_registry import PolicyRegistry
from ..policy.policy_engine import Decision

logger = logging.getLogger(__name__)


class ContinuousEnforcer:
    """
    Escuta continuamente uma pasta de entrada por novos lotes de dados
    e aplica as validações de políticas correspondentes.
    """

    def __init__(
        self,
        contracts_dir: str | Path,
        input_dir: str | Path,
        output_dir: str | Path,
        poll_interval_seconds: float = 2.0,
        record_id_field: str = "id",
    ) -> None:
        self.contracts_dir = Path(contracts_dir)
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.poll_interval_seconds = poll_interval_seconds
        self.record_id_field = record_id_field

        # Subpastas de saída
        self.history_dir = self.output_dir / "input_history"
        self.approved_dir = self.output_dir / "approved"
        self.quarantine_dir = self.output_dir / "quarantine"
        self.review_dir = self.output_dir / "review_pending"
        self.audit_log_path = self.output_dir / "audit_log.jsonl"

        # Inicializa infraestrutura
        self.policy_registry = PolicyRegistry(self.contracts_dir)
        self._create_directories()

        # Threading/Controle
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

        # Status operacional para exibição no dashboard
        self.processed_files_count = 0
        self.last_processed_file: Optional[str] = None
        self.last_process_time: Optional[float] = None
        self.active_orchestrators: Dict[str, SelfHealingOrchestrator] = {}

    def _create_directories(self) -> None:
        """Cria os diretórios necessários se não existirem."""
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.approved_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.review_dir.mkdir(parents=True, exist_ok=True)

    def _get_orchestrator(self, entity_name: str) -> Optional[SelfHealingOrchestrator]:
        """Obtém ou cria um orquestrador para a entidade correspondente."""
        if entity_name in self.active_orchestrators:
            return self.active_orchestrators[entity_name]

        contract = self.policy_registry.get_contract(entity_name)
        if not contract:
            return None

        # Cria orquestrador associado a esta política
        orchestrator = SelfHealingOrchestrator.from_config(
            contracts_dir=self.contracts_dir,
            entity_name=entity_name,
            audit_output=self.audit_log_path,
            record_id_field=self.record_id_field,
        )
        self.active_orchestrators[entity_name] = orchestrator
        return orchestrator

    def start(self) -> None:
        """Inicia o monitoramento contínuo em uma thread em background."""
        if self._is_running:
            logger.warning("Enforcer contínuo já está em execução.")
            return

        self._stop_event.clear()
        self._is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("ContinuousEnforcer iniciado monitorando: %s", self.input_dir)

    def stop(self) -> None:
        """Para o monitoramento contínuo."""
        if not self._is_running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._is_running = False
        logger.info("ContinuousEnforcer finalizado.")

    @property
    def is_running(self) -> bool:
        """Verifica se o enforcer está rodando."""
        return self._is_running

    def _run_loop(self) -> None:
        """Loop de polling de arquivos."""
        while not self._stop_event.is_set():
            try:
                self._poll_input_directory()
            except Exception as e:
                logger.error("Erro no loop do ContinuousEnforcer: %s", e)
            time.sleep(self.poll_interval_seconds)

    def _poll_input_directory(self) -> None:
        """Verifica a presença de novos arquivos na pasta de entrada."""
        # Suporta JSON, JSONL e CSV
        supported_extensions = ["*.json", "*.jsonl", "*.csv"]
        files_to_process: List[Path] = []
        for ext in supported_extensions:
            files_to_process.extend(self.input_dir.glob(ext))

        # Ordena para garantir ordem cronológica de processamento
        files_to_process.sort(key=lambda p: p.stat().st_mtime)

        for file_path in files_to_process:
            if self._stop_event.is_set():
                break
            self._process_file(file_path)

    def _process_file(self, file_path: Path) -> None:
        """Processa um arquivo individual do diretório monitorado."""
        start_time = time.time()
        logger.info("Enforcer detectou arquivo: %s", file_path.name)

        # Identifica a entidade a partir do nome do arquivo (ex: pessoa_fisica_batch1.jsonl -> pessoa_fisica)
        # Tenta casar com as políticas registradas
        entity_name = None
        for p in self.policy_registry.list_policies():
            name = p["entity_name"]
            if file_path.name.startswith(name):
                entity_name = name
                break

        if not entity_name:
            logger.error("Não foi possível identificar a entidade correspondente ao arquivo: %s", file_path.name)
            # Move arquivo inválido para quarentena bruta
            shutil.move(str(file_path), str(self.quarantine_dir / f"invalid_prefix_{file_path.name}"))
            return

        orchestrator = self._get_orchestrator(entity_name)
        if not orchestrator:
            logger.error("Nenhum contrato ativo encontrado para entidade: %s", entity_name)
            shutil.move(str(file_path), str(self.quarantine_dir / f"missing_contract_{file_path.name}"))
            return

        # Carrega os registros
        records = self._load_records(file_path)
        if not records:
            logger.warning("Arquivo vazio ou formato inválido: %s", file_path.name)
            shutil.move(str(file_path), str(self.history_dir / f"empty_{file_path.name}"))
            return

        # Processa em lote usando o orquestrador
        results = orchestrator.process_batch(records)

        # Roteia os resultados para as saídas
        self._route_results(entity_name, file_path.stem, results)

        # Move o arquivo processado para a pasta de histórico
        history_path = self.history_dir / f"{file_path.stem}_processed_{int(time.time())}{file_path.suffix}"
        shutil.move(str(file_path), str(history_path))

        # Atualiza métricas
        self.processed_files_count += 1
        self.last_processed_file = file_path.name
        self.last_process_time = time.time() - start_time
        logger.info("Arquivo %s processado com sucesso em %.2fs", file_path.name, self.last_process_time)

    def _load_records(self, file_path: Path) -> List[Dict[str, Any]]:
        """Lê registros de arquivos JSON, JSONL ou CSV."""
        records: List[Dict[str, Any]] = []
        suffix = file_path.suffix.lower()

        try:
            if suffix == ".jsonl":
                with open(file_path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            records.append(json.loads(line))
            elif suffix == ".json":
                with open(file_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, list):
                        records = data
                    elif isinstance(data, dict):
                        records = [data]
            elif suffix == ".csv":
                import pandas as pd
                df = pd.read_csv(file_path)
                # Converte NaN para None para ficar compatível
                records = df.where(pd.notnull(df), None).to_dict(orient="records")
        except Exception as e:
            logger.error("Erro ao ler registros de %s: %s", file_path.name, e)

        return records

    def _route_results(
        self,
        entity_name: str,
        batch_id: str,
        results: Dict[str, List[Any]]
    ) -> None:
        """Grava os resultados segregados em suas respectivas pastas de saída."""
        timestamp = int(time.time())

        # Função auxiliar para salvar records JSON Lines
        def save_records(records_list: List[Any], dest_path: Path) -> None:
            if not records_list:
                return
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "w", encoding="utf-8") as fh:
                for res in records_list:
                    # Se for PolicyResult, extrai o registro final (ou original para quarentena)
                    if hasattr(res, "corrected_record") and res.corrected_record:
                        data = res.corrected_record
                    else:
                        data = res.original_record
                    
                    # Salva os dados enriquecidos com metadados de governança da decisão
                    record_to_write = dict(data)
                    record_to_write["_governance"] = {
                        "decision": res.decision.value,
                        "reasons": res.quarantine_reasons or res.review_reasons,
                        "timestamp": timestamp,
                        "batch_id": batch_id,
                    }
                    fh.write(json.dumps(record_to_write, ensure_ascii=False) + "\n")

        # 1. Approved & Auto-correct -> vão para Approved (Prontos para Silver)
        approved_records = results.get(Decision.APPROVED.value, []) + results.get(Decision.AUTO_CORRECT.value, [])
        save_records(approved_records, self.approved_dir / f"{entity_name}_approved_{batch_id}_{timestamp}.jsonl")

        # 2. Quarantined -> Quarentena
        quarantine_records = results.get(Decision.QUARANTINED.value, [])
        save_records(quarantine_records, self.quarantine_dir / f"{entity_name}_quarantine_{batch_id}_{timestamp}.jsonl")

        # 3. Review Pending -> Fila de revisão
        review_records = results.get(Decision.REVIEW_PENDING.value, [])
        save_records(review_records, self.review_dir / f"{entity_name}_review_{batch_id}_{timestamp}.jsonl")
