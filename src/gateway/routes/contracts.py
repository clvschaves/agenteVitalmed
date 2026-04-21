"""
Rota para gerenciamento de contratos Vitalmed.
PATCH /contracts/{contract_id}/status → atualiza status (enviado → assinado)
GET  /contracts/{lead_phone}          → lista contratos de um lead
"""
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.db.session import AsyncSessionLocal
from src.db.models import Contract, Lead
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter()

ContractStatus = Literal["a_enviar", "enviado", "assinado"]


class ContractStatusUpdate(BaseModel):
    status: ContractStatus
    note: str | None = None


@router.patch("/{contract_id}/status", summary="Atualiza status do contrato")
async def update_contract_status(contract_id: str, body: ContractStatusUpdate):
    """
    Muda o status de um contrato. Usado pelo n8n/Chatwoot para sinalizar
    que o documento foi assinado pelo cliente.

    Status válidos: **a_enviar** → **enviado** → **assinado**
    """
    async with AsyncSessionLocal() as db:
        stmt = select(Contract).where(Contract.id == contract_id)
        result = await db.execute(stmt)
        contract = result.scalar_one_or_none()

        if not contract:
            raise HTTPException(status_code=404, detail=f"Contrato {contract_id} não encontrado")

        old_status = contract.status
        contract.status = body.status
        contract.updated_at = datetime.utcnow()

        if body.status == "assinado":
            contract.signed_at = datetime.utcnow()

        await db.commit()
        logger.info(f"📝 Contrato {contract_id}: {old_status} → {body.status}")

    return {
        "contract_id": contract_id,
        "old_status": old_status,
        "new_status": body.status,
        "updated_at": datetime.utcnow().isoformat(),
    }


@router.get("/{lead_phone}", summary="Lista contratos do lead")
async def list_contracts_by_phone(lead_phone: str):
    """
    Retorna todos os contratos de um lead pelo telefone.
    Útil para o dashboard de acompanhamento.
    """
    async with AsyncSessionLocal() as db:
        # Buscar lead
        lead_stmt = select(Lead).where(Lead.phone == lead_phone)
        lead_result = await db.execute(lead_stmt)
        lead = lead_result.scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead {lead_phone} não encontrado")

        # Buscar contratos
        stmt = select(Contract).where(Contract.lead_id == lead.id).order_by(Contract.created_at.desc())
        result = await db.execute(stmt)
        contracts = result.scalars().all()

    return {
        "lead_phone": lead_phone,
        "lead_name": lead.name,
        "total": len(contracts),
        "contracts": [
            {
                "id": str(c.id),
                "type": c.contract_type,
                "status": c.status,
                "gcs_path": c.gcs_path or "",
                "filename": c.filename or "",
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "signed_at": c.signed_at.isoformat() if c.signed_at else None,
            }
            for c in contracts
        ],
    }
