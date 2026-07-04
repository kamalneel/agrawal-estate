"""Back-compat shim — CostBasisService now lives in shared services.

Promoted 2026-07-04 (income unification Phase 2): the lot engine is the
single realized-P/L source for both the tax module and the income module.
See docs/INCOME-UNIFICATION-SPEC.md. Import from
app.shared.services.cost_basis_service in new code.
"""
from app.shared.services.cost_basis_service import *  # noqa: F401,F403
from app.shared.services.cost_basis_service import CostBasisService  # noqa: F401
