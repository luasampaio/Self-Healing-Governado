import streamlit as st
import pandas as pd
import json
import os
import shutil
import time
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go

# Configuração e inserção de caminhos do projeto
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quality_audit.enforcement.continuous_enforcer import ContinuousEnforcer
from quality_audit.governance.policy_registry import PolicyRegistry
from quality_audit.policy.policy_engine import Decision

# Configuração da Página
st.set_page_config(
    page_title="Governança & Self-Healing de Dados",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização Premium Customizada (CSS)
st.markdown("""
<style>
    /* Cores de fundo e estrutura */
    .reportview-container {
        background: #0f0f1a;
    }
    .metric-card {
        background-color: #16162a;
        padding: 22px;
        border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        margin-bottom: 20px;
        text-align: center;
        border: 1px solid #2d2d44;
    }
    .metric-value {
        font-size: 36px;
        font-weight: bold;
        color: #4CAF50;
        margin-top: 5px;
    }
    .metric-title {
        font-size: 13px;
        color: #8a8a9e;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }
    
    /* Linha do tempo de linhagem */
    .lineage-step {
        background-color: #151526;
        border-left: 5px solid #2196F3;
        padding: 15px;
        margin-bottom: 12px;
        border-radius: 4px 8px 8px 4px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .lineage-step.raw { border-left-color: #9c27b0; }
    .lineage-step.deterministic { border-left-color: #ff9800; }
    .lineage-step.heuristic { border-left-color: #00bcd4; }
    .lineage-step.final { border-left-color: #4caf50; }
    .lineage-step.quarantined { border-left-color: #f44336; }
    
    .lineage-title {
        font-weight: bold;
        color: #ffffff;
        font-size: 16px;
        margin-bottom: 5px;
    }
    .lineage-desc {
        color: #b0bec5;
        font-size: 13px;
        margin-bottom: 10px;
    }
    
    /* Status Badge */
    .status-badge {
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 12px;
        display: inline-block;
    }
    .status-active { background-color: #1b5e20; color: #a5d6a7; }
    .status-stopped { background-color: #b71c1c; color: #ffcdd2; }
</style>
""", unsafe_allow_html=True)

# Inicialização do Enforcer em Estado de Sessão (Session State)
if "enforcer" not in st.session_state:
    st.session_state.enforcer = ContinuousEnforcer(
        contracts_dir=PROJECT_ROOT / "src" / "quality_audit" / "contracts",
        input_dir=PROJECT_ROOT / "output" / "input_queue",
        output_dir=PROJECT_ROOT / "output",
        poll_interval_seconds=1.0
    )

enforcer: ContinuousEnforcer = st.session_state.enforcer
registry = enforcer.policy_registry

# Constantes de Custos
COST_PER_MANUAL_REVIEW_MIN = 5
COST_PER_HOUR_ANALYST_BRL = 80.0

@st.cache_data(ttl=1.0)
def load_data():
    audit_path = PROJECT_ROOT / "output" / "audit_log.jsonl"
    entries = []
    if audit_path.exists():
        with open(audit_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    return entries

def calculate_metrics(entries):
    total = len(entries)
    counts = {"approved": 0, "auto_correct": 0, "review_pending": 0, "quarantined": 0}
    
    for e in entries:
        decision = e.get("decision", "unknown")
        if decision in counts:
            counts[decision] += 1
            
    auto_resolved = counts["approved"] + counts["auto_correct"]
    auto_resolution_rate = (auto_resolved / total * 100) if total > 0 else 0
    
    manual_needed = counts["review_pending"]
    manual_hours = (manual_needed * COST_PER_MANUAL_REVIEW_MIN) / 60
    manual_cost_brl = manual_hours * COST_PER_HOUR_ANALYST_BRL
    
    saved_reviews = counts["auto_correct"]
    saved_hours = (saved_reviews * COST_PER_MANUAL_REVIEW_MIN) / 60
    saved_cost_brl = saved_hours * COST_PER_HOUR_ANALYST_BRL
    
    roi = 0.0
    if manual_cost_brl > 0 or saved_cost_brl > 0:
        roi = (saved_cost_brl / (manual_cost_brl + saved_cost_brl)) * 100
        
    return {
        "total": total,
        "counts": counts,
        "rate": auto_resolution_rate,
        "manual_hours": manual_hours,
        "manual_cost": manual_cost_brl,
        "saved_hours": saved_hours,
        "saved_cost": saved_cost_brl,
        "roi": roi
    }

def update_record_decision(record_id: str, new_decision: str):
    """
    Função administrativa para atualizar a decisão de um registro no audit log
    e migrar seus dados das pastas de review para approved/quarantine.
    """
    audit_path = PROJECT_ROOT / "output" / "audit_log.jsonl"
    if not audit_path.exists():
        return

    # 1. Atualizar arquivo de audit_log
    lines = []
    updated_record = None
    with open(audit_path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                data = json.loads(line)
                if str(data.get("record_id")) == str(record_id):
                    data["decision"] = new_decision
                    # Atualiza linhagem com o passo manual
                    if "lineage" in data and isinstance(data["lineage"], list):
                        data["lineage"].append({
                            "step": "4_manual_review",
                            "record": data.get("corrected_record") or data.get("original_record"),
                            "description": f"Decisão alterada manualmente para {new_decision.upper()}"
                        })
                    updated_record = data
                    lines.append(json.dumps(data, ensure_ascii=False) + "\n")
                else:
                    lines.append(line)
                    
    with open(audit_path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)

    # 2. Migrar arquivos físicos de pendência
    review_dir = PROJECT_ROOT / "output" / "review_pending"
    dest_dir = PROJECT_ROOT / "output" / ("approved" if new_decision in ["approved", "auto_correct"] else "quarantine")
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Procura o arquivo correspondente nas pendências
    for path in review_dir.glob("*.jsonl"):
        temp_lines = []
        found_in_file = False
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    if str(rec.get("id")) == str(record_id):
                        found_in_file = True
                        # Escreve no destino
                        rec["_governance"]["decision"] = new_decision
                        rec["_governance"]["timestamp"] = int(time.time())
                        
                        dest_file = dest_dir / f"pessoa_fisica_{new_decision}_manual_{int(time.time())}.jsonl"
                        with open(dest_file, "a", encoding="utf-8") as out:
                            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    else:
                        temp_lines.append(line)
        
        if found_in_file:
            if temp_lines:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.writelines(temp_lines)
            else:
                os.remove(path)
            break

    st.cache_data.clear()

def main():
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3208/3208493.png", width=60)
    st.sidebar.title("Self-Healing-Governado")
    st.sidebar.markdown(f"**Contrato Ativo:** `pessoa_fisica`")
    
    # Mostra indicador do Enforcer na Sidebar
    status_class = "status-active" if enforcer.is_running else "status-stopped"
    status_text = "MONITORAMENTO ATIVO" if enforcer.is_running else "MONITORAMENTO PARADO"
    st.sidebar.markdown(f'<span class="status-badge {status_class}">{status_text}</span>', unsafe_allow_html=True)
    st.sidebar.markdown("---")
    
    menu = st.sidebar.radio(
        "Navegação",
        [
            "🛡️ Visão Geral & Custos",
            "📋 Fila de Revisão",
            "🔍 Explorador de Linhagem (Lineage)",
            "🏛️ Governança & Ownership",
            "⚡ Monitoramento Contínuo"
        ]
    )
    
    entries = load_data()
    metrics = calculate_metrics(entries)

    # ------------------------------------------------------------------
    # TAB: Visão Geral
    # ------------------------------------------------------------------
    if menu == "🛡️ Visão Geral & Custos":
        st.title("🛡️ Dashboard de Governança & Qualidade")
        st.markdown("Acompanhamento de eficiência operacional, ROI e qualidade contínua sob governança de dados.")
        
        if not entries:
            st.info("Nenhum dado encontrado no Audit Log. Inicialize o monitoramento ou gere dados simulados.")
            return

        # Top KPIs
        st.markdown("### Métricas de Qualidade")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f'<div class="metric-card"><div class="metric-title">Total Processado</div><div class="metric-value" style="color: #ffffff;">{metrics["total"]}</div></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><div class="metric-title">Taxa de Auto-Remediação</div><div class="metric-value" style="color: #03A9F4;">{metrics["rate"]:.1f}%</div></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><div class="metric-title">Auto-Corrigidos</div><div class="metric-value" style="color: #4CAF50;">{metrics["counts"]["auto_correct"]}</div></div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="metric-card"><div class="metric-title">Quarentena</div><div class="metric-value" style="color: #F44336;">{metrics["counts"]["quarantined"]}</div></div>', unsafe_allow_html=True)

        # Cost KPIs
        st.markdown("### Retorno sobre Investimento (ROI)")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Economia Estimada (Auto-correct)", f"R$ {metrics['saved_cost']:,.2f}", f"{metrics['saved_hours']:.1f}h salvas")
        with c2:
            st.metric("Custo Pendente (Revisão Manual)", f"R$ {metrics['manual_cost']:,.2f}", f"-{metrics['manual_hours']:.1f}h necessárias", delta_color="inverse")
        with c3:
            st.metric("ROI de Automação", f"{metrics['roi']:.1f}%", "Esforço manual evitado")

        st.markdown("---")
        
        # Charts
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.markdown("#### Distribuição de Decisões")
            labels = list(metrics["counts"].keys())
            values = list(metrics["counts"].values())
            colors = ['#4CAF50', '#03A9F4', '#FFC107', '#F44336']
            fig1 = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4, marker=dict(colors=colors))])
            fig1.update_layout(margin=dict(t=30, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#fff")
            st.plotly_chart(fig1, width='stretch')
            
        with col_chart2:
            st.markdown("#### Comparativo de Custos Operacionais (R$)")
            fig2 = go.Figure(data=[
                go.Bar(name='Economia (Auto-correct)', x=['Custos'], y=[metrics['saved_cost']], marker_color='#4CAF50'),
                go.Bar(name='Custo Estimado (Revisão)', x=['Custos'], y=[metrics['manual_cost']], marker_color='#FFC107')
            ])
            fig2.update_layout(barmode='group', margin=dict(t=30, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#fff")
            st.plotly_chart(fig2, width='stretch')

    # ------------------------------------------------------------------
    # TAB: Fila de Revisão
    # ------------------------------------------------------------------
    elif menu == "📋 Fila de Revisão":
        st.title("📋 Fila de Revisão Manual de Pendências")
        st.markdown("Valide anomalias de baixa confiança detectadas pelas políticas e decida o tratamento.")
        
        pending_entries = [e for e in entries if e.get("decision") == "review_pending"]
        
        if not pending_entries:
            st.success("🎉 Excelente! Nenhum registro aguardando revisão manual no momento.")
            return
            
        st.warning(f"**{len(pending_entries)} registros** aguardam sua auditoria e decisão final.")
        
        # Grid para DataFrame rápido
        df_data = []
        for e in pending_entries:
            df_data.append({
                "Record ID": e.get("record_id", "N/A"),
                "Timestamp UTC": e.get("timestamp", "N/A"),
                "Versão Política": e.get("policy_version", "1.0.0"),
                "Dono da Política": e.get("policy_owner", "N/A"),
                "Motivos": len(e.get("review_reasons", []))
            })
        st.dataframe(pd.DataFrame(df_data), width='stretch')
        
        st.markdown("### Detalhamento e Ações por Registro")
        for i, e in enumerate(pending_entries):
            record_id = e.get("record_id", "N/A")
            reasons = e.get("review_reasons", [])
            corrections = e.get("corrections", [])
            field_owners = e.get("field_ownerships", {})
            
            with st.expander(f"🔍 Registro ID: {record_id} | {len(reasons)} anomalias detectadas"):
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.markdown("**🚨 Motivos da Pendência:**")
                    for r in reasons:
                        st.error(f"• {r}")
                        
                    if corrections:
                        st.markdown("**✨ Correções Seguras já Aplicadas (Deterministic):**")
                        for c in corrections:
                            field = c.get('field', '?')
                            orig = c.get('original_value', '?')
                            corr = c.get('corrected_value', '?')
                            rule = c.get('rule_name', '?')
                            owner = field_owners.get(field, "Desconhecido")
                            st.info(f"• **{field}**: `{orig}` ➔ `{corr}` ({rule}) | *Owner: {owner}*")
                            
                with col_right:
                    st.markdown("**📄 Carga de Dados Recebida:**")
                    st.json(e.get("original_record", {}))
                
                # Ações de Governança
                c_btn1, c_btn2, _ = st.columns([1, 1, 2])
                with c_btn1:
                    if st.button("✅ Aprovar Alterações", key=f"approve_{record_id}_{i}", type="primary"):
                        update_record_decision(record_id, "approved")
                        st.success(f"Registro {record_id} aprovado e enviado para Silver!")
                        time.sleep(1.0)
                        st.rerun()
                with c_btn2:
                    if st.button("❌ Enviar para Quarentena", key=f"quarantine_{record_id}_{i}"):
                        update_record_decision(record_id, "quarantined")
                        st.error(f"Registro {record_id} bloqueado e enviado para Quarentena!")
                        time.sleep(1.0)
                        st.rerun()

    # ------------------------------------------------------------------
    # TAB: Explorador de Linhagem
    # ------------------------------------------------------------------
    elif menu == "🔍 Explorador de Linhagem (Lineage)":
        st.title("🔍 Rastreabilidade e Linhagem de Registros")
        st.markdown("Trilha de auditoria passo a passo mostrando a transformação e enriquecimento de dados individuais.")
        
        if not entries:
            st.info("Log de auditoria vazio.")
            return

        # Listagem de ids
        record_ids = list(set([str(e.get("record_id")) for e in entries if e.get("record_id")]))
        record_ids.sort()
        
        selected_id = st.selectbox("Selecione o Record ID para auditar:", record_ids)
        
        # Encontra o registro selecionado
        entry = next((e for e in entries if str(e.get("record_id")) == selected_id), None)
        
        if entry:
            st.markdown(f"### Metadados de Auditoria do Registro: `{selected_id}`")
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("Decisão Operacional", entry.get("decision", "N/A").upper())
            with col_m2:
                st.metric("Versão da Política", entry.get("policy_version", "N/A"))
            with col_m3:
                st.metric("Time Proprietário", entry.get("policy_owner", "N/A"))
                
            st.markdown(f"**Assinatura Hash da Política (SHA256):** `{entry.get('policy_hash', 'N/A')}`")
            st.markdown(f"**Timestamp da Execução (UTC):** `{entry.get('timestamp', 'N/A')}`")
            st.markdown(f"**Contexto de Execução:** Usuário `{entry.get('metadata', {}).get('runner_user', 'N/A')}` rodando em `{entry.get('metadata', {}).get('runner_host', 'N/A')}` ({entry.get('metadata', {}).get('env_environment', 'N/A')})")
            
            st.markdown("---")
            st.markdown("### Linhagem de Transformação do Registro")
            
            lineage = entry.get("lineage", [])
            if not lineage:
                st.warning("Linhagem não gravada para este registro (registro antigo).")
            else:
                for step in lineage:
                    step_name = step.get("step")
                    record_state = step.get("record", {})
                    desc = step.get("description", "")
                    changes = step.get("changes", [])
                    
                    if step_name == "0_raw":
                        st.markdown(f"""
                        <div class="lineage-step raw">
                            <div class="lineage-title">1. Entrada Bruta (Raw Data)</div>
                            <div class="lineage-desc">{desc}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.json(record_state)
                        
                    elif step_name == "1_deterministic_corrections":
                        st.markdown(f"""
                        <div class="lineage-step deterministic">
                            <div class="lineage-title">2. Correções Determinísticas Aplicadas</div>
                            <div class="lineage-desc">{desc}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        for ch in changes:
                            st.write(f"🔄 Campo **{ch.get('field')}**: `{ch.get('original_value')}` ➔ `{ch.get('corrected_value')}` (Regra: `{ch.get('rule_name')}`)")
                        st.json(record_state)
                        
                    elif step_name == "2_heuristic_corrections":
                        st.markdown(f"""
                        <div class="lineage-step heuristic">
                            <div class="lineage-title">3. Correções Heurísticas Aplicadas</div>
                            <div class="lineage-desc">{desc}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        for ch in changes:
                            st.write(f"🔮 Campo **{ch.get('field')}**: `{ch.get('original_value')}` ➔ `{ch.get('suggested_value')}` (Confiança: `{(ch.get('confidence') or 0) * 100:.1f}%`) (Heurística: `{ch.get('heuristic_name')}`)")
                        st.json(record_state)
                        
                    elif step_name == "3_final":
                        card_class = "quarantined" if entry.get("decision") == "quarantined" else "final"
                        st.markdown(f"""
                        <div class="lineage-step {card_class}">
                            <div class="lineage-title">4. Estado Final Avaliado</div>
                            <div class="lineage-desc">{desc}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.json(record_state)

                    elif step_name == "4_manual_review":
                        st.markdown(f"""
                        <div class="lineage-step final">
                            <div class="lineage-title">5. Revisão Humana Direta</div>
                            <div class="lineage-desc">{desc}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.json(record_state)

    # ------------------------------------------------------------------
    # TAB: Governança & Ownership
    # ------------------------------------------------------------------
    elif menu == "🏛️ Governança & Ownership":
        st.title("🏛️ Catálogo de Governança & Mapeamento de Ownership")
        st.markdown("Verificação de políticas ativas, assinaturas criptográficas de integridade e KPIs de qualidade por equipe.")
        
        # 1. Contratos Ativos
        st.markdown("### 📄 Políticas Ativas no Registro")
        policies = registry.list_policies()
        df_p = pd.DataFrame(policies)
        if not df_p.empty:
            df_p.columns = ["Entidade", "Versão", "Owner Geral", "Assinatura SHA256", "Campos Regulados", "Regras Ativas"]
            st.dataframe(df_p, width='stretch')
        else:
            st.info("Nenhuma política carregada.")

        # Detalhar campos da política ativa
        selected_policy_name = "pessoa_fisica" # padrão
        contract = registry.get_contract(selected_policy_name)
        
        if contract:
            st.markdown(f"### 🗂️ Dicionário de Dados e Responsáveis da Entidade: `{selected_policy_name}`")
            fields_data = []
            for f in contract.fields:
                owner = getattr(f, "owner", None) or contract.metadata.get("owner") or "governança_dados"
                fields_data.append({
                    "Campo": f.name,
                    "Tipo de Dado": f.dtype,
                    "Obrigatório": "Sim" if f.required else "Não",
                    "Permite Nulo": "Sim" if f.nullable else "Não",
                    "Validação Regex": f.regex or "Nenhuma",
                    "Dono do Campo (Owner)": owner,
                    "Descrição": f.description
                })
            st.dataframe(pd.DataFrame(fields_data), width='stretch')

        # 2. KPIs de qualidade por Owner
        st.markdown("### 📊 Inconsistências Detectadas por Equipe (Ownership)")
        
        if entries:
            # Conta anomalias por owner
            owner_anomalies = {}
            for e in entries:
                field_owners = e.get("field_ownerships", {})
                reasons = e.get("review_reasons", []) + e.get("quarantine_reasons", [])
                corrections = e.get("corrections", [])
                
                # Para cada correção ou erro, atribui ao owner do respectivo campo
                for c in corrections:
                    field = c.get("field")
                    owner = field_owners.get(field, "Desconhecido")
                    owner_anomalies[owner] = owner_anomalies.get(owner, 0) + 1
                    
                # Atribui motivos de erro analisando quais campos foram mencionados no erro
                for r in reasons:
                    # Tenta identificar qual campo falhou
                    found_field = False
                    for f in field_owners:
                        if f in r:
                            owner = field_owners[f]
                            owner_anomalies[owner] = owner_anomalies.get(owner, 0) + 1
                            found_field = True
                            break
                    if not found_field:
                        # Fallback pro owner do contrato
                        contract_owner = e.get("policy_owner", "governança_dados")
                        owner_anomalies[contract_owner] = owner_anomalies.get(contract_owner, 0) + 1
            
            if owner_anomalies:
                df_owner = pd.DataFrame(list(owner_anomalies.items()), columns=["Equipe Owner", "Ocorrências de Qualidade"])
                fig_owner = px.bar(
                    df_owner, 
                    x="Equipe Owner", 
                    y="Ocorrências de Qualidade", 
                    title="Volume de Incidências de Qualidade Tratadas/Pendentes por Time",
                    color="Equipe Owner",
                    color_discrete_sequence=px.colors.qualitative.Dark24
                )
                fig_owner.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#fff")
                st.plotly_chart(fig_owner, width='stretch')
            else:
                st.info("Nenhuma inconsistência de qualidade registrada no log de auditoria.")
        else:
            st.info("Log de auditoria vazio.")

    # ------------------------------------------------------------------
    # TAB: Monitoramento Contínuo
    # ------------------------------------------------------------------
    elif menu == "⚡ Monitoramento Contínuo":
        st.title("⚡ Painel de Controle de Processamento Contínuo")
        st.markdown("Gerencie a escuta de novos lotes de dados em tempo real nas pastas de recebimento.")
        
        col_ctrl1, col_ctrl2 = st.columns([2, 3])
        
        with col_ctrl1:
            st.markdown("### Controle do Listener")
            
            # Controle Liga/Desliga
            if enforcer.is_running:
                st.success("🟢 O mecanismo de escuta contínua está executando.")
                if st.button("Parar Escuta Contínua (Stop)", type="primary"):
                    enforcer.stop()
                    st.rerun()
            else:
                st.error("🔴 O mecanismo de escuta contínua está parado.")
                if st.button("Iniciar Escuta Contínua (Start)", type="primary"):
                    enforcer.start()
                    st.rerun()
                    
            st.markdown("---")
            st.markdown("### Diretórios Monitorados")
            st.code(f"Entrada:  {enforcer.input_dir.relative_to(PROJECT_ROOT)}")
            st.code(f"Histórico: {enforcer.history_dir.relative_to(PROJECT_ROOT)}")
            st.code(f"Aprovados: {enforcer.approved_dir.relative_to(PROJECT_ROOT)}")
            st.code(f"Revisão:   {enforcer.review_dir.relative_to(PROJECT_ROOT)}")
            st.code(f"Quarent.:  {enforcer.quarantine_dir.relative_to(PROJECT_ROOT)}")

        with col_ctrl2:
            st.markdown("### Métricas Operacionais do Listener")
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                st.metric("Arquivos Processados", enforcer.processed_files_count)
            with c_m2:
                st.metric("Velocidade do Lote", f"{enforcer.last_process_time:.2f}s" if enforcer.last_process_time else "N/A")
            
            st.markdown(f"**Último arquivo lido:** `{enforcer.last_processed_file or 'Nenhum'}`")
            
            # Formulário de Simulação de Registros
            st.markdown("---")
            st.markdown("### 🧪 Simulador de Carga Contínua")
            st.markdown("Crie e envie um arquivo JSON contendo registros inválidos para ver o Enforcer processando-os em tempo real!")
            
            scenario = st.selectbox(
                "Escolha um cenário de simulação:",
                [
                    "Cadastro Válido (Approved)",
                    "Campos Corrigíveis (Auto Correct)",
                    "Dúvidas Cadastrais (Review Pending)",
                    "Inconsistências Críticas (Quarantine)"
                ]
            )
            
            # Dados padrão por cenário
            simulated_data = []
            if scenario == "Cadastro Válido (Approved)":
                simulated_data = [{
                    "id": "SIM_001",
                    "nome": "Carlos Souza",
                    "cpf": "12345678901",
                    "data_nascimento": "1994-08-20",
                    "email": "carlos@provedor.com",
                    "cidade": "São Paulo",
                    "uf": "SP",
                    "status": "ativo"
                }]
            elif scenario == "Campos Corrigíveis (Auto Correct)":
                simulated_data = [{
                    "id": "SIM_002",
                    "nome": "  Julia Rocha  ", # com espaços
                    "cpf": "123.456.789-09", # com pontos/traço
                    "data_nascimento": "1988-11-02",
                    "email": "julia@empresa.com",
                    "cidade": "Curitiba",
                    "uf": "pr", # minúsculo
                    "status": "ativo"
                }]
            elif scenario == "Dúvidas Cadastrais (Review Pending)":
                simulated_data = [{
                    "id": "SIM_003",
                    "nome": "Marcos Lima",
                    "cpf": "44444444444",
                    "data_nascimento": "1991-03-30",
                    "cidade": "Niterói",
                    "uf": "RJ",
                    "renda_mensal": -1500.0, # renda negativa (campo de finanças)
                    "status": "ativo"
                }]
            elif scenario == "Inconsistências Críticas (Quarantine)":
                simulated_data = [
                    {
                        "id": "SIM_004",
                        "nome": None, # nome nulo (obrigatório)
                        "cpf": "123", # CPF curto
                        "data_nascimento": "1990-01-01",
                        "uf": "SP",
                        "status": "ativo"
                    }
                ]
                
            json_text = st.text_area("JSON do registro para simulação:", json.dumps(simulated_data, indent=2, ensure_ascii=False))
            
            if st.button("Enviar Registro para a Fila de Entrada"):
                try:
                    payload = json.loads(json_text)
                    input_file_path = enforcer.input_dir / f"pessoa_fisica_simulated_{int(time.time())}.jsonl"
                    
                    with open(input_file_path, "w", encoding="utf-8") as fh:
                        for item in payload:
                            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                            
                    st.success(f"Arquivo `pessoa_fisica_simulated` salvo com sucesso em `output/input_queue/`!")
                    st.info("Aguarde a atualização automática do Listener...")
                    time.sleep(1.5)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Erro ao processar JSON: {ex}")

if __name__ == "__main__":
    main()
