"""
Script de seed — insere leads mockados no banco para testes locais.
Execute após aplicar as migrations:
    python scripts/seed_leads.py

Gera 10 leads com perfis variados representando diferentes estágios do funil.
"""
import asyncio
import uuid
import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Carrega .env
from dotenv import load_dotenv
load_dotenv()

from src.db.session import AsyncSessionLocal
from src.db.models import Lead, LeadStatusHistory


MOCK_LEADS = [
    {
        "phone": "5511991110001",
        "name": "João Carlos Mendes",
        "email": "joao.mendes@email.com",
        "age": 52,
        "status": "novo",
        "source": "campanha_abril_2026",
        "interested_plan": None,
    },
    {
        "phone": "5511991110002",
        "name": "Maria Aparecida Silva",
        "email": "maria.silva@gmail.com",
        "age": 68,
        "status": "contactado",
        "source": "campanha_abril_2026",
        "interested_plan": "Plano Senior",
    },
    {
        "phone": "5521991110003",
        "name": "Roberto Alves",
        "email": None,
        "age": 45,
        "status": "em_atendimento",
        "source": "indicação",
        "interested_plan": "Plano Família",
    },
    {
        "phone": "5531991110004",
        "name": "Fernanda Costa",
        "email": "fernanda.costa@hotmail.com",
        "age": 38,
        "status": "interessado",
        "source": "campanha_março_2026",
        "interested_plan": "UTI Móvel Individual",
    },
    {
        "phone": "5511991110005",
        "name": "Paulo Roberto Esteves",
        "email": "paulo.esteves@empresa.com.br",
        "age": 55,
        "status": "sem_retorno",
        "source": "campanha_abril_2026",
        "interested_plan": None,
    },
    {
        "phone": "5548991110006",
        "name": "Ana Lúcia Ferreira",
        "email": "ana.ferreira@email.com",
        "age": 61,
        "status": "fechado",
        "source": "campanha_março_2026",
        "interested_plan": "Plano Senior Premium",
    },
    {
        "phone": "5511991110007",
        "name": "Carlos Eduardo Martins",
        "email": None,
        "age": 42,
        "status": "nao_interessado",
        "source": "cold_outreach",
        "interested_plan": None,
    },
    {
        "phone": "5585991110008",
        "name": "Lucia Pereira",
        "email": "lucia.pereira@gmail.com",
        "age": 71,
        "status": "escalado",
        "source": "campanha_abril_2026",
        "interested_plan": "Plano Senior",
    },
    {
        "phone": "5511991110009",
        "name": "Diego Souza",
        "email": "diego.souza@gmail.com",
        "age": 35,
        "status": "perdido",
        "source": "campanha_fevereiro_2026",
        "interested_plan": "Plano Individual",
    },
    {
        "phone": "5511991110010",
        "name": "Sandra Regina Barbosa",
        "email": "sandra.barbosa@email.com",
        "age": 58,
        "status": "novo",
        "source": "campanha_abril_2026",
        "interested_plan": None,
    },
]


async def seed_leads():
    """Insere os leads mockados no banco."""
    async with AsyncSessionLocal() as db:
        created = 0
        skipped = 0

        for lead_data in MOCK_LEADS:
            from sqlalchemy import select
            result = await db.execute(
                select(Lead).where(Lead.phone == lead_data["phone"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                skipped += 1
                print(f"⏭️  Lead já existe: {lead_data['phone']} ({lead_data['name']})")
                continue

            # Criar lead
            days_ago = random.randint(1, 30)
            lead = Lead(
                id=uuid.uuid4(),
                phone=lead_data["phone"],
                name=lead_data["name"],
                email=lead_data["email"],
                age=lead_data["age"],
                status=lead_data["status"],
                source=lead_data["source"],
                interested_plan=lead_data["interested_plan"],
                created_at=datetime.utcnow() - timedelta(days=days_ago),
                updated_at=datetime.utcnow(),
                last_contact_at=datetime.utcnow() - timedelta(days=random.randint(0, days_ago)),
            )
            db.add(lead)

            # Adicionar histórico de status
            history = LeadStatusHistory(
                id=uuid.uuid4(),
                lead_id=lead.id,
                old_status=None,
                new_status="novo",
                reason="Lead criado via seed inicial",
                changed_at=lead.created_at,
            )
            db.add(history)

            if lead_data["status"] != "novo":
                history2 = LeadStatusHistory(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    old_status="novo",
                    new_status=lead_data["status"],
                    reason=f"Status seed: {lead_data['status']}",
                    changed_at=datetime.utcnow(),
                )
                db.add(history2)

            created += 1
            print(f"✅ Lead criado: {lead_data['phone']} — {lead_data['name']} [{lead_data['status']}]")

        await db.commit()
        print(f"\n📊 Resumo: {created} criados | {skipped} já existentes")
        print("\n📱 Leads prontos para testar no Simulador:")
        print("   • 5511991110001 — João Carlos (novo — ideal pra testar 1ª conversa)")
        print("   • 5521991110003 — Roberto Alves (em_atendimento — retomada)")
        print("   • 5531991110004 — Fernanda Costa (interessada — fechamento)")
        print("   • 5511991110005 — Paulo Esteves (sem_retorno — re-engajamento)")


if __name__ == "__main__":
    print("🌱 Iniciando seed de leads mockados...\n")
    asyncio.run(seed_leads())
    print("\n✅ Seed concluído!")
