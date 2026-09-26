"""OpeningPolicy — independent rules, evaluated together, no I/O.

Each rule returns PASS, FAIL or PENDING with a reason code. The vault may open
only when every rule passes *at the moment of opening*; approvals gathered
earlier do not carry a stale evaluation forward.

Rules are configured per process as `[{"type": ..., "params": {...}}]`, copied
from the process type's defaults and tunable before publication.
"""
from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Type

PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"


@dataclass
class ApprovalView:
    approver_id: uuid.UUID
    mfa: bool
    decision: str  # APPROVE | REJECT


@dataclass
class DevicePosture:
    managed: bool
    compliant: bool
    device_id: Optional[str] = None
    source: str = "none"


@dataclass
class OpeningContext:
    now: datetime
    opening_time: datetime
    actor_id: uuid.UUID
    actor_permissions: frozenset
    actor_is_participant: bool
    actor_mfa: bool
    actor_active: bool
    client_ip: Optional[str]
    device: DevicePosture
    approvals: Sequence[ApprovalView] = ()
    required_approvals: int = 1
    designated_official_ids: Sequence[uuid.UUID] = ()


@dataclass
class RuleResult:
    rule: str
    status: str
    code: str
    detail: Dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"rule": self.rule, "status": self.status, "code": self.code, "detail": self.detail}


class Rule:
    type: str = ""
    failure_event: Optional[str] = None

    def __init__(self, **params):
        self.params = params

    def evaluate(self, ctx: OpeningContext) -> RuleResult:  # pragma: no cover - abstract
        raise NotImplementedError


class TimePolicy(Rule):
    type = "time"
    failure_event = "EARLY_OPEN_ATTEMPT"

    def evaluate(self, ctx):
        if ctx.now >= ctx.opening_time:
            return RuleResult(self.type, PASS, "opening_time_reached", {"opening_time": ctx.opening_time.isoformat()})
        return RuleResult(self.type, FAIL, "before_opening_time", {"opening_time": ctx.opening_time.isoformat()})


class NetworkPolicy(Rule):
    type = "network"
    failure_event = "UNAUTHORIZED_NETWORK_ATTEMPT"

    def evaluate(self, ctx):
        cidrs = self.params.get("cidrs") or []
        label = self.params.get("label", "municipal network")
        if not ctx.client_ip:
            return RuleResult(self.type, FAIL, "client_ip_unknown", {"network": label})
        try:
            address = ipaddress.ip_address(ctx.client_ip)
        except ValueError:
            return RuleResult(self.type, FAIL, "client_ip_invalid", {"network": label})
        for cidr in cidrs:
            if address in ipaddress.ip_network(cidr, strict=False):
                return RuleResult(self.type, PASS, "inside_allowed_network", {"network": label})
        return RuleResult(self.type, FAIL, "outside_allowed_network", {"network": label, "client_ip": ctx.client_ip})


class DevicePolicy(Rule):
    type = "device"
    failure_event = "UNAUTHORIZED_DEVICE_ATTEMPT"

    def evaluate(self, ctx):
        need_compliant = self.params.get("require_compliant", True)
        device = ctx.device
        ok = device.managed and (device.compliant or not need_compliant)
        detail = {"source": device.source, "managed": device.managed, "compliant": device.compliant}
        if ok:
            return RuleResult(self.type, PASS, "managed_device", detail)
        return RuleResult(self.type, FAIL, "unmanaged_device", detail)


class IdentityPolicy(Rule):
    type = "identity"

    def evaluate(self, ctx):
        if not ctx.actor_active:
            return RuleResult(self.type, FAIL, "account_inactive")
        if self.params.get("require_mfa") and not ctx.actor_mfa:
            return RuleResult(self.type, FAIL, "mfa_required")
        return RuleResult(self.type, PASS, "identity_ok", {"mfa": ctx.actor_mfa})


class RolePolicy(Rule):
    type = "role"

    def evaluate(self, ctx):
        permission = self.params.get("permission", "opening.initiate")
        if permission not in ctx.actor_permissions:
            return RuleResult(self.type, FAIL, "missing_permission", {"permission": permission})
        if not ctx.actor_is_participant:
            return RuleResult(self.type, FAIL, "not_a_participant")
        return RuleResult(self.type, PASS, "role_ok", {"permission": permission})


class MultiApprovalPolicy(Rule):
    type = "multi_approval"
    failure_event = "FAILED_MULTI_APPROVAL"

    def evaluate(self, ctx):
        designated = set(ctx.designated_official_ids)
        require_mfa = self.params.get("require_mfa_per_approval", False)
        valid = {
            a.approver_id
            for a in ctx.approvals
            if a.decision == "APPROVE"
            and (not designated or a.approver_id in designated)
            and (a.mfa or not require_mfa)
        }
        rejections = [a for a in ctx.approvals if a.decision == "REJECT"]
        detail = {"approved": len(valid), "required": ctx.required_approvals, "designated": len(designated)}
        if rejections:
            return RuleResult(self.type, FAIL, "approval_rejected", detail)
        if len(valid) >= ctx.required_approvals:
            return RuleResult(self.type, PASS, "approvals_satisfied", detail)
        return RuleResult(self.type, PENDING, "awaiting_approvals", detail)


RULE_TYPES: Dict[str, Type[Rule]] = {
    cls.type: cls for cls in (TimePolicy, NetworkPolicy, DevicePolicy, IdentityPolicy, RolePolicy, MultiApprovalPolicy)
}


@dataclass
class PolicyEvaluation:
    results: List[RuleResult]

    @property
    def satisfied(self) -> bool:
        return all(r.status == PASS for r in self.results)

    @property
    def failures(self) -> List[RuleResult]:
        return [r for r in self.results if r.status == FAIL]

    def as_dict(self) -> dict:
        return {"satisfied": self.satisfied, "results": [r.as_dict() for r in self.results]}


class OpeningPolicy:
    def __init__(self, rules: List[Rule]):
        self.rules = rules

    @classmethod
    def from_config(cls, config: List[dict]) -> "OpeningPolicy":
        rules = []
        for item in config:
            rule_cls = RULE_TYPES.get(item["type"])
            if rule_cls is None:
                raise ValueError(f"Unknown opening rule {item['type']!r}")
            rules.append(rule_cls(**(item.get("params") or {})))
        return cls(rules)

    def evaluate(self, ctx: OpeningContext) -> PolicyEvaluation:
        return PolicyEvaluation([rule.evaluate(ctx) for rule in self.rules])

    def failure_event_for(self, result: RuleResult) -> Optional[str]:
        cls = RULE_TYPES.get(result.rule)
        return cls.failure_event if cls else None
