"""Compatibility exports for ``reckon_saas_platform.tenant_security``."""

from reckon_saas_platform.tenant_security import (
    CrossCompanyAccessError as CrossCompanyAccessError,
)
from reckon_saas_platform.tenant_security import (
    TenantContext as TenantContext,
)
from reckon_saas_platform.tenant_security import (
    TenantResolutionError as TenantResolutionError,
)
from reckon_saas_platform.tenant_security import (
    assert_company_matches_tenant as assert_company_matches_tenant,
)
from reckon_saas_platform.tenant_security import (
    assert_file_belongs_to_tenant as assert_file_belongs_to_tenant,
)
from reckon_saas_platform.tenant_security import (
    bind_doc_to_tenant as bind_doc_to_tenant,
)
from reckon_saas_platform.tenant_security import (
    get_tenant_doc as get_tenant_doc,
)
from reckon_saas_platform.tenant_security import (
    get_tenant_owned_query as get_tenant_owned_query,
)
from reckon_saas_platform.tenant_security import (
    get_tenant_user_assignment_query as get_tenant_user_assignment_query,
)
from reckon_saas_platform.tenant_security import (
    get_user_companies as get_user_companies,
)
from reckon_saas_platform.tenant_security import (
    guard_api_company as guard_api_company,
)
from reckon_saas_platform.tenant_security import (
    guarded_background_job_company as guarded_background_job_company,
)
from reckon_saas_platform.tenant_security import (
    guarded_export_rows as guarded_export_rows,
)
from reckon_saas_platform.tenant_security import (
    guarded_link_search as guarded_link_search,
)
from reckon_saas_platform.tenant_security import (
    has_tenant_owned_permission as has_tenant_owned_permission,
)
from reckon_saas_platform.tenant_security import (
    has_tenant_user_assignment_permission as has_tenant_user_assignment_permission,
)
from reckon_saas_platform.tenant_security import (
    require_tenant as require_tenant,
)
from reckon_saas_platform.tenant_security import (
    resolve_tenant as resolve_tenant,
)
from reckon_saas_platform.tenant_security import (
    user_can_bypass_tenant as user_can_bypass_tenant,
)
from reckon_saas_platform.tenant_security import (
    validate_tenant_company_immutable as validate_tenant_company_immutable,
)
from reckon_saas_platform.tenant_security import (
    validate_tenant_owned_doc as validate_tenant_owned_doc,
)
