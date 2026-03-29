from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.device import Policy, PolicyRule, Device
from app.schemas.device import PolicyResponse, PolicyRuleResponse

router = APIRouter()

# --- Schemas (Create/Update) ---
class PolicyRuleCreate(BaseModel):
    priority: int
    action: str
    match_conditions: Dict[str, Any]
    action_params: Dict[str, Any] = None

class PolicyCreate(BaseModel):
    name: str
    type: str = "QoS"
    description: str = None
    site_id: int = None
    rules: List[PolicyRuleCreate] = []

@router.get("", response_model=List[PolicyResponse])
def get_policies(db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    return db.query(Policy).all()

@router.post("", response_model=PolicyResponse)
def create_policy(policy: PolicyCreate, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    new_policy = Policy(
        name=policy.name,
        type=policy.type,
        description=policy.description,
        site_id=policy.site_id,
        auto_remediate=policy.auto_remediate # [NEW]
    )
    db.add(new_policy)
    db.commit()
    db.refresh(new_policy)

    # Add Rules
    for rule in policy.rules:
        new_rule = PolicyRule(
            policy_id=new_policy.id,
            priority=rule.priority,
            action=rule.action,
            match_conditions=rule.match_conditions,
            action_params=rule.action_params
        )
        db.add(new_rule)
    
    db.commit()
    db.refresh(new_policy)
    return new_policy

@router.get("/{policy_id}", response_model=PolicyResponse)
def get_policy(policy_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy

from app.schemas.device import PolicyResponse, PolicyRuleResponse, PolicyUpdate # [FIX] Import PolicyUpdate

# ... imports ...

@router.delete("/{policy_id}")
def delete_policy(policy_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db.delete(policy)
    db.commit()
    return {"message": "Policy deleted"}

@router.put("/{policy_id}", response_model=PolicyResponse)
def update_policy(policy_id: int, update_data: PolicyUpdate, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Update Basic Info
    if update_data.name:
        policy.name = update_data.name
    if update_data.description:
        policy.description = update_data.description
        
    # [NEW] specific check for boolean (can be False, so check explicit None)
    if update_data.auto_remediate is not None:
        policy.auto_remediate = update_data.auto_remediate

    # Update Rules (Full Replacement)
    if update_data.rules is not None:
        # Delete existing rules
        db.query(PolicyRule).filter(PolicyRule.policy_id == policy.id).delete()
        
        # Add new rules
        for rule in update_data.rules:
            new_rule = PolicyRule(
                policy_id=policy.id,
                priority=rule.priority,
                action=rule.action,
                match_conditions=rule.match_conditions,
                action_params=rule.action_params
            )
            db.add(new_rule)
            
    db.commit()
    db.refresh(policy)
    return policy


from app.services.policy_translator import PolicyTranslator
from app.services.ssh_service import DeviceConnection, DeviceInfo

@router.get("/{policy_id}/preview")
def preview_policy_config(policy_id: int, device_type: str = "cisco_ios", db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    """
    Generate and return the text configuration for a given policy without deploying it.
    """
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
        
    translated = PolicyTranslator.translate_or_fallback(policy, device_type)
    return {
        "device_type": device_type,
        "supported": translated["supported"],
        "mode": translated["mode"],
        "plugin": translated["plugin"],
        "message": translated["message"],
        "commands": translated["commands"],
    }


@router.get("/translator/support-matrix")
def get_policy_translator_support_matrix(current_user: User = Depends(deps.require_viewer)):
    return {"translators": PolicyTranslator.support_matrix()}

class PolicyDeployRequest(BaseModel):
    device_ids: List[int]

@router.post("/{policy_id}/deploy")
def deploy_policy(policy_id: int, req: PolicyDeployRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    """
    Deploy policy to a list of devices.
    Translates abstract policy to vendor-specific commands and pushes them.
    """
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    results = []
    for d_id in req.device_ids:
        dev = db.query(Device).filter(Device.id == d_id).first()
        if not dev: continue
        
        # 1. Translate
        translated = PolicyTranslator.translate_or_fallback(policy, dev.device_type)
        commands = translated["commands"]
        if not translated["supported"]:
            results.append({
                "device_id": dev.id,
                "device_name": dev.name,
                "status": "manual_approval_required",
                "message": translated["message"],
                "mode": translated["mode"],
                "plugin": translated["plugin"],
            })
            continue

        # 2. Push to Device
        try:
            # Note: In production, password should be decrypted here
            info = DeviceInfo(
                host=dev.ip_address,
                username=dev.ssh_username,
                password=dev.ssh_password,
                secret=dev.enable_password,
                port=dev.ssh_port or 22,
                device_type=dev.device_type
            )
            conn = DeviceConnection(info)
            if conn.connect():
                # Direct driver access for list of commands
                output = conn.driver.push_config(commands)
                conn.disconnect()
                
                results.append({
                    "device_id": dev.id,
                    "device_name": dev.name,
                    "status": "success",
                    "message": f"Policy '{policy.name}' deployed successfully",
                    "output": output
                })
            else:
                 results.append({
                    "device_id": dev.id,
                    "device_name": dev.name,
                    "status": "failed",
                    "message": f"Connection failed: {conn.last_error}"
                })
        except Exception as e:
            results.append({
                "device_id": dev.id,
                "device_name": dev.name,
                "status": "error",
                "message": str(e)
            })
    
    return {"results": results}

