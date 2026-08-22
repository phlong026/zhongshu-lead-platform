from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.models import Company, User, WechatIdentity


@dataclass(slots=True)
class BindingIntegrityReport:
    """I16：primary_user_id 绑定真相一致性核查报告（上线前脏数据核查用）。"""

    checked_companies: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(issue["severity"] == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, **asdict(self)}


def _issue(code: str, message: str, *, severity: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "severity": severity, "details": details}


def audit_primary_binding_integrity(db: Session) -> BindingIntegrityReport:
    """核查 primary_user_id 绑定真相的一致性（Phase01 评审 I16）。

    Company.primary_user_id 是无外键的裸字符串（既有模型设计），却被邀请与
    派单等流程当作「公司是否已绑定微信主账号」的唯一真相。以下脏形态在运行
    时分别造成「公司永久不能再邀请」或「可绑第二个负责人、旧微信仍可登录」：
    - DANGLING_PRIMARY：指向不存在的用户（create_company_invite 只看非空即
      拒绝邀请，公司被悬空指针锁死）；
    - ORPHAN_OWNER_IDENTITY：主账号被清空但该公司旧微信身份仍在（绑定条件
      UPDATE 重新放行，可再绑第二个负责人；当前模型 primary 是唯一绑定真相，
      该形态只应来自误清空或脏数据）；
    - PRIMARY_USER_COMPANY_MISMATCH：主账号不属于该公司（身份串号）；
    - SHARED_PRIMARY：同一用户被多家公司登记为主账号；
    - PRIMARY_WITHOUT_IDENTITY：主账号无微信身份（warning 级，绑定证据缺失，
      不阻断 valid）。
    """
    report = BindingIntegrityReport()
    companies = db.execute(select(Company).order_by(Company.id)).scalars().all()
    report.checked_companies = len(companies)
    for company in companies:
        primary_id = company.primary_user_id
        if not primary_id:
            orphan_identities = int(
                db.scalar(
                    select(func.count())
                    .select_from(WechatIdentity)
                    .join(User, User.id == WechatIdentity.user_id)
                    .where(User.company_id == company.id)
                )
                or 0
            )
            if orphan_identities:
                report.issues.append(
                    _issue(
                        "ORPHAN_OWNER_IDENTITY",
                        "公司主账号为空但成员仍持有微信身份，绑定真相疑似被误清空",
                        severity="error",
                        company_id=company.id,
                        wechat_identities=orphan_identities,
                    )
                )
            continue
        user = db.get(User, primary_id)
        if user is None:
            report.issues.append(
                _issue(
                    "DANGLING_PRIMARY",
                    "公司主账号指向不存在的用户，公司将无法再发起新邀请",
                    severity="error",
                    company_id=company.id,
                    primary_user_id=primary_id,
                )
            )
            continue
        if user.company_id != company.id:
            report.issues.append(
                _issue(
                    "PRIMARY_USER_COMPANY_MISMATCH",
                    "公司主账号不属于该公司",
                    severity="error",
                    company_id=company.id,
                    primary_user_id=primary_id,
                    user_company_id=user.company_id,
                )
            )
        identity = db.scalar(select(WechatIdentity).where(WechatIdentity.user_id == primary_id))
        if identity is None:
            report.issues.append(
                _issue(
                    "PRIMARY_WITHOUT_IDENTITY",
                    "公司主账号缺少微信身份，绑定证据不完整",
                    severity="warning",
                    company_id=company.id,
                    primary_user_id=primary_id,
                )
            )
    shared_rows = db.execute(
        select(Company.primary_user_id, func.count(Company.id))
        .where(Company.primary_user_id.is_not(None))
        .group_by(Company.primary_user_id)
        .having(func.count(Company.id) > 1)
        .order_by(Company.primary_user_id)
    ).all()
    for primary_id, _count in shared_rows:
        company_ids = (
            db.execute(select(Company.id).where(Company.primary_user_id == primary_id).order_by(Company.id))
            .scalars()
            .all()
        )
        report.issues.append(
            _issue(
                "SHARED_PRIMARY",
                "同一用户被多家公司登记为主账号",
                severity="error",
                primary_user_id=primary_id,
                company_ids=company_ids,
            )
        )
    return report
