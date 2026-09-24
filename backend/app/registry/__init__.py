"""The Common National Material Code registry.

Phase 6. `codegen` is the code string — format, Damm check digit, parsing —
ported unchanged from the prototype because it was already pure and already
right. `service` decides whether a group earns a code at all, which members may
claim it as CONFIRMED rather than PROVISIONAL, and what retirement means.

A superseded code still resolves. Old purchase orders carry printed numbers
nobody will reissue, so retirement is a status change plus a forwarding
pointer, never a deletion — which is what `superseded_needs_target` says in the
schema and what `service.supersede()` refuses to let you skip.
"""
from .codegen import (  # noqa: F401
    MAX_SERIAL, PREFIX, SERIAL_WIDTH, damm_check, damm_valid, is_valid_code,
    mint_code, parse_code,
)
from .service import (  # noqa: F401
    INSUFFICIENT_EVIDENCE, NO_CLASS, PROFILE_CONFLICT, CodePlan, MemberPlan,
    Refusal, RegistryError, Supersession, plan, revoke, signature_of, supersede,
)
